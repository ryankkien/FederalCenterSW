import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def get_auth_secret_key() -> str:
    return os.getenv("AUTH_SECRET_KEY", "dev-only-auth-secret-change-me")


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'data' / 'app.db'}")


def get_azure_storage_connection_string() -> Optional[str]:
    return os.getenv("AZURE_STORAGE_CONNECTION_STRING")


def get_azure_storage_container() -> str:
    return os.getenv("AZURE_STORAGE_CONTAINER", "app-assets")


def get_local_blob_dir() -> Path:
    return Path(os.getenv("LOCAL_BLOB_DIR", str(BACKEND_DIR / "data" / "blobs")))
