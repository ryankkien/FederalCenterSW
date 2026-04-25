from typing import Dict, Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.blob_storage import get_blob_storage
from app.database import Base, get_db
from app.main import app
from app.models import DocumentUpload


class FakeBlobStorage:
    def __init__(self) -> None:
        self.files: Dict[str, bytes] = {}

    def upload_bytes(self, path: str, data: bytes, content_type: str) -> None:
        self.files[path] = data

    def download_bytes(self, path: str) -> bytes:
        return self.files[path]


def test_mock_login_and_me() -> None:
    client = TestClient(app)

    login = client.post("/api/auth/mock-login", json={"role": "contractor"})

    assert login.status_code == 200
    token = login.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "contractor"


def test_contractor_uploads_document_and_official_can_review(tmp_path) -> None:
    fake_storage = FakeBlobStorage()
    client = _client_with_test_dependencies(tmp_path, fake_storage)
    contractor_token = _token(client, "contractor")
    official_token = _token(client, "official")

    upload = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {contractor_token}"},
        data={
            "title": "Monthly progress report",
            "document_type": "Progress Report",
            "notes": "Submitted for review",
        },
        files={"file": ("progress.pdf", b"contractor document", "application/pdf")},
    )

    assert upload.status_code == 201
    body = upload.json()
    assert body["title"] == "Monthly progress report"
    assert body["original_filename"] == "progress.pdf"
    assert len(fake_storage.files) == 1

    contractor_list = client.get(
        "/api/documents",
        headers={"Authorization": f"Bearer {contractor_token}"},
    )
    assert contractor_list.status_code == 200
    assert [document["id"] for document in contractor_list.json()] == [body["id"]]

    official_list = client.get(
        "/api/documents",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    assert official_list.status_code == 200
    assert [document["id"] for document in official_list.json()] == [body["id"]]

    download = client.get(
        f"/api/documents/{body['id']}/download",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    assert download.status_code == 200
    assert download.content == b"contractor document"


def test_official_cannot_upload_documents(tmp_path) -> None:
    client = _client_with_test_dependencies(tmp_path, FakeBlobStorage())
    official_token = _token(client, "official")

    response = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {official_token}"},
        data={"title": "Memo", "document_type": "Memo"},
        files={"file": ("memo.pdf", b"memo", "application/pdf")},
    )

    assert response.status_code == 403


def test_upload_rejects_unsupported_file_type(tmp_path) -> None:
    client = _client_with_test_dependencies(tmp_path, FakeBlobStorage())
    contractor_token = _token(client, "contractor")

    response = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {contractor_token}"},
        data={"title": "Archive", "document_type": "Archive"},
        files={"file": ("archive.zip", b"zip", "application/zip")},
    )

    assert response.status_code == 400


def test_contractor_cannot_download_other_contractors_document(tmp_path) -> None:
    fake_storage = FakeBlobStorage()
    client = _client_with_test_dependencies(tmp_path, fake_storage)
    contractor_token = _token(client, "contractor")

    with next(_test_db_session(tmp_path)) as db:
        document = DocumentUpload(
            id="other-doc",
            title="Other upload",
            document_type="Report",
            notes=None,
            original_filename="other.pdf",
            content_type="application/pdf",
            size_bytes=5,
            blob_path="documents/other/other-doc/other.pdf",
            uploader_id="other-contractor",
            uploader_role="contractor",
        )
        db.add(document)
        db.commit()
    fake_storage.files["documents/other/other-doc/other.pdf"] = b"other"

    response = client.get(
        "/api/documents/other-doc/download",
        headers={"Authorization": f"Bearer {contractor_token}"},
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
        f"sqlite:///{tmp_path / 'documents.db'}",
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
