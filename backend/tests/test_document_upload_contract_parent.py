from typing import Dict, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.blob_storage import get_blob_storage
from app.database import Base, get_db
from app.main import app
from app.models import Contract, ContractAccessGrant, DocumentProcessingJob, DocumentUpload


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


def test_contractor_upload_with_contract_id_becomes_child_report(tmp_path) -> None:
    fake_storage = FakeBlobStorage()
    client = _client_with_test_dependencies(tmp_path, fake_storage)
    contractor_token = _token(client, "contractor")
    official_token = _token(client, "official")

    with next(_test_db_session(tmp_path)) as db:
        db.add(Contract(id="atlantic", contract_number="N40080-24-D-1042", title="Atlantic Environmental"))
        db.add_all(
            [
                ContractAccessGrant(
                    id="grant-contractor-atlantic",
                    contract_id="atlantic",
                    principal_id="contractor-demo",
                    role="uploader",
                ),
                ContractAccessGrant(
                    id="grant-official-atlantic",
                    contract_id="atlantic",
                    principal_id="official-demo",
                    role="viewer",
                ),
            ]
        )
        db.commit()

    upload = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {contractor_token}"},
        data={
            "title": "Monthly progress report",
            "document_type": "Progress Report",
            "notes": "Submitted for review",
            "contract_id": "atlantic",
        },
        files={
            "file": (
                "progress.txt",
                b"RFI-004 remains open but quality control inspections completed.",
                "text/plain",
            )
        },
    )

    assert upload.status_code == 201
    body = upload.json()
    assert body["contract_id"] == "atlantic"
    assert body["match_status"] == "matched"
    assert body["processing_status"] == "queued"
    assert body["document_kind"] == "status_report"
    assert set(fake_storage.files) == {
        f"contracts/{body['id']}/main.pdf",
        f"contracts/{body['id']}/text.json",
    }

    official_detail = client.get(
        f"/api/documents/{body['id']}",
        headers={"Authorization": f"Bearer {official_token}"},
    )

    with next(_test_db_session(tmp_path)) as db:
        document = db.get(DocumentUpload, body["id"])
        jobs = db.scalars(
            select(DocumentProcessingJob).where(DocumentProcessingJob.document_upload_id == body["id"])
        ).all()

    assert official_detail.status_code == 200
    assert official_detail.json()["contract_id"] == "atlantic"
    assert document is not None
    assert document.contract_id == "atlantic"
    assert document.match_status == "matched"
    assert len(jobs) == 1
    assert jobs[0].status == "queued"


def test_contractor_upload_rejects_contract_id_without_upload_access(tmp_path) -> None:
    client = _client_with_test_dependencies(tmp_path, FakeBlobStorage())
    contractor_token = _token(client, "contractor")

    with next(_test_db_session(tmp_path)) as db:
        db.add(Contract(id="restricted", contract_number="N40080-24-D-9999", title="Restricted Contract"))
        db.add(
            ContractAccessGrant(
                id="grant-official-restricted",
                contract_id="restricted",
                principal_id="official-demo",
                role="viewer",
            )
        )
        db.commit()

    response = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {contractor_token}"},
        data={
            "title": "Unauthorized report",
            "document_type": "Progress Report",
            "contract_id": "restricted",
        },
        files={"file": ("progress.txt", b"progress", "text/plain")},
    )

    assert response.status_code == 404


def _client_with_test_dependencies(tmp_path, fake_storage: FakeBlobStorage) -> TestClient:
    def override_get_db() -> Generator[Session, None, None]:
        yield from _test_db_session(tmp_path)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_blob_storage] = lambda: fake_storage
    return TestClient(app)


def _test_db_session(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'document-upload-contract-parent.db'}",
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
