# fedcenter

## Database Schema

> **Rule:** Any change to an existing schema or introduction of a new schema must be reflected in this file immediately — before the task is considered complete. If a table, column, enum, index, or relationship is added, removed, or modified anywhere in the codebase, update the relevant section below. If a schema is referenced that does not yet appear here, add it.

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

**Indices:** `doc_type_id`, `date_submitted`, `summary_embedding` (HNSW cosine)

#### `chunks`
Stores ordered chunks of a document for retrieval.

| Column | Type | Constraints |
|--------|------|-------------|
| `doc_id` | UUID | FK → `documents.uuid`, CASCADE DELETE |
| `chunk_index` | INTEGER | NOT NULL |

**PK:** `(doc_id, chunk_index)`

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

### Relationships

```
document_types ──< documents ──< chunks
                        │
                        └──< document_log
```
