from datetime import date, datetime, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import (
    Contract,
    ContractAccessGrant,
    DocumentReportFact,
    DocumentUpload,
    KnowledgeSourceRecord,
    PerformanceSignal,
    RegressionFinding,
)


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Generator[None, None, None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_single_contract_analysis_is_official_only_and_combines_timeline_signals(tmp_path) -> None:
    client = _client_with_test_db(tmp_path)
    official_token = _token(client, "official")
    contractor_token = _token(client, "contractor")

    with next(_test_db_session(tmp_path)) as db:
        _seed_analysis_contract(db, "atlantic", "N40080-24-D-1042", "Atlantic Environmental")
        db.add_all(
            [
                _access("grant-official-atlantic", "atlantic", "official-demo"),
                _access("grant-contractor-atlantic", "atlantic", "contractor-demo"),
            ]
        )
        report_1 = _document(
            "atlantic-report-1",
            "atlantic",
            "Week 1 report",
            date(2026, 1, 1),
            date(2026, 1, 7),
        )
        report_2 = _document(
            "atlantic-report-2",
            "atlantic",
            "Week 2 report",
            date(2026, 1, 8),
            date(2026, 1, 14),
        )
        report_3 = _document(
            "atlantic-report-3",
            "atlantic",
            "Week 3 report",
            date(2026, 1, 15),
            date(2026, 1, 21),
        )
        db.add_all([report_3, report_1, report_2])
        db.add_all(
            [
                _fact(
                    "rfi-aging-1",
                    "atlantic",
                    report_1.id,
                    "rfi_age",
                    "RFI aging",
                    "RFI-004 has been open 14 days awaiting government response.",
                ),
                _fact(
                    "rfi-aging-2",
                    "atlantic",
                    report_2.id,
                    "rfi_age",
                    "RFI aging",
                    "RFI-004 remains open 21 days and is affecting procurement approvals.",
                ),
                _fact(
                    "qc-approach",
                    "atlantic",
                    report_2.id,
                    "execution",
                    "Quality control approach",
                    "The contractor added quality control checks before each phase turnover.",
                ),
                RegressionFinding(
                    id="schedule-regression",
                    contract_id="atlantic",
                    document_upload_id=report_3.id,
                    finding_type="schedule_regression",
                    title="Critical path schedule slip",
                    summary="Critical path work slipped because submittal approvals were late.",
                    severity="high",
                    confidence=0.85,
                    quote="Critical path work slipped.",
                ),
                PerformanceSignal(
                    id="positive-recovery",
                    contract_id="atlantic",
                    document_upload_id=report_3.id,
                    signal_type="recovery",
                    label="Expedited recovery plan",
                    summary="The recovery plan was approved, expedited, and completed on schedule.",
                    severity="low",
                    confidence=0.8,
                ),
                KnowledgeSourceRecord(
                    id="cpars-atlantic",
                    source_name="cpars_authorized_import",
                    source_type="official",
                    source_key="atlantic-2026-q1",
                    title="CPARS Q1",
                    text="Authorized CPARS export for Atlantic.",
                    contract_id="atlantic",
                    raw_json={"period": "2026 Q1", "schedule": "Marginal", "quality": "Satisfactory"},
                ),
            ]
        )
        db.commit()

    contractor = client.get(
        "/api/analysis/contracts/atlantic",
        headers={"Authorization": f"Bearer {contractor_token}"},
    )
    official = client.get(
        "/api/analysis/contracts/atlantic",
        headers={"Authorization": f"Bearer {official_token}"},
    )

    assert contractor.status_code == 403
    assert official.status_code == 200
    body = official.json()
    assert body["contract_id"] == "atlantic"
    assert [item["period_label"] for item in body["timeline"]] == [
        "2026-01-01 to 2026-01-07",
        "2026-01-08 to 2026-01-14",
        "2026-01-15 to 2026-01-21",
    ]
    assert body["recurring_issues"][0]["title"] == "Aging RFI"
    assert body["recurring_issues"][0]["document_count"] == 2
    assert "Aging RFI" in {item["label"] for item in body["early_warning_signals"]}
    assert "Expedited recovery plan" in {item["label"] for item in body["positive_signals"]}
    assert "Quality control or rework" in {item["label"] for item in body["execution_patterns"]}
    assert {"Schedule", "Quality"} <= {item["label"] for item in body["cpars_ratings"]}
    assert body["analyst_brief"]["recurring_vs_one_off"][0]["citations"]
    assert body["axes"]
    assert {axis["axis"] for axis in body["axes"]} >= {"schedule_performance", "cost_performance", "execution_and_risk"}
    assert body["cpars_predicted"]["Schedule"]["rating"]


def test_cohort_analysis_is_official_only_and_compares_visible_contract_outputs(tmp_path) -> None:
    client = _client_with_test_db(tmp_path)
    official_token = _token(client, "official")
    contractor_token = _token(client, "contractor")

    with next(_test_db_session(tmp_path)) as db:
        _seed_analysis_contract(db, "poor", "N40080-26-D-0001", "Poor Performer")
        _seed_analysis_contract(db, "well", "N40080-26-D-0002", "Well Performer")
        db.add_all(
            [
                _access("grant-official-poor", "poor", "official-demo"),
                _access("grant-official-well", "well", "official-demo"),
                _document("poor-report", "poor", "Poor report", date(2026, 2, 1), date(2026, 2, 7)),
                _document("poor-report-2", "poor", "Poor report 2", date(2026, 2, 8), date(2026, 2, 14)),
                _document("well-report", "well", "Well report", date(2026, 2, 1), date(2026, 2, 7)),
            ]
        )
        db.add_all(
            [
                RegressionFinding(
                    id="poor-delay",
                    contract_id="poor",
                    document_upload_id="poor-report",
                    finding_type="schedule_regression",
                    title="Submittal approval delay",
                    summary="Late government submittal approvals caused critical path delay.",
                    severity="high",
                    confidence=0.8,
                ),
                RegressionFinding(
                    id="poor-delay-2",
                    contract_id="poor",
                    document_upload_id="poor-report-2",
                    finding_type="schedule_regression",
                    title="Submittal approval delay",
                    summary="Submittal approval delays continued to affect critical path work.",
                    severity="medium",
                    confidence=0.75,
                ),
                KnowledgeSourceRecord(
                    id="cpars-poor",
                    source_name="cpars_authorized_import",
                    source_type="official",
                    source_key="poor-2026-q1",
                    contract_id="poor",
                    raw_json={"period": "2026 Q1", "schedule": "Marginal"},
                ),
                PerformanceSignal(
                    id="well-expedited",
                    contract_id="well",
                    document_upload_id="well-report",
                    signal_type="success",
                    label="Expedited approvals",
                    summary="The team expedited approvals and completed turnover on schedule.",
                    confidence=0.8,
                ),
            ]
        )
        db.commit()

    contractor = client.get(
        "/api/analysis/cohort?contract_ids=poor&contract_ids=well",
        headers={"Authorization": f"Bearer {contractor_token}"},
    )
    official = client.get(
        "/api/analysis/cohort?contract_ids=poor&contract_ids=well",
        headers={"Authorization": f"Bearer {official_token}"},
    )

    assert contractor.status_code == 403
    assert official.status_code == 200
    body = official.json()
    assert body["contract_count"] == 2
    assert {item["contract_id"]: item["performance_band"] for item in body["contracts"]} == {
        "poor": "poor",
        "well": "well_performing",
    }
    assert body["poor_contract_common_patterns"][0]["title"] == "Submittal approval delay"
    assert body["well_performing_common_patterns"][0]["title"] == "Expedited approvals"
    assert body["delta_lessons"]
    assert body["qualitative_quantitative_correlations"]


def _client_with_test_db(tmp_path) -> TestClient:
    def override_get_db() -> Generator[Session, None, None]:
        yield from _test_db_session(tmp_path)

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _test_db_session(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'analysis-endpoints.db'}",
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


def _seed_analysis_contract(db: Session, contract_id: str, number: str, title: str) -> None:
    db.add(Contract(id=contract_id, contract_number=number, title=title))


def _access(id: str, contract_id: str, principal_id: str) -> ContractAccessGrant:
    return ContractAccessGrant(
        id=id,
        contract_id=contract_id,
        principal_id=principal_id,
        role="viewer",
    )


def _document(
    id: str,
    contract_id: str,
    title: str,
    period_start: date,
    period_end: date,
) -> DocumentUpload:
    return DocumentUpload(
        id=id,
        contract_id=contract_id,
        title=title,
        document_type="Weekly Status Report",
        document_kind="weekly_report",
        intake_source="portal",
        original_filename=f"{id}.pdf",
        content_type="application/pdf",
        size_bytes=5,
        blob_path=f"contracts/{id}/main.pdf",
        text_blob_path=f"contracts/{id}/text.json",
        report_period_start=period_start,
        report_period_end=period_end,
        match_status="matched",
        processing_status="completed",
        uploader_id="contractor-demo",
        uploader_role="contractor",
        created_at=datetime.now(timezone.utc),
    )


def _fact(
    id: str,
    contract_id: str,
    document_id: str,
    fact_type: str,
    label: str,
    value_text: str,
) -> DocumentReportFact:
    return DocumentReportFact(
        id=id,
        document_upload_id=document_id,
        contract_id=contract_id,
        fact_type=fact_type,
        label=label,
        value_text=value_text,
        quote=value_text,
        confidence=0.75,
    )
