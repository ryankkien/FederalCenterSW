from __future__ import annotations

import argparse

from app.database import SessionLocal, create_db_schema
from app.primitive_backfill import backfill_contract_primitives


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill typed contract primitive rows from processed evidence.")
    parser.add_argument("--contract-id", default=None)
    parser.add_argument("--document-id", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    create_db_schema()
    with SessionLocal() as db:
        totals = backfill_contract_primitives(
            db,
            contract_id=args.contract_id,
            document_id=args.document_id,
            limit=args.limit,
        )
        db.commit()
    print(totals)


if __name__ == "__main__":
    main()
