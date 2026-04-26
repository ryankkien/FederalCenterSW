# fedcenter

## Database Schema

> **Rule:** Any change to an existing schema or introduction of a new schema must be reflected in this file immediately — before the task is considered complete. If a table, column, enum, index, or relationship is added, removed, or modified anywhere in the codebase, update the relevant section below. If a schema is referenced that does not yet appear here, add it. This rule also applies to the input and output schemas of all services (e.g. blob file formats, API request/response bodies): if a service's payload shape changes or a new service is introduced, update or add its schema documentation here before the task is considered complete.

Full schema: [psql/schema.sql](psql/schema.sql)

### Extensions
- **pgvector** — enables the `VECTOR` column type and HNSW indexing for similarity search

### Enums

**`event_type`** — stages in a document's processing pipeline
`Upload` | `OCR` | `Summary` | `Keywords` | `BI` | `Index` | `Chunking`

**`result_type`** — outcome of a pipeline event
`success` | `fail`

### Tables

#### `document_types`
Mutable lookup table acting as a soft enum for document classification.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | SERIAL | PK |
| `name` | TEXT | NOT NULL, UNIQUE |

#### `documents`
Core metadata record for each ingested document.

| Column | Type | Constraints |
|--------|------|-------------|
| `uuid` | UUID | PK, default `gen_random_uuid()` |
| `filename` | TEXT | NOT NULL |
| `title` | TEXT | NOT NULL |
| `date_submitted` | TIMESTAMPTZ | NOT NULL, default `now()` |
| `doc_type_id` | INTEGER | FK → `document_types.id`, nullable |
| `summary_embedding` | VECTOR(1536) | nullable |
| `psc_code` | TEXT | nullable — 4-char DoD Product and Service Code (PSC Manual Apr 2022) |
| `naics_code` | TEXT | nullable — 6-digit North American Industry Classification System code |

**Indices:** `doc_type_id`, `date_submitted`, `summary_embedding` (HNSW cosine)

`psc_code` and `naics_code` are written by the Durable Functions orchestrator after the Summarizer ACA returns its classification result.

#### `chunks`
Stores ordered 256-word chunks of a document for hybrid search (keyword + vector).

| Column | Type | Constraints |
|--------|------|-------------|
| `doc_id` | UUID | FK → `documents.uuid`, CASCADE DELETE |
| `chunk_index` | INTEGER | NOT NULL |
| `text` | TEXT | NOT NULL |

**PK:** `(doc_id, chunk_index)`

Chunks are written by the Summarizer ACA from the full concatenated OCR text, split at 256-word boundaries.

#### `document_log`
Audit trail of pipeline events per document.

| Column | Type | Constraints |
|--------|------|-------------|
| `doc_id` | UUID | FK → `documents.uuid`, CASCADE DELETE |
| `timestamp` | TIMESTAMPTZ | NOT NULL, default `now()` |
| `event` | event_type | NOT NULL |
| `result` | result_type | NOT NULL |

**PK:** `(doc_id, timestamp)`
**Indices:** `event`, `timestamp`

### Blob Storage Path Conventions

Container: `app-assets` (env: `AZURE_STORAGE_CONTAINER`, default `app-assets`)

| Blob path | Stage | Format |
|-----------|-------|--------|
| `documents/{doc_id}/ocr.json` | OCR output | `{"doc_id": "uuid", "pages": ["page 1 text", ...]}` |
| `documents/{doc_id}/summary.json` | Summarizer output | See schema below |

**`summary.json` schema** (written by [summarizer/](summarizer/), read by the Durable Functions orchestrator):
```json
{
  "doc_id": "uuid",
  "generated_at": "2026-04-26T12:00:00+00:00",
  "model": "claude-sonnet-4-6",
  "classification": {
    "psc_code": "D302",
    "psc_description": "ADP Software Development",
    "naics_code": "541511",
    "naics_description": "Custom Computer Programming Services",
    "rationale": "Document describes software development services..."
  },
  "layers": [
    {
      "layer": 0,
      "chunks": [
        {"chunk_index": 0, "page_range": [0, 7], "summary": "..."},
        {"chunk_index": 1, "page_range": [8, 12], "summary": "..."}
      ]
    },
    {
      "layer": 1,
      "chunks": [
        {"chunk_index": 0, "summary_range": [0, 7], "summary": "..."}
      ]
    }
  ],
  "final_summary": "..."
}
```

- `layers[0]` chunks reference `page_range` (0-indexed page numbers from `ocr.json`)
- Subsequent layers reference `summary_range` (indices into the previous layer's chunk summaries)
- The orchestrator writes `classification.psc_code` and `classification.naics_code` back to `documents.psc_code` / `documents.naics_code` in Postgres

### Relationships

```
document_types ──< documents ──< chunks
                        │
                        └──< document_log
```
