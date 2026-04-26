# Federal Center SW

Starter framework with a TypeScript frontend and Python backend.

## Stack

- Frontend: React, TypeScript, Vite, Vitest, ESLint
- Backend: Python, FastAPI, Uvicorn, Pytest

## Project Structure

```text
.
├── backend/
│   ├── app/
│   │   └── main.py
│   ├── tests/
│   ├── pyproject.toml
│   ├── requirements-dev.txt
│   └── requirements.txt
├── docs/
├── infra/
├── scripts/
├── compose.yaml
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
└── package.json
```

## Setup

Install frontend dependencies:

```sh
bun install
```

Create and install backend dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
```

## Development

Start local backing services:

```sh
bun run local:up
```

Run the backend API:

```sh
bun run dev:backend
```

Run the frontend in another terminal:

```sh
bun run dev:frontend
```

Or run both together:

```sh
bun run dev
```

The frontend runs on `http://localhost:5173` and proxies `/api/*` requests to the backend on `http://127.0.0.1:8000`.

See [docs/local-dev.md](docs/local-dev.md) for the Docker-based local mirror of PostgreSQL and Blob Storage.

## Product Direction

The product direction is documented in [docs/product.md](docs/product.md). It covers the
target CO/COR/PM users, Entra ID/RBAC access model, contract records, report intake
sources, document processing pipeline, and first dashboard deliverables.

## Checks

```sh
bun run build
bun run lint
bun run test
```

## Infrastructure

Azure infrastructure is defined with Bicep in `infra/`.

Preview infrastructure changes:

```sh
bun run infra:whatif
```

Apply infrastructure changes:

```sh
bun run infra:deploy
```

See [docs/infra.md](docs/infra.md) for the Bicep/GitHub Actions workflow and drift policy.

## Pull Request Notifications

Pull request notifications can post to a Discord `#pull-requests` channel through
`.github/workflows/discord-pr-notifications.yml`. Create a Discord webhook in that
channel and add its URL to the GitHub repository secret
`DISCORD_PULL_REQUEST_WEBHOOK_URL`.

## Mock Auth And Document Ingest

The app starts with a mock role login. Choose `Contractor` to upload documents, or `Government official` to review contractor uploads. Uploaded files are stored through the backend blob storage adapter and document metadata is stored in the backend database.
Each uploaded or emailed document also gets a sibling extraction artifact:

```text
documents/{uploader_id}/{document_id}/{original_filename}
documents/{uploader_id}/{document_id}/text.json
```

`text.json` stores extracted text and extraction metadata for later contract processing.
PDFs use embedded text when it is usable. Scanned PDFs, PDFs with low-quality embedded
OCR, and uploaded images fall back to Tesseract OCR when it is installed.

For local development without Azure env values, the backend falls back to ignored local storage under `backend/data/`. For Azure-backed runs, fill in `DATABASE_URL`, `AUTH_SECRET_KEY`, and the `AZURE_STORAGE_*` variables in `backend/.env`.

## Email Intake

The backend includes an IMAP intake worker that parses unread mailbox messages into JSONL audit records. In commit mode, supported attachments are uploaded to the same document storage used by the portal and become visible to the mock contractor and official review pages. It can also send an optional receipt auto-reply. Configure it with `EMAIL_INTAKE_*` environment variables, then run:

```sh
bun run email:intake -- --limit 5
```

Use `--commit` only after dry-run output looks correct; commit mode moves processed messages to a `Processed` mailbox. See [docs/email-intake.md](docs/email-intake.md).

## Cloud

Azure resource inventory, access steps, PostgreSQL commands, and Blob Storage commands are documented in [docs/cloud.md](docs/cloud.md).

Local development mirrors the cloud-facing PostgreSQL and Blob Storage contract with Docker Compose. Keep Azure inventory and access notes in `docs/cloud.md`, infrastructure workflow notes in `docs/infra.md`, and local mirror instructions in `docs/local-dev.md`.
