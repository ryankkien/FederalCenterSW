from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.authz import require_unmatched_admin
from app.database import get_db
from app.models import DocumentUpload

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UnmatchedQueueItemResponse(BaseModel):
    id: str
    source: str
    title: str
    reason: str
    received_at: Optional[datetime] = None


class UnmatchedQueueResponse(BaseModel):
    items: List[UnmatchedQueueItemResponse]
    limitations: List[str] = []


@router.get("/unmatched", response_model=UnmatchedQueueResponse)
def list_unmatched_queue(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnmatchedQueueResponse:
    require_unmatched_admin(user)
    documents = list(
        db.scalars(
            select(DocumentUpload)
            .where(DocumentUpload.match_status.in_(("pending", "unmatched", "no_match")))
            .order_by(DocumentUpload.created_at.desc())
        ).all()
    )
    return UnmatchedQueueResponse(items=[_queue_item(document) for document in documents])


def _queue_item(document: DocumentUpload) -> UnmatchedQueueItemResponse:
    return UnmatchedQueueItemResponse(
        id=document.id,
        source=document.intake_source,
        title=document.title,
        reason=document.match_status,
        received_at=document.created_at,
    )
