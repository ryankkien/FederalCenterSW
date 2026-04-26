from __future__ import annotations

import argparse
from typing import Optional, Sequence

from app.ai.providers import get_ai_provider
from app.blob_storage import get_blob_storage
from app.database import SessionLocal, create_db_schema
from app.config import get_document_processing_max_workers
from app.processing_worker import drain_queued_processing_jobs


def run_processing(limit: int, max_workers: int) -> int:
    create_db_schema()
    storage = get_blob_storage()
    provider = get_ai_provider()
    summary = drain_queued_processing_jobs(
        limit=limit,
        storage=storage,
        ai_provider=provider,
        session_factory=SessionLocal,
        ensure_schema=False,
        max_workers=max_workers,
    )
    print(
        "Processed "
        f"{summary.processed} queued job(s): "
        f"{summary.completed} completed, "
        f"{summary.failed} failed, "
        f"{summary.waiting_for_text} waiting for text, "
        f"{summary.queued_remaining} queued remaining."
    )
    return summary.processed


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run queued contract document processing jobs.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--workers", type=int, default=get_document_processing_max_workers())
    args = parser.parse_args(argv)
    run_processing(args.limit, max(1, args.workers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
