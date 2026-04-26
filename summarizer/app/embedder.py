import uuid

import openai
import psycopg

from app.config import get_embedding_model, get_openai_api_key


def embed_chunks(
    conn: psycopg.Connection, chunks: list[tuple[str, str]]
) -> None:
    """Generate embeddings for each (chunk_id, text) pair and write to chunk_embeddings.

    Uses OpenAI text-embedding-3-small (1536 dims) regardless of MODEL_PREFERENCE.
    """
    if not chunks:
        return

    api_key = get_openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for embedding generation")

    model = get_embedding_model()
    client = openai.OpenAI(api_key=api_key)

    texts = [text for _, text in chunks]
    response = client.embeddings.create(model=model, input=texts)
    vectors = [item.embedding for item in response.data]  # list[list[float]], each len 1536

    rows = []
    for (chunk_id, _), vector in zip(chunks, vectors):
        vec_str = "[" + ",".join(str(v) for v in vector) + "]"
        rows.append((str(uuid.uuid4()), chunk_id, model, 1536, vec_str))

    with conn.cursor() as cur:
        # Delete stale embeddings for these chunks before reinserting
        cur.executemany(
            "DELETE FROM chunk_embeddings WHERE chunk_id = %s AND embedding_model = %s",
            [(chunk_id, model) for chunk_id, _ in chunks],
        )
        cur.executemany(
            "INSERT INTO chunk_embeddings"
            " (id, chunk_id, embedding_model, embedding_dimension, embedding)"
            " VALUES (%s, %s, %s, %s, %s::vector)",
            rows,
        )
    conn.commit()
