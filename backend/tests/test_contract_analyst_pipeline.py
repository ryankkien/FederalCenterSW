import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.blob_storage import get_blob_storage
from app.contract_analysis import (
    classify_document,
    create_external_source_ref,
    detect_regression_findings,
    handle_cpars_document,
    handle_gao_oig_report_document,
    handle_modification_document,
    refresh_hypothesis_status,
    seed_contract_from_markdown,
    update_contract_baseline_from_document,
    update_semantic_links,
    upsert_hypothesis_from_finding,
)
from app.contract_matching import ContractMatchContext, match_contract
from app.database import Base, get_db
from app.main import app
from app.models import (
    AuditEvent,
    BaselineObligation,
    BaselineRevision,
    Contract,
    ContractAccessGrant,
    ContractHypothesis,
    ContractPrimitiveDecision,
    ContractSimilarityLink,
    CparsRating,
    DocumentClassificationDecision,
    DocumentEntity,
    DocumentMatchDecision,
    DocumentProcessingJob,
    DocumentPage,
    DocumentReportFact,
    DocumentSemanticLink,
    DocumentUpload,
    HypothesisEvidence,
    ProcessingRun,
    ProcessingRunStep,
)
from app.feature_extractor_client import FeatureExtractorStepResult
from app.synthetic_corpus import SYNTHETIC_DOCUMENTS


class FakeBlobStorage:
    def __init__(self) -> None:
        self.files: Dict[str, bytes] = {}

    def upload_bytes(self, path: str, data: bytes, content_type: str) -> None:
        self.files[path] = data

    def download_bytes(self, path: str) -> bytes:
        return self.files[path]

    def create_read_url(self, path: str, expires_in_minutes: int = 15) -> str:
        return f"https://storage.example.test/{path}?expires={expires_in_minutes}"


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Generator[None, None, None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_natalie_pdf_filenames_hard_link_to_correct_contracts() -> None:
    contracts = [
        {"id": "atlantic", "contract_number": "N40080-24-D-1042"},
        {"id": "beacon", "contract_number": "N40080-25-D-2087"},
        {"id": "cardinal", "contract_number": "N40080-23-D-3155"},
        {"id": "meridian", "contract_number": "N40080-22-D-4221"},
        {"id": "solstice", "contract_number": "N40080-25-D-5318"},
    ]

    for path in Path("testdocs/natalies/reports_pdf").glob("*.pdf"):
        result = match_contract(contracts, ContractMatchContext(filename=path.name))

        assert result.status == "matched"
        assert result.source == "deterministic"
        assert result.matched_contract_number in path.name


def test_ambiguous_and_missing_contract_documents_remain_unmatched_or_reviewable() -> None:
    contracts = [
        {"id": "atlantic", "contract_number": "N40080-24-D-1042"},
        {"id": "beacon", "contract_number": "N40080-25-D-2087"},
    ]

    ambiguous = match_contract(
        contracts,
        ContractMatchContext(text="Refs N40080-24-D-1042 and N40080-25-D-2087 both appear."),
    )
    unmatched = match_contract(contracts, ContractMatchContext(filename="no-contract-report.pdf"))

    assert ambiguous.status == "ambiguous"
    assert unmatched.status == "unmatched"


def test_baseline_extraction_for_wwr_source_and_natalie_markdown_seed(tmp_path) -> None:
    with next(_test_db_session(tmp_path)) as db:
        wwr = _contract(id="wwr", number="M0026426R0001", title="WWR Support")
        db.add(wwr)
        db.flush()
        document = _document(
            id="wwr-rfp",
            contract_id="wwr",
            filename="D.1+RFP+M0026426R0001 (2).pdf",
            title="WWR Source RFP",
            kind="source_contract",
        )
        db.add(document)
        db.flush()

        baseline = update_contract_baseline_from_document(
            db,
            "wwr",
            document,
            (
                "PWS Section 3.2 requires outreach and resource support services. "
                "CDRL A001 requires Monthly Status Report submission. "
                "All direction must be issued in writing by the COR. "
                "Period of Performance begins March 2027."
            ),
            [],
        )
        natalie = seed_contract_from_markdown(
            db,
            Path("testdocs/natalies/reports_markdown/contract_1_atlantic_environmental.md").read_text(),
            source_name="contract_1_atlantic_environmental.md",
        )

        obligations = db.scalars(
            select(BaselineObligation).where(BaselineObligation.contract_id == "wwr")
        ).all()
        obligation_types = {item.obligation_type for item in obligations}
        revision_number = baseline.current_revision_number
        natalie_number = natalie.contract_number if natalie is not None else None
        natalie_title = natalie.title if natalie is not None else ""
        db.commit()

    assert revision_number == 1
    assert obligation_types >= {"scope", "reporting_cadence", "authority_rule"}
    assert natalie_number == "N40080-24-D-1042"
    assert "Environmental Compliance" in natalie_title


def test_regression_detection_finds_scope_rfi_schedule_and_skips_funding_only_mod(tmp_path) -> None:
    with next(_test_db_session(tmp_path)) as db:
        db.add(_contract(id="atlantic", number="N40080-24-D-1042"))
        document = _document(id="report-1", contract_id="atlantic", filename="N40080-24-D-1042_WSR-002.pdf")
        db.add(document)
        db.flush()

        findings = detect_regression_findings(
            db,
            "atlantic",
            document,
            (
                "LCDR Reyes provided informal verbal direction to add two tanks. "
                "RFI-004 has been 21 days open and is on the critical path, creating schedule risk. "
                "Cost variance from unbudgeted effort is emerging."
            ),
            [],
            document_kind="weekly_report",
        )
        mod = _document(id="mod-1", contract_id="atlantic", filename="P00002 funding modification.pdf")
        db.add(mod)
        classify_document(mod, "This modification is funding only and obligates funds.")
        skipped = detect_regression_findings(
            db,
            "atlantic",
            mod,
            "This modification is funding only and obligates funds.",
            [],
            document_kind="modification",
            modification_kind="funding_only",
        )

    assert {finding.finding_type for finding in findings} >= {
        "scope_drift",
        "missing_government_action",
        "schedule_regression",
        "cost_regression",
    }
    assert skipped == []


def test_cpars_handler_extracts_factor_ratings_from_synthetic_narrative(tmp_path) -> None:
    synthetic = next(item for item in SYNTHETIC_DOCUMENTS if item.document_kind == "cpars_evaluation")
    with next(_test_db_session(tmp_path)) as db:
        db.add(_contract(id="wwr", number="M0026426R0001", title="WWR Support"))
        document = _document(
            id="cpars-1",
            contract_id="wwr",
            filename=synthetic.filename,
            title=synthetic.title,
            kind=synthetic.document_kind,
        )
        db.add(document)
        db.flush()

        kind, _ = classify_document(document, synthetic.text)
        rows = handle_cpars_document(db, "wwr", document, synthetic.text)

        persisted = db.scalars(select(CparsRating).where(CparsRating.doc_upload_id == "cpars-1")).all()

    assert kind == "cpars"
    assert len(rows) == 1
    assert len(persisted) == 1
    assert persisted[0].quality_rating == "Very Good"
    assert persisted[0].schedule_rating == "Satisfactory"
    assert persisted[0].management_rating == "Very Good"
    assert persisted[0].evaluation_period == "01 August 2027 - 31 January 2028"


def test_modification_handler_persists_decision_and_baseline_revision(tmp_path) -> None:
    text = (
        "Modification P00001 executed 18 July 2027 and effective 28 July 2027. "
        "The Contracting Officer added one NMCM labor position to address caseload surge. "
        "The action increases contract value by $125,000 and extends the period of performance by 30 days."
    )
    with next(_test_db_session(tmp_path)) as db:
        db.add(_contract(id="wwr", number="M0026426R0001", title="WWR Support"))
        document = _document(
            id="mod-doc",
            contract_id="wwr",
            filename="M0026426R0001_P00001.pdf",
            title="Modification P00001",
            kind="modification",
        )
        db.add(document)
        db.flush()

        rows = handle_modification_document(db, "wwr", document, text, [])
        decisions = db.scalars(select(ContractPrimitiveDecision)).all()
        revisions = db.scalars(
            select(BaselineRevision).where(BaselineRevision.change_type == "modification")
        ).all()

    assert len(rows) == 1
    assert decisions[0].mod_number == "P00001"
    assert float(decisions[0].value_change) == 125000.0
    assert decisions[0].pop_change_days == 30
    assert decisions[0].decision_date.isoformat() == "2027-07-28"
    assert len(revisions) == 1
    assert revisions[0].metadata_json["mod_number"] == "P00001"


def test_gao_oig_handler_stores_official_external_refs(tmp_path) -> None:
    text = (
        "GAO report GAO-26-100 found recurring schedule oversight weaknesses on the contract. "
        "Recommendation: Navy should document corrective action ownership. "
        "Source: https://www.gao.gov/products/gao-26-100"
    )
    with next(_test_db_session(tmp_path)) as db:
        db.add(_contract(id="atlantic", number="N40080-24-D-1042"))
        document = _document(
            id="gao-doc",
            contract_id="atlantic",
            filename="GAO-26-100.pdf",
            title="GAO Contract Oversight Report",
            kind="gao_oig_report",
        )
        db.add(document)
        db.flush()

        rows = handle_gao_oig_report_document(db, "atlantic", document, text)

    assert rows
    assert {row.source_type for row in rows} == {"gao_oig_report"}
    assert all(row.source_domain == "www.gao.gov" for row in rows)
    assert all(row.metadata_json["source_document_upload_id"] == "gao-doc" for row in rows)


def test_hypotheses_are_deduped_evidence_linked_and_can_be_contradicted(tmp_path) -> None:
    with next(_test_db_session(tmp_path)) as db:
        db.add(_contract(id="cardinal", number="N40080-23-D-3155"))
        doc1 = _document(id="report-53", contract_id="cardinal", filename="N40080-23-D-3155_WSR-053.pdf")
        doc2 = _document(id="report-54", contract_id="cardinal", filename="N40080-23-D-3155_WSR-054.pdf")
        db.add_all([doc1, doc2])
        db.flush()

        for document in (doc1, doc2):
            findings = detect_regression_findings(
                db,
                "cardinal",
                document,
                "Tenant command verbal direction requires COR direction and may be out-of-scope.",
                [],
                document_kind="weekly_report",
            )
            for finding in findings:
                upsert_hypothesis_from_finding(db, finding)
        hypothesis = db.scalars(select(ContractHypothesis)).one()
        evidence = db.scalars(
            select(HypothesisEvidence).where(HypothesisEvidence.hypothesis_id == hypothesis.id)
        ).all()

        db.add(
            HypothesisEvidence(
                id=str(uuid4()),
                hypothesis_id=hypothesis.id,
                evidence_type="contradicting",
                document_upload_id=doc2.id,
                summary="Later COR direction confirms the work is authorized.",
                confidence=0.8,
            )
        )
        db.add(
            HypothesisEvidence(
                id=str(uuid4()),
                hypothesis_id=hypothesis.id,
                evidence_type="contradicting",
                document_upload_id=doc2.id,
                summary="Task order mod separately authorizes the work.",
                confidence=0.8,
            )
        )
        db.flush()
        refresh_hypothesis_status(db, hypothesis)

    assert hypothesis.status == "contradicted"
    assert len(evidence) >= 1
    assert all(item.document_upload_id for item in evidence)


def test_semantic_links_do_not_change_document_hard_parent(tmp_path) -> None:
    with next(_test_db_session(tmp_path)) as db:
        db.add_all(
            [
                _contract(id="cardinal", number="N40080-23-D-3155"),
                _contract(id="meridian", number="N40080-22-D-4221"),
            ]
        )
        doc1 = _document(id="cardinal-report", contract_id="cardinal", filename="N40080-23-D-3155_WSR-054.pdf")
        doc2 = _document(id="meridian-report", contract_id="meridian", filename="N40080-22-D-4221_WSR-106.pdf")
        db.add_all([doc1, doc2])
        db.flush()
        for contract_id, document in (("cardinal", doc1), ("meridian", doc2)):
            finding = detect_regression_findings(
                db,
                contract_id,
                document,
                "Aging RFI is 28 days open and tenant command verbal direction requires COR approval.",
                [],
                document_kind="weekly_report",
            )[0]
            upsert_hypothesis_from_finding(db, finding)
        update_semantic_links(db)
        db.commit()

        db.refresh(doc1)
        db.refresh(doc2)
        contract_link_count = len(db.scalars(select(ContractSimilarityLink)).all())
        document_link_count = len(db.scalars(select(DocumentSemanticLink)).all())

    assert contract_link_count >= 1
    assert document_link_count >= 1
    assert doc1.contract_id == "cardinal"
    assert doc2.contract_id == "meridian"


def test_external_research_accepts_only_official_sources(tmp_path) -> None:
    with next(_test_db_session(tmp_path)) as db:
        db.add(_contract(id="atlantic", number="N40080-24-D-1042"))
        official = create_external_source_ref(
            db,
            "https://www.acquisition.gov/far/part-43",
            contract_id="atlantic",
            title="FAR Part 43",
        )

        with pytest.raises(ValueError):
            create_external_source_ref(db, "https://example.com/blog/far-summary", contract_id="atlantic")

    assert official.source_domain == "www.acquisition.gov"
    assert official.is_official is True


def test_processing_job_run_and_analysis_apis_are_contract_scoped(tmp_path, monkeypatch) -> None:
    fake_storage = FakeBlobStorage()
    client = _client_with_test_dependencies(tmp_path, fake_storage)
    official_token = _token(client, "official")
    contractor_token = _token(client, "contractor")
    monkeypatch.delenv("AI_PROCESSING_ENABLED", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    feature_calls = []

    def fake_trigger_feature_extractor(
        document_id: str,
        contract_id: str,
        doc_classification: str,
        processing_run_id=None,
    ):
        feature_calls.append((document_id, contract_id, doc_classification))
        return [
            FeatureExtractorStepResult(
                step_name="feature_extractor.summary",
                event_type="feature_extractor.summary",
                status="success",
                metadata={"blob_path": f"contracts/{document_id}/summary.json"},
            ),
            FeatureExtractorStepResult(
                step_name="feature_extractor.primitives",
                event_type="feature_extractor.primitives",
                status="failed",
                message="extractor unavailable",
                metadata={"endpoint": "/extract-primitives"},
            ),
        ]

    monkeypatch.setattr("app.processing.trigger_feature_extractor", fake_trigger_feature_extractor)

    text = (
        "Weekly Status Report for contract N40080-24-D-1042. "
        "LCDR Reyes provided informal verbal direction to add two USTs pending COR confirmation. "
        "RFI-004 is 21 days open and affects the critical path causing schedule risk."
    )
    with next(_test_db_session(tmp_path)) as db:
        db.add(_contract(id="atlantic", number="N40080-24-D-1042"))
        db.add(_contract(id="hidden", number="N40080-99-D-9999"))
        db.add(
            ContractAccessGrant(
                id="grant-atlantic",
                contract_id="atlantic",
                principal_id="official-demo",
                role="viewer",
            )
        )
        document = _document(
            id="job-doc",
            contract_id=None,
            filename="N40080-24-D-1042_WSR-002.pdf",
            uploader_id="other-contractor",
        )
        db.add(document)
        db.add(
            DocumentProcessingJob(
                id="job-1",
                document_upload_id="job-doc",
                job_type="document_analysis",
                status="queued",
            )
        )
        db.commit()
    fake_storage.upload_bytes(
        "contracts/job-doc/text.json",
        json.dumps(
            {
                "document_id": "job-doc",
                "original_filename": "N40080-24-D-1042_WSR-002.pdf",
                "stored_filename": "main.pdf",
                "content_type": "application/pdf",
                "source": "portal",
                "text": text,
                "extraction_status": "extracted",
            }
        ).encode("utf-8"),
        "application/json",
    )

    run = client.post(
        "/api/processing/jobs/job-1/run",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    regressions = client.get(
        "/api/contracts/atlantic/regressions",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    hypotheses = client.get(
        "/api/contracts/atlantic/hypotheses",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    relationships = client.get(
        "/api/documents/job-doc/relationships",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    hidden = client.get(
        "/api/contracts/hidden/regressions",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    contractor_hidden = client.get(
        "/api/contracts/atlantic/regressions",
        headers={"Authorization": f"Bearer {contractor_token}"},
    )
    contractor_hypotheses = client.get(
        "/api/contracts/atlantic/hypotheses",
        headers={"Authorization": f"Bearer {contractor_token}"},
    )
    contractor_query = client.post(
        "/api/agent/query",
        headers={"Authorization": f"Bearer {contractor_token}"},
        json={"contract_id": "atlantic", "question": "What changed?"},
    )
    with next(_test_db_session(tmp_path)) as db:
        persisted_pages = db.scalars(
            select(DocumentPage).where(DocumentPage.document_upload_id == "job-doc")
        ).all()
        persisted_decisions = db.scalars(
            select(DocumentClassificationDecision).where(
                DocumentClassificationDecision.document_upload_id == "job-doc"
            )
        ).all()
        persisted_entities = db.scalars(
            select(DocumentEntity).where(DocumentEntity.document_upload_id == "job-doc")
        ).all()
        persisted_facts = db.scalars(
            select(DocumentReportFact).where(DocumentReportFact.document_upload_id == "job-doc")
        ).all()
        persisted_runs = db.scalars(
            select(ProcessingRun).where(ProcessingRun.document_upload_id == "job-doc")
        ).all()
        persisted_steps = db.scalars(
            select(ProcessingRunStep).where(ProcessingRunStep.document_upload_id == "job-doc")
        ).all()
        persisted_audit_events = db.scalars(
            select(AuditEvent).where(AuditEvent.document_upload_id == "job-doc")
        ).all()

    assert run.status_code == 200
    assert run.json()["matched_contract_id"] == "atlantic"
    assert regressions.status_code == 200
    assert {item["finding_type"] for item in regressions.json()} >= {
        "scope_drift",
        "missing_government_action",
    }
    assert hypotheses.status_code == 200
    assert hypotheses.json()[0]["evidence"]
    assert relationships.status_code == 200
    assert relationships.json()["hard_parent_contract_id"] == "atlantic"
    assert hidden.status_code == 404
    assert contractor_hidden.status_code == 404
    assert contractor_hypotheses.status_code == 404
    assert contractor_query.status_code == 404
    assert len(persisted_pages) == 1
    assert persisted_pages[0].page_number == 1
    assert persisted_decisions[0].document_kind == "weekly_report"
    assert {entity.entity_type for entity in persisted_entities} >= {"contract_number", "rfi"}
    assert {fact.fact_type for fact in persisted_facts} >= {"rfi_age", "schedule_signal"}
    assert persisted_runs[0].status == "completed"
    assert feature_calls == [("job-doc", "atlantic", "weekly_report")]
    step_statuses = {step.step_name: step.status for step in persisted_steps}
    assert {"extraction", "matching", "analysis"}.issubset(step_statuses)
    assert step_statuses["feature_extractor.summary"] == "success"
    assert step_statuses["feature_extractor.primitives"] == "failed"
    assert {event.event_type for event in persisted_audit_events} >= {
        "feature_extractor.summary",
        "feature_extractor.primitives",
    }


def test_processing_auto_scaffolds_unmatched_source_contract(tmp_path, monkeypatch) -> None:
    fake_storage = FakeBlobStorage()
    client = _client_with_test_dependencies(tmp_path, fake_storage)
    official_token = _token(client, "official")
    monkeypatch.delenv("AI_PROCESSING_ENABLED", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    text = """
Source Contract
Contract Number: N40080-26-C-1001
Contract Title: Harbor Facilities Maintenance Support
Agency: Department of the Navy
Contractor: Tidewater Facilities LLC

The PWS defines inspection, maintenance, and reporting requirements.
"""
    with next(_test_db_session(tmp_path)) as db:
        db.add(_contract(id="hidden", number="N40080-99-D-9999"))
        db.add(
            ContractAccessGrant(
                id="grant-hidden",
                contract_id="hidden",
                principal_id="official-demo",
                role="viewer",
            )
        )
        db.add(
            _document(
                id="source-doc",
                contract_id=None,
                filename="N40080-26-C-1001_source_contract.pdf",
                title="Harbor source contract",
                kind="email_context",
                uploader_id="contractor-demo",
            )
        )
        db.add(
            DocumentProcessingJob(
                id="source-job",
                document_upload_id="source-doc",
                job_type="document_analysis",
                status="queued",
            )
        )
        db.commit()
    fake_storage.upload_bytes(
        "contracts/source-doc/text.json",
        json.dumps(
            {
                "document_id": "source-doc",
                "original_filename": "N40080-26-C-1001_source_contract.pdf",
                "stored_filename": "main.pdf",
                "content_type": "application/pdf",
                "source": "email",
                "text": text,
                "extraction_status": "extracted",
            }
        ).encode("utf-8"),
        "application/json",
    )

    run = client.post(
        "/api/processing/jobs/source-job/run",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    contracts = client.get("/api/contracts", headers={"Authorization": f"Bearer {official_token}"})

    with next(_test_db_session(tmp_path)) as db:
        created = db.scalars(
            select(Contract).where(Contract.contract_number == "N40080-26-C-1001")
        ).one()
        document = db.get(DocumentUpload, "source-doc")
        audit = db.scalars(
            select(AuditEvent).where(AuditEvent.event_type == "contract.auto_created")
        ).one()
        match_decision = db.scalars(
            select(DocumentMatchDecision).where(DocumentMatchDecision.document_upload_id == "source-doc")
        ).one()
        classification = db.scalars(
            select(DocumentClassificationDecision).where(
                DocumentClassificationDecision.document_upload_id == "source-doc"
            )
        ).one()

    assert run.status_code == 200
    assert run.json()["matched_contract_id"] == created.id
    assert contracts.status_code == 200
    assert created.id in {item["id"] for item in contracts.json()}
    assert created.title == "Harbor Facilities Maintenance Support"
    assert created.agency_name == "Department of the Navy"
    assert created.vendor_name == "Tidewater Facilities LLC"
    assert created.status == "pending_review"
    assert created.metadata_json["auto_created"] is True
    assert document.contract_id == created.id
    assert document.match_status == "matched"
    assert audit.contract_id == created.id
    assert audit.document_upload_id == "source-doc"
    assert match_decision.decision_source == "auto_scaffold"
    assert classification.document_kind == "source_contract"
    assert classification.confidence >= 0.85


def _client_with_test_dependencies(tmp_path, fake_storage: FakeBlobStorage) -> TestClient:
    app.dependency_overrides.clear()

    def override_get_db() -> Generator[Session, None, None]:
        yield from _test_db_session(tmp_path)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_blob_storage] = lambda: fake_storage
    return TestClient(app)


def _test_db_session(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'contract-analyst.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def _token(client: TestClient, role: str) -> str:
    response = client.post("/api/auth/mock-login", json={"role": role})
    assert response.status_code == 200
    return response.json()["access_token"]


def _contract(id: str, number: str, title: str = "Fixture Contract") -> Contract:
    return Contract(id=id, contract_number=number, title=title)


def _document(
    id: str,
    filename: str,
    contract_id: str = "atlantic",
    title: str = "Weekly Status Report",
    kind: str = "weekly_report",
    uploader_id: str = "contractor-demo",
) -> DocumentUpload:
    return DocumentUpload(
        id=id,
        contract_id=contract_id,
        title=title,
        document_type="Weekly Status Report",
        document_kind=kind,
        intake_source="portal",
        original_filename=filename,
        content_type="application/pdf",
        size_bytes=5,
        blob_path=f"contracts/{id}/main.pdf",
        text_blob_path=f"contracts/{id}/text.json",
        match_status="matched" if contract_id else "pending",
        processing_status="queued",
        uploader_id=uploader_id,
        uploader_role="contractor",
        created_at=datetime.now(timezone.utc),
    )
