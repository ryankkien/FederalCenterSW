from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai.providers import get_ai_provider
from app.auth import CurrentUser, get_current_user
from app.authz import require_contract_view
from app.blob_storage import BlobStorage, get_blob_storage
from app.contract_analysis import create_investigation_run
from app.database import get_db
from app.models import (
    BaselineObligation,
    BaselineRevision,
    ContractBaseline,
    ContractHypothesis,
    ContractSimilarityLink,
    DocumentProcessingJob,
    DocumentSemanticLink,
    DocumentUpload,
    ExternalSourceRef,
    HypothesisEvidence,
    InvestigationRun,
    ProcessingRun,
    RegressionFinding,
)
from app.official_research import (
    fetch_official_source_text,
    official_source_candidates,
    summarize_official_source,
)
from app.processing import process_processing_job

router = APIRouter(prefix="/api", tags=["analysis"])


class BaselineObligationResponse(BaseModel):
    id: str
    obligation_type: str
    title: str
    description: str
    reference_text: Optional[str] = None
    source_document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    confidence: Optional[float] = None


class BaselineRevisionResponse(BaseModel):
    id: str
    revision_number: int
    change_type: str
    summary: str
    source_document_id: Optional[str] = None
    created_at: datetime


class ContractBaselineResponse(BaseModel):
    contract_id: str
    baseline_id: Optional[str] = None
    summary: Optional[str] = None
    current_revision_number: int = 0
    obligations: List[BaselineObligationResponse] = []
    revisions: List[BaselineRevisionResponse] = []
    limitations: List[str] = []


class RegressionFindingResponse(BaseModel):
    id: str
    contract_id: str
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    baseline_obligation_id: Optional[str] = None
    finding_type: str
    title: str
    summary: str
    severity: str
    status: str
    confidence: Optional[float] = None
    quote: Optional[str] = None
    created_at: datetime


class HypothesisEvidenceResponse(BaseModel):
    id: str
    evidence_type: str
    regression_finding_id: Optional[str] = None
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    quote: Optional[str] = None
    summary: str
    confidence: Optional[float] = None


class HypothesisResponse(BaseModel):
    id: str
    contract_id: str
    hypothesis_key: str
    title: str
    narrative: str
    status: str
    confidence: Optional[float] = None
    evidence: List[HypothesisEvidenceResponse] = []
    created_at: datetime
    updated_at: datetime


class ExternalSourceRequest(BaseModel):
    url: str = Field(min_length=1, max_length=1000)
    title: Optional[str] = Field(default=None, max_length=300)
    citation_text: Optional[str] = Field(default=None, max_length=2000)


class InvestigationRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    external_sources: List[ExternalSourceRequest] = []


class HypothesisStatusRequest(BaseModel):
    status: str = Field(pattern="^(proposed|investigating|supported|contradicted|closed)$")
    summary: Optional[str] = Field(default=None, max_length=2000)


class ExternalSourceResponse(BaseModel):
    id: str
    url: str
    title: Optional[str] = None
    source_domain: str
    source_type: str
    is_official: bool


class InvestigationRunResponse(BaseModel):
    id: str
    contract_id: str
    hypothesis_id: Optional[str] = None
    question: str
    status: str
    result_summary: str
    confidence: Optional[float] = None
    external_sources: List[ExternalSourceResponse] = []
    created_at: datetime


class SimilarContractResponse(BaseModel):
    id: str
    source_contract_id: str
    target_contract_id: str
    related_contract_id: str
    link_type: str
    summary: str
    score: Optional[float] = None
    metadata: Dict[str, object] = {}


class DocumentSemanticLinkResponse(BaseModel):
    id: str
    source_document_id: str
    target_document_id: str
    related_document_id: str
    link_type: str
    summary: str
    score: Optional[float] = None
    metadata: Dict[str, object] = {}


class DocumentRelationshipsResponse(BaseModel):
    document_id: str
    hard_parent_contract_id: Optional[str] = None
    semantic_links: List[DocumentSemanticLinkResponse] = []
    limitations: List[str] = []


class ProcessingJobRunResponse(BaseModel):
    job_id: str
    document_id: str
    status: str
    text_gate_status: str
    contract_match_status: Optional[str] = None
    matched_contract_id: Optional[str] = None
    matched_contract_number: Optional[str] = None
    chunk_count: int
    output_blob_path: Optional[str] = None
    error: Optional[str] = None


@router.post("/processing/jobs/{job_id}/run", response_model=ProcessingJobRunResponse)
def run_processing_job(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: BlobStorage = Depends(get_blob_storage),
) -> ProcessingJobRunResponse:
    job = db.get(DocumentProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processing job not found")
    document = db.get(DocumentUpload, job.document_upload_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    _require_document_access(document, user, db)

    result = process_processing_job(db, storage, job_id, get_ai_provider())
    match = result.contract_match
    return ProcessingJobRunResponse(
        job_id=job_id,
        document_id=result.document_id,
        status=result.status,
        text_gate_status=result.text_gate.status,
        contract_match_status=match.status if match else None,
        matched_contract_id=match.matched_contract_id if match else None,
        matched_contract_number=match.matched_contract_number if match else None,
        chunk_count=len(result.chunks),
        output_blob_path=result.output_blob_path,
        error=result.error,
    )


@router.get("/contracts/{contract_id}/baseline", response_model=ContractBaselineResponse)
def get_contract_baseline(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContractBaselineResponse:
    require_contract_view(user, db, contract_id)
    baseline = db.scalars(
        select(ContractBaseline).where(ContractBaseline.contract_id == contract_id)
    ).first()
    if baseline is None:
        return ContractBaselineResponse(
            contract_id=contract_id,
            limitations=["No interpreted baseline has been created for this contract yet."],
        )
    obligations = list(
        db.scalars(
            select(BaselineObligation)
            .where(BaselineObligation.baseline_id == baseline.id)
            .order_by(BaselineObligation.created_at.asc())
        ).all()
    )
    revisions = list(
        db.scalars(
            select(BaselineRevision)
            .where(BaselineRevision.baseline_id == baseline.id)
            .order_by(BaselineRevision.revision_number.asc())
        ).all()
    )
    return ContractBaselineResponse(
        contract_id=contract_id,
        baseline_id=baseline.id,
        summary=baseline.summary,
        current_revision_number=baseline.current_revision_number,
        obligations=[_obligation_response(item) for item in obligations],
        revisions=[_revision_response(item) for item in revisions],
    )


@router.get("/contracts/{contract_id}/regressions", response_model=List[RegressionFindingResponse])
def list_contract_regressions(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[RegressionFindingResponse]:
    require_contract_view(user, db, contract_id)
    rows = list(
        db.scalars(
            select(RegressionFinding)
            .where(RegressionFinding.contract_id == contract_id)
            .order_by(RegressionFinding.created_at.desc())
        ).all()
    )
    return [_finding_response(row) for row in rows]


@router.get("/contracts/{contract_id}/hypotheses", response_model=List[HypothesisResponse])
def list_contract_hypotheses(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[HypothesisResponse]:
    require_contract_view(user, db, contract_id)
    rows = list(
        db.scalars(
            select(ContractHypothesis)
            .where(ContractHypothesis.contract_id == contract_id)
            .order_by(ContractHypothesis.updated_at.desc())
        ).all()
    )
    return [_hypothesis_response(db, row) for row in rows]


@router.get(
    "/contracts/{contract_id}/hypotheses/{hypothesis_id}",
    response_model=HypothesisResponse,
)
def get_contract_hypothesis(
    contract_id: str,
    hypothesis_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HypothesisResponse:
    require_contract_view(user, db, contract_id)
    hypothesis = _get_hypothesis(db, contract_id, hypothesis_id)
    return _hypothesis_response(db, hypothesis)


@router.post(
    "/contracts/{contract_id}/hypotheses/{hypothesis_id}/investigate",
    response_model=InvestigationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def investigate_contract_hypothesis(
    contract_id: str,
    hypothesis_id: str,
    payload: InvestigationRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvestigationRunResponse:
    require_contract_view(user, db, contract_id)
    hypothesis = _get_hypothesis(db, contract_id, hypothesis_id)
    sources = [source.model_dump() for source in payload.external_sources]
    if not sources:
        sources = []
        for candidate in official_source_candidates(payload.question):
            fetched_text = ""
            try:
                fetched_text = fetch_official_source_text(candidate.url)
            except Exception:
                fetched_text = ""
            sources.append(
                {
                    "url": candidate.url,
                    "title": candidate.title,
                    "citation_text": summarize_official_source(
                        payload.question,
                        candidate.title,
                        fetched_text,
                        candidate.citation_text,
                    ),
                }
            )
    try:
        run = create_investigation_run(
            db,
            hypothesis,
            payload.question,
            created_by_id=user.id,
            external_sources=sources,
        )
        db.commit()
        db.refresh(run)
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return _investigation_response(db, run)


@router.post(
    "/contracts/{contract_id}/hypotheses/{hypothesis_id}/status",
    response_model=HypothesisResponse,
)
def update_hypothesis_status(
    contract_id: str,
    hypothesis_id: str,
    payload: HypothesisStatusRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HypothesisResponse:
    require_contract_view(user, db, contract_id)
    hypothesis = _get_hypothesis(db, contract_id, hypothesis_id)
    hypothesis.status = payload.status
    if payload.summary:
        metadata = hypothesis.metadata_json or {}
        metadata["manual_status_summary"] = payload.summary
        hypothesis.metadata_json = metadata
    db.commit()
    db.refresh(hypothesis)
    return _hypothesis_response(db, hypothesis)


@router.get("/contracts/{contract_id}/evidence")
def list_contract_evidence(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, object]:
    require_contract_view(user, db, contract_id)
    findings = list(
        db.scalars(
            select(RegressionFinding)
            .where(RegressionFinding.contract_id == contract_id)
            .order_by(RegressionFinding.created_at.desc())
        ).all()
    )
    hypotheses = list(
        db.scalars(
            select(ContractHypothesis)
            .where(ContractHypothesis.contract_id == contract_id)
            .order_by(ContractHypothesis.updated_at.desc())
        ).all()
    )
    external_refs = list(
        db.scalars(
            select(ExternalSourceRef)
            .where(ExternalSourceRef.contract_id == contract_id)
            .order_by(ExternalSourceRef.created_at.desc())
        ).all()
    )
    return {
        "contract_id": contract_id,
        "findings": [_finding_response(row).model_dump() for row in findings],
        "hypotheses": [_hypothesis_response(db, row).model_dump() for row in hypotheses],
        "external_sources": [_external_source_response(row).model_dump() for row in external_refs],
    }


@router.get("/contracts/{contract_id}/analysis-runs")
def list_contract_analysis_runs(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, object]]:
    require_contract_view(user, db, contract_id)
    rows = list(
        db.scalars(
            select(ProcessingRun)
            .where(ProcessingRun.contract_id == contract_id)
            .order_by(ProcessingRun.started_at.desc())
        ).all()
    )
    return [
        {
            "id": row.id,
            "document_id": row.document_upload_id,
            "status": row.status,
            "run_type": row.run_type,
            "model_name": row.model_name,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
        }
        for row in rows
    ]


@router.get("/contracts/{contract_id}/similar-contracts", response_model=List[SimilarContractResponse])
def list_similar_contracts(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[SimilarContractResponse]:
    require_contract_view(user, db, contract_id)
    rows = list(
        db.scalars(
            select(ContractSimilarityLink)
            .where(
                or_(
                    ContractSimilarityLink.source_contract_id == contract_id,
                    ContractSimilarityLink.target_contract_id == contract_id,
                )
            )
            .order_by(ContractSimilarityLink.score.desc())
        ).all()
    )
    return [
        _similar_contract_response(row, contract_id)
        for row in rows
        if _can_view_related_contract(row, contract_id, user, db)
    ]


@router.get("/documents/{document_id}/relationships", response_model=DocumentRelationshipsResponse)
def get_document_relationships(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentRelationshipsResponse:
    document = db.get(DocumentUpload, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    _require_document_access(document, user, db)
    rows = list(
        db.scalars(
            select(DocumentSemanticLink)
            .where(
                or_(
                    DocumentSemanticLink.source_document_upload_id == document_id,
                    DocumentSemanticLink.target_document_upload_id == document_id,
                )
            )
            .order_by(DocumentSemanticLink.score.desc())
        ).all()
    )
    links = [
        _document_semantic_link_response(row, document_id)
        for row in rows
        if _can_view_related_document(row, document_id, user, db)
    ]
    limitations = []
    if not links:
        limitations.append("No semantic document links have been created for this document yet.")
    return DocumentRelationshipsResponse(
        document_id=document_id,
        hard_parent_contract_id=document.contract_id,
        semantic_links=links,
        limitations=limitations,
    )


def _get_hypothesis(db: Session, contract_id: str, hypothesis_id: str) -> ContractHypothesis:
    hypothesis = db.get(ContractHypothesis, hypothesis_id)
    if hypothesis is None or hypothesis.contract_id != contract_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hypothesis not found")
    return hypothesis


def _require_document_access(document: DocumentUpload, user: CurrentUser, db: Session) -> None:
    if document.contract_id:
        require_contract_view(user, db, document.contract_id)
        return
    if user.role == "contractor" and document.uploader_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")


def _can_view_related_contract(
    row: ContractSimilarityLink,
    current_contract_id: str,
    user: CurrentUser,
    db: Session,
) -> bool:
    related_id = (
        row.target_contract_id
        if row.source_contract_id == current_contract_id
        else row.source_contract_id
    )
    try:
        require_contract_view(user, db, related_id)
    except HTTPException:
        return False
    return True


def _can_view_related_document(
    row: DocumentSemanticLink,
    current_document_id: str,
    user: CurrentUser,
    db: Session,
) -> bool:
    related_id = (
        row.target_document_upload_id
        if row.source_document_upload_id == current_document_id
        else row.source_document_upload_id
    )
    document = db.get(DocumentUpload, related_id)
    if document is None:
        return False
    try:
        _require_document_access(document, user, db)
    except HTTPException:
        return False
    return True


def _obligation_response(item: BaselineObligation) -> BaselineObligationResponse:
    return BaselineObligationResponse(
        id=item.id,
        obligation_type=item.obligation_type,
        title=item.title,
        description=item.description,
        reference_text=item.reference_text,
        source_document_id=item.source_document_upload_id,
        chunk_id=item.chunk_id,
        confidence=item.confidence,
    )


def _revision_response(item: BaselineRevision) -> BaselineRevisionResponse:
    return BaselineRevisionResponse(
        id=item.id,
        revision_number=item.revision_number,
        change_type=item.change_type,
        summary=item.summary,
        source_document_id=item.source_document_upload_id,
        created_at=item.created_at,
    )


def _finding_response(item: RegressionFinding) -> RegressionFindingResponse:
    return RegressionFindingResponse(
        id=item.id,
        contract_id=item.contract_id,
        document_id=item.document_upload_id,
        chunk_id=item.chunk_id,
        baseline_obligation_id=item.baseline_obligation_id,
        finding_type=item.finding_type,
        title=item.title,
        summary=item.summary,
        severity=item.severity,
        status=item.status,
        confidence=item.confidence,
        quote=item.quote,
        created_at=item.created_at,
    )


def _hypothesis_response(db: Session, item: ContractHypothesis) -> HypothesisResponse:
    evidence = list(
        db.scalars(
            select(HypothesisEvidence)
            .where(HypothesisEvidence.hypothesis_id == item.id)
            .order_by(HypothesisEvidence.created_at.asc())
        ).all()
    )
    return HypothesisResponse(
        id=item.id,
        contract_id=item.contract_id,
        hypothesis_key=item.hypothesis_key,
        title=item.title,
        narrative=item.narrative,
        status=item.status,
        confidence=item.confidence,
        evidence=[_hypothesis_evidence_response(row) for row in evidence],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _hypothesis_evidence_response(item: HypothesisEvidence) -> HypothesisEvidenceResponse:
    return HypothesisEvidenceResponse(
        id=item.id,
        evidence_type=item.evidence_type,
        regression_finding_id=item.regression_finding_id,
        document_id=item.document_upload_id,
        chunk_id=item.chunk_id,
        quote=item.quote,
        summary=item.summary,
        confidence=item.confidence,
    )


def _investigation_response(db: Session, item: InvestigationRun) -> InvestigationRunResponse:
    sources = list(
        db.scalars(
            select(ExternalSourceRef)
            .where(ExternalSourceRef.investigation_run_id == item.id)
            .order_by(ExternalSourceRef.created_at.asc())
        ).all()
    )
    return InvestigationRunResponse(
        id=item.id,
        contract_id=item.contract_id,
        hypothesis_id=item.hypothesis_id,
        question=item.question,
        status=item.status,
        result_summary=item.result_summary,
        confidence=item.confidence,
        external_sources=[_external_source_response(row) for row in sources],
        created_at=item.created_at,
    )


def _external_source_response(item: ExternalSourceRef) -> ExternalSourceResponse:
    return ExternalSourceResponse(
        id=item.id,
        url=item.url,
        title=item.title,
        source_domain=item.source_domain,
        source_type=item.source_type,
        is_official=item.is_official,
    )


def _similar_contract_response(
    item: ContractSimilarityLink,
    current_contract_id: str,
) -> SimilarContractResponse:
    related_id = (
        item.target_contract_id if item.source_contract_id == current_contract_id else item.source_contract_id
    )
    return SimilarContractResponse(
        id=item.id,
        source_contract_id=item.source_contract_id,
        target_contract_id=item.target_contract_id,
        related_contract_id=related_id,
        link_type=item.link_type,
        summary=item.summary,
        score=item.score,
        metadata=item.metadata_json or {},
    )


def _document_semantic_link_response(
    item: DocumentSemanticLink,
    current_document_id: str,
) -> DocumentSemanticLinkResponse:
    related_id = (
        item.target_document_upload_id
        if item.source_document_upload_id == current_document_id
        else item.source_document_upload_id
    )
    return DocumentSemanticLinkResponse(
        id=item.id,
        source_document_id=item.source_document_upload_id,
        target_document_id=item.target_document_upload_id,
        related_document_id=related_id,
        link_type=item.link_type,
        summary=item.summary,
        score=item.score,
        metadata=item.metadata_json or {},
    )
