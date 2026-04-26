from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.blob_storage import get_blob_storage
from app.contract_analysis import seed_contract_from_markdown
from app.database import SessionLocal, create_db_schema
from app.document_assets import store_contract_document
from app.models import (
    AuditEvent,
    BaselineObligation,
    BaselineRevision,
    ChunkEmbedding,
    Contract,
    ContractAccessGrant,
    ContractBaseline,
    ContractHypothesis,
    ContractSimilarityLink,
    ContractTopic,
    ContractTopicRevision,
    DocumentChunk,
    DocumentClassificationDecision,
    DocumentEntity,
    DocumentMatchDecision,
    DocumentPage,
    DocumentProcessingJob,
    DocumentReportFact,
    DocumentSemanticLink,
    DocumentUpload,
    ExternalSourceRef,
    HypothesisEvidence,
    InvestigationRun,
    PerformanceSignal,
    ProcessingRun,
    ProcessingRunStep,
    RegressionFinding,
    TopicEvidence,
    TopicLink,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "testdocs"


def seed_fixtures(fixture_names: Sequence[str], reset_analysis: bool = False) -> List[str]:
    create_db_schema()
    storage = get_blob_storage()
    seeded: List[str] = []
    with SessionLocal() as session:
        names = _expand_fixture_names(fixture_names)
        contracts = []
        if "wwr" in names:
            contracts.extend(_seed_wwr(session, storage))
        if "agor" in names:
            contracts.extend(_seed_agor(session, storage))
        if "natalie" in names:
            contracts.extend(_seed_natalie(session, storage))
        if reset_analysis:
            _reset_analysis(session, [contract.id for contract in contracts])
        for contract in contracts:
            _grant_demo_access(session, contract)
        session.commit()
        seeded = sorted({contract.contract_number for contract in contracts})
    return seeded


def _seed_wwr(session: Session, storage) -> List[Contract]:
    contract = _upsert_contract(
        session,
        contract_id="M0026426R0001",
        contract_number="M0026426R0001",
        title="Sergeant Merlin German Wounded Warrior Outreach and Resource Support Services",
        agency_name="United States Marine Corps",
        office_name="RCO Quantico",
        vendor_name="WWR Fixture Contractor",
        metadata_json={"fixture": "wwr"},
    )
    source = FIXTURE_ROOT / "WWR" / "contract" / "D.1+RFP+M0026426R0001 (2).pdf"
    _seed_document(session, storage, source, contract, "source_contract", "fixture")
    for path in sorted((FIXTURE_ROOT / "WWR").glob("*.pdf")):
        _seed_document(session, storage, path, contract, "monthly_report", "fixture")
    return [contract]


def _seed_agor(session: Session, storage) -> List[Contract]:
    contract = _upsert_contract(
        session,
        contract_id="N00014-12-C-0305",
        contract_number="N00014-12-C-0305",
        title="AGOR 28 Shipyard Representative Bi-Weekly Progress Reports",
        agency_name="Office of Naval Research",
        office_name="Shipyard Representative",
        vendor_name="Dakota Creek Industries",
        metadata_json={"fixture": "agor", "report_only": True},
    )
    for path in sorted((FIXTURE_ROOT / "agor").glob("*.pdf")):
        _seed_document(session, storage, path, contract, "biweekly_report", "fixture")
    return [contract]


def _seed_natalie(session: Session, storage) -> List[Contract]:
    contracts = []
    markdown_root = FIXTURE_ROOT / "natalies" / "reports_markdown"
    for path in sorted(markdown_root.glob("*.md")):
        contract = seed_contract_from_markdown(session, path.read_text(encoding="utf-8"), str(path))
        if contract is not None:
            contracts.append(contract)
            _grant_demo_access(session, contract)
    contract_by_number = {contract.contract_number: contract for contract in contracts}
    for path in sorted((FIXTURE_ROOT / "natalies" / "reports_pdf").glob("*.pdf")):
        contract_number = path.name.split("_", 1)[0]
        contract = contract_by_number.get(contract_number)
        if contract is not None:
            _seed_document(session, storage, path, contract, "weekly_report", "fixture")
    return contracts


def _seed_document(
    session: Session,
    storage,
    path: Path,
    contract: Contract,
    document_kind: str,
    intake_source: str,
) -> DocumentUpload:
    data = path.read_bytes()
    source_hash = hashlib.sha256(data).hexdigest()
    document_id = str(uuid5(NAMESPACE_URL, f"{path.as_posix()}:{source_hash}"))
    existing = session.get(DocumentUpload, document_id)
    if existing is not None:
        if existing.contract_id != contract.id:
            existing.contract_id = contract.id
        _ensure_processing_job(session, existing.id)
        return existing

    stored = store_contract_document(
        storage=storage,
        document_id=document_id,
        original_filename=path.name,
        content_type="application/pdf",
        data=data,
        source=intake_source,
    )
    document = DocumentUpload(
        id=document_id,
        contract_id=contract.id,
        title=path.stem.replace("_", " "),
        document_type=document_kind.replace("_", " ").title(),
        document_kind=document_kind,
        intake_source=intake_source,
        notes=f"Seeded from {path.relative_to(ROOT)}",
        original_filename=path.name,
        content_type=stored.content_type,
        size_bytes=len(data),
        blob_path=stored.blob_path,
        text_blob_path=stored.text_blob_path,
        source_sha256=source_hash,
        match_status="matched",
        processing_status="queued",
        uploader_id="fixture-seed",
        uploader_role="official",
        created_at=datetime.now(timezone.utc),
    )
    session.add(document)
    _ensure_processing_job(session, document.id)
    return document


def _upsert_contract(
    session: Session,
    contract_id: str,
    contract_number: str,
    title: str,
    agency_name: str,
    office_name: str,
    vendor_name: str,
    metadata_json: dict,
) -> Contract:
    contract = session.get(Contract, contract_id)
    if contract is None:
        contract = Contract(
            id=contract_id,
            contract_number=contract_number,
            title=title,
            agency_name=agency_name,
            office_name=office_name,
            vendor_name=vendor_name,
            metadata_json=metadata_json,
        )
        session.add(contract)
        session.flush()
    else:
        contract.title = title
        contract.agency_name = agency_name
        contract.office_name = office_name
        contract.vendor_name = vendor_name
        contract.metadata_json = {**(contract.metadata_json or {}), **metadata_json}
    return contract


def _grant_demo_access(session: Session, contract: Contract) -> None:
    for principal_id, principal_type, role in (
        ("official-demo", "user", "official"),
        ("contractor-demo", "user", "contractor"),
        ("official", "group", "official"),
    ):
        pending = any(
            isinstance(row, ContractAccessGrant)
            and row.contract_id == contract.id
            and row.principal_id == principal_id
            and row.role == role
            for row in session.new
        )
        if pending:
            continue
        existing = session.scalars(
            select(ContractAccessGrant).where(
                ContractAccessGrant.contract_id == contract.id,
                ContractAccessGrant.principal_id == principal_id,
                ContractAccessGrant.role == role,
            )
        ).first()
        if existing is None:
            session.add(
                ContractAccessGrant(
                    id=str(uuid5(NAMESPACE_URL, f"grant:{contract.id}:{principal_id}:{role}")),
                    contract_id=contract.id,
                    principal_id=principal_id,
                    principal_type=principal_type,
                    role=role,
                    granted_by_id="fixture-seed",
                )
            )


def _ensure_processing_job(session: Session, document_id: str) -> None:
    existing = session.scalars(
        select(DocumentProcessingJob).where(
            DocumentProcessingJob.document_upload_id == document_id,
            DocumentProcessingJob.status.in_(("queued", "processing")),
        )
    ).first()
    if existing is None:
        session.add(
            DocumentProcessingJob(
                id=str(uuid5(NAMESPACE_URL, f"processing:{document_id}")),
                document_upload_id=document_id,
                job_type="document_analysis",
                status="queued",
                metadata_json={"source": "fixture_seed"},
            )
        )


def _reset_analysis(session: Session, contract_ids: Iterable[str]) -> None:
    contract_ids = list(contract_ids)
    document_ids = list(
        session.scalars(
            select(DocumentUpload.id).where(DocumentUpload.contract_id.in_(contract_ids))
        ).all()
    )
    if not document_ids:
        return
    session.execute(
        delete(DocumentSemanticLink).where(
            DocumentSemanticLink.source_document_upload_id.in_(document_ids)
            | DocumentSemanticLink.target_document_upload_id.in_(document_ids)
        )
    )
    chunk_ids = list(
        session.scalars(select(DocumentChunk.id).where(DocumentChunk.document_upload_id.in_(document_ids))).all()
    )
    topic_ids = list(
        session.scalars(select(ContractTopic.id).where(ContractTopic.contract_id.in_(contract_ids))).all()
    )
    if topic_ids:
        session.execute(delete(TopicEvidence).where(TopicEvidence.topic_id.in_(topic_ids)))
        session.execute(
            delete(TopicLink).where(
                TopicLink.source_topic_id.in_(topic_ids) | TopicLink.target_topic_id.in_(topic_ids)
            )
        )
        session.execute(delete(ContractTopicRevision).where(ContractTopicRevision.topic_id.in_(topic_ids)))
        session.execute(delete(ContractTopic).where(ContractTopic.id.in_(topic_ids)))
    if chunk_ids:
        session.execute(delete(ChunkEmbedding).where(ChunkEmbedding.chunk_id.in_(chunk_ids)))
    for model in (
        HypothesisEvidence,
        ContractHypothesis,
        ExternalSourceRef,
        InvestigationRun,
        RegressionFinding,
        BaselineRevision,
        BaselineObligation,
        ContractBaseline,
        ContractSimilarityLink,
        PerformanceSignal,
        DocumentReportFact,
        DocumentEntity,
        DocumentClassificationDecision,
        DocumentChunk,
        DocumentPage,
        ProcessingRunStep,
        ProcessingRun,
        DocumentMatchDecision,
        AuditEvent,
    ):
        if hasattr(model, "document_upload_id"):
            session.execute(delete(model).where(model.document_upload_id.in_(document_ids)))
        elif hasattr(model, "contract_id"):
            session.execute(delete(model).where(model.contract_id.in_(contract_ids)))
    session.execute(delete(DocumentProcessingJob).where(DocumentProcessingJob.document_upload_id.in_(document_ids)))
    for document_id in document_ids:
        _ensure_processing_job(session, document_id)
    session.execute(
        delete(ContractSimilarityLink).where(
            ContractSimilarityLink.source_contract_id.in_(contract_ids)
            | ContractSimilarityLink.target_contract_id.in_(contract_ids)
        )
    )
    for document in session.scalars(
        select(DocumentUpload).where(DocumentUpload.id.in_(document_ids))
    ).all():
        document.processing_status = "queued"
        document.processing_error_code = None
        document.processing_error_message = None


def _expand_fixture_names(values: Sequence[str]) -> Set[str]:
    names = set()
    for value in values:
        names.update(part.strip().lower() for part in value.split(",") if part.strip())
    if not names or "all" in names:
        return {"wwr", "agor", "natalie"}
    return names


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Seed local contract analyst fixtures.")
    parser.add_argument("--fixtures", default="all", help="Fixture names: all, wwr, agor, natalie")
    parser.add_argument("--reset-analysis", action="store_true", help="Clear analysis rows for seeded documents")
    args = parser.parse_args(argv)
    seeded = seed_fixtures([args.fixtures], reset_analysis=args.reset_analysis)
    print(f"Seeded fixtures for {len(seeded)} contract(s): {', '.join(seeded)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
