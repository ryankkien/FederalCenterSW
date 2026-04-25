import json
import os
from email.message import EmailMessage
from typing import Dict

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.email_intake import (
    AutoReplyConfig,
    EmailIntakeConfig,
    build_auto_reply_message,
    load_env_files,
    parse_email,
    save_email_documents,
    save_email_intake,
    should_send_auto_reply,
)
from app.models import DocumentUpload


class FakeBlobStorage:
    def __init__(self) -> None:
        self.files: Dict[str, bytes] = {}

    def upload_bytes(self, path: str, data: bytes, content_type: str) -> None:
        self.files[path] = data

    def download_bytes(self, path: str) -> bytes:
        return self.files[path]

    def create_read_url(self, path: str, expires_in_minutes: int = 15) -> str:
        return f"https://storage.example.test/{path}?expires={expires_in_minutes}"


def test_parse_email_extracts_headers_bodies_and_attachment_metadata():
    message = EmailMessage()
    message["Message-ID"] = "<abc123@example.com>"
    message["From"] = "Intake Sender <sender@example.com>"
    message["Reply-To"] = "Case Contact <reply@example.com>"
    message["To"] = "Federal Center SW <intake@example.com>"
    message["Cc"] = "cc@example.com"
    message["Subject"] = "New intake"
    message["Date"] = "Sat, 25 Apr 2026 17:30:00 -0400"
    message.set_content("Plain body")
    message.add_alternative("<p>HTML body</p>", subtype="html")
    message.add_attachment(
        b"example attachment",
        maintype="application",
        subtype="pdf",
        filename="example.pdf",
    )

    record = parse_email(message.as_bytes(), source_uid="42")

    assert record.message_id == "<abc123@example.com>"
    assert record.source_uid == "42"
    assert record.subject == "New intake"
    assert record.from_addresses[0].address == "sender@example.com"
    assert record.reply_to_addresses[0].address == "reply@example.com"
    assert record.to_addresses[0].address == "intake@example.com"
    assert record.cc_addresses[0].address == "cc@example.com"
    assert record.received_at == "2026-04-25T21:30:00+00:00"
    assert record.body_text == "Plain body"
    assert record.body_html == "<p>HTML body</p>"
    assert record.attachments[0].filename == "example.pdf"
    assert record.attachments[0].content_type == "application/pdf"
    assert record.attachments[0].size_bytes == len(b"example attachment")
    assert record.raw_sha256


def test_parse_email_uses_raw_hash_when_message_id_is_missing():
    message = EmailMessage()
    message["From"] = "sender@example.com"
    message["To"] = "intake@example.com"
    message.set_content("No Message-ID")

    record = parse_email(message.as_bytes())

    assert record.message_id.startswith("sha256:")


def test_save_email_intake_writes_jsonl_stub(tmp_path):
    message = EmailMessage()
    message["Message-ID"] = "<abc123@example.com>"
    message["From"] = "sender@example.com"
    message["To"] = "intake@example.com"
    message["Subject"] = "Persist me"
    message.set_content("Body")
    record = parse_email(message.as_bytes())
    output_path = tmp_path / "intake.jsonl"

    save_email_intake(record, output_path)

    rows = output_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    saved = json.loads(rows[0])
    assert saved["message_id"] == "<abc123@example.com>"
    assert saved["subject"] == "Persist me"
    assert saved["body_text"] == "Body"


def test_load_env_files_supports_local_overrides_without_replacing_exported_values(
    tmp_path,
    monkeypatch,
):
    base_env = tmp_path / ".env"
    local_env = tmp_path / ".env.local"
    base_env.write_text(
        "DATABASE_URL=postgresql://cloud.example/federal_center_sw\n"
        "AZURE_STORAGE_CONTAINER=app-assets\n",
        encoding="utf-8",
    )
    local_env.write_text(
        "DATABASE_URL=postgresql://localhost/federal_center_sw\n"
        "AZURE_STORAGE_ACCOUNT=devstoreaccount1\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONTAINER", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT", raising=False)

    load_env_files((base_env, local_env))

    assert os.environ["DATABASE_URL"] == "postgresql://localhost/federal_center_sw"
    assert os.environ["AZURE_STORAGE_CONTAINER"] == "app-assets"
    assert os.environ["AZURE_STORAGE_ACCOUNT"] == "devstoreaccount1"

    monkeypatch.setenv("DATABASE_URL", "postgresql://exported/federal_center_sw")

    load_env_files((base_env, local_env))

    assert os.environ["DATABASE_URL"] == "postgresql://exported/federal_center_sw"


def test_save_email_documents_uploads_supported_attachments_to_portal_storage(tmp_path):
    message = EmailMessage()
    message["Message-ID"] = "<doc123@example.com>"
    message["From"] = "Contractor <contractor@example.com>"
    message["To"] = "intake@example.com"
    message["Subject"] = "Permit packet"
    message["Date"] = "Sat, 25 Apr 2026 17:30:00 -0400"
    message.set_content("See attached.")
    message.add_attachment(
        b"pdf bytes",
        maintype="application",
        subtype="pdf",
        filename="permit.pdf",
    )
    message.add_attachment(
        b"zip bytes",
        maintype="application",
        subtype="zip",
        filename="archive.zip",
    )
    raw_message = message.as_bytes()
    record = parse_email(raw_message, source_uid="77")
    fake_storage = FakeBlobStorage()
    db = _test_db_session(tmp_path)
    config = EmailIntakeConfig(
        host="imap.example.com",
        username="intake@example.com",
        password="secret",
        dry_run=False,
        default_uploader_id="contractor-demo",
        default_document_type="Email Attachment",
    )

    saved_count = save_email_documents(record, raw_message, config, db=db, storage=fake_storage)

    assert saved_count == 1
    documents = db.query(DocumentUpload).all()
    assert len(documents) == 1
    document = documents[0]
    assert document.title == "Permit packet - permit.pdf"
    assert document.document_type == "Email Attachment"
    assert document.original_filename == "permit.pdf"
    assert document.uploader_id == "contractor-demo"
    assert document.blob_path in fake_storage.files
    assert fake_storage.files[document.blob_path] == b"pdf bytes"
    assert "Source UID: 77." in document.notes


def test_save_email_documents_is_idempotent_for_same_email(tmp_path):
    message = EmailMessage()
    message["Message-ID"] = "<dedupe@example.com>"
    message["From"] = "contractor@example.com"
    message["To"] = "intake@example.com"
    message["Subject"] = "Same attachment"
    message.set_content("See attached.")
    message.add_attachment(
        b"same bytes",
        maintype="text",
        subtype="plain",
        filename="same.txt",
    )
    raw_message = message.as_bytes()
    record = parse_email(raw_message)
    fake_storage = FakeBlobStorage()
    db = _test_db_session(tmp_path)
    config = EmailIntakeConfig(
        host="imap.example.com",
        username="intake@example.com",
        password="secret",
        dry_run=False,
    )

    assert save_email_documents(record, raw_message, config, db=db, storage=fake_storage) == 1
    assert save_email_documents(record, raw_message, config, db=db, storage=fake_storage) == 0
    assert db.query(DocumentUpload).count() == 1


def test_auto_reply_message_targets_reply_to_and_threads_to_original_message():
    message = EmailMessage()
    message["Message-ID"] = "<abc123@example.com>"
    message["From"] = "sender@example.com"
    message["Reply-To"] = "reply@example.com"
    message["To"] = "intake@example.com"
    message["Subject"] = "Question"
    message.set_content("Body")
    record = parse_email(message.as_bytes())
    config = AutoReplyConfig(
        smtp_host="smtp.example.com",
        smtp_username="intake@example.com",
        smtp_password="secret",
        from_address="intake@example.com",
    )

    reply = build_auto_reply_message(record, config, "reply@example.com")

    assert should_send_auto_reply(record)
    assert reply["To"] == "reply@example.com"
    assert reply["From"] == "intake@example.com"
    assert reply["Subject"] == "Your email has been received"
    assert reply["Auto-Submitted"] == "auto-replied"
    assert reply["In-Reply-To"] == "<abc123@example.com>"
    assert "Your email has been received. Thank you." in reply.get_content()


def test_auto_reply_skips_automated_or_bulk_messages():
    message = EmailMessage()
    message["Message-ID"] = "<bulk@example.com>"
    message["From"] = "newsletter@example.com"
    message["To"] = "intake@example.com"
    message["Auto-Submitted"] = "auto-generated"
    message.set_content("Body")

    assert not should_send_auto_reply(parse_email(message.as_bytes()))

    message.replace_header("Auto-Submitted", "no")
    message["List-ID"] = "Example Newsletter <newsletter.example.com>"

    assert not should_send_auto_reply(parse_email(message.as_bytes()))


def _test_db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'email-documents.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()
