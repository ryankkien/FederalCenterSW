import os
from pathlib import Path

SUMMARIZER_DIR = Path(__file__).resolve().parents[1]


def get_azure_storage_connection_string() -> str | None:
    return os.getenv("AZURE_STORAGE_CONNECTION_STRING")


def get_azure_storage_container() -> str:
    return os.getenv("AZURE_STORAGE_CONTAINER", "app-assets")


def get_local_blob_dir() -> Path:
    return Path(os.getenv("LOCAL_BLOB_DIR", str(SUMMARIZER_DIR / "data" / "blobs")))


def get_anthropic_api_key() -> str | None:
    return os.getenv("ANTHROPIC_API_KEY")


def get_openai_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def get_model_preference() -> str:
    return os.getenv("MODEL_PREFERENCE", "claude").lower()


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "")


def get_embedding_model() -> str:
    return os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
