import openai
import psycopg

from app.config import get_embedding_model, get_openai_api_key


def embed_and_store(conn: psycopg.Connection, doc_id: str, final_summary: str) -> None:
    """Generate a 1536-dim embedding from the final summary and store it in documents.summary_embedding."""
    api_key = get_openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for embedding generation")

    client = openai.OpenAI(api_key=api_key)
    response = client.embeddings.create(
        model=get_embedding_model(),
        input=final_summary,
    )
    vector = response.data[0].embedding  # list[float], len == 1536

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET summary_embedding = %s::vector WHERE uuid = %s",
            ("[" + ",".join(str(v) for v in vector) + "]", doc_id),
        )
    conn.commit()
