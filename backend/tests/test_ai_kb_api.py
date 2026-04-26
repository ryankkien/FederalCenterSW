from datetime import datetime, timezone
from typing import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Contract, ContractAccessGrant, DocumentProcessingJob, DocumentUpload


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
