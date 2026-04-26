# AGENTS.md

## Project Overview

Federal Center SW is a small full-stack workspace with:

- A React + TypeScript + Vite frontend in `frontend/`.
- A Python FastAPI backend in `backend/`.
- Azure infrastructure defined with Bicep in `infra/`.
- Local development services defined with Docker Compose in `compose.yaml`.
- Shared developer commands in the root `package.json`.
- Operational notes in `docs/`.

The frontend talks to the backend through `/api/*` routes. During local development,
Vite proxies those requests to `http://127.0.0.1:8000`.

Product/domain direction lives in `docs/product.md`. Read it before designing data
models, intake workflows, contract UI, dashboards, or LLM/OCR processing behavior.
Treat `docs/product.md` as future-build planning guidance, not as a description of
features that already exist.

## Future Product Build Direction

The intended product is a contract performance visibility system for CO, COR, and PM
users. Future work should build toward:

1. Contract record foundation with one structured JSON-style record per contract,
   role-aware Entra ID/RBAC access, security-level visibility, contract metadata,
   OCR-ed contract text, report references, and official government identifiers and
   category codes such as DUNS, PSC, and NAICS.
2. Report intake through email, automated contract matching, manual portal upload, and
   scanned report upload by authorized contractor or federal users.
3. CPARS and IPMDAR support: CPARS unclassified evaluation narratives/ratings, IPMDAR
   CPD and SPD JSON datasets, and IPMDAR narrative performance reports.
4. Document processing through OCR, named entity recognition, and LLM-assisted review;
   structured JSON sources should bypass OCR and use direct schema-based ingestion.
5. Contract-level UI showing contract records, ingested reports, processing outputs,
   and extracted performance signals.
6. Cross-contract aggregation with dashboards and reports for lessons learned,
   category-level comparisons, risks, delays, staffing issues, deliverables, costs,
   timeliness, inconsistencies, successes, and benchmarking.

## Architecture

### Frontend

- Put React application code in `frontend/src/`.
- `frontend/src/main.tsx` is the browser entry point.
- `frontend/src/App.tsx` currently owns the main starter UI and calls `/api/health`.
- `frontend/src/styles.css` contains global styles for the starter UI.
- `frontend/src/test/setup.ts` configures Vitest and Testing Library.
- Frontend tests should live beside the code they cover or in `frontend/src/` using
  the existing `*.test.tsx` pattern.

Prefer TypeScript, React function components, and existing Vite/Vitest patterns.
Keep browser API calls relative, such as `/api/health`, so the Vite proxy and deployed
same-origin routing can both work.

### Backend

- Put FastAPI routes, service logic, and backend modules in `backend/app/`.
- `backend/app/main.py` creates the FastAPI app, configures CORS, and defines API routes.
- `backend/app/email_intake.py` contains the IMAP email intake worker, message parsing,
  JSONL/Azure Blob stub persistence, and auto-reply logic.
- `backend/function_app.py` is the Azure Functions timer-trigger entry point for
  running email intake in Azure.
- `backend/host.json` contains Azure Functions host configuration.
- Backend tests live in `backend/tests/`.

When adding API features, keep route definitions close to `backend/app/main.py` unless
the app grows enough to justify routers. Put reusable parsing, persistence, or workflow
logic in separate modules under `backend/app/` and cover it with pytest tests.

### Infrastructure And Cloud

- Azure infrastructure lives in `infra/` and is managed with Bicep.
- `infra/main.bicep` defines the shared dev resources.
- `infra/dev.bicepparam` pins the current dev names and regions.
- Use `bun run infra:whatif` before changing Azure resources.
- Use `bun run infra:deploy` only when the what-if output is understood.
- GitHub Actions workflows for infrastructure live in `.github/workflows/`.
- Pull request Discord notifications live in
  `.github/workflows/discord-pr-notifications.yml` and require the GitHub repository
  secret `DISCORD_PULL_REQUEST_WEBHOOK_URL`.
- Keep cloud inventory, access notes, and manual CLI operations in `docs/cloud.md`.
- Keep infrastructure workflow and drift policy in `docs/infra.md`.
- The active development resource group is `federal-center-sw-dev`.
- Do not commit secrets, app passwords, storage keys, database passwords, or connection
  strings. Use local `.env` files, GitHub environment configuration, Azure app settings,
  or Key Vault.
- Function App app settings currently contain secrets and are not fully managed by Bicep.
  Move secrets to Key Vault before making app settings fully declarative.

### Local Development Mirror

- Local service dependencies live in `compose.yaml`.
- `bun run local:up` starts local PostgreSQL and Azurite and creates the local
  `app-assets` Blob container.
- Local PostgreSQL uses a pgvector-enabled Postgres 16 image. Run `bun run db:upgrade`
  after starting local services so Alembic creates the app schema and `vector`
  extension.
- `backend/.env.local.example` is the local-only env template.
- `backend/.env.local` is ignored and should contain local-only values.
- Keep local and cloud mirrored by env variable names, database name, database user,
  and Blob container name. Hosts, passwords, storage accounts, and credentials can differ.
- Local Compose is not a replacement for Bicep. Use it for fast app testing; use
  `bun run infra:whatif` for Azure drift.
- The local mirror CI workflow is `.github/workflows/local-mirror.yml`.

### Docs And Config

- Use `README.md` for project setup, common commands, and high-level orientation.
- Use `docs/` for longer operational notes, cloud details, and workflow-specific docs.
- Keep product and domain requirements in `docs/product.md`.
- Keep backend environment examples in `backend/.env.example`.
- Do not commit local secrets or generated local data files.

### Change Completion

- Keep documentation current with every feature or workflow change. Update `AGENTS.md`,
  `README.md`, and the relevant `docs/` page before considering the work done.
- Keep `docs/cloud.md` current for Azure inventory, access, and manual cloud commands.
  Keep `docs/infra.md` current for Bicep, GitHub Actions, and drift policy.
- When a commit is requested, review the diff, run the relevant checks, and commit the
  intended work after documentation is updated.

## Commands

Install frontend dependencies:

```sh
bun install
```

Create and install backend dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
```

Run both dev servers:

```sh
bun run dev
```

Start or stop local dependencies:

```sh
bun run local:up
bun run local:down
bun run local:reset
```

Run one side only:

```sh
bun run dev:frontend
bun run dev:backend
```

Run checks:

```sh
bun run db:upgrade
bun run build
bun run lint
bun run test
```

Run the email intake worker:

```sh
bun run email:intake -- --limit 5
```

Use `--commit` only after dry-run output has been checked.

Build the file-first Navy service fixture corpus:

```sh
bun run corpus:build-synthetic
```

Preview or apply infrastructure:

```sh
bun run infra:whatif
bun run infra:deploy
```

## Coding Conventions

- Use `rg`/`rg --files` for repository searches.
- Keep changes scoped to the requested feature or fix.
- Follow the existing style before introducing new abstractions.
- Prefer structured libraries and framework APIs over ad hoc parsing.
- Use ASCII unless the edited file already uses another character set or the content
  requires it.
- Add comments only where they clarify non-obvious behavior.

## Testing Guidance

- For frontend UI behavior, use Vitest and Testing Library.
- For backend behavior, use pytest under `backend/tests/`.
- Add or update tests when changing API responses, parsing behavior, email intake logic,
  or user-visible frontend behavior.
- Run the narrowest relevant test first, then run `bun run test` when the change affects
  both sides or shared behavior.

## Where New Work Should Go

- New React components: `frontend/src/`, split out from `App.tsx` when the UI grows.
- New frontend styles: `frontend/src/styles.css` unless a component-level styling
  convention is introduced later.
- New API endpoints: `backend/app/main.py` for now; introduce routers only when route
  groups become meaningfully separate.
- New backend domain logic: focused modules under `backend/app/`.
- New Azure Function triggers: `backend/function_app.py`, reusing logic from
  `backend/app/` instead of duplicating worker behavior.
- New Azure resources: `infra/main.bicep` and environment parameters in
  `infra/dev.bicepparam`.
- New cloud workflow notes: `docs/infra.md`.
- New local dependency services: `compose.yaml`, with setup behavior in `scripts/local-*.sh`.
- New local environment examples: `backend/.env.local.example`.
- New product/domain notes: `docs/product.md`.
- New backend tests: `backend/tests/test_<feature>.py`.
- New frontend tests: `frontend/src/<feature>.test.tsx` or beside the component.
- New operational documentation: `docs/`.

## Current Feature Notes

- `/api/health` is the basic backend health endpoint.
- New portal uploads, fixture documents, and committed email uploads store blobs in
  immutable document artifact folders:
  `contracts/{document_id}/main.{ext}` and `contracts/{document_id}/text.json`.
  The hard parent contract is stored in Postgres on `document_uploads.contract_id`.
- Contract hard-link parentage lives on `document_uploads.contract_id`. Cross-contract
  and cross-document pattern relationships live in semantic link tables and must not
  rewrite the hard parent contract.
- The contract analyst pipeline stores page text, classifier decisions, extracted
  entities, report facts, interpreted baselines, baseline obligations, baseline
  revisions, regression findings, hypotheses, hypothesis evidence, investigation
  runs, official external-source references, processing run logs, and semantic
  similarity links.
- The knowledge wiki index stores local fixture/synthetic ingestion runs, source
  records, wiki nodes, edges, citations, and contractor evidence profiles. The
  frontend uses `/api/wiki/*` for the Grokipedia workspace; it should not rebuild the
  full wiki client-side from every contract analysis endpoint.
- Government officials use the contract analysis workspace for contract-first
  narrative briefs, chronological report signals, recurring versus one-off issues,
  early warnings, positive signals, contractor execution patterns, CPARS outcome
  context, and cohort comparisons. Contractors remain upload-focused and use the
  contract selector to hard-link new reports to `document_uploads.contract_id`.
- External research references are restricted in v1 to official sources such as `.gov`,
  `.mil`, Acquisition.gov, Federal Register, GAO/OIG, Congress.gov, and agency domains.
  Uploaded contract-file evidence remains authoritative for contract-specific findings.
- Default knowledge ingestion should use local fixture documents and the generated
  synthetic fixture corpus only. Do not make bulk downloads or live official-source
  calls part of the default local ingest path.
- The optional `feature_extractor/` service reads canonical `contracts/{document_id}/text.json`
  artifacts, writes `contracts/{document_id}/summary.json`, extracts structured primitives
  (deliverable, financial, decisions, issue, personnel) into the DB, and may provide
  supplemental PSC/NAICS classification evidence. It is not the canonical analyst
  store.
- `bun run corpus:build-synthetic` creates an ignored file corpus under
  `backend/data/corpus/navy-service-v1/` from the WWR, AGOR, and Natalie fixture
  families. Treat `real_fixture` downloaded anchors separately from
  `synthetic_fixture` reports, CPARS-style narratives, IPMDAR-style JSON, decision
  logs, and cross-contract lesson notes. Each contract has one CPARS-style
  `cpars_evaluation` fixture for extraction testing; these generated records are
  not real CPARS data.
- Optional knowledge sources use `SAM_API_KEY`, `REGULATIONS_API_KEY`, and
  `CPARS_IMPORT_DIR`; absent optional sources should be logged as unavailable rather
  than failing ingestion. CPARS data must come from authorized exports/imports, not
  unauthenticated scraping.
- Product source planning includes CPARS unclassified evaluations, SAM.gov as a
  potential source for contract-number discovery, IPMDAR CPD/SPD monthly JSON datasets,
  and IPMDAR narrative performance reports. CPD/SPD JSON should be direct-ingested
  without OCR; Word/PDF narratives should use OCR, NER, and LLM-assisted review.
- Postgres is the canonical store for contracts, RBAC grants, processing jobs,
  processing run steps, pages, chunks, embeddings, signals, entities, facts,
  agent-curated topics, evidence links, topic revisions, and audit events. Blob Storage
  stores source artifacts and extracted text artifacts.
- AI processing is feature-flagged with `AI_PROCESSING_ENABLED` and
  `AI_INLINE_PROCESSING_ENABLED`. Keep OpenAI and future provider keys out of git.
- Email intake is currently a worker-style module, not a FastAPI route.
- Email intake persistence is intentionally stubbed: it writes JSONL locally by default
  and can write JSON records to Azure Blob Storage when configured.
- In Azure Functions, email intake should use Blob Storage for durable stub output
  because local function storage is ephemeral.
- Cloud setup and Azure resource notes belong in `docs/cloud.md`.
- Infrastructure workflow and drift policy belong in `docs/infra.md`.
- Local development mirror instructions belong in `docs/local-dev.md`.
- Email intake configuration and operating notes belong in `docs/email-intake.md`.
- Product direction, users, contract records, intake sources, processing signals, and
  deliverables belong in `docs/product.md`.
