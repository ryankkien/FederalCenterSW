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

Backend, feature extractor, and email intake logs are emitted as structured JSON with
`request_id`, `contract_id`, `document_upload_id`, and `processing_run_id` fields when
available. Set `APPINSIGHTS_CONNECTION_STRING` to export telemetry to Azure Application
Insights; leave it blank for local-only JSON logs.

## Product Direction

The product direction is documented in [docs/product.md](docs/product.md). It covers the
target CO/COR/PM users, Entra ID/RBAC access model, contract records, report intake
sources, CPARS/IPMDAR source planning, document processing pipeline, and first
dashboard deliverables.

Local fixture PDFs for contract and recurring-report processing are documented in
[docs/testdocs.md](docs/testdocs.md).

## Checks

```sh
bun run db:upgrade
bun run build
bun run lint
bun run test
```

## Local Analyst Fixtures

Seed the bundled WWR, AGOR, and Natalie contract/report fixtures into the local
database and blob backend:

```sh
bun run fixtures:seed -- --fixtures all
bun run fixtures:seed -- --fixtures wwr,natalie --reset-analysis
bun run processing:run -- --limit 200
```

Fixture seeding is idempotent. Document IDs are deterministic from fixture path and
file hash, PDFs are copied to `contracts/{document_id}/main.pdf`, extracted text is
stored at `contracts/{document_id}/text.json`, and processing jobs are queued for
new or reset documents. In Azure, the backend Function App drains queued document
processing jobs on `DOCUMENT_PROCESSING_TIMER_SCHEDULE`; locally, use
`bun run processing:run -- --limit 200` for an immediate drain.

An optional local feature extractor service lives in `feature_extractor/`. It can read
`contracts/{document_id}/text.json`, generate a layered summary, classify PSC/NAICS,
extract structured primitives (deliverable, financial, decisions, issue, personnel) into
the DB, and write `contracts/{document_id}/summary.json`. When `FEATURE_EXTRACTOR_URL`
is configured for the backend, completed document processing runs automatically call
`/summarize` and then `/extract-primitives`; extractor failures are recorded on the
processing run and do not roll back the completed run. When `BACKEND_API_URL` and
`INTERNAL_SERVICE_TOKEN` are configured, successful primitive extraction asks the
backend to enqueue a debounced per-contract analysis run for the document's
`contract_id`.
The main analyst pipeline does not require it; it is supplemental to the DB-backed
processing store.

## Infrastructure

Azure infrastructure is defined with Bicep in `infra/`.
The template provisions the shared Log Analytics workspace, Azure Application Insights
component, Function App resources, storage, database, ACR, and Container Apps environment.

Preview infrastructure changes:

```sh
bun run infra:whatif
```

Apply infrastructure changes:

```sh
bun run infra:deploy
```

See [docs/infra.md](docs/infra.md) for the Bicep/GitHub Actions workflow and drift policy.
Azure secrets are stored in Key Vault and consumed by the Function App and Feature Extractor
Container App through user-assigned managed-identity Key Vault references, not raw app
setting values.

The optional feature extractor cloud service is deployed by
`.github/workflows/feature-extractor-deploy.yml` from the `feature_extractor/` image
into the dev Container App `fcsw-feature-extractor-dev`.

## Pull Request Notifications

Pull request notifications can post to a Discord `#pull-requests` channel through
`.github/workflows/discord-pr-notifications.yml`. Create a Discord webhook in that
channel and add its URL to the GitHub repository secret
`DISCORD_PULL_REQUEST_WEBHOOK_URL`.

## AI Processing Foundation

The backend stores uploaded source files and extracted `text.json` artifacts in Blob
Storage, while Postgres is the canonical store for contract records, processing jobs,
chunks, embeddings, signals, topics, evidence links, and audit history. Local Postgres
uses a pgvector-enabled image so embeddings can live beside contract-scoped metadata.

AI processing defaults on when `OPENAI_API_KEY` is set and the AI flags are omitted.
Configure `AI_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_LLM_MODEL`, and
`OPENAI_EMBEDDING_MODEL` in an ignored env file or Azure Key Vault-backed app setting
before running OpenAI-backed extraction. Set `AI_PROCESSING_ENABLED=false` or
`AI_INLINE_PROCESSING_ENABLED=false` to force-disable either path. Upload and email intake
workflows continue to store documents when AI processing is disabled or blocked.

Queued document processing runs automatically in Azure through the timer trigger in
`backend/function_app.py`. The worker skips jobs whose `text.json` still has
`extraction_status="pending_ocr"` so OCR-delayed documents stay queued until extracted
text is available.

The contract analyst pipeline extends the processing foundation with page-level
extraction, deterministic v1 classification, hard-link matching, extracted entities
and report facts, interpreted baselines, regression findings, hypotheses,
investigation logs, official external-source references, semantic links, and
step-level run logs. Hard parentage stays on `document_uploads.contract_id`;
cross-contract and cross-document pattern relationships are stored separately as
semantic links.

Kind-specific routing runs after the generic extraction pass. CPARS-style documents
populate `cpars_ratings`, modifications populate `contract_primitives_decisions` and
append `baseline_revisions`, and GAO/OIG reports are stored as official
`external_source_refs` for the linked contract instead of becoming baseline evidence.

The knowledge wiki index is a server-backed Grokipedia-style layer for officials. It
mines seeded local fixture contracts, processed report evidence, and the generated
synthetic fixture corpus by default. Optional official-source clients remain available
for deliberate research runs, but they are not part of the default local ingest.
Contractor profiles use evidence labels such as schedule variance, funding variance,
unresolved issues, and contradiction counts; they do not make unsupported honesty or
responsibility judgments.

Local analyst endpoints include:

```text
GET  /api/contracts
POST /api/knowledge/ingestion-runs
GET  /api/wiki/search
GET  /api/wiki/contracts/{contract_id}
GET  /api/wiki/contractors/{vendor_uei}
GET  /api/wiki/nodes/{node_id}
GET  /api/wiki/runs/{run_id}
GET  /api/contracts/{contract_id}/documents
GET  /api/contracts/{contract_id}/evidence
GET  /api/contracts/{contract_id}/analysis-runs
POST /api/processing/jobs/{job_id}/run
GET  /api/contracts/{contract_id}/baseline
GET  /api/contracts/{contract_id}/regressions
GET  /api/contracts/{contract_id}/hypotheses
GET  /api/contracts/{contract_id}/hypotheses/{hypothesis_id}
POST /api/contracts/{contract_id}/hypotheses/{hypothesis_id}/investigate
POST /api/contracts/{contract_id}/hypotheses/{hypothesis_id}/status
GET  /api/contracts/{contract_id}/similar-contracts
GET  /api/contracts/{contract_id}/similarity-insights
GET  /api/documents/{document_id}
GET  /api/documents/{document_id}/relationships
POST /api/documents/{document_id}/match-decisions
POST /api/documents/{document_id}/processing-jobs
```

External research references are v1 allowlisted to official sources such as `.gov`,
`.mil`, Acquisition.gov, Federal Register, GAO/OIG, Congress.gov, and agency domains.
Uploaded contract-file evidence remains authoritative for contract-specific findings.

Build the local wiki index after fixture processing:

```sh
bun run corpus:build-synthetic
bun run knowledge:ingest -- --scope fixtures --sources local --limit 500
bun run knowledge:build -- --scope fixtures
```

Build a file-first Navy service fixture corpus from the three downloaded fixture
families plus clearly labeled synthetic reports and knowledge artifacts:

```sh
bun run corpus:build-synthetic
```

The generated corpus lives under ignored `backend/data/corpus/navy-service-v1/` and
keeps `real_fixture` downloaded anchors separate from `synthetic_fixture` reports,
CPARS-style narratives, IPMDAR-style JSON, decision logs, and cross-contract lesson
notes. Each contract has one CPARS-style `cpars_evaluation` fixture for extraction
testing; these generated records are not real CPARS data.

## Auth Modes

Set `AUTH_MODE=mock` for local development and tests. Mock mode exposes
`POST /api/auth/mock-login` and returns deterministic contractor/official demo users.

Set `AUTH_MODE=entra` for production-style auth. Entra mode disables mock login,
validates JWT issuer, audience, expiry, and JWKS signature, and maps Entra user/group
ids to `contract_access_grants.principal_id` for contract-scoped RBAC.

## Document Ingest

In mock local mode, choose `Contractor` to upload documents or `Government official`
to inspect the contract analyst workspace and review queue. Uploaded files are stored
through the backend blob storage adapter and document metadata is stored in Postgres.
Each upload gets an immutable document artifact folder:

```text
contracts/{document_id}/main.{ext}
contracts/{document_id}/text.json
```

`main.*` is the primary stored file. PDFs stay PDF, and TXT/CSV/image uploads are
converted to PDF when the backend can do that locally. `text.json` stores extracted
text, page text, extraction metadata, and warnings/errors for later contract
processing.
For PDFs with embedded text, extraction uses the PDF text layer. For scanned PDFs and
uploaded images, extraction falls back to OCR when Tesseract is installed.

Contractor uploads include a visible contract selector. The selected contract is stored
as `document_uploads.contract_id`, so new reports immediately become child documents of
the contract while semantic cross-document and cross-contract relationships remain
separate.

Portal uploads run cheap deterministic intake decisions before the async processor:
filename, title, notes, and type cues update `document_kind`, `match_status`, and
`contract_id` when a known contract number is found. The upload response includes
`detected_kind` and `matched_contract_id`; full text classification and AI-assisted
matching still run later through processing jobs.

Government officials see a contract-first analysis workspace. The current v1 view uses
existing extracted primitives and wiki records to show a cited contract brief,
chronological report signals, recurring versus one-off issues, early warnings before
degradation, positive signals, contractor execution patterns, CPARS outcome context
when imported, cohort-level pattern comparisons, similar-contract failure points, and
drafting guidance for future contract writing. Similarity insights use chunk embeddings
when available, stored semantic links when available, and cohort metadata as a fallback.

For local development without Azure env values, the backend falls back to ignored
local storage under `backend/data/`. For Azure-backed runs, fill in `DATABASE_URL`,
`AUTH_SECRET_KEY`, and the `AZURE_STORAGE_*` variables in `backend/.env`.

## Email Intake

The backend includes an IMAP intake worker that parses unread mailbox messages into JSONL audit records. In commit mode, supported attachments are uploaded to the same contract-folder storage used by the portal, run the same deterministic intake decisions, and become visible to the mock contractor portal and official analyst workspace. It can also send an optional receipt auto-reply. Configure it with `EMAIL_INTAKE_*` environment variables, then run:

```sh
bun run email:intake -- --limit 5
```

Use `--commit` only after dry-run output looks correct; commit mode moves processed messages to a `Processed` mailbox. See [docs/email-intake.md](docs/email-intake.md).

## Cloud

Azure resource inventory, access steps, PostgreSQL commands, and Blob Storage commands are documented in [docs/cloud.md](docs/cloud.md).

Local development mirrors the cloud-facing PostgreSQL and Blob Storage contract with Docker Compose: PostgreSQL 16 plus pgvector, database `federal_center_sw`, and private Blob container `app-assets`. The Azure Function deploy workflow writes the matching non-secret app settings and expects the database and storage connection strings in GitHub secrets. Keep Azure inventory and access notes in `docs/cloud.md`, infrastructure workflow notes in `docs/infra.md`, and local mirror instructions in `docs/local-dev.md`.
