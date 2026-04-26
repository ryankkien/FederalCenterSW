# fedcenter

## Database Schema

> **Rule:** Any change to an existing schema or introduction of a new schema must be
> reflected in this file immediately before the task is considered complete. If a
> table, column, enum, index, or relationship is added, removed, or modified anywhere
> in the codebase, update the relevant section below and the full SQL mirror.

Full SQL mirror: [psql/schema.sql](psql/schema.sql)

Alembic migrations under `backend/migrations/versions/` are authoritative for live
database upgrades. SQLAlchemy models in `backend/app/models.py` are the runtime schema
contract. The SQL mirror is maintained for review and local psql reference.

### Extensions

- `vector`: PostgreSQL pgvector extension for chunk embeddings and HNSW cosine search.

### Core Contract Tables

- `contracts`: contract master records, agency/vendor/category metadata, security
  level, and optional source record blob path.
- `contract_access_grants`: RBAC grants keyed by `contract_id`, `principal_id`,
  `principal_type`, and role. Entra user and group ids map to `principal_id`.
- `document_uploads`: canonical upload/intake rows. Hard parentage lives only on
  `document_uploads.contract_id`.
- `email_intake_messages`: append-only IMAP intake audit rows.
- `audit_events`: append-only admin, matching, status, and workflow audit trail.

### Processing Store

- `document_processing_jobs`: queued/running/completed processing jobs.
- `processing_runs`: run-level extraction, matching, classification, baseline,
  regression, hypothesis, semantic-link, and research metadata.
- `processing_run_steps`: step-level logs with status and optional metadata.
- `document_pages`: page-level extracted text, extraction status, offsets, warnings,
  and errors.
- `document_chunks`: contract-scoped text chunks for retrieval and evidence links.
- `chunk_embeddings`: pgvector embeddings per chunk/model.
- `document_classification_decisions`: append-only classifier decisions, including
  document kind, modification kind, confidence, rationale, and source run.
- `document_entities`: extracted contract numbers, RFIs, people, offices, dates,
  dollar values, deliverables, facilities, clauses, normalized values, citations, and
  evidence hashes.
- `document_report_facts`: report periods, counts, costs, schedule values, labor
  metrics, deliverables, government-action items, quotes, and evidence hashes.

### Analyst Tables

- `contract_baselines`: current interpreted baseline summary per contract.
- `baseline_obligations`: baseline obligations with document/page/chunk/run citations.
- `baseline_revisions`: append-only baseline history.
- `regression_findings`: citation-backed baseline/prior-report regressions.
- `contract_hypotheses`: proposed, investigating, supported, contradicted, or closed
  hypothesis records.
- `hypothesis_evidence`: uploaded-file or external-source evidence linked to
  hypotheses. Only supported hypotheses may be presented as supported findings.
- `investigation_runs`: official-source research runs.
- `external_source_refs`: allowlisted official external citations stored separately
  from uploaded-file evidence.
- `contract_similarity_links`: cross-contract semantic relationships.
- `document_semantic_links`: cross-document semantic relationships; these must not
  rewrite `document_uploads.contract_id`.

### Earlier AI Knowledge Tables

- `performance_signals`: extracted contract performance signals.
- `contract_topics`: analyst-curated contract topics.
- `topic_evidence`: evidence linked to topics.
- `topic_links`: topic-to-topic semantic links.
- `contract_topic_revisions`: append-only topic revision history.

- `contractor_profiles`: contractor evidence summaries, award counts, and issue/contradiction counts.

### Primitive Extraction Tables (`feature_extractor/` service, migration 0006)

These tables store structured records extracted from documents by the `feature_extractor` service. They feed the per-contract and cohort analysis pipelines.

**New columns on `contracts`:**
- `contract_type VARCHAR(40)` — e.g. FFP, CPFF, T&M, IDIQ
- `competition_type VARCHAR(40)` — e.g. full_and_open, set_aside, sole_source

**New tables:**
- `primitive_extraction_runs`: audit trail per document extraction run. `contract_id` and `doc_upload_id` are nullable until matched.
- `contract_primitives_deliverable`: CDRL items, planned/actual dates, status, days late.
- `contract_primitives_financial`: EVM metrics (BCWS/BCWP/ACWP), BAC/EAC/ETC, CPI/SPI, per period.
- `contract_primitives_decisions`: contract mods and decisions — mod number, reason, value/POP/scope changes.
- `contract_primitives_issues`: issues and risks — category, severity, responsible party, open/resolved dates.
- `contract_primitives_personnel`: key persons, labor categories, FTE planned vs. actual, staffing gaps.
- `cpars_ratings`: per-factor adjectival CPARS ratings ingested from CPARS documents.
- `analysis_runs`: stores JSON outputs of per-contract and cohort analyses.

### Feature Extractor Service (`feature_extractor/`)

The optional `feature_extractor/` service replaces the old `summarizer/`. It reads a text artifact from blob, runs hierarchical summarization, classifies the document (PSC/NAICS), chunks and embeds the text, and extracts structured primitives into the DB. When `FEATURE_EXTRACTOR_URL` is configured, completed backend processing runs call `/summarize` and then call `/extract-primitives` with `doc_id`, `contract_id`, and `doc_classification`.

**New endpoints:**
- `POST /summarize` — unchanged, runs summarization + chunking + embedding (pipeline steps 1-4)
- `POST /extract-primitives` — extracts primitives for a document given its classification

**Audit events** use `event_type` values: `feature_extractor.summary`, `feature_extractor.chunking`, `feature_extractor.index`, `feature_extractor.primitives`. Backend-triggered summary and primitive failures are also surfaced in `processing_run_steps`; they must not roll back the upstream processing run.

**Blob paths** (container: `app-assets`, env: `AZURE_STORAGE_CONTAINER`):

| Path | Stage | Format |
|------|-------|--------|
| `contracts/{document_upload_id}/text.json` | Primary text input | `{"pages": ["page 1 text", ...]}` |
| `documents/{document_upload_id}/ocr.json` | Legacy text input (fallback) | `{"doc_id": "...", "pages": [...]}` |
| `contracts/{document_upload_id}/summary.json` | Feature extractor output | See schema below |

**`summary.json` schema:**
```json
{
  "doc_id": "document_upload_id",
  "generated_at": "2026-04-26T12:00:00+00:00",
  "model": "gpt-5.4-mini",
  "source_path": "contracts/{id}/text.json",
  "classification": {
    "psc_code": "D302",
    "psc_description": "ADP Software Development",
    "naics_code": "541511",
    "naics_description": "Custom Computer Programming Services",
    "rationale": "..."
  },
  "layers": [
    {
      "layer": 0,
      "chunks": [{"chunk_index": 0, "page_range": [0, 7], "summary": "..."}]
    }
  ],
  "final_summary": "..."
}
```

### Analysis Pipeline (Backend)

**`backend/app/cohort_builder.py`**: Given a `contract_id`, finds comparable contracts using NAICS 4-digit prefix, `contract_type`, agency, `competition_type`, POP length (±25%), and obligated value band (±50%). Flags `low_confidence: true` when N < 20.

**`backend/app/analysis_orchestrator.py`**: Loads primitives + CPARS for target + cohort, assembles the analysis prompt, calls OpenAI, stores result in `analysis_runs`.

**New API endpoints:**
- `GET /api/contracts/{id}/cohort` → cohort definition + contract IDs
- `POST /api/contracts/{id}/performance-analysis` → trigger per-contract analysis
- `GET /api/contracts/{id}/performance-analysis/{run_id}` → get result
- `POST /api/analysis/cohort-runs` → trigger cohort analysis
- `GET /api/analysis/cohort-runs/{run_id}` → get result

### Relationships

```text
contracts
  ├─< contract_access_grants
  ├─< document_uploads
  │    ├─< document_pages
  │    ├─< document_chunks ──< chunk_embeddings
  │    ├─< document_match_decisions
  │    ├─< document_processing_jobs ──< processing_runs ──< processing_run_steps
  │    ├─< document_classification_decisions
  │    ├─< document_entities
  │    └─< document_report_facts
  ├─< contract_baselines ──< baseline_obligations
  ├─< regression_findings
  ├─< contract_hypotheses ──< hypothesis_evidence
  ├─< investigation_runs ──< external_source_refs
  ├─< contract_similarity_links
  ├─< contract_topics ──< topic_evidence/topic_links/contract_topic_revisions
  ├─< primitive_extraction_runs ──< contract_primitives_deliverable
  │                               ──< contract_primitives_financial
  │                               ──< contract_primitives_decisions
  │                               ──< contract_primitives_issues
  │                               ──< contract_primitives_personnel
  ├─< cpars_ratings
  └─< analysis_runs (target) / analysis_runs (cohort, no direct FK)
```
