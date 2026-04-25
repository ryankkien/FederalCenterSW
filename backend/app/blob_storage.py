from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from azure.storage.blob import BlobSasPermissions, BlobServiceClient, ContentSettings, generate_blob_sas

from app.config import (
    get_azure_storage_connection_string,
    get_azure_storage_container,
    get_local_blob_dir,
)


class BlobStorage(Protocol):
    def upload_bytes(self, path: str, data: bytes, content_type: str) -> None:
        ...

    def download_bytes(self, path: str) -> bytes:
        ...

    def create_read_url(self, path: str, expires_in_minutes: int = 15) -> str:
        ...


class AzureBlobStorage:
    def __init__(self) -> None:
        connection_string = get_azure_storage_connection_string()
        if not connection_string:
            raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not configured")
        self._container = get_azure_storage_container()
        self._client = BlobServiceClient.from_connection_string(connection_string)
        self._account_name = self._client.account_name
        self._account_key = self._client.credential.account_key

    def upload_bytes(self, path: str, data: bytes, content_type: str) -> None:
        blob = self._client.get_blob_client(container=self._container, blob=path)
        blob.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    def download_bytes(self, path: str) -> bytes:
        blob = self._client.get_blob_client(container=self._container, blob=path)
        return blob.download_blob().readall()

    def create_read_url(self, path: str, expires_in_minutes: int = 15) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)
        sas = generate_blob_sas(
            account_name=self._account_name,
            container_name=self._container,
            blob_name=path,
            account_key=self._account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expires_at,
        )
        blob = self._client.get_blob_client(container=self._container, blob=path)
        return f"{blob.url}?{sas}"


class LocalBlobStorage:
    def __init__(self, root: Path = None) -> None:
        self._root = root or get_local_blob_dir()

    def upload_bytes(self, path: str, data: bytes, content_type: str) -> None:
        target = self._safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def download_bytes(self, path: str) -> bytes:
        return self._safe_path(path).read_bytes()

    def create_read_url(self, path: str, expires_in_minutes: int = 15) -> str:
        raise RuntimeError("SAS URLs require Azure Blob Storage configuration")

    def _safe_path(self, path: str) -> Path:
        target = (self._root / path).resolve()
        root = self._root.resolve()
        if root not in target.parents and target != root:
            raise ValueError("Invalid blob path")
        return target


def get_blob_storage() -> BlobStorage:
    if get_azure_storage_connection_string():
        return AzureBlobStorage()
    return LocalBlobStorage()
