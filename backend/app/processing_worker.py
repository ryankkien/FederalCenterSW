from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import sessionmaker

from app.ai.providers import AIProvider, get_ai_provider
from app.blob_storage import BlobStorage, get_blob_storage
from app.database import SessionLocal, create_db_schema
from app.processing import (
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
) -> ProcessingDrainSummary:
    if ensure_schema:
        create_db_schema()

    processed = 0
    completed = 0
    failed = 0
    storage_adapter = storage or get_blob_storage()
    provider = ai_provider or get_ai_provider()

    with session_factory() as session:
        for _ in range(max(0, limit)):
            result = process_one_queued_job(session, storage_adapter, provider)
            if result.status == "idle":
                break

            processed += 1
            if result.status == "processed":
                completed += 1
            elif result.status == "failed":
                failed += 1

        waiting_for_text = waiting_for_text_processing_job_count(session, storage_adapter)
        queued_remaining = queued_processing_job_count(session)

    return ProcessingDrainSummary(
        processed=processed,
        completed=completed,
        failed=failed,
        waiting_for_text=waiting_for_text,
        queued_remaining=queued_remaining,
    )
