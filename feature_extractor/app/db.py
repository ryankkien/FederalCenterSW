from contextlib import contextmanager
import uuid

import psycopg

from app.config import get_database_url


@contextmanager
def get_connection():
    url = get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    with psycopg.connect(url) as conn:
        yield conn


def log_event(conn: psycopg.Connection, doc_id: str, event_type: str, status: str) -> None:
    """Write a feature extraction pipeline event to audit_events.

    event_type examples: 'feature_extractor.summary', 'feature_extractor.chunking', 'feature_extractor.index'
    status: 'success' or 'fail'
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_events
                (id, event_type, entity_type, entity_id, document_upload_id, metadata_json)
            VALUES (%s, %s, %s, %s, %s, %s::json)
            """,
            (
                str(uuid.uuid4()),
                event_type,
                "document_upload",
                doc_id,
                doc_id,
                f'{{"status": "{status}"}}',
            ),
        )
    conn.commit()
