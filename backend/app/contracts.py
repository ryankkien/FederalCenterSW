from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.authz import require_contract_view, seeded_contract, visible_contract_ids
from app.database import get_db
from app.models import (
    Contract,
    ContractAccessGrant,
    ContractHypothesis,
    ContractPrimitiveDeliverable,
    DocumentProcessingJob,
    DocumentUpload,
    RegressionFinding,
)

router = APIRouter(prefix="/api", tags=["contracts"])


class CitationResponse(BaseModel):
    document_id: str
    title: str
    source_path: Optional[str] = None
    excerpt: str


class SignalResponse(BaseModel):
    id: str
    label: str
    value: str
    confidence: Optional[float] = None
    citation_ids: List[str] = []


class TopicResponse(BaseModel):
    id: str
    contract_id: str
    title: str
    summary: str
    citations: List[CitationResponse] = []
    signals: List[SignalResponse] = []


class ContractResponse(BaseModel):
    id: str
    title: str
    status: str
    source: str
    contract_number: Optional[str] = None
    description: Optional[str] = None
    agency_name: Optional[str] = None
    office_name: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_uei: Optional[str] = None
    naics_code: Optional[str] = None
    psc_code: Optional[str] = None
    contract_type: Optional[str] = None
    competition_type: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    security_level: Optional[str] = None
    obligated_value: Optional[Decimal] = None
    contracting_officer: Optional[str] = None
    contractor_id: Optional[str] = None
    category_code: Optional[str] = None
    document_count: int
    open_regression_count: int = 0
    active_hypothesis_count: int = 0
    pending_job_count: int = 0
    unmatched_document_count: int = 0
    has_knowledge_base: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ContractCreateRequest(BaseModel):
    contract_number: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = Field(default=None, max_length=4000)
    agency_name: Optional[str] = Field(default=None, max_length=200)
    office_name: Optional[str] = Field(default=None, max_length=200)
    vendor_name: Optional[str] = Field(default=None, max_length=200)
    vendor_uei: Optional[str] = Field(default=None, max_length=32)
    naics_code: Optional[str] = Field(default=None, max_length=20)
    psc_code: Optional[str] = Field(default=None, max_length=20)
    contract_type: Optional[str] = Field(default=None, max_length=40)
    competition_type: Optional[str] = Field(default=None, max_length=40)
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    status: str = Field(default="pending_review", max_length=40)
    security_level: str = Field(default="standard", max_length=40)
    obligated_value: Optional[Decimal] = None
    contracting_officer: Optional[str] = Field(default=None, max_length=200)


class TrendResponse(BaseModel):
    contract_id: str
    topics: List[str]
    signal_counts: dict
    limitations: List[str] = []


@router.get("/contracts", response_model=List[ContractResponse])
def list_contracts(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ContractResponse]:
    ids = visible_contract_ids(user, db)
    return [_contract_response(contract_id, db) for contract_id in ids]


@router.post("/contracts", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
def create_contract(
    payload: ContractCreateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContractResponse:
    if user.role != "official":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Official access required")
    existing = db.scalars(
        select(Contract).where(Contract.contract_number == payload.contract_number)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Contract number already exists")
    contract = Contract(
        id=str(uuid4()),
        contract_number=payload.contract_number.strip(),
        title=payload.title.strip(),
        description=payload.description,
        agency_name=payload.agency_name,
        office_name=payload.office_name,
        vendor_name=payload.vendor_name,
        vendor_uei=payload.vendor_uei,
        naics_code=payload.naics_code,
        psc_code=payload.psc_code,
        contract_type=payload.contract_type,
        competition_type=payload.competition_type,
        period_start=payload.period_start,
        period_end=payload.period_end,
        status=payload.status,
        security_level=payload.security_level,
        metadata_json={
            "created_from": "portal",
            "created_by_id": user.id,
            "obligated_value": str(payload.obligated_value) if payload.obligated_value is not None else None,
            "contracting_officer": payload.contracting_officer,
        },
    )
    db.add(contract)
    db.add(
        ContractAccessGrant(
            id=str(uuid4()),
            contract_id=contract.id,
            principal_id=user.id,
            principal_type="user",
            role="owner",
            security_level=contract.security_level,
            granted_by_id=user.id,
        )
    )
    db.commit()
    return _contract_response(contract.id, db)


@router.get("/contracts/{contract_id}", response_model=ContractResponse)
def get_contract(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContractResponse:
    require_contract_view(user, db, contract_id)
    return _contract_response(contract_id, db)


@router.get("/contracts/{contract_id}/topics", response_model=List[TopicResponse])
def list_contract_topics(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[TopicResponse]:
    require_contract_view(user, db, contract_id)
    return topics_for_contract(db, contract_id)


@router.get("/contracts/{contract_id}/trends", response_model=TrendResponse)
def get_contract_trends(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrendResponse:
    require_contract_view(user, db, contract_id)
    topics = topics_for_contract(db, contract_id)
    signal_counts = {}
    for topic in topics:
        for signal in topic.signals:
            signal_counts[signal.label] = signal_counts.get(signal.label, 0) + 1

    limitations = []
    if not topics:
        limitations.append("No citable topics or extracted signals are available for this contract yet.")
    elif not signal_counts:
        limitations.append("Topics are available, but extracted trend signals are not available yet.")

    return TrendResponse(
        contract_id=contract_id,
        topics=[topic.title for topic in topics],
        signal_counts=signal_counts,
        limitations=limitations,
    )


@router.get("/contracts/{contract_id}/documents", response_model=List[dict])
def list_contract_documents(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    require_contract_view(user, db, contract_id)
    rows = list(
        db.scalars(
            select(DocumentUpload)
            .where(DocumentUpload.contract_id == contract_id)
            .order_by(DocumentUpload.created_at.desc())
        ).all()
    )
    return [
        {
            "id": row.id,
            "title": row.title,
            "document_type": row.document_type,
            "document_kind": row.document_kind,
            "match_status": row.match_status,
            "processing_status": row.processing_status,
            "original_filename": row.original_filename,
            "created_at": row.created_at,
        }
        for row in rows
    ]


class DeliverableItemResponse(BaseModel):
    id: str
    cdrl_item: Optional[str] = None
    deliverable_name: Optional[str] = None
    period_label: Optional[str] = None
    planned_due_date: Optional[str] = None
    actual_delivery_date: Optional[str] = None
    status: Optional[str] = None
    acceptance_status: Optional[str] = None
    days_late: Optional[int] = None


@router.get("/contracts/{contract_id}/deliverables", response_model=List[DeliverableItemResponse])
def list_contract_deliverables(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[DeliverableItemResponse]:
    require_contract_view(user, db, contract_id)
    rows = list(
        db.scalars(
            select(ContractPrimitiveDeliverable)
            .where(ContractPrimitiveDeliverable.contract_id == contract_id)
            .order_by(ContractPrimitiveDeliverable.planned_due_date.asc())
        ).all()
    )

    def _date_str(d) -> Optional[str]:
        if d is None:
            return None
        return d.isoformat() if hasattr(d, "isoformat") else str(d)

    return [
        DeliverableItemResponse(
            id=row.id,
            cdrl_item=row.cdrl_item,
            deliverable_name=row.deliverable_name,
            period_label=row.period_label,
            planned_due_date=_date_str(row.planned_due_date),
            actual_delivery_date=_date_str(row.actual_delivery_date),
            status=row.status,
            acceptance_status=row.acceptance_status,
            days_late=row.days_late,
        )
        for row in rows
    ]


def topics_for_contract(db: Session, contract_id: str) -> List[TopicResponse]:
    model_topics = _model_topics_for_contract(db, contract_id)
    if model_topics:
        return model_topics

    conditions = [DocumentUpload.id == contract_id]
    if hasattr(DocumentUpload, "contract_id"):
        conditions.append(DocumentUpload.contract_id == contract_id)
    documents = list(
        db.scalars(
            select(DocumentUpload)
            .where(or_(*conditions))
            .order_by(DocumentUpload.created_at.desc())
        ).all()
    )
    if not documents and seeded_contract(contract_id):
        return []

    topics: List[TopicResponse] = []
    for document in documents:
        citation = CitationResponse(
            document_id=document.id,
            title=document.title,
            source_path=document.blob_path,
            excerpt=_document_excerpt(document),
        )
        topics.append(
            TopicResponse(
                id=f"{document.id}:intake",
                contract_id=contract_id,
                title="Intake document",
                summary=f"{document.document_type} uploaded for contract review.",
                citations=[citation],
                signals=[],
            )
        )
    return topics


def _contract_response(contract_id: str, db: Session) -> ContractResponse:
    document = db.get(DocumentUpload, contract_id)
    record = _contract_record(db, contract_id)
    seed = seeded_contract(contract_id)

    if record is not None:
        topics = topics_for_contract(db, contract_id)
        metadata = _metadata(record)
        return ContractResponse(
            id=str(_attr(record, "id", "contract_id", "contract_key") or contract_id),
            title=str(_attr(record, "title", "contract_number", "name") or contract_id),
            status=str(_attr(record, "status") or "active"),
            source="contract_record",
            contract_number=_attr(record, "contract_number"),
            description=_attr(record, "description"),
            agency_name=_attr(record, "agency_name"),
            office_name=_attr(record, "office_name"),
            vendor_name=_attr(record, "vendor_name"),
            vendor_uei=_attr(record, "vendor_uei"),
            naics_code=_attr(record, "naics_code"),
            psc_code=_attr(record, "psc_code"),
            contract_type=_attr(record, "contract_type"),
            competition_type=_attr(record, "competition_type"),
            period_start=_attr(record, "period_start"),
            period_end=_attr(record, "period_end"),
            security_level=_attr(record, "security_level"),
            obligated_value=_decimal_or_none(metadata.get("obligated_value")),
            contracting_officer=metadata.get("contracting_officer"),
            contractor_id=_attr(record, "contractor_id", "vendor_uei", "vendor_name"),
            category_code=_attr(record, "category_code", "psc_code", "naics_code"),
            document_count=_document_count(db, contract_id),
            **_contract_counts(db, contract_id),
            has_knowledge_base=bool(topics),
            created_at=_attr(record, "created_at"),
            updated_at=_attr(record, "updated_at"),
        )

    if document is not None:
        topics = topics_for_contract(db, contract_id)
        return ContractResponse(
            id=document.id,
            title=document.title,
            status="uploaded",
            source="document_upload",
            contract_number=document.title,
            description=document.notes,
            security_level=document.security_level,
            contractor_id=document.uploader_id if document.uploader_role == "contractor" else None,
            category_code=seed.get("category_code") if seed else None,
            document_count=1,
            **_contract_counts(db, contract_id),
            has_knowledge_base=bool(topics),
            created_at=document.created_at,
        )

    if seed is not None:
        return ContractResponse(
            id=seed["id"],
            title=seed["title"],
            status=seed.get("status", "active"),
            source="seed",
            contractor_id=(seed.get("contractor_ids") or [None])[0],
            category_code=seed.get("category_code"),
            document_count=0,
            open_regression_count=0,
            active_hypothesis_count=0,
            pending_job_count=0,
            unmatched_document_count=0,
            has_knowledge_base=False,
            created_at=None,
            updated_at=None,
        )

    return ContractResponse(
        id=contract_id,
        title=contract_id,
        status="unknown",
        source="contract_record",
        contractor_id=None,
        category_code=None,
        document_count=0,
        open_regression_count=0,
        active_hypothesis_count=0,
        pending_job_count=0,
        unmatched_document_count=0,
        has_knowledge_base=False,
        created_at=None,
        updated_at=None,
    )


def _document_excerpt(document: DocumentUpload) -> str:
    if document.notes:
        return document.notes
    return f"{document.document_type}: {document.title}"


def _model_topics_for_contract(db: Session, contract_id: str) -> List[TopicResponse]:
    topic_model = _first_model("ContractTopic", "Topic")
    if topic_model is None or not _model_table_exists(db, topic_model):
        return []
    try:
        topic_rows = list(
            db.scalars(select(topic_model).where(topic_model.contract_id == contract_id)).all()
        )
    except SQLAlchemyError:
        return []

    topics: List[TopicResponse] = []
    for topic in topic_rows:
        citations = _topic_citations(db, topic)
        signals = _topic_signals(db, contract_id, citations)
        topics.append(
            TopicResponse(
                id=str(_attr(topic, "id", "topic_id", "topic_key") or ""),
                contract_id=contract_id,
                title=str(_attr(topic, "title", "topic_key") or "Contract topic"),
                summary=str(_attr(topic, "description", "summary") or "No topic summary is available."),
                citations=citations,
                signals=signals,
            )
        )
    return topics


def _topic_citations(db: Session, topic: Any) -> List[CitationResponse]:
    evidence_model = _first_model("TopicEvidence", "Evidence")
    topic_id = _attr(topic, "id", "topic_id")
    if evidence_model is None or topic_id is None or not _model_table_exists(db, evidence_model):
        return []
    try:
        rows = list(db.scalars(select(evidence_model).where(evidence_model.topic_id == topic_id)).all())
    except SQLAlchemyError:
        return []

    citations = []
    for evidence in rows:
        document_id = _attr(evidence, "document_upload_id", "document_id", "chunk_id", "id")
        document = db.get(DocumentUpload, document_id) if document_id else None
        citations.append(
            CitationResponse(
                document_id=str(document_id or ""),
                title=document.title if document is not None else str(_attr(evidence, "evidence_type") or "Evidence"),
                source_path=document.blob_path if document is not None else None,
                excerpt=str(_attr(evidence, "quote", "summary") or "Evidence text is not available."),
            )
        )
    return citations


def _topic_signals(
    db: Session, contract_id: str, citations: List[CitationResponse]
) -> List[SignalResponse]:
    signal_model = _first_model("PerformanceSignal", "ContractSignal", "Signal")
    if signal_model is None or not _model_table_exists(db, signal_model):
        return []
    try:
        rows = list(db.scalars(select(signal_model).where(signal_model.contract_id == contract_id)).all())
    except SQLAlchemyError:
        return []
    citation_ids = [citation.document_id for citation in citations if citation.document_id]
    return [
        SignalResponse(
            id=str(_attr(signal, "id", "signal_id") or ""),
            label=str(_attr(signal, "signal_type", "label") or "signal"),
            value=str(_attr(signal, "summary", "value", "label") or "No signal summary is available."),
            confidence=_attr(signal, "confidence"),
            citation_ids=citation_ids,
        )
        for signal in rows
    ]


def _document_count(db: Session, contract_id: str) -> int:
    conditions = [DocumentUpload.id == contract_id]
    if hasattr(DocumentUpload, "contract_id"):
        conditions.append(DocumentUpload.contract_id == contract_id)
    return len(list(db.scalars(select(DocumentUpload.id).where(or_(*conditions))).all()))


def _contract_counts(db: Session, contract_id: str) -> dict:
    document_ids = list(
        db.scalars(select(DocumentUpload.id).where(DocumentUpload.contract_id == contract_id)).all()
    )
    pending_jobs = 0
    if document_ids:
        pending_jobs = len(
            list(
                db.scalars(
                    select(DocumentProcessingJob.id).where(
                        DocumentProcessingJob.document_upload_id.in_(document_ids),
                        DocumentProcessingJob.status.in_(("queued", "processing", "pending")),
                    )
                ).all()
            )
        )
    return {
        "open_regression_count": len(
            list(
                db.scalars(
                    select(RegressionFinding.id).where(
                        RegressionFinding.contract_id == contract_id,
                        RegressionFinding.status == "open",
                    )
                ).all()
            )
        ),
        "active_hypothesis_count": len(
            list(
                db.scalars(
                    select(ContractHypothesis.id).where(
                        ContractHypothesis.contract_id == contract_id,
                        ContractHypothesis.status.in_(("proposed", "investigating", "supported")),
                    )
                ).all()
            )
        ),
        "pending_job_count": pending_jobs,
        "unmatched_document_count": len(
            list(
                db.scalars(
                    select(DocumentUpload.id).where(
                        DocumentUpload.contract_id == contract_id,
                        DocumentUpload.match_status.in_(("pending", "unmatched", "ambiguous")),
                    )
                ).all()
            )
        ),
    }


def _contract_record(db: Session, contract_id: str) -> Optional[Any]:
    model = _first_model("Contract", "ContractRecord")
    if model is None:
        return None
    try:
        return db.get(model, contract_id)
    except SQLAlchemyError:
        return None


def _metadata(row: Any) -> dict:
    value = getattr(row, "metadata_json", None)
    return value if isinstance(value, dict) else {}


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _first_model(*names: str) -> Optional[type]:
    try:
        import app.models as models
    except ImportError:
        return None
    for name in names:
        model = getattr(models, name, None)
        if model is not None:
            return model
    return None


def _model_table_exists(db: Session, model: type) -> bool:
    try:
        return sqlalchemy_inspect(db.get_bind()).has_table(model.__table__.name)
    except SQLAlchemyError:
        return False


def _attr(row: Any, *names: str) -> Optional[Any]:
    for name in names:
        value = getattr(row, name, None)
        if value is not None:
            return value
    return None
