import re
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user, require_contractor
from app.blob_storage import BlobStorage, get_blob_storage
from app.database import get_db
from app.models import DocumentUpload

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".csv", ".xlsx", ".png", ".jpg", ".jpeg"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png",
    "image/jpeg",
}


class DocumentResponse(BaseModel):
    id: str
    title: str
    document_type: str
    notes: Optional[str]
    original_filename: str
    content_type: str
    size_bytes: int
    uploader_id: str
    uploader_role: str
    created_at: datetime


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    title: str = Form(...),
    document_type: str = Form(...),
    notes: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: BlobStorage = Depends(get_blob_storage),
) -> DocumentResponse:
    require_contractor(user)

    filename = _clean_filename(file.filename or "document")
    content_type = file.content_type or "application/octet-stream"
    _validate_file(filename, content_type)

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

    document_id = str(uuid4())
    blob_path = f"documents/{user.id}/{document_id}/{filename}"
    storage.upload_bytes(blob_path, data, content_type)

    document = DocumentUpload(
        id=document_id,
        title=title.strip(),
        document_type=document_type.strip(),
        notes=notes.strip() if notes else None,
        original_filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        blob_path=blob_path,
        uploader_id=user.id,
        uploader_role=user.role,
        created_at=datetime.now(timezone.utc),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return _document_response(document)


@router.get("", response_model=List[DocumentResponse])
def list_documents(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[DocumentResponse]:
    statement = select(DocumentUpload).order_by(DocumentUpload.created_at.desc())
    if user.role == "contractor":
        statement = statement.where(DocumentUpload.uploader_id == user.id)
    documents = db.scalars(statement).all()
    return [_document_response(document) for document in documents]


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: BlobStorage = Depends(get_blob_storage),
) -> Response:
    document = db.get(DocumentUpload, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if user.role == "contractor" and document.uploader_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    data = storage.download_bytes(document.blob_path)
    return Response(
        content=data,
        media_type=document.content_type,
        headers={"Content-Disposition": f'attachment; filename="{document.original_filename}"'},
    )


def _validate_file(filename: str, content_type: str) -> None:
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS or content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type",
        )


def _clean_filename(filename: str) -> str:
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].strip()
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return cleaned or "document"


def _document_response(document: DocumentUpload) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        title=document.title,
        document_type=document.document_type,
        notes=document.notes,
        original_filename=document.original_filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        uploader_id=document.uploader_id,
        uploader_role=document.uploader_role,
        created_at=document.created_at,
    )
