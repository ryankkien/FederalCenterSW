import base64
import json
import time
from io import BytesIO
from typing import Dict, Generator

import fitz
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import document_assets
from app.blob_storage import get_blob_storage
from app.database import Base, get_db
from app.main import app
from app.models import Contract, ContractAccessGrant, DocumentUpload


class FakeBlobStorage:
    def __init__(self) -> None:
        self.files: Dict[str, bytes] = {}

    def upload_bytes(self, path: str, data: bytes, content_type: str) -> None:
        self.files[path] = data

    def download_bytes(self, path: str) -> bytes:
        return self.files[path]

    def create_read_url(self, path: str, expires_in_minutes: int = 15) -> str:
        return f"https://storage.example.test/app-assets/{path}?sas=true&expires={expires_in_minutes}"


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
    assert len(fake_storage.files) == 2
    assert body["stored_filename"] == "main.pdf"

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

    sas_url = client.get(
        f"/api/documents/{body['id']}/sas-url",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    assert sas_url.status_code == 200
    assert sas_url.json() == {
        "url": f"https://storage.example.test/app-assets/contracts/{body['id']}/main.pdf?sas=true&expires=15",
        "expires_in_minutes": 15,
    }


def test_scanned_pdf_upload_uses_ocr_when_embedded_text_is_missing(tmp_path, monkeypatch) -> None:
    fake_storage = FakeBlobStorage()
    client = _client_with_test_dependencies(tmp_path, fake_storage)
    contractor_token = _token(client, "contractor")
    monkeypatch.setattr(
        document_assets,
        "_ocr_pdf_text",
        lambda _data: ("OCR recovered status report text", None),
    )

    upload = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {contractor_token}"},
        data={"title": "Scanned report", "document_type": "Progress Report"},
        files={"file": ("scanned.pdf", _blank_pdf_bytes(), "application/pdf")},
    )

    assert upload.status_code == 201
    body = upload.json()
    text_blob = f"contracts/{body['id']}/text.json"
    text_json = json.loads(fake_storage.files[text_blob])
    assert text_json["extraction_status"] == "ocr_extracted"
    assert text_json["status"] == "ocr_extracted"
    assert text_json["method"] == "ocr"
    assert text_json["text"] == "OCR recovered status report text"


def test_scanned_pdf_upload_uses_ocr_when_embedded_text_is_low_quality(
    tmp_path,
    monkeypatch,
) -> None:
    fake_storage = FakeBlobStorage()
    client = _client_with_test_dependencies(tmp_path, fake_storage)
    contractor_token = _token(client, "contractor")
    monkeypatch.setattr(document_assets, "_is_image_heavy_pdf", lambda _document: True)
    monkeypatch.setattr(
        document_assets,
        "_ocr_pdf_text",
        lambda _data: ("clear monthly progress report text with normal words", None),
    )

    upload = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {contractor_token}"},
        data={"title": "Noisy report", "document_type": "Progress Report"},
        files={"file": ("noisy.pdf", _low_quality_text_pdf_bytes(), "application/pdf")},
    )

    assert upload.status_code == 201
    body = upload.json()
    text_blob = f"contracts/{body['id']}/text.json"
    text_json = json.loads(fake_storage.files[text_blob])
    assert text_json["extraction_status"] == "ocr_extracted"
    assert text_json["method"] == "ocr"
    assert "clear monthly progress" in text_json["text"]
    assert text_json["ocr_quality"] > text_json["embedded_quality"]


def test_scanned_pdf_upload_records_ocr_failure(tmp_path, monkeypatch) -> None:
    fake_storage = FakeBlobStorage()
    client = _client_with_test_dependencies(tmp_path, fake_storage)
    contractor_token = _token(client, "contractor")

    def fail_ocr(_data):
        raise RuntimeError("Tesseract command 'tesseract' is not installed or not on PATH")

    monkeypatch.setattr(document_assets, "_ocr_pdf_text", fail_ocr)

    upload = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {contractor_token}"},
        data={"title": "Scanned report", "document_type": "Progress Report"},
        files={"file": ("scanned.pdf", _blank_pdf_bytes(), "application/pdf")},
    )

    assert upload.status_code == 201
    body = upload.json()
    text_blob = f"contracts/{body['id']}/text.json"
    text_json = json.loads(fake_storage.files[text_blob])
    assert text_json["extraction_status"] == "failed"
    assert "PDF text extraction produced no usable text and OCR failed" in text_json["extraction_error"]


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


def test_contractor_cannot_create_sas_url_for_other_contractors_document(tmp_path) -> None:
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

    response = client.get(
        "/api/documents/other-doc/sas-url",
        headers={"Authorization": f"Bearer {contractor_token}"},
    )

    assert response.status_code == 404


def test_entra_jwt_group_mapping_authorizes_contract_access(tmp_path, monkeypatch) -> None:
    from cryptography.hazmat.primitives.asymmetric import rsa
    import jwt

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = "https://login.microsoftonline.com/test-tenant/v2.0"
    audience = "api://fcsw-test"
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("ENTRA_ISSUER", issuer)
    monkeypatch.setenv("ENTRA_AUDIENCE", audience)
    monkeypatch.setenv("ENTRA_OFFICIAL_GROUP_IDS", "official-group")
    monkeypatch.setenv("ENTRA_CONTRACTOR_GROUP_IDS", "contractor-group")
    monkeypatch.setenv(
        "ENTRA_JWKS_JSON",
        json.dumps({"keys": [_public_jwk(private_key.public_key(), "test-key")]}),
    )

    client = _client_with_test_dependencies(tmp_path, FakeBlobStorage())
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": audience,
            "exp": int(time.time()) + 300,
            "oid": "entra-user-1",
            "preferred_username": "official@example.gov",
            "name": "Entra Official",
            "groups": ["official-group"],
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    with next(_test_db_session(tmp_path)) as db:
        db.add(Contract(id="contract-1", contract_number="N00000-26-C-0001", title="Granted Contract"))
        db.add(
            ContractAccessGrant(
                id="grant-entra-group",
                contract_id="contract-1",
                principal_id="official-group",
                principal_type="group",
                role="viewer",
            )
        )
        db.commit()

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    contracts = client.get("/api/contracts", headers={"Authorization": f"Bearer {token}"})
    mock_login = client.post("/api/auth/mock-login", json={"role": "official"})

    assert me.status_code == 200
    assert me.json()["id"] == "entra-user-1"
    assert me.json()["role"] == "official"
    assert me.json()["group_ids"] == ["official-group"]
    assert contracts.status_code == 200
    assert "contract-1" in {contract["id"] for contract in contracts.json()}
    assert mock_login.status_code == 404


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


def _public_jwk(public_key, kid: str) -> Dict[str, str]:
    numbers = public_key.public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "kid": kid,
        "alg": "RS256",
        "n": _b64int(numbers.n),
        "e": _b64int(numbers.e),
    }


def _b64int(value: int) -> str:
    data = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _blank_pdf_bytes() -> bytes:
    output = BytesIO()
    document = fitz.open()
    document.new_page(width=72, height=72)
    document.save(output)
    return output.getvalue()


def _low_quality_text_pdf_bytes() -> bytes:
    output = BytesIO()
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 72), " ".join(["xqz", "brr", "nth", "cwm", "pfft"] * 80))
    document.save(output)
    return output.getvalue()
