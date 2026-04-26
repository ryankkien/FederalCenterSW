from __future__ import annotations

import argparse
from typing import List

from sqlalchemy import select

from app.ai.providers import get_ai_provider
from app.database import SessionLocal
from app.knowledge import build_knowledge_index, run_knowledge_ingestion
from app.models import Contract


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local contract wiki knowledge index.")
    subparsers = parser.add_subparsers(dest="command")

    ingest = subparsers.add_parser("ingest", help="Mine source records and build wiki nodes.")
    ingest.add_argument("--scope", default="visible")
    ingest.add_argument("--contract-ids", default="")
    ingest.add_argument("--vendor-ueis", default="")
    ingest.add_argument("--sources", default="local")
    ingest.add_argument("--limit", type=int, default=100)

    build = subparsers.add_parser("build", help="Build wiki nodes from existing local data/source records.")
    build.add_argument("--scope", default="all")
    build.add_argument("--contract-ids", default="")

    args = parser.parse_args()
    command = args.command or "ingest"
    with SessionLocal() as db:
        if command == "build":
            contracts = _contracts(db, _csv(args.contract_ids))
            counts = build_knowledge_index(db, contracts, get_ai_provider())
            db.commit()
            print(
                "Built knowledge index for "
                f"{len(contracts)} contract(s): {counts['nodes']} node(s), {counts['edges']} edge(s), "
                f"{counts['citations']} citation(s)."
            )
            return

        result = run_knowledge_ingestion(
            db,
            scope=args.scope,
            contract_ids=_csv(args.contract_ids),
            vendor_ueis=_csv(args.vendor_ueis),
            sources=_csv(args.sources) or ["open"],
            limit=args.limit,
        )
        db.commit()
        print(
            f"Knowledge ingestion {result.run.id} {result.run.status}: "
            f"{result.source_record_count} source record(s), {result.node_count} node(s), "
            f"{result.edge_count} edge(s), {result.citation_count} citation(s)."
        )


def _csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _contracts(db, contract_ids: List[str]) -> List[Contract]:
    statement = select(Contract)
    if contract_ids:
        statement = statement.where(Contract.id.in_(contract_ids))
    return list(db.scalars(statement.order_by(Contract.updated_at.desc())).all())


if __name__ == "__main__":
    main()
