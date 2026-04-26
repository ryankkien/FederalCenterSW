from __future__ import annotations

import importlib
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session

from app.ai.providers import AIProcessingResult, AIProvider, NullAIProvider, ProcessingSignalRequest
from app.blob_storage import BlobStorage
from app.chunking import PageText, TextChunk, chunk_text
from app.contract_matching import ContractMatchContext, ContractMatchResult, match_contract
from app.contract_analysis import apply_contract_analysis_pipeline, classify_document
from app.document_assets import TEXT_JSON_FILENAME
from app.feature_extractor_client import FeatureExtractorStepResult, trigger_feature_extractor
from app.observability import get_logger, log_context

logger = get_logger(__name__)

AUTO_SCAFFOLD_DOCUMENT_KINDS = {"source_contract", "task_order"}
AUTO_SCAFFOLD_CONFIDENCE = 0.85


class TextJsonPayload(BaseModel):
    document_id: Optional[str] = None
    original_filename: Optional[str] = None
    stored_filename: Optional[str] = None
    content_type: Optional[str] = None
    source: Optional[str] = None
    text: str = ""
    extraction_status: Optional[str] = None
    extraction_error: Optional[str] = None
    extraction_warning: Optional[str] = None
    pages: List[Dict[str, object]] = Field(default_factory=list)


class TextGateResult(BaseModel):
    status: str
    reason: Optional[str] = None
    text: str = ""


class ProcessingResult(BaseModel):
    document_id: str
    status: str
    text_gate: TextGateResult
    pages: List[PageText] = Field(default_factory=list)
    chunks: List[TextChunk] = Field(default_factory=list)
    contract_match: Optional[ContractMatchResult] = None
    ai_result: Optional[AIProcessingResult] = None
    output_blob_path: Optional[str] = None
    error: Optional[str] = None


def load_text_json(
    storage: BlobStorage,
    document_id: Optional[str] = None,
    text_blob_path: Optional[str] = None,
) -> Tuple[Optional[TextJsonPayload], Optional[str]]:
    path = text_blob_path or _text_blob_path(document_id)
    try:
        data = storage.download_bytes(path)
    except Exception as error:
        logger.warning(
            "Failed to load text artifact",
            extra={"document_upload_id": document_id, "text_blob_path": path, "error": str(error)},
        )
        return None, str(error)

    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        logger.warning(
            "Failed to parse text artifact",
            extra={"document_upload_id": document_id, "text_blob_path": path, "error": str(error)},
        )
        return None, str(error)
    if not isinstance(payload, dict):
        return None, "text.json must contain a JSON object"
    return TextJsonPayload(**payload), None


def gate_text_payload(payload: Optional[TextJsonPayload], load_error: Optional[str] = None) -> TextGateResult:
    if payload is None:
        return TextGateResult(status="pending_ocr", reason=load_error or "text.json is not available")

    status = (payload.extraction_status or "").strip().lower()
    text = (payload.text or "").strip()
    if status in {"pending_ocr", "ocr_pending", "pending"}:
        return TextGateResult(status="pending_ocr", reason=status or None)
    if status == "failed" and not text:
        return TextGateResult(
            status="failed",
            reason=payload.extraction_error or "no_extractable_text",
        )
    if not text:
        return TextGateResult(status="no_extractable_text", reason=status or "empty_text")
    return TextGateResult(status="ready", text=text)


def process_document_upload(
    document: object,
    storage: BlobStorage,
    contracts: Sequence[object] = (),
    ai_provider: Optional[AIProvider] = None,
) -> ProcessingResult:
    document_id = _string_attr(document, "id", "document_id", "documentId")
    if not document_id:
        raise ValueError("document must have an id or document_id")

    text_blob_path = _document_text_blob_path(document, document_id)
    payload, load_error = load_text_json(storage, document_id=document_id, text_blob_path=text_blob_path)
    gate = gate_text_payload(payload, load_error)
    if gate.status != "ready":
        return _write_processing_result(
            storage,
            ProcessingResult(document_id=document_id, status=gate.status, text_gate=gate),
        )

    pages = _payload_pages(payload, gate.text)
    chunks = chunk_text(gate.text, pages=pages)
    if not chunks:
        no_chunks_gate = TextGateResult(status="no_extractable_text", reason="empty_chunks")
        return _write_processing_result(
            storage,
            ProcessingResult(
                document_id=document_id,
                status="no_extractable_text",
                text_gate=no_chunks_gate,
                pages=pages,
            ),
        )

    provider = ai_provider or NullAIProvider()
    context = ContractMatchContext(
        filename=(payload.original_filename if payload else None)
        or _string_attr(document, "original_filename", "filename"),
        title=_string_attr(document, "title", "name"),
        notes=_string_attr(document, "notes", "description"),
        email_subject=_string_attr(document, "email_subject", "subject"),
        email_body=_string_attr(document, "email_body", "body_text"),
        text=gate.text,
    )
    contract_match = match_contract(contracts, context, provider)
    ai_result = None
    if provider.status.available:
        ai_result = provider.extract_document_signals(
            ProcessingSignalRequest(
                document_id=document_id,
                title=_string_attr(document, "title", "name"),
                document_type=_string_attr(document, "document_type", "type"),
                chunks=[chunk.text for chunk in chunks],
            )
        )

    return _write_processing_result(
        storage,
        ProcessingResult(
            document_id=document_id,
            status="processed",
            text_gate=gate,
            pages=pages,
            chunks=chunks,
            contract_match=contract_match,
            ai_result=ai_result,
        ),
    )


def process_one_queued_job(
    session: Session,
    storage: BlobStorage,
    ai_provider: Optional[AIProvider] = None,
) -> ProcessingResult:
    models = importlib.import_module("app.models")
    job_model = _first_model(models, "DocumentProcessingJob", "ProcessingJob", "AIProcessingJob")
    if job_model is None:
        return ProcessingResult(
            document_id="",
            status="skipped",
            text_gate=TextGateResult(
                status="pending_ocr",
                reason="No processing job model is available yet",
            ),
        )

    for job in _queued_jobs(session, job_model):
        if _job_is_waiting_for_text(session, models, job, storage):
            continue
        return _process_job_with_status(session, models, job, storage, ai_provider)

    return ProcessingResult(
        document_id="",
        status="idle",
        text_gate=TextGateResult(status="pending_ocr", reason="No queued processing job is ready"),
    )


def queued_processing_job_count(session: Session) -> int:
    models = importlib.import_module("app.models")
    job_model = _first_model(models, "DocumentProcessingJob", "ProcessingJob", "AIProcessingJob")
    if job_model is None:
        return 0
    return len(_queued_jobs(session, job_model))


def waiting_for_text_processing_job_count(session: Session, storage: BlobStorage) -> int:
    models = importlib.import_module("app.models")
    job_model = _first_model(models, "DocumentProcessingJob", "ProcessingJob", "AIProcessingJob")
    if job_model is None:
        return 0
    return sum(
        1
        for job in _queued_jobs(session, job_model)
        if _job_is_waiting_for_text(session, models, job, storage)
    )


def _queued_jobs(session: Session, job_model: object) -> List[object]:
    statement = _queued_job_statement(job_model)
    return list(session.scalars(statement).all())


def _next_queued_job(session: Session, job_model: object) -> Optional[object]:
    rows = _queued_jobs(session, job_model)
    return rows[0] if rows else None


def _queued_job_statement(job_model: object):
    statement = select(job_model)
    status_column = getattr(job_model, "status", None)
    if status_column is None:
        status_column = getattr(job_model, "state", None)
    if status_column is not None:
        statement = statement.where(status_column.in_(("queued", "pending")))
    created_at = getattr(job_model, "created_at", None)
    if created_at is not None:
        statement = statement.order_by(created_at.asc())
    return statement


def _job_is_waiting_for_text(
    session: Session,
    models: object,
    job: object,
    storage: BlobStorage,
) -> bool:
    try:
        document = _document_for_job(session, models, job)
        document_id = _string_attr(document, "id", "document_id", "documentId")
        text_blob_path = _document_text_blob_path(document, document_id)
    except (RuntimeError, ValueError):
        return False

    payload, load_error = load_text_json(storage, document_id=document_id, text_blob_path=text_blob_path)
    gate = gate_text_payload(payload, load_error)
    return gate.status == "pending_ocr"


def process_processing_job(
    session: Session,
    storage: BlobStorage,
    job_id: str,
    ai_provider: Optional[AIProvider] = None,
) -> ProcessingResult:
    models = importlib.import_module("app.models")
    job_model = _first_model(models, "DocumentProcessingJob", "ProcessingJob", "AIProcessingJob")
    if job_model is None:
        raise RuntimeError("No processing job model is available")
    job = session.get(job_model, job_id)
    if job is None:
        raise RuntimeError(f"Processing job '{job_id}' was not found")
    return _process_job_with_status(session, models, job, storage, ai_provider)


def _process_job_with_status(
    session: Session,
    models: object,
    job: object,
    storage: BlobStorage,
    ai_provider: Optional[AIProvider] = None,
) -> ProcessingResult:
    _set_first_existing(job, ("status", "state"), "processing")
    _set_first_existing(job, ("started_at", "processing_started_at"), datetime.now(timezone.utc))
    session.commit()

    try:
        document = _document_for_job(session, models, job)
        contracts = _available_contracts(session, models)
        result = process_document_upload(document, storage, contracts, ai_provider)
        run = _persist_processing_outputs(
            session,
            models,
            document,
            result,
            ai_provider or NullAIProvider(),
            job=job,
        )
        _set_first_existing(job, ("status", "state"), _job_status_for_result(result))
        _set_first_existing(job, ("result_json", "output_json", "processing_result"), _model_dump(result))
        _set_first_existing(job, ("output_blob_path", "result_blob_path"), result.output_blob_path)
        _set_first_existing(job, ("completed_at", "processed_at", "finished_at"), datetime.now(timezone.utc))
        if run is not None:
            _set_first_existing(run, ("status",), _job_status_for_result(result))
            _set_first_existing(run, ("completed_at",), datetime.now(timezone.utc))
            _set_first_existing(run, ("result_json",), _model_dump(result))
        session.commit()
        try:
            _trigger_feature_extractor_after_commit(session, models, document, result, run)
        except Exception:
            session.rollback()
        return result
    except Exception as error:
        session.rollback()
        document_id = _string_attr(job, "document_id", "document_upload_id", "upload_id") or ""
        logger.exception(
            "Processing job failed",
            extra={
                "processing_job_id": _string_attr(job, "id"),
                "document_upload_id": document_id,
                "error": str(error),
            },
        )
        _set_first_existing(job, ("status", "state"), "failed")
        _set_first_existing(job, ("error_message", "error", "failure_reason"), str(error))
        _set_first_existing(job, ("completed_at", "processed_at", "finished_at"), datetime.now(timezone.utc))
        session.commit()
        return ProcessingResult(
            document_id=document_id,
            status="failed",
            text_gate=TextGateResult(status="failed", reason=str(error)),
            error=str(error),
        )


def _next_queued_job(session: Session, job_model: object) -> Optional[object]:
    statement = select(job_model)
    status_column = getattr(job_model, "status", None)
    if status_column is None:
        status_column = getattr(job_model, "state", None)
    if status_column is not None:
        statement = statement.where(status_column.in_(("queued", "pending")))
    created_at = getattr(job_model, "created_at", None)
    if created_at is not None:
        statement = statement.order_by(created_at.asc())
    return session.scalars(statement).first()


def _document_for_job(session: Session, models: object, job: object) -> object:
    document = getattr(job, "document", None) or getattr(job, "document_upload", None)
    if document is not None:
        return document

    document_model = _first_model(models, "DocumentUpload", "Document", "ContractDocument")
    document_id = _string_attr(job, "document_id", "document_upload_id", "upload_id")
    if document_model is None or not document_id:
        raise RuntimeError("Processing job does not reference a document")
    document = session.get(document_model, document_id)
    if document is None:
        raise RuntimeError(f"Document '{document_id}' was not found")
    return document


def _available_contracts(session: Session, models: object) -> List[object]:
    contract_model = _first_model(models, "Contract", "ContractRecord")
    if contract_model is None or not _model_table_exists(session, contract_model):
        return []
    return list(session.scalars(select(contract_model)).all())


def _create_processing_run(
    session: Session,
    models: object,
    document: object,
    result: ProcessingResult,
    provider: AIProvider,
    job: Optional[object] = None,
) -> Optional[object]:
    run_model = _first_model(models, "ProcessingRun")
    if run_model is None or not _model_table_exists(session, run_model):
        return None
    run = run_model(
        id=str(uuid4()),
        document_upload_id=_string_attr(document, "id", "document_id"),
        contract_id=result.contract_match.matched_contract_id if result.contract_match else None,
        job_id=_string_attr(job, "id"),
        run_type="document_analysis",
        status="running",
        model_name=getattr(getattr(provider, "status", None), "name", None),
        prompt_version="deterministic_v1",
        raw_model_json=_model_dump(result.ai_result) if result.ai_result is not None else None,
        metadata_json={"text_gate_status": result.text_gate.status},
    )
    session.add(run)
    session.flush()
    return run


def _add_run_step(
    session: Session,
    models: object,
    run: Optional[object],
    document: object,
    step_name: str,
    status: str,
    message: Optional[str] = None,
    metadata: Optional[Dict[str, object]] = None,
) -> None:
    step_model = _first_model(models, "ProcessingRunStep")
    if run is None or step_model is None or not _model_table_exists(session, step_model):
        return
    now = datetime.now(timezone.utc)
    session.add(
        step_model(
            id=str(uuid4()),
            processing_run_id=_string_attr(run, "id") or "",
            document_upload_id=_string_attr(document, "id", "document_id"),
            step_name=step_name,
            status=status,
            message=message,
            started_at=now,
            completed_at=now,
            metadata_json=metadata or {},
        )
    )


def _persist_processing_outputs(
    session: Session,
    models: object,
    document: object,
    result: ProcessingResult,
    provider: AIProvider,
    job: Optional[object] = None,
) -> Optional[object]:
    if result.text_gate.text:
        document_kind, _modification_kind = classify_document(document, result.text_gate.text)
        _auto_scaffold_contract_for_unmatched_upload(session, models, document, result, document_kind)
    run = _create_processing_run(session, models, document, result, provider, job=job)
    _add_run_step(session, models, run, document, "extraction", result.text_gate.status)
    _update_document_status(document, result)
    _persist_match_decision(session, models, document, result)
    page_rows = _persist_pages(session, models, document, result, run)
    chunk_rows = _persist_chunks(session, models, document, result, page_rows)
    _add_run_step(session, models, run, document, "matching", result.contract_match.status if result.contract_match else "unmatched")
    _persist_embeddings(session, models, chunk_rows, provider)
    signal_rows = _persist_signals(session, models, document, result, chunk_rows)
    _persist_signal_topics(session, models, document, result, signal_rows, chunk_rows)
    analysis_chunks = chunk_rows or _stored_chunks_for_document(session, models, document)
    contract_id = result.contract_match.matched_contract_id if result.contract_match else None
    apply_contract_analysis_pipeline(
        session,
        document,
        contract_id,
        result.text_gate.text,
        analysis_chunks,
        processing_run_id=_string_attr(run, "id"),
        ai_provider=provider,
    )
    _persist_classification_decision(session, models, document, run)
    _persist_entities_and_facts(session, models, document, result, page_rows, analysis_chunks, run)
    _add_run_step(session, models, run, document, "analysis", result.status)
    return run


def _trigger_feature_extractor_after_commit(
    session: Session,
    models: object,
    document: object,
    result: ProcessingResult,
    run: Optional[object],
) -> None:
    document_id = _string_attr(document, "id", "document_id")
    if run is None or result.status != "processed" or not document_id:
        return

    contract_id = _string_attr(document, "contract_id")
    doc_classification = _document_classification(document)
    processing_run_id = _string_attr(run, "id")
    try:
        with log_context(
            document_upload_id=document_id,
            contract_id=contract_id,
            processing_run_id=processing_run_id,
        ):
            step_results = trigger_feature_extractor(
                document_id,
                contract_id,
                doc_classification,
                processing_run_id=processing_run_id,
            )
    except Exception as error:
        step_results = [
            FeatureExtractorStepResult(
                step_name="feature_extractor.summary",
                event_type="feature_extractor.summary",
                status="failed",
                message=str(error),
                metadata={
                    "doc_classification": doc_classification,
                    "unexpected_error": True,
                },
            )
        ]
    if not step_results:
        return

    try:
        for step in step_results:
            metadata = {
                **step.metadata,
                "doc_classification": doc_classification,
                "source": "backend_processing",
            }
            _add_run_step(
                session,
                models,
                run,
                document,
                step.step_name,
                step.status,
                message=step.message,
                metadata=metadata,
            )
            _add_audit_event(
                session,
                models,
                document,
                step.event_type,
                step.status,
                contract_id=contract_id,
                message=step.message,
                metadata=metadata,
            )
        session.commit()
    except Exception:
        session.rollback()


def _add_audit_event(
    session: Session,
    models: object,
    document: object,
    event_type: str,
    status: str,
    contract_id: Optional[str] = None,
    message: Optional[str] = None,
    metadata: Optional[Dict[str, object]] = None,
) -> None:
    audit_model = _first_model(models, "AuditEvent")
    document_id = _string_attr(document, "id", "document_id")
    if audit_model is None or not document_id or not _model_table_exists(session, audit_model):
        return
    event_metadata: Dict[str, object] = {"status": status, **(metadata or {})}
    if message:
        event_metadata["message"] = message
    session.add(
        audit_model(
            id=str(uuid4()),
            event_type=event_type,
            entity_type="document_upload",
            entity_id=document_id,
            contract_id=contract_id,
            document_upload_id=document_id,
            metadata_json=event_metadata,
        )
    )


def _persist_pages(
    session: Session,
    models: object,
    document: object,
    result: ProcessingResult,
    run: Optional[object],
) -> List[object]:
    page_model = _first_model(models, "DocumentPage")
    document_id = _string_attr(document, "id", "document_id")
    if page_model is None or not document_id or not _model_table_exists(session, page_model):
        return []

    existing_by_number = {
        int(row.page_number): row
        for row in session.scalars(
            select(page_model).where(page_model.document_upload_id == document_id)
        ).all()
    }
    rows = []
    for page in result.pages or [PageText(page_number=1, text=result.text_gate.text, start_char=0, end_char=len(result.text_gate.text))]:
        existing = existing_by_number.get(page.page_number)
        if existing is not None:
            rows.append(existing)
            continue
        row = page_model(
            id=str(uuid4()),
            document_upload_id=document_id,
            processing_run_id=_string_attr(run, "id"),
            page_number=page.page_number,
            text=page.text,
            extraction_status=result.text_gate.status if result.text_gate.status != "ready" else "extracted",
            source_start_offset=page.start_char,
            source_end_offset=page.end_char,
            extraction_warning=None,
            extraction_error=result.text_gate.reason if result.status == "failed" else None,
            metadata_json={},
        )
        session.add(row)
        rows.append(row)
    return rows


def _persist_classification_decision(
    session: Session,
    models: object,
    document: object,
    run: Optional[object],
) -> None:
    decision_model = _first_model(models, "DocumentClassificationDecision")
    document_id = _string_attr(document, "id", "document_id")
    if decision_model is None or not document_id or not _model_table_exists(session, decision_model):
        return
    metadata = getattr(document, "metadata_json", None) or {}
    classification = metadata.get("classification", {}) if isinstance(metadata, dict) else {}
    document_kind = classification.get("document_kind") or _string_attr(document, "document_kind") or "other"
    session.add(
        decision_model(
            id=str(uuid4()),
            document_upload_id=document_id,
            processing_run_id=_string_attr(run, "id"),
            document_kind=document_kind,
            modification_kind=classification.get("modification_kind"),
            confidence=classification.get("confidence") or 0.6,
            rationale=classification.get("rationale") or "Deterministic classifier matched local document cues.",
            classifier_name=classification.get("classifier") or "deterministic_v1",
            metadata_json=classification,
        )
    )


def _persist_entities_and_facts(
    session: Session,
    models: object,
    document: object,
    result: ProcessingResult,
    page_rows: Sequence[object],
    chunk_rows: Sequence[object],
    run: Optional[object],
) -> None:
    entity_model = _first_model(models, "DocumentEntity")
    fact_model = _first_model(models, "DocumentReportFact")
    document_id = _string_attr(document, "id", "document_id")
    contract_id = result.contract_match.matched_contract_id if result.contract_match else None
    if not document_id:
        return

    first_page = page_rows[0] if page_rows else None
    first_chunk = chunk_rows[0] if chunk_rows else None
    if entity_model is not None and _model_table_exists(session, entity_model):
        for entity in _extract_entities(result.text_gate.text):
            evidence_hash = hashlib.sha256(
                f"{document_id}:{entity['entity_type']}:{entity['normalized_value']}".encode("utf-8")
            ).hexdigest()
            if _row_with_evidence_hash_exists(session, entity_model, document_id, evidence_hash):
                continue
            session.add(
                entity_model(
                    id=str(uuid4()),
                    document_upload_id=document_id,
                    contract_id=contract_id,
                    page_id=_string_attr(first_page, "id"),
                    chunk_id=_string_attr(first_chunk, "id"),
                    processing_run_id=_string_attr(run, "id"),
                    entity_type=entity["entity_type"],
                    value=entity["value"],
                    normalized_value=entity["normalized_value"],
                    quote=entity["quote"],
                    confidence=entity["confidence"],
                    evidence_hash=evidence_hash,
                    metadata_json={"extractor": "deterministic_v1"},
                )
            )

    if fact_model is not None and _model_table_exists(session, fact_model):
        for fact in _extract_report_facts(result.text_gate.text):
            evidence_hash = hashlib.sha256(
                f"{document_id}:{fact['fact_type']}:{fact['value_text']}".encode("utf-8")
            ).hexdigest()
            if _row_with_evidence_hash_exists(session, fact_model, document_id, evidence_hash):
                continue
            session.add(
                fact_model(
                    id=str(uuid4()),
                    document_upload_id=document_id,
                    contract_id=contract_id,
                    page_id=_string_attr(first_page, "id"),
                    chunk_id=_string_attr(first_chunk, "id"),
                    processing_run_id=_string_attr(run, "id"),
                    fact_type=fact["fact_type"],
                    label=fact["label"],
                    value_text=fact["value_text"],
                    value_json=fact.get("value_json"),
                    quote=fact["quote"],
                    confidence=fact["confidence"],
                    evidence_hash=evidence_hash,
                    metadata_json={"extractor": "deterministic_v1"},
                )
            )


def _payload_pages(payload: Optional[TextJsonPayload], text: str) -> List[PageText]:
    pages = []
    for index, item in enumerate((payload.pages if payload else []) or [], start=1):
        try:
            page_number = int(item.get("page_number") or index)
        except (TypeError, ValueError):
            page_number = index
        page_text = str(item.get("text") or "")
        if not page_text.strip():
            continue
        pages.append(
            PageText(
                page_number=page_number,
                text=page_text,
                start_char=_optional_int(item.get("start_char")),
                end_char=_optional_int(item.get("end_char")),
            )
        )
    if pages:
        return pages
    return [PageText(page_number=1, text=text, start_char=0, end_char=len(text))] if text else []


def _extract_entities(text: str) -> List[Dict[str, object]]:
    patterns = [
        ("contract_number", r"\b[A-Z]\d{7}[A-Z]\d{4}\b|\b[A-Z]\d{5}-\d{2}-[A-Z]-\d{4}\b"),
        ("rfi", r"\bRFI[- ]?\d+\b"),
        ("dollar_value", r"\$[0-9][0-9,]*(?:\.[0-9]{2})?"),
        ("date", r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b"),
        ("clause", r"\b(?:FAR|DFARS)\s+\d{1,3}\.\d+(?:-\d+)?\b"),
    ]
    entities: List[Dict[str, object]] = []
    seen = set()
    for entity_type, pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = match.group(0).strip()
            normalized = value.upper()
            key = (entity_type, normalized)
            if key in seen:
                continue
            seen.add(key)
            entities.append(
                {
                    "entity_type": entity_type,
                    "value": value,
                    "normalized_value": normalized,
                    "quote": _surrounding_text(text, match.start(), match.end()),
                    "confidence": 0.72,
                }
            )
    return entities[:100]


def _extract_report_facts(text: str) -> List[Dict[str, object]]:
    facts: List[Dict[str, object]] = []
    lower = text.lower()
    for value in re.findall(r"(\d+)\s+days?\s+open", lower):
        facts.append(
            {
                "fact_type": "rfi_age",
                "label": "RFI age",
                "value_text": f"{value} days open",
                "value_json": {"days_open": int(value)},
                "quote": _snippet_for_text(text, f"{value} days open"),
                "confidence": 0.74,
            }
        )
    if "government action required" in lower or "pending government" in lower:
        facts.append(
            {
                "fact_type": "government_action_item",
                "label": "Government action item",
                "value_text": "Government action required",
                "value_json": {},
                "quote": _snippet_for_text(text, "government action"),
                "confidence": 0.7,
            }
        )
    if "schedule risk" in lower or "critical path" in lower:
        facts.append(
            {
                "fact_type": "schedule_signal",
                "label": "Schedule signal",
                "value_text": "Schedule risk or critical path dependency",
                "value_json": {},
                "quote": _snippet_for_text(text, "schedule"),
                "confidence": 0.68,
            }
        )
    if "cost variance" in lower or "unbudgeted" in lower or "eac" in lower:
        facts.append(
            {
                "fact_type": "cost_signal",
                "label": "Cost signal",
                "value_text": "Cost variance or unbudgeted effort",
                "value_json": {},
                "quote": _snippet_for_text(text, "cost"),
                "confidence": 0.68,
            }
        )
    return facts[:80]


def _auto_scaffold_contract_for_unmatched_upload(
    session: Session,
    models: object,
    document: object,
    result: ProcessingResult,
    document_kind: str,
) -> None:
    match = result.contract_match
    if (
        match is None
        or match.matched_contract_id
        or document_kind not in AUTO_SCAFFOLD_DOCUMENT_KINDS
        or _classification_confidence(document) < AUTO_SCAFFOLD_CONFIDENCE
    ):
        return

    contract_number = _single_contract_hint(match.hints)
    if contract_number is None:
        return

    contract_model = _first_model(models, "Contract", "ContractRecord")
    if contract_model is None or not _model_table_exists(session, contract_model):
        return

    existing = session.scalars(
        select(contract_model).where(contract_model.contract_number == contract_number)
    ).first()
    created = False
    if existing is None:
        metadata = _extract_contract_metadata(result.text_gate.text)
        existing = contract_model(
            id=_auto_contract_id(contract_number),
            contract_number=contract_number,
            title=metadata.get("title") or f"Contract {contract_number}",
            agency_name=metadata.get("agency_name"),
            vendor_name=metadata.get("vendor_name"),
            status="pending_review",
            security_level=_string_attr(document, "security_level") or "standard",
            metadata_json={
                "auto_created": True,
                "auto_created_from_document_id": _string_attr(document, "id", "document_id"),
                "auto_create_reason": "unmatched_source_contract_or_task_order",
                "classification": _classification_metadata(document),
                "review_status": "pending",
            },
        )
        session.add(existing)
        session.flush()
        created = True

    contract_id = _string_attr(existing, "id")
    _set_first_existing(document, ("contract_id",), contract_id)
    result.contract_match = ContractMatchResult(
        status="matched",
        source="auto_scaffold" if created else "auto_scaffold_existing",
        matched_contract_id=contract_id,
        matched_contract_number=contract_number,
        confidence=_classification_confidence(document),
        hints=match.hints,
        ai_hints=match.ai_hints,
    )
    if created:
        _grant_auto_scaffold_review_access(session, models, existing, document)
        _add_auto_created_audit_event(session, models, existing, document, contract_number)


def _single_contract_hint(hints: Sequence[str]) -> Optional[str]:
    normalized_to_hint: Dict[str, str] = {}
    for hint in hints:
        normalized = re.sub(r"[^A-Z0-9]", "", (hint or "").upper())
        if normalized:
            normalized_to_hint[normalized] = hint.strip().upper()
    if len(normalized_to_hint) != 1:
        return None
    return next(iter(normalized_to_hint.values()))


def _classification_metadata(document: object) -> Dict[str, object]:
    metadata = getattr(document, "metadata_json", None) or {}
    if not isinstance(metadata, dict):
        return {}
    classification = metadata.get("classification")
    return classification if isinstance(classification, dict) else {}


def _classification_confidence(document: object) -> float:
    value = _classification_metadata(document).get("confidence")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _extract_contract_metadata(text: str) -> Dict[str, Optional[str]]:
    return {
        "title": _first_labeled_value(text, ("Contract Title", "Title", "Description")),
        "agency_name": _first_labeled_value(
            text,
            ("Agency", "Department", "Ordering Agency", "Contracting Agency", "Contracting Office"),
        ),
        "vendor_name": _first_labeled_value(text, ("Contractor", "Vendor", "Awardee", "Recipient")),
    }


def _first_labeled_value(text: str, labels: Sequence[str]) -> Optional[str]:
    for label in labels:
        pattern = rf"(?im)^\s*(?:\*\*)?{re.escape(label)}(?:\*\*)?\s*:\s*(.+?)\s*$"
        match = re.search(pattern, text[:8000])
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" -*")
            if value:
                return value[:300]
    return None


def _auto_contract_id(contract_number: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"federal-center-sw:auto-contract:{contract_number}"))


def _grant_auto_scaffold_review_access(
    session: Session,
    models: object,
    contract: object,
    document: object,
) -> None:
    grant_model = _first_model(models, "ContractAccessGrant")
    if grant_model is None or not _model_table_exists(session, grant_model):
        return
    contract_id = _string_attr(contract, "id")
    if not contract_id:
        return
    uploader_id = _string_attr(document, "uploader_id")
    security_level = _string_attr(document, "security_level") or "standard"
    grants = [("official", "role", "reviewer")]
    if uploader_id:
        grants.append((uploader_id, "user", "uploader"))
    for principal_id, principal_type, role in grants:
        grant_id = str(uuid5(NAMESPACE_URL, f"auto-grant:{contract_id}:{principal_id}:{role}"))
        if session.get(grant_model, grant_id) is not None:
            continue
        session.add(
            grant_model(
                id=grant_id,
                contract_id=contract_id,
                principal_id=principal_id,
                principal_type=principal_type,
                role=role,
                security_level=security_level,
                granted_by_id="system:auto_scaffold",
            )
        )


def _add_auto_created_audit_event(
    session: Session,
    models: object,
    contract: object,
    document: object,
    contract_number: str,
) -> None:
    audit_model = _first_model(models, "AuditEvent")
    if audit_model is None or not _model_table_exists(session, audit_model):
        return
    contract_id = _string_attr(contract, "id")
    document_id = _string_attr(document, "id", "document_id")
    if not contract_id or not document_id:
        return
    session.add(
        audit_model(
            id=str(uuid4()),
            actor_id="system:auto_scaffold",
            actor_role="system",
            event_type="contract.auto_created",
            entity_type="contract",
            entity_id=contract_id,
            contract_id=contract_id,
            document_upload_id=document_id,
            metadata_json={
                "contract_number": contract_number,
                "document_kind": _string_attr(document, "document_kind"),
                "classification": _classification_metadata(document),
                "review_status": "pending",
            },
        )
    )


def _update_document_status(document: object, result: ProcessingResult) -> None:
    if result.contract_match and result.contract_match.matched_contract_id:
        _set_first_existing(document, ("contract_id",), result.contract_match.matched_contract_id)
        _set_first_existing(document, ("match_status",), result.contract_match.status)
    elif result.contract_match:
        _set_first_existing(document, ("match_status",), result.contract_match.status)
    _set_first_existing(document, ("processing_status",), result.status)
    if result.error:
        _set_first_existing(document, ("processing_error_message",), result.error)


def _persist_match_decision(
    session: Session,
    models: object,
    document: object,
    result: ProcessingResult,
) -> None:
    match = result.contract_match
    decision_model = _first_model(models, "DocumentMatchDecision", "ContractMatchDecision")
    if match is None or decision_model is None or not _model_table_exists(session, decision_model):
        return

    document_id = _string_attr(document, "id", "document_id", "documentId")
    if not document_id:
        return
    decision = decision_model(
        id=str(uuid4()),
        document_upload_id=document_id,
        contract_id=match.matched_contract_id,
        matched_contract_number=match.matched_contract_number,
        decision_status=match.status,
        decision_source=match.source,
        confidence=match.confidence,
        rationale=", ".join(match.hints[:5]) or None,
        metadata_json={"ai_hints": [_model_dump(hint) for hint in match.ai_hints]},
    )
    session.add(decision)


def _persist_chunks(
    session: Session,
    models: object,
    document: object,
    result: ProcessingResult,
    page_rows: Sequence[object] = (),
) -> List[object]:
    chunk_model = _first_model(models, "DocumentChunk", "Chunk")
    if chunk_model is None or not result.chunks or not _model_table_exists(session, chunk_model):
        return []

    document_id = _string_attr(document, "id", "document_id", "documentId")
    if not document_id:
        return []
    contract_id = result.contract_match.matched_contract_id if result.contract_match else None
    page_ids_by_number = {
        int(getattr(page, "page_number")): _string_attr(page, "id")
        for page in page_rows
        if getattr(page, "page_number", None) is not None
    }
    existing_indexes = {
        row.chunk_index
        for row in session.scalars(
            select(chunk_model).where(chunk_model.document_upload_id == document_id)
        ).all()
        if hasattr(row, "chunk_index")
    }

    rows = []
    for chunk in result.chunks:
        if chunk.index in existing_indexes:
            continue
        row = chunk_model(
            id=str(uuid4()),
            document_upload_id=document_id,
            contract_id=contract_id,
            chunk_index=chunk.index,
            page_number=chunk.pages[0] if chunk.pages else None,
            text=chunk.text,
            token_count=max(1, len(chunk.text) // 4),
            metadata_json={
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "pages": chunk.pages,
                "page_ids": [page_ids_by_number[number] for number in chunk.pages if number in page_ids_by_number],
            },
        )
        session.add(row)
        rows.append(row)
    return rows


def _stored_chunks_for_document(
    session: Session,
    models: object,
    document: object,
) -> List[object]:
    chunk_model = _first_model(models, "DocumentChunk", "Chunk")
    document_id = _string_attr(document, "id", "document_id", "documentId")
    if chunk_model is None or not document_id or not _model_table_exists(session, chunk_model):
        return []
    try:
        return list(
            session.scalars(
                select(chunk_model)
                .where(chunk_model.document_upload_id == document_id)
                .order_by(chunk_model.chunk_index.asc())
            ).all()
        )
    except SQLAlchemyError:
        return []


def _persist_embeddings(
    session: Session,
    models: object,
    chunk_rows: Sequence[object],
    provider: AIProvider,
) -> None:
    embedding_model = _first_model(models, "ChunkEmbedding", "Embedding")
    if embedding_model is None or not chunk_rows or not provider.status.available:
        return
    if not _model_table_exists(session, embedding_model):
        return

    texts = [_string_attr(row, "text") or "" for row in chunk_rows]
    embeddings = provider.embed_texts(texts)
    if len(embeddings) != len(chunk_rows):
        return
    for row, embedding in zip(chunk_rows, embeddings):
        session.add(
            embedding_model(
                id=str(uuid4()),
                chunk_id=_string_attr(row, "id") or "",
                embedding_model=getattr(provider.status, "name", "unknown"),
                embedding_dimension=len(embedding),
                embedding=embedding,
                metadata_json={},
            )
        )


def _persist_signals(
    session: Session,
    models: object,
    document: object,
    result: ProcessingResult,
    chunk_rows: Sequence[object],
) -> List[object]:
    signal_model = _first_model(models, "PerformanceSignal", "Signal")
    if (
        signal_model is None
        or result.ai_result is None
        or not result.ai_result.signals
        or result.contract_match is None
        or not result.contract_match.matched_contract_id
        or not _model_table_exists(session, signal_model)
    ):
        return []

    document_id = _string_attr(document, "id", "document_id", "documentId")
    first_chunk_id = _string_attr(chunk_rows[0], "id") if chunk_rows else None
    rows = []
    for signal in result.ai_result.signals:
        row = signal_model(
            id=str(uuid4()),
            contract_id=result.contract_match.matched_contract_id,
            document_upload_id=document_id,
            chunk_id=first_chunk_id,
            signal_type=signal.category,
            label=signal.label,
            summary=signal.summary,
            confidence=signal.confidence,
            metadata_json={"evidence": signal.evidence},
        )
        session.add(row)
        rows.append(row)
    return rows


def _persist_signal_topics(
    session: Session,
    models: object,
    document: object,
    result: ProcessingResult,
    signal_rows: Sequence[object],
    chunk_rows: Sequence[object],
) -> None:
    topic_model = _first_model(models, "ContractTopic", "Topic")
    evidence_model = _first_model(models, "TopicEvidence", "Evidence")
    revision_model = _first_model(models, "ContractTopicRevision", "TopicRevision")
    if (
        topic_model is None
        or evidence_model is None
        or not signal_rows
        or result.contract_match is None
        or not result.contract_match.matched_contract_id
        or not _model_table_exists(session, topic_model)
        or not _model_table_exists(session, evidence_model)
    ):
        return

    contract_id = result.contract_match.matched_contract_id
    document_id = _string_attr(document, "id", "document_id", "documentId")
    first_chunk = chunk_rows[0] if chunk_rows else None
    for signal in signal_rows:
        topic_key = _topic_key(signal)
        topic = _topic_by_key(session, topic_model, contract_id, topic_key)
        is_new = topic is None
        if topic is None:
            topic = topic_model(
                id=str(uuid4()),
                contract_id=contract_id,
                topic_key=topic_key,
                title=_topic_title(signal),
                description=_string_attr(signal, "summary") or "Agent-observed contract signal.",
                status="candidate",
                metadata_json={
                    "source": "signal_extract",
                    "signal_types": [_string_attr(signal, "signal_type")],
                },
            )
            session.add(topic)
            session.flush()
        else:
            _set_first_existing(topic, ("description", "summary"), _string_attr(signal, "summary") or "")

        quote = _validated_quote(signal, first_chunk)
        session.add(
            evidence_model(
                id=str(uuid4()),
                topic_id=_string_attr(topic, "id") or "",
                document_upload_id=document_id,
                chunk_id=_string_attr(first_chunk, "id") if first_chunk is not None else None,
                performance_signal_id=_string_attr(signal, "id"),
                evidence_type="supporting",
                quote=quote,
                summary=_string_attr(signal, "summary"),
                confidence=getattr(signal, "confidence", None),
                metadata_json={
                    "quote_hash": hashlib.sha256(quote.encode("utf-8")).hexdigest() if quote else None,
                    "validation_status": "validated" if quote else "missing_quote",
                },
            )
        )
        if revision_model is not None and _model_table_exists(session, revision_model):
            topic_id = _string_attr(topic, "id") or ""
            session.add(
                revision_model(
                    id=str(uuid4()),
                    topic_id=topic_id,
                    revision_number=_next_revision_number(session, revision_model, topic_id),
                    title=_string_attr(topic, "title") or _topic_title(signal),
                    description=_string_attr(topic, "description", "summary"),
                    status=_string_attr(topic, "status") or "candidate",
                    change_summary="Created topic from extracted signal" if is_new else "Added signal evidence",
                    changed_by_id="agent",
                    metadata_json={
                        "document_upload_id": document_id,
                        "performance_signal_id": _string_attr(signal, "id"),
                        "topic_operation": "create" if is_new else "update",
                    },
                )
            )


def _topic_by_key(session: Session, topic_model: object, contract_id: str, topic_key: str) -> Optional[object]:
    try:
        return session.scalars(
            select(topic_model).where(
                topic_model.contract_id == contract_id,
                topic_model.topic_key == topic_key,
            )
        ).first()
    except SQLAlchemyError:
        return None


def _topic_key(signal: object) -> str:
    value = f"{_string_attr(signal, 'signal_type') or 'signal'}-{_string_attr(signal, 'label') or 'topic'}"
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:120] or "contract-signal"


def _topic_title(signal: object) -> str:
    label = _string_attr(signal, "label")
    signal_type = _string_attr(signal, "signal_type")
    if label and signal_type:
        return f"{label} ({signal_type})"[:200]
    return (label or signal_type or "Contract signal")[:200]


def _validated_quote(signal: object, chunk: Optional[object]) -> Optional[str]:
    metadata = getattr(signal, "metadata_json", None) or {}
    evidence_values = metadata.get("evidence") if isinstance(metadata, dict) else None
    chunk_text = _string_attr(chunk, "text") or ""
    if isinstance(evidence_values, list):
        for value in evidence_values:
            quote = str(value).strip()
            if quote and quote in chunk_text:
                return quote
    summary = _string_attr(signal, "summary") or ""
    return summary if summary and summary in chunk_text else None


def _next_revision_number(session: Session, revision_model: object, topic_id: str) -> int:
    try:
        revisions = session.scalars(select(revision_model).where(revision_model.topic_id == topic_id)).all()
    except SQLAlchemyError:
        return 1
    return len(revisions) + 1


def _job_status_for_result(result: ProcessingResult) -> str:
    if result.status == "processed":
        return "completed"
    return result.status


def _document_classification(document: object) -> str:
    metadata = getattr(document, "metadata_json", None) or {}
    classification = metadata.get("classification", {}) if isinstance(metadata, dict) else {}
    if isinstance(classification, dict):
        document_kind = classification.get("document_kind")
        if document_kind:
            return str(document_kind)
    return _string_attr(document, "document_kind") or "other"


def _optional_int(value: object) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _row_with_evidence_hash_exists(
    session: Session,
    model: object,
    document_id: str,
    evidence_hash: str,
) -> bool:
    try:
        return (
            session.scalars(
                select(model).where(
                    model.document_upload_id == document_id,
                    model.evidence_hash == evidence_hash,
                )
            ).first()
            is not None
        )
    except SQLAlchemyError:
        return False


def _surrounding_text(text: str, start: int, end: int, radius: int = 160) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)].strip()


def _snippet_for_text(text: str, needle: str, radius: int = 180) -> str:
    index = text.lower().find(needle.lower())
    if index < 0:
        return text[: radius * 2].strip()
    return _surrounding_text(text, index, index + len(needle), radius=radius)


def _model_table_exists(session: Session, model: object) -> bool:
    bind = session.get_bind()
    try:
        return sqlalchemy_inspect(bind).has_table(model.__tablename__)
    except (AttributeError, SQLAlchemyError):
        return False


def _write_processing_result(storage: BlobStorage, result: ProcessingResult) -> ProcessingResult:
    if not result.document_id:
        return result
    result.output_blob_path = f"contracts/{result.document_id}/processing.json"
    storage.upload_bytes(
        result.output_blob_path,
        json.dumps(_model_dump(result), indent=2, sort_keys=True).encode("utf-8"),
        "application/json",
    )
    return result


def _document_text_blob_path(document: object, document_id: str) -> str:
    explicit = _string_attr(document, "text_blob_path", "text_path")
    if explicit:
        return explicit
    blob_path = _string_attr(document, "blob_path")
    if blob_path and "/" in blob_path:
        return f"{blob_path.rsplit('/', 1)[0]}/{TEXT_JSON_FILENAME}"
    return _text_blob_path(document_id)


def _text_blob_path(document_id: Optional[str]) -> str:
    if not document_id:
        raise ValueError("document_id is required when text_blob_path is not provided")
    return f"contracts/{document_id}/{TEXT_JSON_FILENAME}"


def _first_model(models: object, *names: str) -> Optional[object]:
    for name in names:
        model = getattr(models, name, None)
        if model is not None:
            return model
    return None


def _set_first_existing(item: object, names: Sequence[str], value: object) -> bool:
    for name in names:
        if hasattr(item, name):
            setattr(item, name, value)
            return True
    return False


def _string_attr(item: object, *names: str) -> Optional[str]:
    for name in names:
        value = item.get(name) if isinstance(item, dict) else getattr(item, name, None)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _model_dump(model: BaseModel) -> Dict[str, object]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
