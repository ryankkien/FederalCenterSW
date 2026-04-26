from contextlib import contextmanager

import psycopg

from app.config import get_database_url


@contextmanager
def get_connection():
    url = get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    with psycopg.connect(url) as conn:
        yield conn


def log_event(conn, doc_id: str, event: str, result: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO document_log (doc_id, event, result) VALUES (%s, %s::event_type, %s::result_type)",
            (doc_id, event, result),
        )
    conn.commit()
