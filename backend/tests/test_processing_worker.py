import json
from datetime import datetime, timezone
from typing import Dict, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.providers import NullAIProvider
from app.blob_storage import get_blob_storage
from app.database import Base, get_db
from app.main import app
from app.models import DocumentChunk, DocumentProcessingJob, DocumentUpload
from app.processing_worker import _worker_count_for_session_factory, drain_queued_processing_jobs


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


def test_processing_worker_completes_uploaded_fixture_without_cli(tmp_path) -> None:
    fake_storage = FakeBlobStorage()
    session_factory = _session_factory(tmp_path)
    client = _client_with_test_dependencies(session_factory, fake_storage)
    contractor_token = _token(client, "contractor")

    upload = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {contractor_token}"},
        data={
            "title": "Weekly progress report",
            "document_type": "Progress Report",
            "notes": "Submitted for processing",
        },
        files={
            "file": (
                "progress.txt",
                b"Weekly Status Report. RFI-004 is 21 days open and creates schedule risk.",
                "text/plain",
            )
        },
    )

    assert upload.status_code == 201
    document_id = upload.json()["id"]

    summary = drain_queued_processing_jobs(
        limit=5,
        storage=fake_storage,
        ai_provider=NullAIProvider(),
        session_factory=session_factory,
        ensure_schema=False,
    )

    with session_factory() as db:
        job = db.scalars(
            select(DocumentProcessingJob).where(DocumentProcessingJob.document_upload_id == document_id)
        ).one()
        document = db.get(DocumentUpload, document_id)
        chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.document_upload_id == document_id)).all()

    assert summary.processed == 1
    assert summary.completed == 1
    assert job.status == "completed"
    assert document is not None
    assert document.processing_status == "processed"
    assert chunks


def test_processing_worker_leaves_pending_ocr_jobs_queued_until_text_is_ready(tmp_path) -> None:
    fake_storage = FakeBlobStorage()
    session_factory = _session_factory(tmp_path)
    document_id = "pending-ocr-doc"
    fake_storage.upload_bytes(
        f"contracts/{document_id}/text.json",
        json.dumps(
            {
                "document_id": document_id,
                "original_filename": "scan.pdf",
                "stored_filename": "main.pdf",
                "content_type": "application/pdf",
                "source": "portal",
                "text": "",
                "extraction_status": "pending_ocr",
            }
        ).encode("utf-8"),
        "application/json",
    )
    with session_factory() as db:
        db.add(_document(document_id))
        db.add(
            DocumentProcessingJob(
                id="pending-job",
                document_upload_id=document_id,
                job_type="document_analysis",
                status="queued",
            )
        )
        db.commit()

    first = drain_queued_processing_jobs(
        limit=5,
        storage=fake_storage,
        ai_provider=NullAIProvider(),
        session_factory=session_factory,
        ensure_schema=False,
    )
    with session_factory() as db:
        waiting_job = db.get(DocumentProcessingJob, "pending-job")

    assert first.processed == 0
    assert first.waiting_for_text == 1
    assert waiting_job is not None
    assert waiting_job.status == "queued"

    fake_storage.upload_bytes(
        f"contracts/{document_id}/text.json",
        json.dumps(
            {
                "document_id": document_id,
                "original_filename": "scan.pdf",
                "stored_filename": "main.pdf",
                "content_type": "application/pdf",
                "source": "portal",
                "text": "Weekly Status Report. Critical path risk is unresolved.",
                "extraction_status": "extracted",
            }
        ).encode("utf-8"),
        "application/json",
    )

    second = drain_queued_processing_jobs(
        limit=5,
        storage=fake_storage,
        ai_provider=NullAIProvider(),
        session_factory=session_factory,
        ensure_schema=False,
    )
    with session_factory() as db:
        completed_job = db.get(DocumentProcessingJob, "pending-job")

    assert second.processed == 1
    assert second.completed == 1
    assert completed_job is not None
    assert completed_job.status == "completed"


def test_processing_worker_concurrent_drain_claims_each_job_once(tmp_path) -> None:
    fake_storage = FakeBlobStorage()
    session_factory = _session_factory(tmp_path)
    document_ids = [f"concurrent-doc-{index}" for index in range(6)]
    with session_factory() as db:
        for document_id in document_ids:
            fake_storage.upload_bytes(
                f"contracts/{document_id}/text.json",
                json.dumps(
                    {
                        "document_id": document_id,
                        "original_filename": f"{document_id}.txt",
                        "stored_filename": "main.txt",
                        "content_type": "text/plain",
                        "source": "portal",
                        "text": f"Weekly Status Report {document_id}. RFI-004 remains open.",
                        "extraction_status": "extracted",
                    }
                ).encode("utf-8"),
                "application/json",
            )
            db.add(_document(document_id))
            db.add(
                DocumentProcessingJob(
                    id=f"job-{document_id}",
                    document_upload_id=document_id,
                    job_type="document_analysis",
                    status="queued",
                )
            )
        db.commit()

    summary = drain_queued_processing_jobs(
        limit=len(document_ids),
        storage=fake_storage,
        ai_provider=NullAIProvider(),
        session_factory=session_factory,
        ensure_schema=False,
        max_workers=3,
    )

    with session_factory() as db:
        jobs = db.scalars(select(DocumentProcessingJob)).all()
        documents = db.scalars(select(DocumentUpload)).all()

    assert summary.processed == len(document_ids)
    assert summary.completed == len(document_ids)
    assert summary.failed == 0
    assert summary.queued_remaining == 0
    assert {job.status for job in jobs} == {"completed"}
    assert {job.attempt_count for job in jobs} == {1}
    assert all(job.worker_id for job in jobs)
    assert {document.processing_status for document in documents} == {"processed"}


def test_sqlite_processing_drains_are_serialized_to_avoid_write_locks(tmp_path) -> None:
    session_factory = _session_factory(tmp_path)

    assert _worker_count_for_session_factory(4, session_factory) == 1


def _client_with_test_dependencies(session_factory: sessionmaker, fake_storage: FakeBlobStorage) -> TestClient:
    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_blob_storage] = lambda: fake_storage
    return TestClient(app)


def _session_factory(tmp_path) -> sessionmaker:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'processing-worker.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _token(client: TestClient, role: str) -> str:
    response = client.post("/api/auth/mock-login", json={"role": role})
    assert response.status_code == 200
    return response.json()["access_token"]


def _document(document_id: str) -> DocumentUpload:
    return DocumentUpload(
        id=document_id,
        contract_id=None,
        title="Pending OCR report",
        document_type="Weekly Status Report",
        document_kind="status_report",
        intake_source="portal",
        original_filename="scan.pdf",
        content_type="application/pdf",
        size_bytes=5,
        blob_path=f"contracts/{document_id}/main.pdf",
        text_blob_path=f"contracts/{document_id}/text.json",
        match_status="pending",
        processing_status="queued",
        uploader_id="contractor-demo",
        uploader_role="contractor",
        created_at=datetime.now(timezone.utc),
    )
