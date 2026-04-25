"""IMAP email intake worker with a stubbed persistence layer."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import imaplib
import json
import os
import smtplib
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import formatdate, getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "email_intake.jsonl"
ENV_PATHS = (
    Path(__file__).resolve().parents[2] / ".env",
    Path(__file__).resolve().parents[1] / ".env",
)


@dataclass
class EmailIntakeConfig:
    host: str
    username: str
    password: str
    port: int = 993
    mailbox: str = "INBOX"
    search_criteria: Tuple[str, ...] = ("UNSEEN",)
    processed_mailbox: str = "Processed"
    failed_mailbox: str = "Failed"
    dry_run: bool = True
    output_path: Path = DEFAULT_OUTPUT_PATH
    auto_reply: Optional["AutoReplyConfig"] = None

    @classmethod
    def from_env(cls) -> "EmailIntakeConfig":
        host = _require_env("EMAIL_INTAKE_HOST")
        username = _require_env("EMAIL_INTAKE_USERNAME")
        password = _require_env("EMAIL_INTAKE_PASSWORD")

        return cls(
            host=host,
            username=username,
            password=password,
            port=int(os.getenv("EMAIL_INTAKE_PORT", "993")),
            mailbox=os.getenv("EMAIL_INTAKE_MAILBOX", "INBOX"),
            search_criteria=tuple(
                part
                for part in os.getenv("EMAIL_INTAKE_SEARCH", "UNSEEN").split()
                if part.strip()
            ),
            processed_mailbox=os.getenv("EMAIL_INTAKE_PROCESSED_MAILBOX", "Processed"),
            failed_mailbox=os.getenv("EMAIL_INTAKE_FAILED_MAILBOX", "Failed"),
            dry_run=_env_bool("EMAIL_INTAKE_DRY_RUN", default=True),
            output_path=Path(os.getenv("EMAIL_INTAKE_OUTPUT_PATH", str(DEFAULT_OUTPUT_PATH))),
            auto_reply=AutoReplyConfig.from_env(),
        )


@dataclass
class AutoReplyConfig:
    smtp_host: str
    smtp_username: str
    smtp_password: str
    from_address: str
    smtp_port: int = 587
    use_starttls: bool = True
    subject: str = "Your email has been received"
    body: str = "Your email has been received. Thank you."

    @classmethod
    def from_env(cls) -> Optional["AutoReplyConfig"]:
        if not _env_bool("EMAIL_INTAKE_AUTO_REPLY_ENABLED", default=False):
            return None

        smtp_username = os.getenv("EMAIL_INTAKE_SMTP_USERNAME") or _require_env(
            "EMAIL_INTAKE_USERNAME"
        )
        smtp_password = os.getenv("EMAIL_INTAKE_SMTP_PASSWORD") or _require_env(
            "EMAIL_INTAKE_PASSWORD"
        )

        return cls(
            smtp_host=_require_env("EMAIL_INTAKE_SMTP_HOST"),
            smtp_username=smtp_username,
            smtp_password=smtp_password,
            smtp_port=int(os.getenv("EMAIL_INTAKE_SMTP_PORT", "587")),
            from_address=os.getenv("EMAIL_INTAKE_AUTO_REPLY_FROM", smtp_username),
            use_starttls=_env_bool("EMAIL_INTAKE_SMTP_STARTTLS", default=True),
            subject=os.getenv(
                "EMAIL_INTAKE_AUTO_REPLY_SUBJECT",
                "Your email has been received",
            ),
            body=os.getenv(
                "EMAIL_INTAKE_AUTO_REPLY_BODY",
                "Your email has been received. Thank you.",
            ),
        )


@dataclass
class EmailAddress:
    name: str
    address: str


@dataclass
class AttachmentInfo:
    filename: Optional[str]
    content_type: str
    size_bytes: int


@dataclass
class EmailIntakeRecord:
    message_id: str
    source_uid: Optional[str]
    subject: str
    from_addresses: List[EmailAddress]
    reply_to_addresses: List[EmailAddress]
    to_addresses: List[EmailAddress]
    cc_addresses: List[EmailAddress]
    received_at: Optional[str]
    ingested_at: str
    body_text: str
    body_html: str
    attachments: List[AttachmentInfo]
    headers: Dict[str, str]
    raw_sha256: str


def parse_email(raw_message: bytes, source_uid: Optional[str] = None) -> EmailIntakeRecord:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    message_id = _clean_header(message.get("Message-ID")) or _raw_message_id(raw_message)

    return EmailIntakeRecord(
        message_id=message_id,
        source_uid=source_uid,
        subject=_clean_header(message.get("Subject")),
        from_addresses=_parse_addresses(message.get_all("From", [])),
        reply_to_addresses=_parse_addresses(message.get_all("Reply-To", [])),
        to_addresses=_parse_addresses(message.get_all("To", [])),
        cc_addresses=_parse_addresses(message.get_all("Cc", [])),
        received_at=_parse_date(message.get("Date")),
        ingested_at=datetime.now(timezone.utc).isoformat(),
        body_text=_extract_body(message, "text/plain"),
        body_html=_extract_body(message, "text/html"),
        attachments=_extract_attachments(message),
        headers={key: str(value) for key, value in message.items()},
        raw_sha256=hashlib.sha256(raw_message).hexdigest(),
    )


def save_email_intake(record: EmailIntakeRecord, output_path: Path) -> None:
    """Stub persistence layer.

    Replace this function with a database insert once the intake schema is settled.
    For now it writes JSON to Azure Blob Storage when configured, otherwise
    newline-delimited JSON locally so the worker can be tested end to end.
    """

    if _env_bool("EMAIL_INTAKE_STUB_BLOB_ENABLED", default=False):
        save_email_intake_blob(record)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(_record_to_json(record), sort_keys=True) + "\n")


def save_email_intake_blob(record: EmailIntakeRecord) -> None:
    connection_string = os.getenv("EMAIL_INTAKE_STUB_BLOB_CONNECTION_STRING") or os.getenv(
        "AZURE_STORAGE_CONNECTION_STRING"
    )
    container_name = os.getenv("EMAIL_INTAKE_STUB_BLOB_CONTAINER") or os.getenv(
        "AZURE_STORAGE_CONTAINER",
        "app-assets",
    )
    prefix = os.getenv("EMAIL_INTAKE_STUB_BLOB_PREFIX", "email-intake")
    if not connection_string:
        raise RuntimeError(
            "Missing EMAIL_INTAKE_STUB_BLOB_CONNECTION_STRING or AZURE_STORAGE_CONNECTION_STRING"
        )
    storage = _parse_storage_connection_string(connection_string)

    received = _blob_record_datetime(record)
    blob_name = (
        f"{prefix}/{received:%Y/%m/%d}/"
        f"{_safe_blob_component(record.message_id)}-{record.raw_sha256[:16]}.json"
    )
    payload = json.dumps(_record_to_json(record), indent=2, sort_keys=True).encode("utf-8")

    _put_blob_if_absent(storage, container_name, blob_name, payload)


def _parse_storage_connection_string(connection_string: str) -> Dict[str, str]:
    values = {}
    for part in connection_string.split(";"):
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        values[key] = value

    if "AccountName" not in values or "AccountKey" not in values:
        raise RuntimeError("Storage connection string must include AccountName and AccountKey")

    if "BlobEndpoint" not in values:
        protocol = values.get("DefaultEndpointsProtocol", "https")
        suffix = values.get("EndpointSuffix", "core.windows.net")
        values["BlobEndpoint"] = f"{protocol}://{values['AccountName']}.blob.{suffix}"

    return values


def _put_blob_if_absent(
    storage: Dict[str, str],
    container_name: str,
    blob_name: str,
    payload: bytes,
) -> None:
    account_name = storage["AccountName"]
    account_key = storage["AccountKey"]
    encoded_blob_name = "/".join(quote(part, safe="") for part in blob_name.split("/"))
    url = f"{storage['BlobEndpoint'].rstrip('/')}/{container_name}/{encoded_blob_name}"
    date = formatdate(usegmt=True)
    content_type = "application/json"
    headers = {
        "Content-Length": str(len(payload)),
        "Content-Type": content_type,
        "If-None-Match": "*",
        "x-ms-blob-type": "BlockBlob",
        "x-ms-date": date,
        "x-ms-version": "2023-11-03",
    }
    headers["Authorization"] = _storage_authorization_header(
        account_name=account_name,
        account_key=account_key,
        method="PUT",
        container_name=container_name,
        blob_name=blob_name,
        headers=headers,
    )
    request = Request(url, data=payload, headers=headers, method="PUT")

    try:
        with urlopen(request, timeout=30):
            return
    except HTTPError as error:
        if error.code in {409, 412}:
            return
        raise


def _storage_authorization_header(
    account_name: str,
    account_key: str,
    method: str,
    container_name: str,
    blob_name: str,
    headers: Dict[str, str],
) -> str:
    canonicalized_headers = "".join(
        f"{key.lower()}:{value}\n"
        for key, value in sorted(headers.items())
        if key.lower().startswith("x-ms-")
    )
    canonicalized_resource = f"/{account_name}/{container_name}/{blob_name}"
    string_to_sign = (
        f"{method}\n"
        "\n"
        "\n"
        f"{headers['Content-Length']}\n"
        "\n"
        f"{headers['Content-Type']}\n"
        "\n"
        "\n"
        "\n"
        f"{headers['If-None-Match']}\n"
        "\n"
        "\n"
        f"{canonicalized_headers}"
        f"{canonicalized_resource}"
    )
    decoded_key = base64.b64decode(account_key)
    signature = base64.b64encode(
        hmac.new(decoded_key, string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    ).decode("ascii")
    return f"SharedKey {account_name}:{signature}"


def run_once(config: EmailIntakeConfig, limit: Optional[int] = None) -> int:
    processed_count = 0

    with imaplib.IMAP4_SSL(config.host, config.port) as client:
        client.login(config.username, config.password)
        _check_ok(client.select(config.mailbox), f"select mailbox {config.mailbox}")
        uids = _search_uids(client, config.search_criteria)

        for uid in uids[:limit]:
            uid_text = uid.decode("ascii", errors="replace")
            try:
                raw_message = _fetch_message(client, uid)
                record = parse_email(raw_message, source_uid=uid_text)
                save_email_intake(record, config.output_path)
                if not config.dry_run and config.auto_reply:
                    send_auto_reply(record, config.auto_reply)

                if not config.dry_run:
                    _move_message(client, uid, config.processed_mailbox)
                processed_count += 1
            except Exception:
                if not config.dry_run:
                    _move_message(client, uid, config.failed_mailbox)
                raise

    return processed_count


def send_auto_reply(record: EmailIntakeRecord, config: AutoReplyConfig) -> bool:
    if not should_send_auto_reply(record):
        return False

    recipient = _reply_recipient(record)
    if not recipient:
        return False

    message = build_auto_reply_message(record, config, recipient)
    with smtplib.SMTP(config.smtp_host, config.smtp_port) as smtp:
        if config.use_starttls:
            smtp.starttls()
        smtp.login(config.smtp_username, config.smtp_password)
        smtp.send_message(message)
    return True


def should_send_auto_reply(record: EmailIntakeRecord) -> bool:
    recipient = _reply_recipient(record)
    if not recipient:
        return False

    lower_recipient = recipient.lower()
    if "no-reply" in lower_recipient or "noreply" in lower_recipient:
        return False
    if lower_recipient.startswith(("mailer-daemon@", "postmaster@")):
        return False

    auto_submitted = _record_header(record, "Auto-Submitted").lower()
    if auto_submitted and auto_submitted != "no":
        return False

    precedence = _record_header(record, "Precedence").lower()
    if precedence in {"bulk", "junk", "list"}:
        return False

    if _record_header(record, "List-ID") or _record_header(record, "List-Unsubscribe"):
        return False

    return True


def build_auto_reply_message(
    record: EmailIntakeRecord,
    config: AutoReplyConfig,
    recipient: str,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = config.from_address
    message["To"] = recipient
    message["Subject"] = config.subject
    message["Auto-Submitted"] = "auto-replied"

    if record.message_id and not record.message_id.startswith("sha256:"):
        message["In-Reply-To"] = record.message_id
        references = _record_header(record, "References")
        message["References"] = f"{references} {record.message_id}".strip()

    message.set_content(config.body)
    return message


def _reply_recipient(record: EmailIntakeRecord) -> Optional[str]:
    addresses = record.reply_to_addresses or record.from_addresses
    if not addresses:
        return None
    return addresses[0].address


def _record_header(record: EmailIntakeRecord, name: str) -> str:
    lower_name = name.lower()
    for key, value in record.headers.items():
        if key.lower() == lower_name:
            return value
    return ""


def main(argv: Optional[Sequence[str]] = None) -> int:
    load_env_files()

    parser = argparse.ArgumentParser(description="Fetch intake emails over IMAP.")
    parser.add_argument("--limit", type=int, help="Maximum number of messages to process.")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Move successfully processed messages to the processed mailbox.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run mode even if EMAIL_INTAKE_DRY_RUN=false.",
    )
    parser.add_argument("--output", type=Path, help="Override JSONL stub output path.")
    args = parser.parse_args(argv)

    config = EmailIntakeConfig.from_env()
    if args.commit:
        config.dry_run = False
    if args.dry_run:
        config.dry_run = True
    if args.output:
        config.output_path = args.output

    try:
        count = run_once(config, limit=args.limit)
    except imaplib.IMAP4.error as error:
        print(
            "IMAP login or mailbox operation failed. For Gmail, enable IMAP and use a "
            "Google app password instead of the normal account password.",
            file=sys.stderr,
        )
        print(f"IMAP error: {error}", file=sys.stderr)
        return 1

    mode = "dry run" if config.dry_run else "commit"
    print(f"Processed {count} email(s) in {mode} mode. Output: {config.output_path}")
    return 0


def load_env_files(paths: Sequence[Path] = ENV_PATHS) -> None:
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            key, value = _parse_env_line(line)
            if key and key not in os.environ:
                os.environ[key] = value


def _parse_env_line(line: str) -> Tuple[Optional[str], str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None, ""

    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _search_uids(client: imaplib.IMAP4_SSL, criteria: Iterable[str]) -> List[bytes]:
    status, data = client.uid("SEARCH", None, *criteria)
    _check_ok((status, data), "search messages")
    if not data or data[0] is None:
        return []
    return data[0].split()


def _fetch_message(client: imaplib.IMAP4_SSL, uid: bytes) -> bytes:
    status, data = client.uid("FETCH", uid, "(RFC822)")
    _check_ok((status, data), f"fetch message {uid!r}")

    for item in data:
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], bytes):
            return item[1]
    raise RuntimeError(f"IMAP fetch returned no RFC822 payload for UID {uid!r}")


def _move_message(client: imaplib.IMAP4_SSL, uid: bytes, mailbox: str) -> None:
    _ensure_mailbox(client, mailbox)
    status, data = client.uid("MOVE", uid, mailbox)
    if status == "OK":
        return

    status, data = client.uid("COPY", uid, mailbox)
    _check_ok((status, data), f"copy message {uid!r} to {mailbox}")
    _check_ok(client.uid("STORE", uid, "+FLAGS", r"(\Deleted)"), f"delete message {uid!r}")
    _check_ok(client.expunge(), "expunge deleted messages")


def _ensure_mailbox(client: imaplib.IMAP4_SSL, mailbox: str) -> None:
    status, _data = client.create(mailbox)
    if status not in {"OK", "NO"}:
        raise RuntimeError(f"Could not ensure mailbox exists: {mailbox}")


def _check_ok(response: Tuple[str, object], action: str) -> None:
    status, data = response
    if status != "OK":
        raise RuntimeError(f"IMAP failed to {action}: {data!r}")


def _clean_header(value: object) -> str:
    return "" if value is None else str(value).strip()


def _raw_message_id(raw_message: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw_message).hexdigest()}"


def _parse_addresses(values: Iterable[str]) -> List[EmailAddress]:
    return [
        EmailAddress(name=name, address=address)
        for name, address in getaddresses(values)
        if address
    ]


def _parse_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _extract_body(message: Message, content_type: str) -> str:
    texts = [_part_text(part) for part in _iter_content_parts(message, content_type)]
    return "\n\n".join(text for text in texts if text).strip()


def _iter_content_parts(message: Message, content_type: str) -> List[Message]:
    if not message.is_multipart():
        if message.get_content_type() == content_type and not _is_attachment(message):
            return [message]
        return []

    return [
        part
        for part in message.walk()
        if part.get_content_type() == content_type and not part.is_multipart() and not _is_attachment(part)
    ]


def _part_text(part: Message) -> str:
    if isinstance(part, EmailMessage):
        content = part.get_content()
        return content if isinstance(content, str) else ""

    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return str(part.get_payload() or "")
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _extract_attachments(message: Message) -> List[AttachmentInfo]:
    attachments: List[AttachmentInfo] = []

    for part in message.walk() if message.is_multipart() else [message]:
        if not _is_attachment(part):
            continue
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            AttachmentInfo(
                filename=part.get_filename(),
                content_type=part.get_content_type(),
                size_bytes=len(payload),
            )
        )

    return attachments


def _is_attachment(part: Message) -> bool:
    disposition = part.get_content_disposition()
    return disposition == "attachment" or bool(part.get_filename())


def _record_to_json(record: EmailIntakeRecord) -> Dict[str, object]:
    return asdict(record)


def _blob_record_datetime(record: EmailIntakeRecord) -> datetime:
    if record.received_at:
        try:
            return datetime.fromisoformat(record.received_at).astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _safe_blob_component(value: str) -> str:
    safe_chars = []
    for char in value.lower():
        if char.isalnum():
            safe_chars.append(char)
        elif char in {"-", "_", "."}:
            safe_chars.append(char)
        else:
            safe_chars.append("-")
    return "".join(safe_chars).strip("-")[:120] or "message"


if __name__ == "__main__":
    raise SystemExit(main())
