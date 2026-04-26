from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.authz import require_contract_view
from app.contracts import topics_for_contract
from app.database import get_db
from app.models import DocumentProcessingJob, DocumentUpload

router = APIRouter(prefix="/api", tags=["processing"])


class ProcessingJobResponse(BaseModel):
    id: str
    contract_id: str
    job_type: str
    status: Literal["pending", "queued", "running", "completed", "failed"]
    message: Optional[str] = None
    created_at: datetime


@router.get("/contracts/{contract_id}/processing-jobs", response_model=List[ProcessingJobResponse])
def list_processing_jobs(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ProcessingJobResponse]:
    require_contract_view(user, db, contract_id)
    jobs = _stored_processing_jobs(db, contract_id)
    if jobs:
        return jobs

    topics = topics_for_contract(db, contract_id)
    if topics:
        return [
            ProcessingJobResponse(
                id=f"{contract_id}:topic-index",
                contract_id=contract_id,
                job_type="topic-index",
                status="completed",
                message="Document intake metadata is available as v1 retrieval scaffolding.",
                created_at=datetime.now(timezone.utc),
            )
        ]
    return []


@router.post(
    "/contracts/{contract_id}/processing-jobs",
    response_model=ProcessingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_processing_job(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProcessingJobResponse:
    require_contract_view(user, db, contract_id)
    return ProcessingJobResponse(
        id=f"{contract_id}:manual-review",
        contract_id=contract_id,
        job_type="manual-review",
        status="queued",
        message="Processing job accepted as a v1 placeholder; no background worker was started.",
        created_at=datetime.now(timezone.utc),
    )


def _stored_processing_jobs(db: Session, contract_id: str) -> List[ProcessingJobResponse]:
    document_ids = list(
        db.scalars(
            select(DocumentUpload.id).where(
                or_(DocumentUpload.id == contract_id, DocumentUpload.contract_id == contract_id)
            )
        ).all()
    )
    if not document_ids:
        return []
    rows = list(
        db.scalars(
            select(DocumentProcessingJob)
            .where(DocumentProcessingJob.document_upload_id.in_(document_ids))
            .order_by(DocumentProcessingJob.created_at.desc())
        ).all()
    )
    return [
        ProcessingJobResponse(
            id=job.id,
            contract_id=contract_id,
            job_type=job.job_type,
            status=_response_status(job.status),
            message=job.error_message,
            created_at=job.created_at,
        )
        for job in rows
    ]


def _response_status(job_status: str) -> str:
    if job_status == "processing":
        return "running"
    if job_status in {"pending", "queued", "running", "completed", "failed"}:
        return job_status
    return "pending"
