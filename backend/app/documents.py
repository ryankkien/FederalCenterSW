from datetime import datetime, timezone
import hashlib
import json
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.authz import can_upload_to_contract, require_unmatched_admin
from app.ai.providers import get_ai_provider
from app.blob_storage import BlobStorage, get_blob_storage
from app.config import get_ai_inline_processing_enabled
from app.database import get_db
from app.document_assets import store_contract_document
from app.document_files import ALLOWED_CONTENT_TYPES, ALLOWED_EXTENSIONS, clean_filename, file_extension
from app.document_intake_decisions import apply_inline_intake_decisions
from app.models import (
    Contract,
    DocumentChunk,
    DocumentEntity,
    DocumentMatchDecision,
    DocumentPage,
    DocumentProcessingJob,
    DocumentReportFact,
    DocumentSemanticLink,
    DocumentUpload,
)
from app.processing import process_processing_job

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class DocumentSasUrlResponse(BaseModel):
    url: str
    expires_in_minutes: int


class DocumentResponse(BaseModel):
    id: str
    title: str
    document_type: str
    notes: Optional[str]
    original_filename: str
    stored_filename: str
    content_type: str
    size_bytes: int
    uploader_id: str
    uploader_role: str
    contract_id: Optional[str] = None
    detected_kind: str = "report"
    matched_contract_id: Optional[str] = None
    document_kind: str = "report"
    match_status: str = "pending"
    processing_status: str = "pending"
    report_period_start: Optional[str] = None
    report_period_end: Optional[str] = None
    created_at: datetime


class MatchDecisionRequest(BaseModel):
    contract_id: Optional[str] = Field(default=None, max_length=36)
    decision_status: str = Field(default="matched", max_length=40)
    rationale: Optional[str] = Field(default=None, max_length=2000)


class ProcessingJobResponse(BaseModel):
    id: str
    document_id: str
    status: str
    job_type: str
    created_at: datetime


class DocumentDetailResponse(DocumentResponse):
    blob_path: str
    text_blob_path: Optional[str] = None
    pages: List[Dict[str, object]] = []
    chunks: List[Dict[str, object]] = []
    entities: List[Dict[str, object]] = []
    facts: List[Dict[str, object]] = []
    semantic_links: List[Dict[str, object]] = []


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    title: str = Form(...),
    document_type: str = Form(...),
    notes: Optional[str] = Form(default=None),
    contract_id: Optional[str] = Form(default=None),
    process_inline: bool = Form(default=False),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: BlobStorage = Depends(get_blob_storage),
) -> DocumentResponse:
    filename = clean_filename(file.filename or "document")
    content_type = file.content_type or "application/octet-stream"
    _validate_file(filename, content_type)
    linked_contract_id = contract_id.strip() if contract_id else None
    if linked_contract_id and not can_upload_to_contract(user, db, linked_contract_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

    document_id = str(uuid4())
    stored = store_contract_document(
        storage=storage,
        document_id=document_id,
        original_filename=filename,
        content_type=content_type,
        data=data,
        source="portal",
    )

    document = DocumentUpload(
        id=document_id,
        contract_id=linked_contract_id,
        title=title.strip(),
        document_type=document_type.strip(),
        document_kind="other",
        intake_source="portal",
        notes=notes.strip() if notes else None,
        original_filename=filename,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        blob_path=stored.blob_path,
        text_blob_path=stored.text_blob_path,
        source_sha256=hashlib.sha256(data).hexdigest(),
        match_status="matched" if linked_contract_id else "pending",
        processing_status="queued",
        uploader_id=user.id,
        uploader_role=user.role,
        created_at=datetime.now(timezone.utc),
    )
    db.add(document)
    db.flush()
    inline_text = _inline_extracted_text(storage, stored.text_blob_path) if get_ai_inline_processing_enabled() else ""
    inline_provider = get_ai_provider() if inline_text else None
    apply_inline_intake_decisions(db, document, text=inline_text, ai_provider=inline_provider)
    job = _processing_job(document_id)
    db.add(job)
    db.commit()
    if process_inline:
        process_processing_job(db, storage, job.id, get_ai_provider())
        db.commit()
    db.refresh(document)
    return _document_response(document)


@router.get("", response_model=List[DocumentResponse])
def list_documents(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[DocumentResponse]:
    statement = select(DocumentUpload).order_by(DocumentUpload.created_at.desc())
    if user.role == "contractor":
        statement = statement.where(DocumentUpload.uploader_id == user.id)
    documents = db.scalars(statement).all()
    return [_document_response(document) for document in documents]


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: BlobStorage = Depends(get_blob_storage),
) -> Response:
    document = _get_authorized_document(document_id, user, db)
    data = storage.download_bytes(document.blob_path)
    return Response(
        content=data,
        media_type=document.content_type,
        headers={"Content-Disposition": f'attachment; filename="{_stored_filename(document)}"'},
    )


@router.get("/{document_id}/sas-url", response_model=DocumentSasUrlResponse)
def document_sas_url(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: BlobStorage = Depends(get_blob_storage),
) -> DocumentSasUrlResponse:
    document = _get_authorized_document(document_id, user, db)
    try:
        url = storage.create_read_url(document.blob_path)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="SAS URLs require Azure Blob Storage configuration",
        ) from exc
    return DocumentSasUrlResponse(url=url, expires_in_minutes=15)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document_detail(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentDetailResponse:
    document = _get_authorized_document(document_id, user, db)
    pages = list(
        db.scalars(
            select(DocumentPage)
            .where(DocumentPage.document_upload_id == document.id)
            .order_by(DocumentPage.page_number.asc())
        ).all()
    )
    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_upload_id == document.id)
            .order_by(DocumentChunk.chunk_index.asc())
        ).all()
    )
    entities = list(
        db.scalars(
            select(DocumentEntity)
            .where(DocumentEntity.document_upload_id == document.id)
            .order_by(DocumentEntity.created_at.asc())
        ).all()
    )
    facts = list(
        db.scalars(
            select(DocumentReportFact)
            .where(DocumentReportFact.document_upload_id == document.id)
            .order_by(DocumentReportFact.created_at.asc())
        ).all()
    )
    links = list(
        db.scalars(
            select(DocumentSemanticLink).where(
                (DocumentSemanticLink.source_document_upload_id == document.id)
                | (DocumentSemanticLink.target_document_upload_id == document.id)
            )
        ).all()
    )
    base = _document_response(document).model_dump()
    return DocumentDetailResponse(
        **base,
        blob_path=document.blob_path,
        text_blob_path=document.text_blob_path,
        pages=[
            {
                "id": page.id,
                "page_number": page.page_number,
                "extraction_status": page.extraction_status,
                "text": page.text[:2000],
            }
            for page in pages
        ],
        chunks=[
            {
                "id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "text": chunk.text[:2000],
            }
            for chunk in chunks
        ],
        entities=[
            {
                "id": entity.id,
                "entity_type": entity.entity_type,
                "value": entity.value,
                "normalized_value": entity.normalized_value,
                "quote": entity.quote,
            }
            for entity in entities
        ],
        facts=[
            {
                "id": fact.id,
                "fact_type": fact.fact_type,
                "label": fact.label,
                "value_text": fact.value_text,
                "quote": fact.quote,
            }
            for fact in facts
        ],
        semantic_links=[
            {
                "id": link.id,
                "related_document_id": (
                    link.target_document_upload_id
                    if link.source_document_upload_id == document.id
                    else link.source_document_upload_id
                ),
                "link_type": link.link_type,
                "summary": link.summary,
                "score": link.score,
            }
            for link in links
        ],
    )


@router.post("/{document_id}/match-decisions")
def create_match_decision(
    document_id: str,
    payload: MatchDecisionRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, object]:
    require_unmatched_admin(user)
    document = _get_authorized_document(document_id, user, db)
    contract = db.get(Contract, payload.contract_id) if payload.contract_id else None
    document.contract_id = contract.id if contract is not None else None
    document.match_status = payload.decision_status
    decision = DocumentMatchDecision(
        id=str(uuid4()),
        document_upload_id=document.id,
        contract_id=document.contract_id,
        matched_contract_number=contract.contract_number if contract is not None else None,
        decision_status=payload.decision_status,
        decision_source="manual",
        confidence=1.0 if contract is not None else 0.0,
        rationale=payload.rationale,
        decided_by_id=user.id,
        decided_at=datetime.now(timezone.utc),
    )
    db.add(decision)
    db.commit()
    return {"id": decision.id, "document_id": document.id, "contract_id": document.contract_id}


@router.post(
    "/{document_id}/processing-jobs",
    response_model=ProcessingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_document_processing_job(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProcessingJobResponse:
    document = _get_authorized_document(document_id, user, db)
    job = _processing_job(document.id)
    document.processing_status = "queued"
    db.add(job)
    db.commit()
    db.refresh(job)
    return ProcessingJobResponse(
        id=job.id,
        document_id=document.id,
        status=job.status,
        job_type=job.job_type,
        created_at=job.created_at,
    )


def _validate_file(filename: str, content_type: str) -> None:
    extension = file_extension(filename)
    if extension not in ALLOWED_EXTENSIONS or content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type",
        )


def _inline_extracted_text(storage: BlobStorage, text_blob_path: str) -> str:
    try:
        payload = json.loads(storage.download_bytes(text_blob_path).decode("utf-8"))
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    status = str(payload.get("extraction_status") or "").strip().lower()
    text = str(payload.get("text") or "").strip()
    if status in {"pending_ocr", "ocr_pending", "pending", "failed"}:
        return ""
    return text


def _get_authorized_document(document_id: str, user: CurrentUser, db: Session) -> DocumentUpload:
    document = db.get(DocumentUpload, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if user.role == "contractor" and document.uploader_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


def _document_response(document: DocumentUpload) -> DocumentResponse:
    def _date_str(d) -> Optional[str]:
        if d is None:
            return None
        return d.isoformat() if hasattr(d, "isoformat") else str(d)

    return DocumentResponse(
        id=document.id,
        title=document.title,
        document_type=document.document_type,
        notes=document.notes,
        original_filename=document.original_filename,
        stored_filename=_stored_filename(document),
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        uploader_id=document.uploader_id,
        uploader_role=document.uploader_role,
        contract_id=document.contract_id,
        detected_kind=document.document_kind,
        matched_contract_id=document.contract_id,
        document_kind=document.document_kind,
        match_status=document.match_status,
        processing_status=document.processing_status,
        report_period_start=_date_str(getattr(document, "report_period_start", None)),
        report_period_end=_date_str(getattr(document, "report_period_end", None)),
        created_at=document.created_at,
    )


def _stored_filename(document: DocumentUpload) -> str:
    return document.blob_path.rsplit("/", 1)[-1] or document.original_filename


def _processing_job(document_id: str) -> DocumentProcessingJob:
    return DocumentProcessingJob(
        id=str(uuid4()),
        document_upload_id=document_id,
        job_type="document_analysis",
        status="queued",
        metadata_json={"stage": "text_gate"},
    )
