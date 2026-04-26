CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_types (
    id   SERIAL PRIMARY KEY,
    name TEXT   NOT NULL UNIQUE
);

CREATE TYPE event_type AS ENUM (
    'Upload',
    'OCR',
    'Summary',
    'Keywords',
    'BI',
    'Index',
    'Chunking'
);

CREATE TYPE result_type AS ENUM ('success', 'fail');

CREATE TABLE documents (
    uuid              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    filename          TEXT        NOT NULL,
    title             TEXT        NOT NULL,
    date_submitted    TIMESTAMPTZ NOT NULL DEFAULT now(),
    doc_type_id       INTEGER     REFERENCES document_types(id),
    summary_embedding VECTOR(1536),
    psc_code          TEXT,
    naics_code        TEXT
);

CREATE TABLE chunks (
    doc_id      UUID    NOT NULL REFERENCES documents(uuid) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    PRIMARY KEY (doc_id, chunk_index)
);

CREATE TABLE document_log (
    doc_id    UUID        NOT NULL REFERENCES documents(uuid) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    event     event_type  NOT NULL,
    result    result_type NOT NULL,
    PRIMARY KEY (doc_id, timestamp)
);

-- FK on documents.doc_type_id (Postgres does not auto-index FK columns)
CREATE INDEX idx_documents_doc_type_id ON documents (doc_type_id);

-- Range queries and ordering by submission date
CREATE INDEX idx_documents_date_submitted ON documents (date_submitted);

-- Vector similarity search on embeddings
CREATE INDEX idx_documents_summary_embedding ON documents USING hnsw (summary_embedding vector_cosine_ops);

-- Filter document_log by event type across all documents
CREATE INDEX idx_document_log_event ON document_log (event);

-- Global timeline queries across all documents
CREATE INDEX idx_document_log_timestamp ON document_log (timestamp);
