from __future__ import annotations

import argparse
from typing import Optional, Sequence

from app.ai.providers import get_ai_provider
from app.blob_storage import get_blob_storage
from app.database import SessionLocal, create_db_schema
from app.processing import process_one_queued_job


def run_processing(limit: int) -> int:
    create_db_schema()
    processed = 0
    storage = get_blob_storage()
    provider = get_ai_provider()
    with SessionLocal() as session:
        for _ in range(max(0, limit)):
            result = process_one_queued_job(session, storage, provider)
            if result.status == "idle":
                break
            processed += 1
            print(f"{result.document_id}: {result.status}")
    return processed


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run queued contract document processing jobs.")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)
    count = run_processing(args.limit)
    print(f"Processed {count} queued job(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
