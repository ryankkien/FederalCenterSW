import json
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import classifier, summarizer
from app.blob import get_blob_storage
from app.models import get_llm_client

app = FastAPI(title="Summarizer")


class SummarizeRequest(BaseModel):
    doc_id: str


class ClassificationResult(BaseModel):
    psc_code: str | None
    psc_description: str | None
    naics_code: str | None
    naics_description: str | None
    rationale: str | None


class SummarizeResponse(BaseModel):
    doc_id: str
    blob_path: str
    model: str
    final_summary: str
    classification: ClassificationResult


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/summarize", response_model=SummarizeResponse)
def summarize(req: SummarizeRequest):
    blob = get_blob_storage()
    client = get_llm_client()

    raw, source_path = _download_text_artifact(blob, req.doc_id)

    try:
        ocr = json.loads(raw)
    except (json.JSONDecodeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid text artifact format: {exc}")

    pages = _artifact_pages(ocr)

    if not pages:
        raise HTTPException(status_code=422, detail="text artifact contains no pages")

    # Run hierarchical summarization
    result = summarizer.run(pages, client)

    # Classify document
    classification = classifier.classify(result["final_summary"], client)

    # Build and upload summary.json
    summary_doc = {
        "doc_id": req.doc_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": client.model_name,
        "source_path": source_path,
        "classification": classification,
        **result,
    }
    summary_path = f"contracts/{req.doc_id}/summary.json"
    blob.upload_bytes(
        summary_path,
        json.dumps(summary_doc, indent=2).encode(),
        "application/json",
    )

    return SummarizeResponse(
        doc_id=req.doc_id,
        blob_path=summary_path,
        model=client.model_name,
        final_summary=result["final_summary"],
        classification=ClassificationResult(**classification),
    )


def _download_text_artifact(blob, doc_id: str) -> tuple[bytes, str]:
    candidate_paths = (
        f"contracts/{doc_id}/text.json",
        f"documents/{doc_id}/ocr.json",
    )
    last_error = None
    for path in candidate_paths:
        try:
            return blob.download_bytes(path), path
        except Exception as exc:
            last_error = exc
    raise HTTPException(status_code=404, detail=f"text artifact not found: {last_error}")


def _artifact_pages(artifact: dict) -> list[str]:
    raw_pages = artifact.get("pages") or []
    pages = []
    for page in raw_pages:
        if isinstance(page, str):
            text = page
        elif isinstance(page, dict):
            text = str(page.get("text") or "")
        else:
            text = ""
        if text.strip():
            pages.append(text.strip())

    if pages:
        return pages

    text = str(artifact.get("text") or "").strip()
    return [text] if text else []
