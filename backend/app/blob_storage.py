from pathlib import Path
from typing import Protocol

from azure.storage.blob import ContentSettings
from azure.storage.blob import BlobServiceClient

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


class AzureBlobStorage:
    def __init__(self) -> None:
        connection_string = get_azure_storage_connection_string()
        if not connection_string:
            raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not configured")
        self._container = get_azure_storage_container()
        self._client = BlobServiceClient.from_connection_string(connection_string)

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


class LocalBlobStorage:
    def __init__(self, root: Path = None) -> None:
        self._root = root or get_local_blob_dir()

    def upload_bytes(self, path: str, data: bytes, content_type: str) -> None:
        target = self._safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def download_bytes(self, path: str) -> bytes:
        return self._safe_path(path).read_bytes()

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
