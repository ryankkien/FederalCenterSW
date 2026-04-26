import uuid

import psycopg

_CHUNK_WORDS = 256


def chunk_and_store(
    conn: psycopg.Connection, document_upload_id: str, pages: list[str]
) -> list[tuple[str, str]]:
    """Split all pages into 256-word chunks and bulk-insert into document_chunks.

    Returns list of (chunk_id, text) for use by the embedder.
    """
    full_text = " ".join(pages)
    words = full_text.split()

    rows: list[tuple[str, str, None, int, str]] = []
    for i, start in enumerate(range(0, len(words), _CHUNK_WORDS)):
        chunk_text = " ".join(words[start : start + _CHUNK_WORDS])
        rows.append((str(uuid.uuid4()), document_upload_id, None, i, chunk_text))

    if not rows:
        return []

    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM document_chunks WHERE document_upload_id = %s",
            (document_upload_id,),
        )
        cur.executemany(
            "INSERT INTO document_chunks (id, document_upload_id, contract_id, chunk_index, text)"
            " VALUES (%s, %s, %s, %s, %s)",
            rows,
        )
    conn.commit()

    return [(row[0], row[4]) for row in rows]  # (id, text)
