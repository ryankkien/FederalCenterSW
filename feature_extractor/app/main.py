import json
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import analysis_trigger, classifier, chunker, embedder, primitive_extractor, summary_pipeline
from app.blob import get_blob_storage
from app.db import get_connection, log_event
from app.models import get_llm_client

app = FastAPI(title="Feature Extractor")


class SummaryRequest(BaseModel):
    doc_id: str


class ClassificationResult(BaseModel):
    psc_code: str | None
    psc_description: str | None
    naics_code: str | None
    naics_description: str | None
    rationale: str | None


class SummaryResponse(BaseModel):
    doc_id: str
    blob_path: str
    model: str
    final_summary: str
    classification: ClassificationResult


class ExtractPrimitivesRequest(BaseModel):
    doc_id: str
    contract_id: str | None = None
    doc_classification: str


class ExtractPrimitivesResponse(BaseModel):
    doc_id: str
    extraction_run_id: str | None
    primitives_extracted: dict[str, int]
    analysis_trigger: dict | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/summarize", response_model=SummaryResponse)
def summarize(req: SummaryRequest):
    blob = get_blob_storage()
    llm = get_llm_client()

    raw, source_path = _download_text_artifact(blob, req.doc_id)

    try:
        ocr = json.loads(raw)
    except (json.JSONDecodeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid text artifact format: {exc}")

    pages = _artifact_pages(ocr)

    if not pages:
        raise HTTPException(status_code=422, detail="text artifact contains no pages")

    with get_connection() as conn:
        # 1. Hierarchical summarization
        try:
            result = summary_pipeline.run(pages, llm)
            log_event(conn, req.doc_id, "feature_extractor.summary", "success")
        except Exception as exc:
            log_event(conn, req.doc_id, "feature_extractor.summary", "fail")
            raise HTTPException(status_code=500, detail=f"Summarization failed: {exc}")

        # 2. Classification (part of the Summary step — no separate log entry)
        classification = classifier.classify(result["final_summary"], llm)

        # 3. Chunking
        try:
            chunk_list = chunker.chunk_and_store(conn, req.doc_id, pages)
            log_event(conn, req.doc_id, "feature_extractor.chunking", "success")
        except Exception as exc:
            log_event(conn, req.doc_id, "feature_extractor.chunking", "fail")
            raise HTTPException(status_code=500, detail=f"Chunking failed: {exc}")

        # 4. Embedding — one API call for all chunks (batched by OpenAI client)
        try:
            embedder.embed_chunks(conn, chunk_list)
            log_event(conn, req.doc_id, "feature_extractor.index", "success")
        except Exception as exc:
            log_event(conn, req.doc_id, "feature_extractor.index", "fail")
            raise HTTPException(status_code=500, detail=f"Embedding failed: {exc}")

    # 5. Upload summary.json to blob
    summary_doc = {
        "doc_id": req.doc_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": llm.model_name,
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

    return SummaryResponse(
        doc_id=req.doc_id,
        blob_path=summary_path,
        model=llm.model_name,
        final_summary=result["final_summary"],
        classification=ClassificationResult(**classification),
    )


@app.post("/extract-primitives", response_model=ExtractPrimitivesResponse)
def extract_primitives(req: ExtractPrimitivesRequest):
    blob = get_blob_storage()
    llm = get_llm_client()

    raw, _ = _download_text_artifact(blob, req.doc_id)

    try:
        ocr = json.loads(raw)
    except (json.JSONDecodeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid text artifact format: {exc}")

    pages = _artifact_pages(ocr)
    if not pages:
        raise HTTPException(status_code=422, detail="text artifact contains no pages")

    summary_text = ""
    try:
        summary_raw = blob.download_bytes(f"contracts/{req.doc_id}/summary.json")
        summary_doc = json.loads(summary_raw)
        summary_text = summary_doc.get("final_summary", "")
    except Exception:
        pass

    with get_connection() as conn:
        try:
            run_id, counts = primitive_extractor.run(
                conn, req.doc_id, req.contract_id, req.doc_classification, pages, summary_text, llm
            )
            log_event(conn, req.doc_id, "feature_extractor.primitives", "success")
        except Exception as exc:
            log_event(conn, req.doc_id, "feature_extractor.primitives", "fail")
            raise HTTPException(status_code=500, detail=f"Primitive extraction failed: {exc}")

        trigger_result = analysis_trigger.trigger_per_contract_analysis(
            req.doc_id,
            req.contract_id,
            run_id,
        )
        log_event(
            conn,
            req.doc_id,
            "feature_extractor.analysis_trigger",
            trigger_result.get("status", "unknown"),
            {
                key: value
                for key, value in trigger_result.items()
                if key not in {"status"}
            },
        )

    return ExtractPrimitivesResponse(
        doc_id=req.doc_id,
        extraction_run_id=run_id,
        primitives_extracted=counts,
        analysis_trigger=trigger_result,
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
