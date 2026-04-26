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

- `knowledge_ingestion_runs`: fixture/synthetic and optional-source index build runs.
- `knowledge_source_records`: normalized source records from uploaded evidence,
  fixtures, generated synthetic evidence, and deliberate optional-source imports.
- `knowledge_nodes`: contract, contractor, topic, and source wiki articles.
- `knowledge_edges`: typed links between wiki nodes.
- `knowledge_citations`: article citations to uploaded documents, fixture/synthetic
  records, optional-source records, or external-source references.
- `contractor_profiles`: contractor evidence summaries and counts.

### Optional Summarizer Service

The optional `summarizer/` service can summarize and PSC/NAICS-classify extracted
document text. It reads canonical `contracts/{document_id}/text.json` artifacts first,
falls back to legacy `documents/{doc_id}/ocr.json`, and writes
`contracts/{document_id}/summary.json`. The core analyst pipeline remains DB-backed;
summarizer output is supplemental classification evidence, not the canonical contract
record.

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
