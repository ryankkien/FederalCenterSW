from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from sqlalchemy import select

from app.ai.providers import get_ai_provider
from app.database import SessionLocal
from app.knowledge import build_knowledge_index, run_knowledge_ingestion
from app.knowledge_bulk import (
    import_ecfr_title48_bulk,
    import_federal_register_bulk,
    import_sam_opportunities_bulk,
    import_usaspending_bulk,
)
from app.models import Contract, KnowledgeSourceRecord


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local contract wiki knowledge index.")
    subparsers = parser.add_subparsers(dest="command")

    ingest = subparsers.add_parser("ingest", help="Mine source records and build wiki nodes.")
    ingest.add_argument("--scope", default="visible")
    ingest.add_argument("--contract-ids", default="")
    ingest.add_argument("--vendor-ueis", default="")
    ingest.add_argument("--sources", default="open")
    ingest.add_argument("--limit", type=int, default=100)

    build = subparsers.add_parser("build", help="Build wiki nodes from existing local data/source records.")
    build.add_argument("--scope", default="all")
    build.add_argument("--contract-ids", default="")

    bulk = subparsers.add_parser(
        "import-usaspending-bulk",
        help="Import Department of Navy service contracts from local USAspending CSV/ZIP bulk files.",
    )
    bulk.add_argument("--paths", required=True, help="Comma-separated CSV/TSV/ZIP files or directories.")
    bulk.add_argument("--limit", type=int, default=0)
    bulk.add_argument("--build-index", action="store_true")

    ecfr_bulk = subparsers.add_parser(
        "import-ecfr-title48-bulk",
        help="Import eCFR Title 48 sections from local govinfo XML bulk files.",
    )
    ecfr_bulk.add_argument("--paths", required=True, help="Comma-separated XML files or directories.")
    ecfr_bulk.add_argument("--limit", type=int, default=0)

    sam_bulk = subparsers.add_parser(
        "import-sam-opportunities-bulk",
        help="Import Department of Navy service opportunities from local SAM.gov public CSV bulk files.",
    )
    sam_bulk.add_argument("--paths", required=True, help="Comma-separated CSV/TSV/ZIP files or directories.")
    sam_bulk.add_argument("--limit", type=int, default=0)

    fr_bulk = subparsers.add_parser(
        "import-federal-register-bulk",
        help="Import acquisition-relevant Federal Register documents from local govinfo XML/ZIP bulk files.",
    )
    fr_bulk.add_argument("--paths", required=True, help="Comma-separated XML/ZIP files or directories.")
    fr_bulk.add_argument("--limit", type=int, default=0)

    export = subparsers.add_parser(
        "export-claude",
        help="Export a sanitized local knowledge-base build packet for Claude Code CLI.",
    )
    export.add_argument("--output-dir", default="backend/data/claude_knowledge")
    export.add_argument("--limit", type=int, default=1000)

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

        if command == "import-usaspending-bulk":
            result = import_usaspending_bulk(
                db,
                paths=_paths(args.paths),
                limit=args.limit or None,
            )
            counts = {"nodes": 0, "edges": 0, "citations": 0}
            if args.build_index:
                contracts = _contracts(db, [])
                counts = build_knowledge_index(db, contracts, get_ai_provider())
            db.commit()
            print(
                "Imported Department of Navy service bulk data: "
                f"{result.rows_matched}/{result.rows_seen} matching row(s), "
                f"{result.contracts_upserted} contract(s), "
                f"{result.source_records_upserted} source record(s), run {result.run_id}. "
                f"Knowledge index: {counts['nodes']} node(s), {counts['edges']} edge(s), "
                f"{counts['citations']} citation(s)."
            )
            return

        if command == "import-ecfr-title48-bulk":
            result = import_ecfr_title48_bulk(
                db,
                paths=_paths(args.paths),
                limit=args.limit or None,
            )
            db.commit()
            print(
                "Imported eCFR Title 48 bulk data: "
                f"{result.rows_matched}/{result.rows_seen} section(s), "
                f"{result.source_records_upserted} source record(s), run {result.run_id}."
            )
            return

        if command == "import-sam-opportunities-bulk":
            result = import_sam_opportunities_bulk(
                db,
                paths=_paths(args.paths),
                limit=args.limit or None,
            )
            db.commit()
            print(
                "Imported SAM.gov public opportunity bulk data: "
                f"{result.rows_matched}/{result.rows_seen} Department of Navy service notice(s), "
                f"{result.source_records_upserted} source record(s), run {result.run_id}."
            )
            return

        if command == "import-federal-register-bulk":
            result = import_federal_register_bulk(
                db,
                paths=_paths(args.paths),
                limit=args.limit or None,
            )
            db.commit()
            print(
                "Imported Federal Register bulk data: "
                f"{result.rows_matched}/{result.rows_seen} acquisition-relevant document(s), "
                f"{result.source_records_upserted} source record(s), run {result.run_id}."
            )
            return

        if command == "export-claude":
            output_dir = Path(args.output_dir)
            counts = _export_claude_packet(db, output_dir, args.limit)
            print(
                f"Exported Claude knowledge packet to {output_dir}: "
                f"{counts['contracts']} contract(s), {counts['sources']} source record(s)."
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


def _paths(value: str):
    from pathlib import Path

    return [Path(item) for item in _csv(value)]


def _contracts(db, contract_ids: List[str]) -> List[Contract]:
    statement = select(Contract)
    if contract_ids:
        statement = statement.where(Contract.id.in_(contract_ids))
    return list(db.scalars(statement.order_by(Contract.updated_at.desc())).all())


def _export_claude_packet(db, output_dir: Path, limit: int) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    contracts = _contracts(db, [])[:limit]
    sources = list(
        db.scalars(
            select(KnowledgeSourceRecord).order_by(KnowledgeSourceRecord.updated_at.desc()).limit(limit)
        ).all()
    )
    _write_jsonl(
        output_dir / "contracts.jsonl",
        [
            {
                "id": item.id,
                "contract_number": item.contract_number,
                "title": item.title,
                "description": item.description,
                "agency_name": item.agency_name,
                "office_name": item.office_name,
                "vendor_name": item.vendor_name,
                "vendor_uei": item.vendor_uei,
                "naics_code": item.naics_code,
                "psc_code": item.psc_code,
                "period_start": str(item.period_start) if item.period_start else None,
                "period_end": str(item.period_end) if item.period_end else None,
                "metadata_json": item.metadata_json,
            }
            for item in contracts
        ],
    )
    _write_jsonl(
        output_dir / "source_records.jsonl",
        [
            {
                "id": item.id,
                "source_name": item.source_name,
                "source_type": item.source_type,
                "source_key": item.source_key,
                "status": item.status,
                "title": item.title,
                "text": item.text,
                "url": item.url,
                "contract_id": item.contract_id,
                "vendor_uei": item.vendor_uei,
                "metadata_json": item.metadata_json,
            }
            for item in sources
        ],
    )
    (output_dir / "instructions.md").write_text(
        """
# Claude Knowledge Build Instructions

Build a compact, citation-aware Department of Navy service-contract knowledge base from
the JSONL files in this directory.

Inputs:
- `contracts.jsonl`: sanitized contract records from local bulk imports.
- `source_records.jsonl`: sanitized official bulk source records.

Write:
- `knowledge_base.md`: analyst-readable summary grouped by PSC service family,
  command/office, vendor, NAICS, competition/set-aside, dollar value, and performance
  evidence availability.
- `knowledge_base.json`: structured facts, labels, and source ids suitable for later
  database import.

Rules:
- Use only the files in this directory.
- Do not call live data APIs.
- Do not use or request API keys.
- Keep CPARS/IPMDAR marked absent unless an authorized local import source exists.
- Treat uploaded contract/report evidence as authoritative over public bulk metadata.
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return {"contracts": len(contracts), "sources": len(sources)}


def _write_jsonl(path: Path, rows: List[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
