from __future__ import annotations

import csv
import json
import os
import subprocess
import zipfile
from dataclasses import dataclass
from io import BytesIO, StringIO
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree

from openpyxl import load_workbook
from PIL import Image
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from app.blob_storage import BlobStorage
from app.document_files import file_extension

try:
    import fitz
except ImportError:
    fitz = None


TEXT_JSON_FILENAME = "text.json"
DEFAULT_OCR_DPI_SCALE = 2.0
DEFAULT_OCR_MAX_PAGES = 25


@dataclass
class StoredContractDocument:
    blob_path: str
    text_blob_path: str
    stored_filename: str
    content_type: str
    size_bytes: int


def store_contract_document(
    storage: BlobStorage,
    document_id: str,
    original_filename: str,
    content_type: str,
    data: bytes,
    source: str,
) -> StoredContractDocument:
    converted = _convert_primary_file(original_filename, content_type, data)
    folder = f"contracts/{document_id}"
    blob_path = f"{folder}/{converted.filename}"
    text_blob_path = f"{folder}/{TEXT_JSON_FILENAME}"

    storage.upload_bytes(blob_path, converted.data, converted.content_type)
    storage.upload_bytes(
        text_blob_path,
        _text_json_payload(
            document_id=document_id,
            original_filename=original_filename,
            original_content_type=content_type,
            original_data=data,
            stored_filename=converted.filename,
            content_type=converted.content_type,
            source=source,
        ),
        "application/json",
    )

    return StoredContractDocument(
        blob_path=blob_path,
        text_blob_path=text_blob_path,
        stored_filename=converted.filename,
        content_type=converted.content_type,
        size_bytes=len(data),
    )


@dataclass
class _ConvertedFile:
    filename: str
    content_type: str
    data: bytes


def _convert_primary_file(filename: str, content_type: str, data: bytes) -> _ConvertedFile:
    extension = file_extension(filename)
    if extension == ".pdf":
        return _ConvertedFile(filename="main.pdf", content_type="application/pdf", data=data)
    if extension in {".txt", ".csv"}:
        try:
            text = _decode_text(data)
            return _ConvertedFile(
                filename="main.pdf",
                content_type="application/pdf",
                data=_text_to_pdf(text),
            )
        except Exception:
            return _ConvertedFile(filename=f"main{extension}", content_type=content_type, data=data)
    if extension in {".png", ".jpg", ".jpeg"}:
        try:
            return _ConvertedFile(
                filename="main.pdf",
                content_type="application/pdf",
                data=_image_to_pdf(data),
            )
        except Exception:
            return _ConvertedFile(filename=f"main{extension}", content_type=content_type, data=data)
    return _ConvertedFile(filename=f"main{extension or '.bin'}", content_type=content_type, data=data)


def _text_json_payload(
    document_id: str,
    original_filename: str,
    original_content_type: str,
    original_data: bytes,
    stored_filename: str,
    content_type: str,
    source: str,
) -> bytes:
    extracted = _extract_text(original_filename, original_content_type, original_data)
    payload = {
        "document_id": document_id,
        "original_filename": original_filename,
        "stored_filename": stored_filename,
        "content_type": content_type,
        "source": source,
        "text": extracted.text,
        "extraction_status": extracted.status,
        "extraction_error": extracted.error,
        "extraction_warning": extracted.warning,
        "pages": extracted.pages,
    }
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


@dataclass
class _ExtractedText:
    text: str
    status: str
    error: Optional[str] = None
    warning: Optional[str] = None
    pages: Optional[List[Dict[str, object]]] = None

    def __post_init__(self) -> None:
        if self.pages is None:
            self.pages = []


def _extract_text(filename: str, content_type: str, data: bytes) -> _ExtractedText:
    extension = file_extension(filename)
    try:
        if content_type == "application/pdf" or extension == ".pdf":
            return _extract_pdf_text(data)
        elif content_type in {"text/plain", "text/csv"} or extension in {".txt", ".csv"}:
            text = _decode_text(data)
        elif content_type in {"image/png", "image/jpeg"} or extension in {".png", ".jpg", ".jpeg"}:
            text, warning = _ocr_image_text(data)
            return _ExtractedText(
                text=text,
                status="ocr_extracted",
                warning=warning,
                pages=_single_page_payload(text, "ocr_extracted", warning=warning),
            )
        elif (
            content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or extension == ".docx"
        ):
            text = _extract_docx_text(data)
        elif (
            content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            or extension == ".xlsx"
        ):
            text = _extract_xlsx_text(data)
        else:
            return _ExtractedText(text="", status="unsupported")
    except Exception as error:
        return _ExtractedText(text="", status="failed", error=str(error))

    return _ExtractedText(
        text=text,
        status="extracted",
        pages=_single_page_payload(text, "extracted"),
    )


def _extract_pdf_text(data: bytes) -> _ExtractedText:
    reader = PdfReader(BytesIO(data))
    pages = []
    offset = 0
    page_text_values = []
    for index, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if page_text:
            start = offset
            page_text_values.append(page_text)
            offset += len(page_text)
            pages.append(
                {
                    "page_number": index,
                    "text": page_text,
                    "start_char": start,
                    "end_char": offset,
                    "extraction_status": "extracted",
                }
            )
            offset += 2
    text = "\n\n".join(page_text_values).strip()
    if text:
        return _ExtractedText(text=text, status="extracted", pages=pages)

    try:
        ocr_text, warning = _ocr_pdf_text(data)
    except Exception as error:
        return _ExtractedText(
            text="",
            status="failed",
            error=f"PDF text extraction produced no text and OCR failed: {error}",
        )

    if not ocr_text.strip():
        return _ExtractedText(text="", status="failed", error="PDF OCR completed but produced no text")
    return _ExtractedText(
        text=ocr_text.strip(),
        status="ocr_extracted",
        warning=warning,
        pages=_single_page_payload(ocr_text.strip(), "ocr_extracted", warning=warning),
    )


def _ocr_pdf_text(data: bytes) -> Tuple[str, Optional[str]]:
    if fitz is None:
        raise RuntimeError("PyMuPDF is required for PDF OCR rendering")

    document = fitz.open(stream=data, filetype="pdf")
    max_pages = _ocr_max_pages()
    page_count = len(document)
    pages_to_process = min(page_count, max_pages) if max_pages else page_count
    scale = _ocr_dpi_scale()
    matrix = fitz.Matrix(scale, scale)
    page_text = []

    for page_index in range(pages_to_process):
        page = document[page_index]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        page_text.append(_run_tesseract(pixmap.tobytes("png")).strip())

    warning = None
    if max_pages and page_count > max_pages:
        warning = f"OCR limited to first {max_pages} of {page_count} pages"

    return "\n\n".join(text for text in page_text if text), warning


def _ocr_image_text(data: bytes) -> Tuple[str, Optional[str]]:
    text = _run_tesseract(data).strip()
    if not text:
        raise RuntimeError("image OCR completed but produced no text")
    return text, None


def _single_page_payload(
    text: str,
    status: str,
    warning: Optional[str] = None,
) -> List[Dict[str, object]]:
    if not text:
        return []
    payload: Dict[str, object] = {
        "page_number": 1,
        "text": text,
        "start_char": 0,
        "end_char": len(text),
        "extraction_status": status,
    }
    if warning:
        payload["extraction_warning"] = warning
    return [payload]


def _run_tesseract(image_data: bytes) -> str:
    command = os.getenv("DOCUMENT_OCR_TESSERACT_CMD", "tesseract")
    language = os.getenv("DOCUMENT_OCR_LANGUAGE", "eng")
    try:
        result = subprocess.run(
            [command, "stdin", "stdout", "-l", language],
            input=image_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            f"Tesseract command '{command}' is not installed or not on PATH"
        ) from error

    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"Tesseract exited with status {result.returncode}")

    return result.stdout.decode("utf-8", errors="replace")


def _ocr_max_pages() -> int:
    value = os.getenv("DOCUMENT_OCR_MAX_PAGES", str(DEFAULT_OCR_MAX_PAGES))
    try:
        return max(0, int(value))
    except ValueError:
        return DEFAULT_OCR_MAX_PAGES


def _ocr_dpi_scale() -> float:
    value = os.getenv("DOCUMENT_OCR_DPI_SCALE", str(DEFAULT_OCR_DPI_SCALE))
    try:
        return max(1.0, float(value))
    except ValueError:
        return DEFAULT_OCR_DPI_SCALE


def _extract_docx_text(data: bytes) -> str:
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(BytesIO(data)) as archive:
        document_xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(document_xml)
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        paragraph_text = "".join(texts).strip()
        if paragraph_text:
            paragraphs.append(paragraph_text)
    return "\n".join(paragraphs).strip()


def _extract_xlsx_text(data: bytes) -> str:
    workbook = load_workbook(BytesIO(data), data_only=True, read_only=True)
    lines = []
    for worksheet in workbook.worksheets:
        lines.append(f"[{worksheet.title}]")
        for row in worksheet.iter_rows(values_only=True):
            values = ["" if value is None else str(value) for value in row]
            if any(values):
                output = StringIO()
                csv.writer(output).writerow(values)
                lines.append(output.getvalue().strip())
    workbook.close()
    return "\n".join(lines).strip()


def _decode_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


def _text_to_pdf(text: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    margin = 72
    y = height - margin
    line_height = 14

    for paragraph in text.splitlines() or [""]:
        lines = simpleSplit(paragraph or " ", "Helvetica", 10, width - (margin * 2))
        for line in lines:
            if y < margin:
                pdf.showPage()
                y = height - margin
            pdf.drawString(margin, y, line)
            y -= line_height
        if y < margin:
            pdf.showPage()
            y = height - margin
        y -= line_height

    pdf.save()
    return buffer.getvalue()


def _image_to_pdf(data: bytes) -> bytes:
    with Image.open(BytesIO(data)) as image:
        converted = image.convert("RGB")
        buffer = BytesIO()
        converted.save(buffer, format="PDF")
        return buffer.getvalue()
