# Email Intake

The email intake worker fetches unread messages from an IMAP mailbox, parses them into a normalized audit record, and writes newline-delimited JSON to a local file. In commit mode, supported attachments are also uploaded through the backend blob storage adapter and inserted into the same document table used by the contractor and official portals.

## Local Run

Create `backend/.env` locally or export these values in your shell. The worker loads `.env` and `backend/.env` automatically without overriding already-exported environment variables.

```env
EMAIL_INTAKE_HOST=imap.example.com
EMAIL_INTAKE_PORT=993
EMAIL_INTAKE_USERNAME=intake@example.com
EMAIL_INTAKE_PASSWORD=<mailbox-app-password>
EMAIL_INTAKE_MAILBOX=INBOX
EMAIL_INTAKE_SEARCH=UNSEEN
EMAIL_INTAKE_OUTPUT_PATH=backend/data/email_intake.jsonl
EMAIL_INTAKE_DRY_RUN=true
EMAIL_INTAKE_DEFAULT_UPLOADER_ID=contractor-demo
EMAIL_INTAKE_DEFAULT_DOCUMENT_TYPE=Email Attachment
EMAIL_INTAKE_AUTO_REPLY_ENABLED=false
```

Run a dry-run fetch:

```sh
bun run email:intake -- --limit 5
```

Dry-run mode writes parsed JSON but does not move email out of the inbox. Once the parsed output looks right, run commit mode:

```sh
bun run email:intake -- --limit 5 --commit
```

Commit mode writes the JSON audit record, stores supported attachments as portal documents, and then moves the email to the `Processed` mailbox. If a processing error occurs, it moves the email to `Failed`.

Until real contractor accounts are added, emailed attachments are assigned to `EMAIL_INTAKE_DEFAULT_UPLOADER_ID`, which defaults to the mock contractor `contractor-demo`. That means they appear on the mock contractor page and on the official review page. Unsupported attachment types are skipped; the accepted types match the web upload form: PDF, DOC, DOCX, TXT, CSV, XLSX, PNG, JPG, and JPEG.

## Auto Reply

Auto-replies are disabled by default. Enable them only after dry-run parsing looks correct:

```env
EMAIL_INTAKE_AUTO_REPLY_ENABLED=true
EMAIL_INTAKE_SMTP_HOST=smtp.gmail.com
EMAIL_INTAKE_SMTP_PORT=587
EMAIL_INTAKE_SMTP_STARTTLS=true
EMAIL_INTAKE_SMTP_USERNAME=<intake-email-address>
EMAIL_INTAKE_SMTP_PASSWORD=<mailbox-app-password>
EMAIL_INTAKE_AUTO_REPLY_FROM=<intake-email-address>
EMAIL_INTAKE_AUTO_REPLY_SUBJECT=Your email has been received
EMAIL_INTAKE_AUTO_REPLY_BODY=Your email has been received. Thank you.
```

If `EMAIL_INTAKE_SMTP_USERNAME` or `EMAIL_INTAKE_SMTP_PASSWORD` are omitted, the worker reuses `EMAIL_INTAKE_USERNAME` and `EMAIL_INTAKE_PASSWORD`.

The worker sends auto-replies only in commit mode. It skips obvious automated, list, bulk, postmaster, mailer-daemon, and no-reply messages to reduce mail loops.

## JSONL Audit Record

The JSONL audit writer is:

```python
def save_email_intake(record: EmailIntakeRecord, output_path: Path) -> None:
    ...
```

- `message_id`
- `source_uid`
- `subject`
- `from_addresses`
- `reply_to_addresses`
- `to_addresses`
- `cc_addresses`
- `received_at`
- `ingested_at`
- `body_text`
- `body_html`
- `attachments`
- `headers`
- `raw_sha256`

If a message has no `Message-ID` header, the worker uses a SHA-256 hash of the raw message. Attachment document rows use a deterministic id derived from message id, attachment index, filename, and attachment bytes. Rerunning the same email does not create duplicate portal documents.

## Azure VM Timer

On the Azure Linux VM, install the app and Python dependencies, then create an env file readable only by the service user:

```sh
sudo mkdir -p /etc/federal-center-sw
sudo nano /etc/federal-center-sw/email-intake.env
sudo chmod 600 /etc/federal-center-sw/email-intake.env
```

Example service unit at `/etc/systemd/system/fcsw-email-intake.service`:

```ini
[Unit]
Description=Federal Center SW email intake

[Service]
Type=oneshot
WorkingDirectory=/opt/federal-center-sw
EnvironmentFile=/etc/federal-center-sw/email-intake.env
ExecStart=/opt/federal-center-sw/.venv/bin/python -m app.email_intake --commit
Environment=PYTHONPATH=/opt/federal-center-sw/backend
```

Example timer at `/etc/systemd/system/fcsw-email-intake.timer`:

```ini
[Unit]
Description=Run Federal Center SW email intake every minute

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
Unit=fcsw-email-intake.service

[Install]
WantedBy=timers.target
```

Enable it:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now fcsw-email-intake.timer
sudo systemctl status fcsw-email-intake.timer
```

View logs:

```sh
journalctl -u fcsw-email-intake.service -n 100 --no-pager
```

## Mailbox Choice

If the intake mailbox is Microsoft 365, prefer Microsoft Graph later for production-grade auth and mailbox access. This IMAP worker is still the right first step for simple intake, especially with a mailbox provider that supports app passwords.
