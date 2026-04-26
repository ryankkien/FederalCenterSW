import json
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import classifier, chunker, embedder, summarizer
from app.blob import get_blob_storage
from app.db import get_connection, log_event
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
    llm = get_llm_client()

    # Fetch OCR output from blob
    ocr_path = f"documents/{req.doc_id}/ocr.json"
    try:
        raw = blob.download_bytes(ocr_path)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"ocr.json not found: {exc}")

    try:
        ocr = json.loads(raw)
        pages: list[str] = ocr["pages"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid ocr.json format: {exc}")

    if not pages:
        raise HTTPException(status_code=422, detail="ocr.json contains no pages")

    with get_connection() as conn:
        # 1. Hierarchical summarization
        try:
            result = summarizer.run(pages, llm)
            log_event(conn, req.doc_id, "Summary", "success")
        except Exception as exc:
            log_event(conn, req.doc_id, "Summary", "fail")
            raise HTTPException(status_code=500, detail=f"Summarization failed: {exc}")

        # 2. Classification (part of the Summary step — no separate log entry)
        classification = classifier.classify(result["final_summary"], llm)

        # 3. Chunking
        try:
            chunker.chunk_and_store(conn, req.doc_id, pages)
            log_event(conn, req.doc_id, "Chunking", "success")
        except Exception as exc:
            log_event(conn, req.doc_id, "Chunking", "fail")
            raise HTTPException(status_code=500, detail=f"Chunking failed: {exc}")

        # 4. Embedding
        try:
            embedder.embed_and_store(conn, req.doc_id, result["final_summary"])
            log_event(conn, req.doc_id, "Index", "success")
        except Exception as exc:
            log_event(conn, req.doc_id, "Index", "fail")
            raise HTTPException(status_code=500, detail=f"Embedding failed: {exc}")

    # 5. Upload summary.json to blob
    summary_doc = {
        "doc_id": req.doc_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": llm.model_name,
        "classification": classification,
        **result,
    }
    summary_path = f"documents/{req.doc_id}/summary.json"
    blob.upload_bytes(
        summary_path,
        json.dumps(summary_doc, indent=2).encode(),
        "application/json",
    )

    return SummarizeResponse(
        doc_id=req.doc_id,
        blob_path=summary_path,
        model=llm.model_name,
        final_summary=result["final_summary"],
        classification=ClassificationResult(**classification),
    )
