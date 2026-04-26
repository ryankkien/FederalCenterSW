# Email Intake

The email intake worker fetches unread messages from an IMAP mailbox and parses them into a normalized audit record. Locally, the audit record can be written as newline-delimited JSON; in Azure Functions, it can write durable JSON records to Blob Storage. In commit mode, supported attachments are also uploaded through the backend blob storage adapter, run deterministic intake classification and contract matching, and are inserted into the same document table used by the contractor and official portals.

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

Until real contractor accounts are added, emailed attachments are assigned to `EMAIL_INTAKE_DEFAULT_UPLOADER_ID`, which defaults to the mock contractor `contractor-demo`. That means they appear on the mock contractor portal and on the official analyst workspace. Unsupported attachment types are skipped; the accepted types match the web upload form: PDF, DOC, DOCX, TXT, CSV, XLSX, PNG, JPG, and JPEG.

Each committed attachment runs the same inline deterministic intake step as portal
uploads. Filename, email-subject-derived title, notes, and configured document type
can set the initial `document_kind`; filename, title, and notes can also match a known
contract number and hard-link `document_uploads.contract_id`. The decisions are
persisted to `document_classification_decisions` and `document_match_decisions` with
deterministic source metadata. OCR, full text classification, and AI fallback matching
remain processing-job work.

## Auto Reply

Auto-replies are sent through [Resend](https://resend.com). They are disabled by default. Enable them only after dry-run parsing looks correct and the sender domain is verified in Resend:

```env
EMAIL_INTAKE_AUTO_REPLY_ENABLED=true
RESEND_API_KEY=<resend-api-key>
EMAIL_INTAKE_AUTO_REPLY_FROM=<verified-sender-on-resend-domain>
EMAIL_INTAKE_AUTO_REPLY_SUBJECT=Your email has been received
EMAIL_INTAKE_AUTO_REPLY_BODY=Your email has been received. Thank you.
```

`EMAIL_INTAKE_AUTO_REPLY_FROM` must be on a domain you have verified in Resend (SPF, DKIM, DMARC). Keep `RESEND_API_KEY` in an ignored local env file, Azure app settings, or Key Vault.

The worker sends auto-replies only in commit mode. It threads each reply by setting `In-Reply-To` and `References` headers on the Resend send request, sets `Auto-Submitted: auto-replied`, and skips obvious automated, list, bulk, postmaster, mailer-daemon, and no-reply messages to reduce mail loops.

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

## Azure Function Timer

The preferred deployment is an Azure Function timer trigger, not a VM. The function lives in `backend/function_app.py` and uses the same `app.email_intake` worker. The same Function App also hosts the queued document processing timer so emailed attachments and portal uploads can move from `queued` to analyzed without a manual CLI run.

Create a Linux Python Function App with Bicep, configure non-secret `EMAIL_INTAKE_*`
settings, populate Key Vault secrets, then deploy the `backend/` folder. The repo deploys
this automatically from `.github/workflows/function-deploy.yml` after backend changes land
on `main`, and the workflow can also be run manually.

The deployment workflow uses the `azure-dev` GitHub environment plus these repository values:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_FUNCTION_APP_NAME`

The timer schedule uses Azure Functions NCRONTAB format:

```env
EMAIL_INTAKE_TIMER_SCHEDULE=0 */5 * * * *
DOCUMENT_PROCESSING_TIMER_SCHEDULE=0 */5 * * * *
DOCUMENT_PROCESSING_LIMIT=25
```

Those examples run every five minutes. Use `0 */1 * * * *` for every minute. The document processing timer drains queued jobs that already have extracted text and leaves `extraction_status="pending_ocr"` jobs queued until `text.json` is ready.

For serverless deployment, enable the durable JSON stub so parsed records go to Azure Blob Storage instead of an ephemeral local file:

```env
EMAIL_INTAKE_DRY_RUN=false
EMAIL_INTAKE_STUB_BLOB_ENABLED=true
EMAIL_INTAKE_STUB_BLOB_CONTAINER=app-assets
EMAIL_INTAKE_STUB_BLOB_PREFIX=email-intake
```

The Function App reads secret-bearing settings through Key Vault references configured by
`infra/main.bicep`. Populate these vault secrets before enabling the timer:

```text
database-url
app-storage-connection-string
function-storage-connection-string
email-intake-host
email-intake-username
email-intake-password
openai-api-key
resend-api-key
internal-service-token
```

`AZURE_STORAGE_CONNECTION_STRING` and `DATABASE_URL` remain the application env variable
names, but their app setting values should be Key Vault references rather than raw
connection strings. The same storage and database settings are used to write email audit
records, store emailed attachments, read document artifacts, and drain queued processing
jobs.

Useful Azure CLI shape:

```sh
az functionapp create \
  --resource-group federal-center-sw-dev \
  --name <globally-unique-function-app-name> \
  --storage-account <storage-account-name> \
  --flexconsumption-location eastus \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4

az functionapp config appsettings set \
  --resource-group federal-center-sw-dev \
  --name <function-app-name> \
  --settings EMAIL_INTAKE_HOST=imap.gmail.com

az functionapp deployment source config-zip \
  --resource-group federal-center-sw-dev \
  --name <function-app-name> \
  --src function.zip
```

## Legacy VM Timer

A VM can still run the worker, but it is no longer the preferred path for this project. If a VM is used, run `PYTHONPATH=backend .venv/bin/python -m app.email_intake --commit` from a systemd timer.

Example service unit:

```ini
[Service]
Type=oneshot
WorkingDirectory=/opt/federal-center-sw
EnvironmentFile=/etc/federal-center-sw/email-intake.env
ExecStart=/opt/federal-center-sw/.venv/bin/python -m app.email_intake --commit
Environment=PYTHONPATH=/opt/federal-center-sw/backend
```

View logs:

```sh
journalctl -u fcsw-email-intake.service -n 100 --no-pager
```

## Mailbox Choice

If the intake mailbox is Microsoft 365, prefer Microsoft Graph later for production-grade auth and mailbox access. This IMAP worker is still the right first step for simple intake, especially with a mailbox provider that supports app passwords.
