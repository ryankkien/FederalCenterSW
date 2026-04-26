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

### Knowledge Wiki Tables

- `knowledge_ingestion_runs`: official-source and fixture-index build runs.
- `knowledge_source_records`: normalized source records from uploaded evidence,
  fixtures, and official bulk imports.
- `knowledge_nodes`: contract, contractor, topic, and source wiki articles.
- `knowledge_edges`: typed links between wiki nodes.
- `knowledge_citations`: article citations to uploaded documents, official-source
  records, or external-source references.
- `contractor_profiles`: contractor evidence summaries and counts.

### Summarizer Service (`summarizer/`)

The optional `summarizer/` ACA reads a text artifact from blob, runs hierarchical summarization, classifies the document with a PSC and NAICS code, splits the full text into 256-word chunks written to `document_chunks`, and generates per-chunk embeddings written to `chunk_embeddings`. Pipeline events are logged to `audit_events` with `entity_type = 'document_upload'`.

**Blob paths** (container: `app-assets`, env: `AZURE_STORAGE_CONTAINER`):

| Path | Stage | Format |
|------|-------|--------|
| `contracts/{document_upload_id}/text.json` | Primary text input | `{"pages": ["page 1 text", ...]}` |
| `documents/{document_upload_id}/ocr.json` | Legacy text input (fallback) | `{"doc_id": "...", "pages": [...]}` |
| `contracts/{document_upload_id}/summary.json` | Summarizer output | See schema below |

**`summary.json` schema:**
```json
{
  "doc_id": "document_upload_id",
  "generated_at": "2026-04-26T12:00:00+00:00",
  "model": "claude-sonnet-4-6",
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

- `layers[0]` chunks reference `page_range` (0-indexed page numbers from input)
- Subsequent layers reference `summary_range` (indices into previous layer summaries)
- `classification.psc_code` / `naics_code` are written to `contracts.psc_code` / `contracts.naics_code` by the orchestrator
- Audit events use `event_type` values: `summarizer.summary`, `summarizer.chunking`, `summarizer.index`

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
  └─< knowledge_nodes ──< knowledge_citations/knowledge_edges
```
