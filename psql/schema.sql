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
    summary_embedding VECTOR(1536)
);

CREATE TABLE chunks (
    doc_id      UUID    NOT NULL REFERENCES documents(uuid) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    PRIMARY KEY (doc_id, chunk_index)
);

CREATE TABLE document_log (
    doc_id    UUID        NOT NULL REFERENCES documents(uuid) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    event     event_type  NOT NULL,
    result    result_type NOT NULL,
    PRIMARY KEY (doc_id, timestamp)
);
