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
new or reset documents.

An optional local feature extractor service lives in `feature_extractor/`. It can read
`contracts/{document_id}/text.json`, generate a layered summary, classify PSC/NAICS,
extract structured primitives (deliverable, financial, decisions, issue, personnel) into
the DB, and write `contracts/{document_id}/summary.json`. The main analyst pipeline does not
require it; it is supplemental to the DB-backed processing store.

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

## AI Processing Foundation

The backend stores uploaded source files and extracted `text.json` artifacts in Blob
Storage, while Postgres is the canonical store for contract records, processing jobs,
chunks, embeddings, signals, topics, evidence links, and audit history. Local Postgres
uses a pgvector-enabled image so embeddings can live beside contract-scoped metadata.

AI processing is feature-flagged off by default. Configure `AI_PROVIDER`,
`AI_PROCESSING_ENABLED`, `AI_INLINE_PROCESSING_ENABLED`, `OPENAI_API_KEY`,
`OPENAI_LLM_MODEL`, and `OPENAI_EMBEDDING_MODEL` in an ignored env file or Azure app
settings before running OpenAI-backed extraction. Upload and email intake workflows
continue to store documents when AI processing is disabled or blocked.

The contract analyst pipeline extends the processing foundation with page-level
extraction, deterministic v1 classification, hard-link matching, extracted entities
and report facts, interpreted baselines, regression findings, hypotheses,
investigation logs, official external-source references, semantic links, and
step-level run logs. Hard parentage stays on `document_uploads.contract_id`;
cross-contract and cross-document pattern relationships are stored separately as
semantic links. When an unmatched upload is confidently classified as a source
contract or task order and exactly one contract number is extracted, processing
auto-creates a `pending_review` contract record, links the upload, and writes a
`contract.auto_created` audit event for official review.

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
to inspect the contract analyst workspace. Uploaded files are stored
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

Email or portal uploads that cannot match an existing contract remain unmatched unless
processing can safely scaffold a new parent. Auto-scaffolding only runs for high
confidence `source_contract` or `task_order` classifications with one regex-extracted
contract number; the created contract is marked `pending_review` and records its source
document in audit history.

Government officials see a contract-first analysis workspace. The current v1 view uses
existing extracted primitives and wiki records to show a cited contract brief,
chronological report signals, recurring versus one-off issues, early warnings before
degradation, positive signals, contractor execution patterns, CPARS outcome context
when imported, and cohort-level pattern comparisons.

For local development without Azure env values, the backend falls back to ignored
local storage under `backend/data/`. For Azure-backed runs, fill in `DATABASE_URL`,
`AUTH_SECRET_KEY`, and the `AZURE_STORAGE_*` variables in `backend/.env`.

## Email Intake

The backend includes an IMAP intake worker that parses unread mailbox messages into JSONL audit records. In commit mode, supported attachments are uploaded to the same contract-folder storage used by the portal and become visible to the mock contractor portal and official analyst workspace. It can also send an optional receipt auto-reply. Configure it with `EMAIL_INTAKE_*` environment variables, then run:

```sh
bun run email:intake -- --limit 5
```

Use `--commit` only after dry-run output looks correct; commit mode moves processed messages to a `Processed` mailbox. See [docs/email-intake.md](docs/email-intake.md).

## Cloud

Azure resource inventory, access steps, PostgreSQL commands, and Blob Storage commands are documented in [docs/cloud.md](docs/cloud.md).

Local development mirrors the cloud-facing PostgreSQL and Blob Storage contract with Docker Compose. Keep Azure inventory and access notes in `docs/cloud.md`, infrastructure workflow notes in `docs/infra.md`, and local mirror instructions in `docs/local-dev.md`.
