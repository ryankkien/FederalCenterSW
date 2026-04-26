"""pgvector cosine search over chunk_embeddings.

Uses the existing HNSW index `ix_chunk_embeddings_embedding_hnsw` (vector_cosine_ops).
On non-Postgres backends (SQLite tests), returns an empty list rather than raising.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.providers import get_ai_provider
from app.config import get_openai_embedding_model


def embed_query(query: str) -> List[float]:
    provider = get_ai_provider()
    vectors = provider.embed_texts([query])
    if not vectors:
        raise RuntimeError("Embedding provider returned no vector for query")
    return vectors[0]


def search_similar_chunks(
    db: Session,
    query: str,
    *,
    k: int = 10,
    exclude_contract_id: Optional[str] = None,
    visible_contract_ids: Optional[Sequence[str]] = None,
) -> List[dict]:
    """Top-k semantically similar chunks across the portfolio.

    `visible_contract_ids` enforces RBAC: only chunks whose `contract_id` is in this
    list are returned. Pass `None` to skip the filter (caller is responsible).
    """
    if visible_contract_ids is not None and not visible_contract_ids:
        return []

    if db.bind is None or db.bind.dialect.name != "postgresql":
        # pgvector operators aren't available on the SQLite test backend.
        return []

    embedding = embed_query(query)
    embedding_literal = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"
    model = get_openai_embedding_model()

    where_clauses = ["e.embedding_model = :model"]
    params: dict = {"model": model, "vec": embedding_literal, "k": k}
    if exclude_contract_id:
        where_clauses.append("(c.contract_id IS NULL OR c.contract_id <> :exclude)")
        params["exclude"] = exclude_contract_id
    if visible_contract_ids is not None:
        ids_csv = ",".join(f":vid{i}" for i in range(len(visible_contract_ids)))
        for i, vid in enumerate(visible_contract_ids):
            params[f"vid{i}"] = vid
        where_clauses.append(f"c.contract_id IN ({ids_csv})")

    sql = text(
        f"""
        SELECT c.id AS chunk_id,
               c.document_upload_id,
               c.contract_id,
               substring(c.text from 1 for 480) AS snippet,
               co.contract_number,
               co.title AS contract_title,
               co.psc_code,
               (e.embedding <=> CAST(:vec AS vector)) AS distance
        FROM chunk_embeddings e
        JOIN document_chunks c ON e.chunk_id = c.id
        LEFT JOIN contracts co ON c.contract_id = co.id
        WHERE {" AND ".join(where_clauses)}
        ORDER BY e.embedding <=> CAST(:vec AS vector)
        LIMIT :k
        """
    )
    try:
        rows = db.execute(sql, params).mappings().all()
    except SQLAlchemyError:
        db.rollback()
        return []
    return [dict(r) for r in rows]
