import os
from pathlib import Path
from typing import Optional, Set

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env.local", override=True)


def get_auth_secret_key() -> str:
    return os.getenv("AUTH_SECRET_KEY", "dev-only-auth-secret-change-me")


def get_auth_mode() -> str:
    return os.getenv("AUTH_MODE", "mock").strip().lower()


def get_entra_tenant_id() -> Optional[str]:
    return os.getenv("ENTRA_TENANT_ID") or os.getenv("AZURE_TENANT_ID")


def get_entra_issuer() -> Optional[str]:
    explicit = os.getenv("ENTRA_ISSUER")
    if explicit:
        return explicit.rstrip("/")
    tenant_id = get_entra_tenant_id()
    if tenant_id:
        return f"https://login.microsoftonline.com/{tenant_id}/v2.0"
    return None


def get_entra_audience() -> Optional[str]:
    return os.getenv("ENTRA_AUDIENCE") or os.getenv("ENTRA_CLIENT_ID")


def get_entra_jwks_url() -> Optional[str]:
    explicit = os.getenv("ENTRA_JWKS_URL")
    if explicit:
        return explicit
    tenant_id = get_entra_tenant_id()
    if tenant_id:
        return f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    return None


def get_entra_jwks_json() -> Optional[str]:
    return os.getenv("ENTRA_JWKS_JSON")


def get_entra_official_group_ids() -> Set[str]:
    return _csv_env("ENTRA_OFFICIAL_GROUP_IDS")


def get_entra_contractor_group_ids() -> Set[str]:
    return _csv_env("ENTRA_CONTRACTOR_GROUP_IDS")


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'data' / 'app.db'}")


def get_azure_storage_connection_string() -> Optional[str]:
    return os.getenv("AZURE_STORAGE_CONNECTION_STRING")


def get_azure_storage_container() -> str:
    return os.getenv("AZURE_STORAGE_CONTAINER", "app-assets")


def get_local_blob_dir() -> Path:
    return Path(os.getenv("LOCAL_BLOB_DIR", str(BACKEND_DIR / "data" / "blobs")))


def get_ai_provider_name() -> str:
    return os.getenv("AI_PROVIDER", "openai").strip().lower()


def get_ai_processing_enabled() -> bool:
    return _env_bool("AI_PROCESSING_ENABLED", default=False)


def get_ai_inline_processing_enabled() -> bool:
    return _env_bool("AI_INLINE_PROCESSING_ENABLED", default=False)


def get_openai_api_key() -> Optional[str]:
    return os.getenv("OPENAI_API_KEY")


def get_openai_llm_model() -> str:
    return os.getenv("OPENAI_LLM_MODEL", "gpt-5.4-mini")


def get_openai_embedding_model() -> str:
    return os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def get_openai_embedding_dimensions() -> Optional[int]:
    value = os.getenv("OPENAI_EMBEDDING_DIMENSIONS")
    if not value:
        return None
    try:
        dimensions = int(value)
    except ValueError:
        return None
    return dimensions if dimensions > 0 else None


def get_ai_request_timeout_seconds() -> float:
    value = os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "30")
    try:
        return max(1.0, float(value))
    except ValueError:
        return 30.0


def get_ai_max_retries() -> int:
    value = os.getenv("AI_MAX_RETRIES", "2")
    try:
        return max(0, int(value))
    except ValueError:
        return 2


def get_sam_api_key() -> Optional[str]:
    return os.getenv("SAM_API_KEY")


def get_regulations_api_key() -> Optional[str]:
    return os.getenv("REGULATIONS_API_KEY")


def get_cpars_import_dir() -> Optional[Path]:
    value = os.getenv("CPARS_IMPORT_DIR")
    return Path(value) if value else None


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str) -> Set[str]:
    value = os.getenv(name, "")
    return {part.strip() for part in value.split(",") if part.strip()}
