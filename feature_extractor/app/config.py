import os
from pathlib import Path

SUMMARIZER_DIR = Path(__file__).resolve().parents[1]


def get_azure_storage_connection_string() -> str | None:
    return os.getenv("AZURE_STORAGE_CONNECTION_STRING")


def get_azure_storage_container() -> str:
    return os.getenv("AZURE_STORAGE_CONTAINER", "app-assets")


def get_local_blob_dir() -> Path:
    return Path(os.getenv("LOCAL_BLOB_DIR", str(SUMMARIZER_DIR / "data" / "blobs")))


def get_openai_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def get_openai_llm_model() -> str:
    return os.getenv("OPENAI_LLM_MODEL", "gpt-5.4-mini")


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "")


def get_embedding_model() -> str:
    return os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


def get_backend_api_url() -> str:
    return os.getenv("BACKEND_API_URL", "").rstrip("/")


def get_internal_service_token() -> str:
    return os.getenv("INTERNAL_SERVICE_TOKEN", "")
