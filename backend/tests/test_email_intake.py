import json
import os
from email.message import EmailMessage

from app.email_intake import (
    AutoReplyConfig,
    build_auto_reply_message,
    load_env_files,
    parse_email,
    save_email_intake,
    should_send_auto_reply,
)


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
