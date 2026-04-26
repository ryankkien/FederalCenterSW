import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import analysis_orchestrator
from app.database import Base
from app.models import AuditEvent, Contract


def test_auto_analysis_enqueues_and_executes_when_primitives_are_newer(tmp_path, monkeypatch) -> None:
    db = _session(tmp_path)
    try:
        _create_analysis_tables(db)
        db.add(_contract("contract-1"))
        db.execute(
            text(
                """
                INSERT INTO primitive_extraction_runs
                    (id, contract_id, doc_upload_id, period_label, extracted_at, model, status)
                VALUES (:id, :contract_id, :doc_id, :period_label, :extracted_at, :model, :status)
                """
            ),
            {
                "id": "extract-1",
                "contract_id": "contract-1",
                "doc_id": "doc-1",
                "period_label": "2026-04",
                "extracted_at": datetime.now(timezone.utc),
                "model": "test-model",
                "status": "success",
            },
        )
        db.commit()
        monkeypatch.setattr(
            analysis_orchestrator,
            "_openai_json_response",
            lambda *_args, **_kwargs: {"axes": [{"axis": "schedule_performance"}]},
        )

        queued = analysis_orchestrator.enqueue_per_contract_analysis_after_extraction(
            db,
            "contract-1",
            document_upload_id="doc-1",
            extraction_run_id="extract-1",
        )
        assert queued["status"] == "queued"
        assert queued["low_confidence"] is True

        result = analysis_orchestrator.execute_enqueued_per_contract_analysis(
            db,
            queued["run_id"],
            "contract-1",
            document_upload_id="doc-1",
            extraction_run_id="extract-1",
        )

        assert result["status"] == "complete"
        stored = db.execute(
            text("SELECT status, result FROM analysis_runs WHERE id = :id"),
            {"id": queued["run_id"]},
        ).mappings().one()
        stored_result = _json_value(stored["result"])
        assert stored["status"] == "complete"
        assert stored_result["low_confidence"] is True
        assert stored_result["axes"][0]["low_confidence"] is True

        events = db.query(AuditEvent).order_by(AuditEvent.event_time).all()
        assert [event.event_type for event in events] == [
            "analysis.per_contract.auto_enqueued",
            "analysis.per_contract.auto_completed",
        ]
    finally:
        db.close()


def test_auto_analysis_debounces_when_existing_run_is_newer_than_primitives(tmp_path) -> None:
    db = _session(tmp_path)
    try:
        _create_analysis_tables(db)
        db.add(_contract("contract-1"))
        primitive_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.execute(
            text(
                """
                INSERT INTO primitive_extraction_runs
                    (id, contract_id, doc_upload_id, extracted_at, model, status)
                VALUES (:id, :contract_id, :doc_id, :extracted_at, :model, :status)
                """
            ),
            {
                "id": "extract-1",
                "contract_id": "contract-1",
                "doc_id": "doc-1",
                "extracted_at": primitive_time,
                "model": "test-model",
                "status": "success",
            },
        )
        db.execute(
            text(
                """
                INSERT INTO analysis_runs
                    (id, run_type, target_contract_id, status, created_at, model)
                VALUES (:id, 'per_contract', :contract_id, 'complete', :created_at, :model)
                """
            ),
            {
                "id": "analysis-existing",
                "contract_id": "contract-1",
                "created_at": primitive_time + timedelta(minutes=1),
                "model": "test-model",
            },
        )
        db.commit()

        queued = analysis_orchestrator.enqueue_per_contract_analysis_after_extraction(
            db,
            "contract-1",
            document_upload_id="doc-1",
            extraction_run_id="extract-1",
        )

        assert queued == {
            "status": "skipped",
            "reason": "debounced",
            "run_id": "analysis-existing",
        }
        count = db.execute(text("SELECT COUNT(*) FROM analysis_runs")).scalar_one()
        assert count == 1
        event = db.query(AuditEvent).one()
        assert event.event_type == "analysis.per_contract.auto_skipped"
        assert event.metadata_json["reason"] == "debounced"
    finally:
        db.close()


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analysis-auto-trigger.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return factory()


def _contract(contract_id: str) -> Contract:
    return Contract(
        id=contract_id,
        contract_number=f"N00000-26-D-{contract_id[-1]}",
        title="Test contract",
        naics_code="541330",
        contract_type="firm_fixed_price",
        agency_name="Department of Test",
    )


def _create_analysis_tables(db) -> None:
    db.execute(
        text(
            """
            CREATE TABLE primitive_extraction_runs (
                id TEXT PRIMARY KEY,
                contract_id TEXT,
                doc_upload_id TEXT,
                period_label TEXT,
                extracted_at DATETIME,
                model TEXT,
                status TEXT
            )
            """
        )
    )
    db.execute(
        text(
            """
            CREATE TABLE analysis_runs (
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
    for table_name in (
        "contract_primitives_deliverable",
        "contract_primitives_financial",
        "contract_primitives_decisions",
        "contract_primitives_issues",
        "contract_primitives_personnel",
    ):
        db.execute(
            text(
                f"""
                CREATE TABLE {table_name} (
                    id TEXT PRIMARY KEY,
                    extraction_run_id TEXT,
                    contract_id TEXT,
                    period_label TEXT
                )
                """
            )
        )
    db.execute(
        text(
            """
            CREATE TABLE cpars_ratings (
                id TEXT PRIMARY KEY,
                contract_id TEXT,
                evaluation_date DATE
            )
            """
        )
    )
    db.commit()


def _json_value(value):
    if isinstance(value, str):
        return json.loads(value)
    return value
