from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from time import sleep
from typing import Optional
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.ai.providers import AIProvider, get_ai_provider
from app.blob_storage import BlobStorage, get_blob_storage
from app.config import get_document_processing_max_workers
from app.database import SessionLocal, create_db_schema
from app.models import DocumentProcessingJob
from app.processing import (
    ProcessingResult,
    TextGateResult,
    process_one_queued_job,
    queued_processing_job_count,
    waiting_for_text_processing_job_count,
)


@dataclass(frozen=True)
class ProcessingDrainSummary:
    processed: int
    completed: int
    failed: int
    waiting_for_text: int
    queued_remaining: int


def drain_queued_processing_jobs(
    limit: int = 25,
    storage: Optional[BlobStorage] = None,
    ai_provider: Optional[AIProvider] = None,
    session_factory: sessionmaker = SessionLocal,
    ensure_schema: bool = True,
    max_workers: Optional[int] = None,
) -> ProcessingDrainSummary:
    if ensure_schema:
        create_db_schema()

    processed = 0
    completed = 0
    failed = 0
    storage_adapter = storage or get_blob_storage()
    provider = ai_provider or get_ai_provider()
    worker_count = max(1, max_workers or get_document_processing_max_workers())

    if worker_count == 1:
        with session_factory() as session:
            for _ in range(max(0, limit)):
                result = process_one_queued_job(session, storage_adapter, provider, worker_id="worker-serial")
                if result.status == "idle":
                    break

                processed += 1
                if result.status == "processed":
                    completed += 1
                elif result.status == "failed":
                    failed += 1
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(
                    _process_one_in_new_session,
                    session_factory,
                    storage_adapter,
                    provider,
                    f"worker-{uuid4()}",
                )
                for _ in range(max(0, limit))
            ]
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as error:
                    result = ProcessingResult(
                        document_id="",
                        status="failed",
                        text_gate=TextGateResult(status="failed", reason=str(error)),
                        error=str(error),
                    )
                if result.status == "idle":
                    continue
                processed += 1
                if result.status == "processed":
                    completed += 1
                elif result.status == "failed":
                    failed += 1

    with session_factory() as session:
        waiting_for_text = waiting_for_text_processing_job_count(session, storage_adapter)
        queued_remaining = queued_processing_job_count(session)

    return ProcessingDrainSummary(
        processed=processed,
        completed=completed,
        failed=failed,
        waiting_for_text=waiting_for_text,
        queued_remaining=queued_remaining,
    )


def _process_one_in_new_session(
    session_factory: sessionmaker,
    storage: BlobStorage,
    provider: AIProvider,
    worker_id: str,
) -> ProcessingResult:
    try:
        with session_factory() as session:
            return process_one_queued_job(session, storage, provider, worker_id=worker_id)
    except Exception as error:
        _mark_worker_jobs_failed(session_factory, worker_id, str(error))
        return ProcessingResult(
            document_id="",
            status="failed",
            text_gate=TextGateResult(status="failed", reason=str(error)),
            error=str(error),
        )


def _mark_worker_jobs_failed(session_factory: sessionmaker, worker_id: str, error: str) -> None:
    for attempt in range(3):
        try:
            with session_factory() as session:
                session.execute(
                    update(DocumentProcessingJob)
                    .where(
                        DocumentProcessingJob.worker_id == worker_id,
                        DocumentProcessingJob.status == "processing",
                    )
                    .values(
                        status="failed",
                        completed_at=datetime.now(timezone.utc),
                        error_message=error[:4000],
                    )
                )
                session.commit()
            return
        except SQLAlchemyError:
            sleep(0.25 * (attempt + 1))
