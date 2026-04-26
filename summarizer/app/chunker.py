import psycopg

_CHUNK_WORDS = 256


def chunk_and_store(conn: psycopg.Connection, doc_id: str, pages: list[str]) -> int:
    """Split all OCR pages into 256-word chunks and bulk-insert into the chunks table.

    Returns the number of chunks written.
    """
    full_text = " ".join(pages)
    words = full_text.split()

    chunks: list[tuple[str, int, str]] = []
    for i in range(0, len(words), _CHUNK_WORDS):
        chunk_text = " ".join(words[i : i + _CHUNK_WORDS])
        chunks.append((doc_id, len(chunks), chunk_text))

    if not chunks:
        return 0

    with conn.cursor() as cur:
        # Delete any existing chunks for this doc before reinserting (idempotent)
        cur.execute("DELETE FROM chunks WHERE doc_id = %s", (doc_id,))
        cur.executemany(
            "INSERT INTO chunks (doc_id, chunk_index, text) VALUES (%s, %s, %s)",
            chunks,
        )
    conn.commit()
    return len(chunks)
