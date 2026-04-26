from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_database_url


class Base(DeclarativeBase):
    pass


def _connect_args() -> dict:
    if get_database_url().startswith("sqlite"):
        return {"check_same_thread": False, "timeout": 30}
    return {}


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///") or database_url == "sqlite:///:memory:":
        return
    Path(database_url.replace("sqlite:///", "", 1)).parent.mkdir(parents=True, exist_ok=True)


database_url = get_database_url()
_ensure_sqlite_parent(database_url)
engine = create_engine(database_url, connect_args=_connect_args(), pool_pre_ping=True)


if database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=30000")
        if database_url != "sqlite:///:memory:":
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def create_db_schema() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
