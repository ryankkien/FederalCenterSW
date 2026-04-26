from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.document_assets import _extract_docx_text, _extract_pdf_text
from app.main import app
from app.models import (
    BaselineObligation,
    Contract,
    ContractAccessGrant,
    ContractBaseline,
    ContractPrimitiveDeliverable,
    ContractPrimitiveFinancial,
    ContractPrimitiveIssue,
    ContractPrimitivePersonnel,
    DocumentPage,
    DocumentProcessingJob,
    DocumentReportFact,
    DocumentUpload,
    PerformanceSignal,
    RegressionFinding,
)
from app.portfolio import run_portfolio_lessons_analysis
from app.primitive_backfill import backfill_contract_primitives


def test_contract_routes_include_official_fallback_and_agent_citations(tmp_path, monkeypatch) -> None:
    client = _client_with_test_db(tmp_path)
    contractor_token = _token(client, "contractor")
    official_token = _token(client, "official")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)

    with next(_test_db_session(tmp_path)) as db:
        db.add(_document(id="upload-1", uploader_id="contractor-demo"))
        db.commit()

    official_contracts = client.get(
        "/api/contracts",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    assert official_contracts.status_code == 200
    assert "upload-1" in {contract["id"] for contract in official_contracts.json()}

    contractor_contracts = client.get(
        "/api/contracts",
        headers={"Authorization": f"Bearer {contractor_token}"},
    )
    assert contractor_contracts.status_code == 200
    assert "upload-1" in {contract["id"] for contract in contractor_contracts.json()}

    topics = client.get(
        "/api/contracts/upload-1/topics",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    assert topics.status_code == 200
    assert topics.json()[0]["citations"][0]["document_id"] == "upload-1"

    query = client.post(
        "/api/agent/query",
        headers={"Authorization": f"Bearer {official_token}"},
        json={"contract_id": "upload-1", "question": "What is the status?"},
    )
    assert query.status_code == 200
    assert query.json()["citations"][0]["document_id"] == "upload-1"
    assert query.json()["generated"] is False

    generate = client.post(
        "/api/agent/query",
        headers={"Authorization": f"Bearer {official_token}"},
        json={"contract_id": "upload-1", "question": "What is the status?", "generate": True},
    )
    assert generate.status_code == 503

    pending = client.post(
        "/api/agent/query",
        headers={"Authorization": f"Bearer {official_token}"},
        json={
            "contract_id": "upload-1",
            "question": "What is the status?",
            "scope_status": "pending",
        },
    )
    assert pending.status_code == 409


def test_agent_draft_without_citations_returns_limitations(tmp_path) -> None:
    client = _client_with_test_db(tmp_path)
    official_token = _token(client, "official")

    draft = client.post(
        "/api/agent/drafts",
        headers={"Authorization": f"Bearer {official_token}"},
        json={"contract_id": "contract-demo-operations", "draft_type": "briefing"},
    )

    assert draft.status_code == 200
    body = draft.json()
    assert body["citations"] == []
    assert body["limitations"]
    assert "No citable draft text" in body["text"]


def test_contract_grants_limit_official_visibility_when_grants_exist(tmp_path) -> None:
    client = _client_with_test_db(tmp_path)
    official_token = _token(client, "official")

    with next(_test_db_session(tmp_path)) as db:
        db.add(
            Contract(
                id="contract-granted",
                contract_number="GS-001",
                title="Granted Contract",
            )
        )
        db.add(
            Contract(
                id="contract-ungranted",
                contract_number="GS-002",
                title="Ungranted Contract",
            )
        )
        db.add(
            ContractAccessGrant(
                id="grant-1",
                contract_id="contract-granted",
                principal_id="official-demo",
                role="viewer",
            )
        )
        db.add(_document(id="ungranted-upload", uploader_id="other-contractor"))
        db.commit()

    response = client.get("/api/contracts", headers={"Authorization": f"Bearer {official_token}"})

    assert response.status_code == 200
    contracts = {contract["id"]: contract for contract in response.json()}
    assert contracts["contract-granted"]["title"] == "Granted Contract"
    assert "contract-ungranted" not in contracts
    assert "ungranted-upload" not in contracts


def test_official_can_create_contract_record_for_portal(tmp_path) -> None:
    client = _client_with_test_db(tmp_path)
    official_token = _token(client, "official")
    contractor_token = _token(client, "contractor")

    response = client.post(
        "/api/contracts",
        headers={"Authorization": f"Bearer {official_token}"},
        json={
            "contract_number": "N00024-26-C-9001",
            "title": "Portal Logged Support Contract",
            "vendor_name": "Atlantic Logistics LLC",
            "psc_code": "R706",
            "naics_code": "541614",
            "office_name": "PMS 325",
            "period_start": "2026-01-01",
            "period_end": "2027-12-31",
            "obligated_value": "4210440",
            "contracting_officer": "LCDR Nicole Jacobs",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["contract_number"] == "N00024-26-C-9001"
    assert body["vendor_name"] == "Atlantic Logistics LLC"
    assert body["psc_code"] == "R706"
    assert body["obligated_value"] == "4210440"
    assert body["contracting_officer"] == "LCDR Nicole Jacobs"

    contracts = client.get("/api/contracts", headers={"Authorization": f"Bearer {official_token}"})
    assert body["id"] in {contract["id"] for contract in contracts.json()}

    contractor_response = client.post(
        "/api/contracts",
        headers={"Authorization": f"Bearer {contractor_token}"},
        json={"contract_number": "N00024-26-C-9002", "title": "Unauthorized"},
    )
    assert contractor_response.status_code == 403


def test_portfolio_themes_are_built_from_backend_evidence(tmp_path, monkeypatch) -> None:
    client = _client_with_test_db(tmp_path)
    official_token = _token(client, "official")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with next(_test_db_session(tmp_path)) as db:
        db.add_all(
            [
                Contract(
                    id="theme-c1",
                    contract_number="N00024-26-C-9101",
                    title="Logistics Support East",
                    psc_code="R706",
                    office_name="PMS 325",
                    vendor_name="Atlantic Logistics LLC",
                    metadata_json={"obligated_value": "1000000"},
                ),
                Contract(
                    id="theme-c2",
                    contract_number="N00024-26-C-9102",
                    title="Admin Support West",
                    psc_code="R408",
                    office_name="PMS 325",
                    vendor_name="Atlantic Logistics LLC",
                    metadata_json={"obligated_value": "2500000"},
                ),
                Contract(
                    id="theme-c3",
                    contract_number="N00024-26-C-9103",
                    title="Cyber Support",
                    psc_code="D310",
                    office_name="NAVWAR",
                    metadata_json={"obligated_value": "4000000"},
                ),
                RegressionFinding(
                    id="finding-1",
                    contract_id="theme-c1",
                    finding_type="schedule_regression",
                    title="Weekly CDRL report filed late",
                    summary="The report slipped by 5 days against the required cadence.",
                    severity="high",
                    status="open",
                ),
                PerformanceSignal(
                    id="signal-1",
                    contract_id="theme-c2",
                    signal_type="schedule",
                    label="Deliverable slip",
                    summary="Monthly deliverable was late and pushed downstream review dates.",
                    severity="medium",
                ),
                DocumentReportFact(
                    id="fact-1",
                    document_upload_id="theme-c3-doc",
                    contract_id="theme-c3",
                    fact_type="cost_variance",
                    label="EAC growth",
                    value_text="EAC increased after invoice variance review.",
                ),
            ]
        )
        db.commit()

    response = client.get(
        "/api/portfolio/themes",
        headers={"Authorization": f"Bearer {official_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kpis"]["source"] == "backend"
    assert body["kpis"]["flagged"] == 3
    assert body["kpis"]["evidence_count"] == 3
    titles = {theme["title"] for theme in body["themes"]}
    assert "Schedule and deliverable slip" in titles
    assert "Cost or financial drift" in titles
    schedule_theme = next(theme for theme in body["themes"] if theme["title"] == "Schedule and deliverable slip")
    assert schedule_theme["flagged"] == 2
    assert schedule_theme["total"] == 2
    assert schedule_theme["value_flagged"] == "3500000"
    assert {contract["id"] for contract in schedule_theme["contracts"]} == {"theme-c1", "theme-c2"}

    lessons = client.get(
        "/api/portfolio/lessons",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    assert lessons.status_code == 200
    lesson_body = lessons.json()
    assert lesson_body["source"] == "deterministic_from_backend_evidence"
    assert lesson_body["lessons"]
    assert any("Atlantic Logistics LLC" in lesson["subject_label"] for lesson in lesson_body["lessons"])
    assert all(lesson["evidence"] for lesson in lesson_body["lessons"])

    with next(_test_db_session(tmp_path)) as db:
        _create_analysis_runs_table(db)
        run = run_portfolio_lessons_analysis(db, period="last_30_days", use_ai=False)
        assert run["status"] == "complete"

    stored_lessons = client.get(
        "/api/portfolio/lessons",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    assert stored_lessons.status_code == 200
    stored_body = stored_lessons.json()
    assert stored_body["source"] == "deterministic_from_backend_evidence"
    assert stored_body["lessons"]


def test_deliverables_endpoint_reports_source_absence(tmp_path) -> None:
    client = _client_with_test_db(tmp_path)
    official_token = _token(client, "official")

    with next(_test_db_session(tmp_path)) as db:
        db.add(
            Contract(
                id="empty-contract",
                contract_number="N00024-26-C-9201",
                title="No Documents Yet",
            )
        )
        db.commit()

    response = client.get(
        "/api/contracts/empty-contract/deliverables",
        headers={"Authorization": f"Bearer {official_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["availability"] == "source_absent"
    assert body["groups"] == []
    assert body["limitations"]


def test_backfill_source_deliverables_populates_deliverables_endpoint(tmp_path) -> None:
    client = _client_with_test_db(tmp_path)
    official_token = _token(client, "official")

    with next(_test_db_session(tmp_path)) as db:
        db.add(
            Contract(
                id="deliverable-contract",
                contract_number="N00024-26-C-9202",
                title="Deliverable Contract",
            )
        )
        db.add(
            DocumentUpload(
                id="source-doc",
                contract_id="deliverable-contract",
                title="Base award",
                document_type="Source Contract",
                document_kind="source_contract",
                original_filename="base.pdf",
                content_type="application/pdf",
                size_bytes=5,
                blob_path="contracts/source-doc/main.pdf",
                uploader_id="official-demo",
                uploader_role="official",
                created_at=datetime.now(timezone.utc),
            )
        )
        db.add(
            ContractBaseline(
                id="baseline-1",
                contract_id="deliverable-contract",
                source_document_upload_id="source-doc",
                summary="Baseline includes CDRL A001.",
            )
        )
        db.add(
            BaselineObligation(
                id="obligation-1",
                baseline_id="baseline-1",
                contract_id="deliverable-contract",
                source_document_upload_id="source-doc",
                obligation_type="deliverable",
                title="Weekly status report",
                description="Submit CDRL A001 weekly status reports.",
                reference_text="CDRL A001 Weekly Status Report",
            )
        )
        db.flush()
        totals = backfill_contract_primitives(db, contract_id="deliverable-contract")
        db.commit()

    assert totals["deliverable"] == 1

    response = client.get(
        "/api/contracts/deliverable-contract/deliverables",
        headers={"Authorization": f"Bearer {official_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["availability"] == "available"
    assert body["groups"][0]["cdrl_item"] == "A001"
    assert body["groups"][0]["items"][0]["status"] == "requirement"


def test_backfill_report_primitives_from_existing_evidence(tmp_path) -> None:
    client = _client_with_test_db(tmp_path)
    _token(client, "official")

    with next(_test_db_session(tmp_path)) as db:
        db.add(
            Contract(
                id="report-contract",
                contract_number="N00024-26-C-9203",
                title="Report Contract",
            )
        )
        db.add(
            DocumentUpload(
                id="report-doc",
                contract_id="report-contract",
                title="Weekly status report",
                document_type="Weekly Status",
                document_kind="weekly_report",
                report_period_end=datetime(2026, 4, 24, tzinfo=timezone.utc).date(),
                original_filename="week.pdf",
                content_type="application/pdf",
                size_bytes=5,
                blob_path="contracts/report-doc/main.pdf",
                uploader_id="contractor-demo",
                uploader_role="contractor",
                created_at=datetime.now(timezone.utc),
            )
        )
        db.add(
            DocumentPage(
                id="page-1",
                document_upload_id="report-doc",
                page_number=1,
                text="CDRL A001 was submitted 4 days late and accepted. EAC $1.2M. planned 3 FTE actual 2 FTE.",
            )
        )
        db.add_all(
            [
                DocumentReportFact(
                    id="report-fact-del",
                    document_upload_id="report-doc",
                    contract_id="report-contract",
                    fact_type="deliverable",
                    label="CDRL A001",
                    value_text="Submitted 4 days late and accepted.",
                ),
                DocumentReportFact(
                    id="report-fact-cost",
                    document_upload_id="report-doc",
                    contract_id="report-contract",
                    fact_type="cost_variance",
                    label="EAC",
                    value_text="EAC $1.2M",
                ),
                DocumentReportFact(
                    id="report-fact-staff",
                    document_upload_id="report-doc",
                    contract_id="report-contract",
                    fact_type="personnel",
                    label="Program manager staffing",
                    value_text="planned 3 FTE actual 2 FTE with staffing gap",
                ),
                RegressionFinding(
                    id="finding-report-1",
                    contract_id="report-contract",
                    document_upload_id="report-doc",
                    finding_type="schedule_regression",
                    title="Late report",
                    summary="CDRL A001 was late.",
                    severity="medium",
                    status="open",
                ),
            ]
        )
        db.flush()
        totals = backfill_contract_primitives(db, document_id="report-doc")
        db.commit()

        assert totals["deliverable"] == 1
        assert totals["financial"] == 1
        assert totals["issues"] == 1
        assert totals["personnel"] == 1
        deliverable = db.query(ContractPrimitiveDeliverable).one()
        assert deliverable.contract_id == "report-contract"
        assert deliverable.cdrl_item == "A001"
        assert deliverable.days_late == 4
        assert db.query(ContractPrimitiveFinancial).one().estimate_at_completion == 1200000
        assert db.query(ContractPrimitiveIssue).one().issue_id == "finding-report-1"
        assert db.query(ContractPrimitivePersonnel).one().staffing_gap_flag is True


def test_contract_lifecycle_api_extracts_full_sample_packet(tmp_path) -> None:
    client = _client_with_test_db(tmp_path)
    official_token = _token(client, "official")
    fixture_root = Path(__file__).resolve().parents[2] / "testdocs" / "full sample contract + data"

    with next(_test_db_session(tmp_path)) as db:
        db.add(
            Contract(
                id="full-sample",
                contract_number="N00173-25-C-XXXX",
                title="C4ISR Systems Design and Development",
                agency_name="Naval Research Laboratory",
                vendor_name="Apex Systems Engineering, Inc.",
            )
        )
        fixture_docs = [
            ("cdrl-doc", "Exhibit A CDRLs", "cdrl", fixture_root / "Exhibit+A+CDRLs.pdf"),
            ("month-01", "Monthly Status Report Month 01", "monthly_report", fixture_root / "full contract sample" / "Monthly_Status_Report_Month01.docx"),
            ("month-06", "Monthly Status Report Month 06", "monthly_report", fixture_root / "full contract sample" / "Monthly_Status_Report_Month06.docx"),
            ("ipmdar-01", "IPMDAR PNR Submission 1", "ipmdar_pnr", fixture_root / "full contract sample" / "IPMDAR_PNR_Submission1_Month06_Mar2025.docx"),
            ("ipmdar-02", "IPMDAR PNR Submission 2", "ipmdar_pnr", fixture_root / "full contract sample" / "IPMDAR_PNR_Submission2_Month10_Jul2025.docx"),
            ("ipmdar-03", "IPMDAR PNR Submission 3", "ipmdar_pnr", fixture_root / "full contract sample" / "IPMDAR_PNR_Submission3_OY1Month04_Apr2026.docx"),
            ("cpar-oy1", "CPAR Option Year 1", "cpars", fixture_root / "full contract sample" / "CPAR_OptionYear1.docx"),
        ]
        for document_id, title, kind, path in fixture_docs:
            db.add(
                DocumentUpload(
                    id=document_id,
                    contract_id="full-sample",
                    title=title,
                    document_type=kind.replace("_", " ").title(),
                    document_kind=kind,
                    original_filename=path.name,
                    content_type="application/pdf" if path.suffix == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    size_bytes=path.stat().st_size,
                    blob_path=f"contracts/{document_id}/main{path.suffix}",
                    uploader_id="fixture",
                    uploader_role="official",
                    created_at=datetime.now(timezone.utc),
                    processing_status="processed",
                )
            )
            text = _extract_pdf_text(path.read_bytes()).text if path.suffix == ".pdf" else _extract_docx_text(path.read_bytes())
            db.add(
                DocumentPage(
                    id=f"{document_id}-page-1",
                    document_upload_id=document_id,
                    page_number=1,
                    text=text,
                )
            )
        db.commit()

    response = client.get(
        "/api/contracts/full-sample/lifecycle",
        headers={"Authorization": f"Bearer {official_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["availability"] == "available"
    assert body["contract"]["contract_number"] == "N00173-25-C-XXXX"
    assert body["contract"]["contractor"] == "Apex Systems Engineering, Inc."
    assert {item["cdrl_item"] for item in body["deliverables"]} >= {"A001", "A002", "A003", "A004"}
    assert len(body["monthly_reports"]) == 2
    month_6 = next(item for item in body["monthly_reports"] if item["month_number"] == 6)
    assert month_6["invoiced_to_date"] == 2074390
    assert "MINOR SLIP" in month_6["schedule_status"]
    assert len(body["ipmdar_metrics"]) == 3
    assert {item["spi"] for item in body["ipmdar_metrics"]} >= {0.94, 0.898, 0.984}
    assert any(item["rating"] == "Very Good" for item in body["cpars_ratings"])
    assert any(item["issue_id"] == "gfi_delay" for item in body["issue_register"])
    assert any(item["type"] == "modification" for item in body["lifecycle_events"])
    assert body["not_proven"]


def test_processing_jobs_and_unmatched_admin_access(tmp_path) -> None:
    client = _client_with_test_db(tmp_path)
    contractor_token = _token(client, "contractor")
    official_token = _token(client, "official")

    with next(_test_db_session(tmp_path)) as db:
        db.add(_document(id="upload-2", uploader_id="contractor-demo"))
        db.add(
            DocumentProcessingJob(
                id="job-1",
                document_upload_id="upload-2",
                job_type="document_analysis",
                status="queued",
            )
        )
        db.commit()

    jobs = client.get(
        "/api/contracts/upload-2/processing-jobs",
        headers={"Authorization": f"Bearer {contractor_token}"},
    )
    assert jobs.status_code == 200
    assert jobs.json()[0]["id"] == "job-1"
    assert jobs.json()[0]["status"] == "queued"

    contractor_queue = client.get(
        "/api/admin/unmatched",
        headers={"Authorization": f"Bearer {contractor_token}"},
    )
    assert contractor_queue.status_code == 403

    official_queue = client.get(
        "/api/admin/unmatched",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    assert official_queue.status_code == 200
    assert official_queue.json()["items"][0]["id"] == "upload-2"
    assert official_queue.json()["items"][0]["reason"] == "pending"


def _client_with_test_db(tmp_path) -> TestClient:
    def override_get_db() -> Generator[Session, None, None]:
        yield from _test_db_session(tmp_path)

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _test_db_session(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ai-kb.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def _create_analysis_runs_table(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id TEXT PRIMARY KEY,
                run_type TEXT NOT NULL,
                target_contract_id TEXT,
                cohort_definition JSON,
                cohort_contract_ids JSON,
                status TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                completed_at DATETIME,
                model TEXT,
                result JSON
            )
            """
        )
    )
    db.commit()


def _token(client: TestClient, role: str) -> str:
    response = client.post("/api/auth/mock-login", json={"role": role})
    assert response.status_code == 200
    return response.json()["access_token"]


def _document(id: str, uploader_id: str) -> DocumentUpload:
    return DocumentUpload(
        id=id,
        title="Monthly progress report",
        document_type="Progress Report",
        notes="Submitted for review",
        original_filename="progress.pdf",
        content_type="application/pdf",
        size_bytes=5,
        blob_path=f"contracts/{id}/main.pdf",
        uploader_id=uploader_id,
        uploader_role="contractor",
        created_at=datetime.now(timezone.utc),
    )
