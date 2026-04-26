# Local Development Mirror

The local mirror is for development and testing only. It mirrors the app-facing service
contract of Azure without trying to run Azure control-plane resources locally.

Local services:

- PostgreSQL 16 with pgvector in Docker, matching the Azure PostgreSQL major version
  plus the `vector` extension used for document chunk embeddings.
- Azurite in Docker, matching the Blob Storage API used by email intake stub persistence.
- Local env values in `backend/.env.local`, copied from `backend/.env.local.example`.

Start local dependencies:

```sh
bun run local:up
```

This requires Docker Desktop plus either the backend Python dependencies or Azure CLI.
The Python Azure Blob SDK is preferred for initializing the local Azurite blob
container, with Azure CLI as a fallback. `local:up` retries Azurite container setup for
up to `AZURITE_SETUP_RETRIES` attempts; the default is 90 seconds for slower CI runners.

Stop local dependencies:

```sh
bun run local:down
```

Reset local dependency data:

```sh
bun run local:reset
```

Run the app normally after `local:up`:

```sh
bun run db:upgrade
bun run dev
```

Seed and process local contract analyst fixtures:

```sh
bun run fixtures:seed -- --fixtures all
bun run processing:run -- --limit 200
bun run corpus:build-synthetic
bun run knowledge:ingest -- --scope fixtures --sources local --limit 500
bun run knowledge:build -- --scope fixtures
```

Use `--reset-analysis` when you want to clear derived pages, chunks, entities, facts,
baselines, findings, hypotheses, semantic links, and run logs for the seeded fixture
documents while keeping the source PDFs and contract/document rows:

```sh
bun run fixtures:seed -- --fixtures wwr,natalie --reset-analysis
```

Knowledge ingestion uses local fixture documents and generated synthetic fixture
evidence by default. Optional keyed/import sources are controlled with local-only env
vars and should be used only for deliberate research runs:

```env
SAM_API_KEY=
REGULATIONS_API_KEY=
CPARS_IMPORT_DIR=
```

When optional sources are not configured, deliberate optional-source runs persist
`source_unavailable` records so the wiki can show the limitation without failing.

## Mirroring Rules

Keep the cloud and local environments mirrored at the contract level:

- Same database name: `federal_center_sw`.
- Same app database user name: `fcadmin`.
- Same Blob container name: `app-assets`.
- Same backend env variable names as Azure app settings.
- Same email intake blob prefix shape, with a local-only prefix by default:
  `email-intake-local`.

Local values may use different hosts, passwords, and storage account names. Those values
must remain local-only and should not be copied into Bicep or Azure app settings.

## What Belongs Where

- Cloud resource definitions: `infra/main.bicep`.
- Cloud environment values: `infra/dev.bicepparam`.
- Local service definitions: `compose.yaml`.
- Local app env example: `backend/.env.local.example`.
- Real local app env file: `backend/.env.local`, ignored by git.
- Shared env contract examples: `backend/.env.example`.

Local services emit structured JSON logs by default. Leave
`APPINSIGHTS_CONNECTION_STRING` blank for local-only logs, or set it in an ignored env
file or shell export when you intentionally want local telemetry sent to the shared Azure
Application Insights component. `X-Request-ID` is echoed on FastAPI responses and
forwarding helpers preserve it for service-to-service calls.

## Azurite Notes

`bun run local:up` creates the local `app-assets` container in Azurite. The email intake
worker can then write blob stub records when these local env values are active:

```env
EMAIL_INTAKE_STUB_BLOB_ENABLED=true
EMAIL_INTAKE_STUB_BLOB_CONTAINER=app-assets
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;...
```

On slow Docker hosts or cold CI runners, `local-up.sh` waits for PostgreSQL and Azurite
before creating the blob container. Override `POSTGRES_READY_ATTEMPTS` or
`AZURITE_SETUP_RETRIES` only when the default readiness window is not long enough.
Compose starts Azurite with `--skipApiVersionCheck` so newer Azure CLI storage clients
can still talk to the pinned local emulator image.

Portal uploads, fixture PDFs, and committed email attachments use the same local blob
layout as Azure:

```text
contracts/{document_id}/main.{ext}
contracts/{document_id}/text.json
```

The `document_id` folder is the immutable document artifact folder. Contract hard
parentage lives in Postgres on `document_uploads.contract_id`; semantic links never
rewrite that parent contract.

## pgvector Notes

Local Compose uses a pgvector-enabled Postgres 16 image. If an existing local volume was
created with the previous plain Postgres image, reset the local mirror before applying
vector migrations:

```sh
bun run local:reset
bun run local:up
bun run db:upgrade
```

The app migration creates `CREATE EXTENSION IF NOT EXISTS vector` on PostgreSQL. SQLite
test databases skip the extension and keep vector-backed behavior covered by Postgres
integration tests.

## AI Processing Notes

AI processing stays disabled when `OPENAI_API_KEY` is unset. When the key is present
and the AI flags are omitted, both processing and inline processing default on:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_LLM_MODEL=gpt-5.4-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
```

Set `OPENAI_API_KEY` only in ignored local env files or deployed app settings. When AI is
disabled, unset, or misconfigured, uploads and email intake still store documents and
create processing jobs; extraction and indexing remain blocked until configuration is
enabled. To force-disable either path even with a key present, set
`AI_PROCESSING_ENABLED=false` or `AI_INLINE_PROCESSING_ENABLED=false`.

## Synthetic Corpus Notes

For file-first knowledge testing, build a local Navy service-contract fixture corpus
from the three downloaded fixture families plus clearly labeled synthetic evidence:

```sh
bun run corpus:build-synthetic
```

The command writes ignored artifacts to `backend/data/corpus/navy-service-v1/`:

- `manifest.json`: contract, document, provenance, permission, and pattern metadata.
- `extraction_packet.jsonl`: flattened rows for cheap labeling and higher-quality
  synthesis.
- `synthetic/`: generated markdown and JSON reports, including CPARS-style narratives,
  IPMDAR-style CPD JSON, decision logs, corrective actions, and cross-contract lesson
  notes.

Synthetic documents are always marked `synthetic_fixture`; downloaded fixture anchors
from `testdocs/` are marked `real_fixture`. Keep that distinction visible in any UI,
model prompt, or export that uses the corpus.

## Auth Notes

Local development defaults to `AUTH_MODE=mock`, which keeps `/api/auth/mock-login`
available for contractor and official demo users. Production-style runs use
`AUTH_MODE=entra`; the backend validates Entra JWT issuer, audience, expiry, and JWKS
signature, then maps Entra user and group ids to `contract_access_grants.principal_id`.

## OCR Notes

PDF text extraction uses embedded PDF text when the text layer is usable. Scanned PDFs,
PDFs with low-quality embedded OCR, and uploaded images need OCR. The backend renders
PDF pages with PyMuPDF and calls the local Tesseract binary.

Install Tesseract locally before testing scanned documents:

```sh
brew install tesseract
```

Optional OCR environment variables:

```env
DOCUMENT_OCR_TESSERACT_CMD=tesseract
DOCUMENT_OCR_LANGUAGE=eng
DOCUMENT_OCR_MAX_PAGES=25
DOCUMENT_OCR_DPI_SCALE=2.0
```

When Tesseract is missing, uploads still succeed. `text.json` records the extraction
failure, or falls back to embedded PDF text with a warning when usable embedded text is
available. Long PDFs are limited by `DOCUMENT_OCR_MAX_PAGES` so synchronous uploads do
not spend unbounded time in OCR.

## Optional Feature Extractor Notes

The local Compose file includes an optional `feature_extractor` service on port `8001`. It is
not started by `bun run local:up`; start it explicitly when you want layered summary,
PSC/NAICS classification, and primitive extraction output:

```sh
docker compose up -d feature_extractor
```

The service reads `contracts/{document_id}/text.json`, falls back to legacy
`documents/{doc_id}/ocr.json`, and writes `contracts/{document_id}/summary.json`.
Set `FEATURE_EXTRACTOR_URL=http://127.0.0.1:8001` for a locally run backend, or use
`http://feature_extractor:8000` for the backend Compose service, to auto-trigger it
after processing jobs complete. The backend calls `/summarize` first and then
`/extract-primitives` with the document classification from the processing run.
Extractor failures are logged to `processing_run_steps` and `audit_events` but do not
roll back the completed processing job.

After primitive extraction succeeds for a document with a known `contract_id`, the
service calls the backend internal analysis trigger when `BACKEND_API_URL` and
`INTERNAL_SERVICE_TOKEN` are configured. The backend debounces the request: it skips
the run when an `analysis_runs` row for that contract is newer than the latest
successful or partial primitive extraction. Low-N cohorts still run and are tagged
`low_confidence`.

Configure `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENAI_LLM_MODEL`, and
`MODEL_PREFERENCE` only in ignored local env files or shell exports. The backend
default LLM model is `gpt-5.5`. The feature extractor also accepts
`APPINSIGHTS_CONNECTION_STRING` and emits the same structured correlation fields as the
backend API. `backend/.env.example`, `backend/.env.local.example`, and
`feature_extractor/.env.example` intentionally carry the same ordered variable names so
local backend and optional feature-extractor config do not drift.

## Boundaries

The local mirror does not emulate:

- Azure Functions hosting and scaling behavior.
- Azure PostgreSQL firewall, identity, backup, or regional behavior.
- Azure RBAC, managed identities, or Key Vault references.
- Real IMAP/SMTP mailbox behavior.

Use local tests for fast feedback. Use `bun run infra:whatif` and the GitHub Actions
what-if workflow for Azure drift and cloud resource changes.

## CI

`.github/workflows/local-mirror.yml` starts the Docker Compose mirror in GitHub Actions
and runs backend tests. This catches local/cloud contract drift for service names, env
shape, and dependency startup without touching Azure.
