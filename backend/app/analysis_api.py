from collections import Counter, defaultdict
from datetime import date, datetime
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai.providers import get_ai_provider
from app.analysis_orchestrator import (
    get_analysis_run,
    get_latest_analysis_run,
    run_cohort_analysis,
    run_per_contract_analysis,
)
from app.auth import CurrentUser, get_current_user
from app.authz import require_contract_view, visible_contract_ids
from app.blob_storage import BlobStorage, get_blob_storage
from app.cohort_builder import build_cohort
from app.contract_analysis import create_investigation_run
from app.database import get_db
from app.models import (
    BaselineObligation,
    BaselineRevision,
    Contract,
    ContractBaseline,
    ContractHypothesis,
    ContractSimilarityLink,
    ChunkEmbedding,
    DocumentChunk,
    DocumentProcessingJob,
    DocumentReportFact,
    DocumentSemanticLink,
    DocumentUpload,
    ExternalSourceRef,
    HypothesisEvidence,
    InvestigationRun,
    KnowledgeSourceRecord,
    PerformanceSignal,
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


class TimelineSignalResponse(BaseModel):
    id: str
    category: str
    label: str
    summary: str
    polarity: str
    severity: Optional[str] = None
    confidence: Optional[float] = None
    document_id: Optional[str] = None
    quote: Optional[str] = None
    responsible_party: Optional[str] = None
    recurrence_key: str


class TimelineReportResponse(BaseModel):
    document_id: str
    title: str
    document_kind: str
    period_label: str
    report_period_start: Optional[str] = None
    report_period_end: Optional[str] = None
    created_at: datetime
    processing_status: str
    signals: List[TimelineSignalResponse] = []


class ContractPatternResponse(BaseModel):
    key: str
    title: str
    count: int
    document_count: int
    first_period_label: Optional[str] = None
    last_period_label: Optional[str] = None
    examples: List[str] = []


class CparsRatingResponse(BaseModel):
    label: str
    rating: str
    period_label: Optional[str] = None
    summary: Optional[str] = None
    source: str


class PrimitiveCitationResponse(BaseModel):
    primitive_id: str
    primitive_type: str
    document_id: Optional[str] = None
    label: Optional[str] = None
    excerpt: Optional[str] = None


class AnalystClaimResponse(BaseModel):
    title: str
    finding: str
    citations: List[PrimitiveCitationResponse] = []
    confidence: Optional[float] = None


class PerformanceAxisResponse(BaseModel):
    axis: str
    status: str
    target_value: Dict[str, object] = {}
    cohort_distribution: Optional[Dict[str, Optional[float]]] = None
    target_percentile: Optional[float] = None
    low_confidence: bool = False
    rationale: str
    citations: List[PrimitiveCitationResponse] = []


class PredictedCparsFactorResponse(BaseModel):
    factor: str
    rating: Optional[str] = None
    not_extractable: bool = False
    rationale: str
    citations: List[PrimitiveCitationResponse] = []


class AnalysisRunResponse(BaseModel):
    id: str
    run_type: str
    status: str
    target_contract_id: Optional[str] = None
    cohort_N: Optional[int] = None
    result: Optional[Dict[str, object]] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    model: Optional[str] = None


class ContractAnalystBriefResponse(BaseModel):
    problem_statement: str
    summary: str
    outcome_context: List[AnalystClaimResponse] = []
    recurring_vs_one_off: List[AnalystClaimResponse] = []
    pre_degradation_signals: List[AnalystClaimResponse] = []
    success_or_recovery_signals: List[AnalystClaimResponse] = []
    execution_assessment: List[AnalystClaimResponse] = []
    government_vs_contractor: List[AnalystClaimResponse] = []
    limitations: List[str] = []


class ContractTimelineAnalysisResponse(BaseModel):
    contract_id: str
    contract_title: str
    timeline: List[TimelineReportResponse]
    recurring_issues: List[ContractPatternResponse]
    one_off_issues: List[ContractPatternResponse]
    early_warning_signals: List[TimelineSignalResponse]
    positive_signals: List[TimelineSignalResponse]
    execution_patterns: List[TimelineSignalResponse]
    cpars_ratings: List[CparsRatingResponse]
    analyst_brief: Optional[ContractAnalystBriefResponse] = None
    ai_analysis: Optional[AnalysisRunResponse] = None
    axes: List[PerformanceAxisResponse] = []
    cpars_predicted: Dict[str, PredictedCparsFactorResponse] = {}
    limitations: List[str] = []


class CohortContractBriefResponse(BaseModel):
    contract_id: str
    contract_title: str
    performance_band: str
    document_count: int
    recurring_issue_count: int
    positive_signal_count: int
    execution_pattern_count: int
    cpars_rating_count: int


class CohortAnalysisResponse(BaseModel):
    contract_count: int
    contracts: List[CohortContractBriefResponse]
    poor_contract_common_patterns: List[ContractPatternResponse]
    well_performing_common_patterns: List[ContractPatternResponse]
    delta_lessons: List[str]
    qualitative_quantitative_correlations: List[str]
    execution_correlations: List[str]
    limitations: List[str] = []


class SimilarContractInsightResponse(BaseModel):
    contract_id: str
    contract_title: str
    similarity_score: Optional[float] = None
    match_basis: List[str] = []
    failure_points: List[ContractPatternResponse] = []
    early_warnings: List[TimelineSignalResponse] = []
    recommendations: List[str] = []


class ContractSimilarityInsightsResponse(BaseModel):
    contract_id: str
    target_contract_title: str
    similar_contracts: List[SimilarContractInsightResponse]
    shared_failure_points: List[ContractPatternResponse]
    recommendations: List[str]
    methodology: List[str]
    limitations: List[str] = []


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


@router.get("/analysis/contracts/{contract_id}", response_model=ContractTimelineAnalysisResponse)
def get_single_contract_analysis(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContractTimelineAnalysisResponse:
    _require_official_analysis(user)
    require_contract_view(user, db, contract_id)
    return _contract_timeline_analysis(db, contract_id, visible_contract_ids(user, db))


@router.get("/analysis/cohort", response_model=CohortAnalysisResponse)
def get_cohort_analysis(
    contract_ids: List[str] = Query(default_factory=list),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CohortAnalysisResponse:
    _require_official_analysis(user)
    visible_ids = visible_contract_ids(user, db)
    selected_ids = contract_ids or visible_ids
    for contract_id in selected_ids:
        require_contract_view(user, db, contract_id)
    analyses = [_contract_timeline_analysis(db, contract_id) for contract_id in selected_ids]
    return _cohort_analysis(analyses)


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


@router.get("/contracts/{contract_id}/similarity-insights", response_model=ContractSimilarityInsightsResponse)
def get_contract_similarity_insights(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContractSimilarityInsightsResponse:
    _require_official_analysis(user)
    require_contract_view(user, db, contract_id)
    return _contract_similarity_insights(db, contract_id, user)


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


class CohortDefinitionResponse(BaseModel):
    target_contract_id: str
    match_criteria: Dict[str, object]
    contract_ids: List[str]
    N: int
    low_confidence: bool


class CohortAnalysisRequest(BaseModel):
    contract_ids: List[str]
    cohort_definition: Optional[Dict[str, object]] = None


@router.get("/contracts/{contract_id}/cohort", response_model=CohortDefinitionResponse)
def get_contract_cohort(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CohortDefinitionResponse:
    require_contract_view(user, db, contract_id)
    cohort = build_cohort(db, contract_id)
    return CohortDefinitionResponse(
        target_contract_id=cohort.target_contract_id,
        match_criteria=cohort.match_criteria,
        contract_ids=cohort.contract_ids,
        N=cohort.N,
        low_confidence=cohort.low_confidence,
    )


@router.post(
    "/contracts/{contract_id}/performance-analysis",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_per_contract_analysis(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisRunResponse:
    require_contract_view(user, db, contract_id)
    try:
        run = run_per_contract_analysis(db, contract_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {exc}",
        ) from exc
    return AnalysisRunResponse(
        id=run["id"],
        run_type="per_contract",
        status=run["status"],
        target_contract_id=contract_id,
        result=run.get("result"),
        model=run.get("model"),
    )


@router.get(
    "/contracts/{contract_id}/performance-analysis/{run_id}",
    response_model=AnalysisRunResponse,
)
def get_per_contract_analysis(
    contract_id: str,
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisRunResponse:
    require_contract_view(user, db, contract_id)
    run = get_analysis_run(db, run_id)
    if run is None or run.get("target_contract_id") != contract_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found")
    return AnalysisRunResponse(
        id=run["id"],
        run_type=run["run_type"],
        status=run["status"],
        target_contract_id=run.get("target_contract_id"),
        result=run.get("result"),
        created_at=run.get("created_at"),
        completed_at=run.get("completed_at"),
        model=run.get("model"),
    )


@router.post(
    "/analysis/cohort-runs",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_cohort_analysis_run(
    payload: CohortAnalysisRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisRunResponse:
    if not payload.contract_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="contract_ids required")
    for cid in payload.contract_ids:
        require_contract_view(user, db, cid)
    try:
        run = run_cohort_analysis(db, payload.contract_ids, payload.cohort_definition)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cohort analysis failed: {exc}",
        ) from exc
    return AnalysisRunResponse(
        id=run["id"],
        run_type="cohort",
        status=run["status"],
        cohort_N=len(payload.contract_ids),
        result=run.get("result"),
        model=run.get("model"),
    )


@router.get("/analysis/cohort-runs/{run_id}", response_model=AnalysisRunResponse)
def get_cohort_analysis_run(
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisRunResponse:
    run = get_analysis_run(db, run_id)
    if run is None or run.get("run_type") != "cohort":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found")
    cids = run.get("cohort_contract_ids") or []
    for cid in cids:
        require_contract_view(user, db, cid)
    return AnalysisRunResponse(
        id=run["id"],
        run_type=run["run_type"],
        status=run["status"],
        cohort_N=len(cids),
        result=run.get("result"),
        created_at=run.get("created_at"),
        completed_at=run.get("completed_at"),
        model=run.get("model"),
    )


def _contract_timeline_analysis(
    db: Session,
    contract_id: str,
    cohort_ids: Optional[Sequence[str]] = None,
) -> ContractTimelineAnalysisResponse:
    contract = db.get(Contract, contract_id)
    documents = _timeline_documents(db, contract_id)
    signals_by_document = _timeline_signals_by_document(db, contract_id)
    timeline = [
        TimelineReportResponse(
            document_id=document.id,
            title=document.title,
            document_kind=_display_document_kind(document),
            period_label=_period_label(db, document),
            report_period_start=str(_report_period(db, document)[0]) if _report_period(db, document)[0] else None,
            report_period_end=str(_report_period(db, document)[1]) if _report_period(db, document)[1] else None,
            created_at=document.created_at,
            processing_status=document.processing_status,
            signals=signals_by_document.get(document.id, []),
        )
        for document in documents
    ]
    all_signals = [signal for report in timeline for signal in report.signals]
    recurring, one_off = _issue_patterns(timeline)
    cpars_ratings = _cpars_ratings(db, contract_id)
    cohort_scope = list(dict.fromkeys(cohort_ids or [contract_id]))
    if contract_id not in cohort_scope:
        cohort_scope.insert(0, contract_id)
    axes = _contract_axes(db, contract_id, timeline, cohort_scope)
    cpars_predicted = _predicted_cpars_from_axes(axes)
    latest_ai_run = get_latest_analysis_run(db, contract_id)
    limitations = []
    if not timeline:
        limitations.append("No child reports are linked to this contract yet.")
    if not cpars_ratings:
        limitations.append("No CPARS ratings are available unless authorized CPARS exports have been imported.")
    if not all_signals:
        limitations.append("No report signals are available yet; run document processing after ingesting report text.")

    return ContractTimelineAnalysisResponse(
        contract_id=contract_id,
        contract_title=contract.title if contract is not None else contract_id,
        timeline=timeline,
        recurring_issues=recurring,
        one_off_issues=one_off,
        early_warning_signals=_early_warning_signals(timeline, cpars_ratings),
        positive_signals=[signal for signal in all_signals if signal.polarity == "positive"][:20],
        execution_patterns=[signal for signal in all_signals if signal.category == "execution_pattern"][:20],
        cpars_ratings=cpars_ratings,
        ai_analysis=_analysis_run_response(latest_ai_run) if latest_ai_run else None,
        analyst_brief=_contract_analyst_brief(
            contract,
            timeline,
            recurring,
            one_off,
            cpars_ratings,
            axes,
            cpars_predicted,
        ),
        axes=axes,
        cpars_predicted=cpars_predicted,
        limitations=limitations,
    )


def _analysis_run_response(run: Dict[str, object]) -> AnalysisRunResponse:
    return AnalysisRunResponse(
        id=str(run["id"]),
        run_type=str(run["run_type"]),
        status=str(run["status"]),
        target_contract_id=run.get("target_contract_id"),  # type: ignore[arg-type]
        cohort_N=len(run.get("cohort_contract_ids") or []) if run.get("cohort_contract_ids") else None,
        result=run.get("result"),  # type: ignore[arg-type]
        created_at=run.get("created_at"),  # type: ignore[arg-type]
        completed_at=run.get("completed_at"),  # type: ignore[arg-type]
        model=run.get("model"),  # type: ignore[arg-type]
    )


def _require_official_analysis(user: CurrentUser) -> None:
    if user.role != "official":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Official access required")


def _contract_analyst_brief(
    contract: Optional[Contract],
    timeline: Sequence[TimelineReportResponse],
    recurring: Sequence[ContractPatternResponse],
    one_off: Sequence[ContractPatternResponse],
    cpars_ratings: Sequence[CparsRatingResponse],
    axes: Sequence[PerformanceAxisResponse],
    cpars_predicted: Dict[str, PredictedCparsFactorResponse],
) -> ContractAnalystBriefResponse:
    all_signals = [signal for report in timeline for signal in report.signals]
    weak_cpars = [item for item in cpars_ratings if _is_weak_cpars_rating(item.rating)]
    negative_signals = [signal for signal in all_signals if signal.polarity == "negative"]
    positive_signals = [signal for signal in all_signals if signal.polarity == "positive"]
    title = contract.title if contract is not None else "Selected contract"
    problem_statement = (
        "Explain the performance outcome using cited primitive records from the contract timeline and comparable cohort. "
        "Do not infer contract structure or CPARS outcomes when the required primitives are absent."
    )

    outcome_context: List[AnalystClaimResponse] = []
    if weak_cpars:
        outcome_context.append(
            AnalystClaimResponse(
                title="Imported CPARS outcome",
                finding=(
                    f"{title} has weak imported CPARS rating(s): "
                    f"{', '.join(f'{item.label} {item.rating}' for item in weak_cpars[:4])}."
                ),
                citations=[
                    PrimitiveCitationResponse(
                        primitive_id=f"cpars:{item.label}:{item.period_label or item.source}",
                        primitive_type="cpars_rating",
                        label=item.label,
                        excerpt=item.summary,
                    )
                    for item in weak_cpars[:4]
                ],
                confidence=0.8,
            )
        )
    else:
        flagged_axis = next((axis for axis in axes if axis.axis in {"cost_performance", "schedule_performance"} and axis.status == "measured"), None)
        if flagged_axis is not None:
            outcome_context.append(
                AnalystClaimResponse(
                    title="Performance outcome proxy",
                    finding=(
                        f"No actual CPARS rating is imported, so the analyst layer uses measured "
                        f"{flagged_axis.axis.replace('_', ' ')} primitives as the outcome proxy."
                    ),
                    citations=flagged_axis.citations[:4],
                    confidence=0.62,
                )
            )

    recurring_claims = [
        AnalystClaimResponse(
            title=f"Recurring issue: {pattern.title}",
            finding=(
                f"{pattern.title} appears across {pattern.document_count} report period(s), "
                f"which makes it more likely to be a timeline pattern than a one-off."
            ),
            citations=_citations_for_pattern(timeline, pattern)[:5],
            confidence=0.7,
        )
        for pattern in recurring[:5]
    ]
    if one_off:
        recurring_claims.append(
            AnalystClaimResponse(
                title="One-off issues",
                finding=(
                    f"{len(one_off)} issue family/families appear in a single report period and should be treated as one-off until repeated."
                ),
                citations=_citations_for_pattern(timeline, one_off[0])[:3],
                confidence=0.58,
            )
        )

    early_warnings = _early_warning_signals(timeline, cpars_ratings)
    pre_degradation_claims = [
        AnalystClaimResponse(
            title=f"Pre-degradation signal: {signal.label}",
            finding=f"{signal.label} was present before the first detected degradation marker: {signal.summary}",
            citations=[_citation_for_signal(_report_for_signal(timeline, signal), signal)],
            confidence=signal.confidence,
        )
        for signal in early_warnings[:5]
        if _report_for_signal(timeline, signal) is not None
    ]

    success_claims = [
        AnalystClaimResponse(
            title=f"Positive signal: {signal.label}",
            finding=f"{signal.label} appears as a positive or recovery signal: {signal.summary}",
            citations=[_citation_for_signal(_report_for_signal(timeline, signal), signal)],
            confidence=signal.confidence,
        )
        for signal in positive_signals[:5]
        if _report_for_signal(timeline, signal) is not None
    ]

    execution_claims = []
    for label, signals in _signals_by_label([signal for signal in all_signals if signal.category == "execution_pattern"]).items():
        polarities = Counter(signal.polarity for signal in signals)
        first = signals[0]
        report = _report_for_signal(timeline, first)
        execution_claims.append(
            AnalystClaimResponse(
                title=f"Execution pattern: {label}",
                finding=(
                    f"{label} appears in {len({signal.document_id for signal in signals if signal.document_id})} report period(s) "
                    f"with polarity mix {dict(polarities)}. This describes how work was being executed, not just whether outcomes were good or bad."
                ),
                citations=[_citation_for_signal(report, signal) for signal in signals[:4] if _report_for_signal(timeline, signal) is not None],
                confidence=0.64,
            )
        )

    responsible_party_counts = Counter(signal.responsible_party or "unclear" for signal in negative_signals)
    party_claims = []
    if responsible_party_counts:
        party, count = responsible_party_counts.most_common(1)[0]
        party_signals = [signal for signal in negative_signals if (signal.responsible_party or "unclear") == party]
        party_claims.append(
            AnalystClaimResponse(
                title="Responsibility pattern",
                finding=f"Negative report signals most often point to {party} as the responsible-party bucket ({count} signal(s)).",
                citations=[
                    _citation_for_signal(_report_for_signal(timeline, signal), signal)
                    for signal in party_signals[:5]
                    if _report_for_signal(timeline, signal) is not None
                ],
                confidence=0.6,
            )
        )

    measured_axes = [axis for axis in axes if axis.status == "measured"]
    predicted = [item for item in cpars_predicted.values() if not item.not_extractable and item.rating]
    summary_parts = []
    if recurring_claims and recurring_claims[0].citations:
        summary_parts.append(f"{recurring_claims[0].finding} [{recurring_claims[0].citations[0].primitive_id}]")
    if measured_axes and measured_axes[0].citations:
        summary_parts.append(f"{measured_axes[0].rationale} [{measured_axes[0].citations[0].primitive_id}]")
    if predicted and predicted[0].citations:
        summary_parts.append(f"Predicted {predicted[0].factor} CPARS is {predicted[0].rating} because {predicted[0].rationale} [{predicted[0].citations[0].primitive_id}]")
    summary = " ".join(summary_parts) or "No cited analyst summary is available until report primitives are extracted."

    limitations = []
    if not cpars_ratings:
        limitations.append("Actual CPARS ratings are absent; predicted CPARS mappings are labeled separately and only use extracted primitives.")
    if not measured_axes:
        limitations.append("No measurement axis has enough primitives for a measured finding.")
    if len(timeline) < 3:
        limitations.append("Timeline has fewer than three report periods, so recurring-vs-one-off analysis is weak.")

    return ContractAnalystBriefResponse(
        problem_statement=problem_statement,
        summary=_trim(summary, 1200),
        outcome_context=outcome_context,
        recurring_vs_one_off=recurring_claims,
        pre_degradation_signals=pre_degradation_claims,
        success_or_recovery_signals=success_claims,
        execution_assessment=execution_claims[:6],
        government_vs_contractor=party_claims,
        limitations=limitations,
    )


def _contract_axes(
    db: Session,
    contract_id: str,
    timeline: Sequence[TimelineReportResponse],
    cohort_ids: Sequence[str],
) -> List[PerformanceAxisResponse]:
    metrics_by_contract = {item: _axis_metrics_for_contract(db, item) for item in cohort_ids}
    target_metrics = metrics_by_contract.get(contract_id) or _axis_metrics_for_timeline(timeline)
    cohort_n = len(metrics_by_contract)
    low_confidence = cohort_n < 20
    return [
        _schedule_axis(target_metrics, metrics_by_contract, low_confidence),
        _cost_axis(target_metrics, metrics_by_contract, low_confidence),
        _scope_axis(target_metrics, metrics_by_contract, low_confidence),
        _execution_risk_axis(target_metrics, metrics_by_contract, low_confidence),
        _forecasting_axis(target_metrics, metrics_by_contract, low_confidence),
        _quality_axis(target_metrics, metrics_by_contract, low_confidence),
        _small_business_axis(),
        _compliance_axis(target_metrics, metrics_by_contract, low_confidence),
        _closeout_axis(),
    ]


def _axis_metrics_for_contract(db: Session, contract_id: str) -> Dict[str, object]:
    documents = _timeline_documents(db, contract_id)
    signals_by_document = _timeline_signals_by_document(db, contract_id)
    timeline = [
        TimelineReportResponse(
            document_id=document.id,
            title=document.title,
            document_kind=_display_document_kind(document),
            period_label=_period_label(db, document),
            report_period_start=str(_report_period(db, document)[0]) if _report_period(db, document)[0] else None,
            report_period_end=str(_report_period(db, document)[1]) if _report_period(db, document)[1] else None,
            created_at=document.created_at,
            processing_status=document.processing_status,
            signals=signals_by_document.get(document.id, []),
        )
        for document in documents
    ]
    return _axis_metrics_for_timeline(timeline)


def _axis_metrics_for_timeline(timeline: Sequence[TimelineReportResponse]) -> Dict[str, object]:
    signals = [signal for report in timeline for signal in report.signals]
    negative = [signal for signal in signals if signal.polarity == "negative"]
    positive = [signal for signal in signals if signal.polarity == "positive"]
    eac_values = _eac_values(signals)
    return {
        "timeline": timeline,
        "signals": signals,
        "negative_signals": negative,
        "positive_signals": positive,
        "schedule_signals": [
            signal
            for signal in negative
            if signal.category != "execution_pattern"
            and _contains_any(_signal_text(signal), ("schedule", "slip", "late", "critical path", "on-time", "on time"))
        ],
        "cost_signals": [
            signal
            for signal in signals
            if signal.category != "execution_pattern"
            and _contains_any(_signal_text(signal), ("cost", "eac", "cv ", "variance", "burn", "rea", "unbudgeted"))
        ],
        "scope_signals": [signal for signal in signals if _contains_any(_signal_text(signal), ("scope", "modification", "out-of-scope", "unauthorized", "superseded direction"))],
        "execution_signals": [signal for signal in signals if signal.category == "execution_pattern"],
        "quality_negative": [signal for signal in negative if _contains_any(_signal_text(signal), ("quality", "qc", "defect", "rework", "rejection"))],
        "quality_positive": [signal for signal in positive if _contains_any(_signal_text(signal), ("quality", "qc", "accepted", "acceptance", "recovered", "approved"))],
        "compliance_signals": [signal for signal in signals if _contains_any(_signal_text(signal), ("compliance", "regulatory", "corrective action", "incident"))],
        "eac_values": eac_values,
        "citations": [_citation_for_signal(report, signal) for report in timeline for signal in report.signals],
    }


def _schedule_axis(
    target: Dict[str, object],
    cohort: Dict[str, Dict[str, object]],
    low_confidence: bool,
) -> PerformanceAxisResponse:
    signals = target["schedule_signals"]
    if not signals:
        return _not_extractable_axis("schedule_performance", "No deliverable-level schedule primitive or schedule regression signal is extracted.")
    values = {contract_id: float(len(metrics["schedule_signals"])) for contract_id, metrics in cohort.items()}
    return _measured_axis(
        "schedule_performance",
        {"schedule_signal_count": len(signals), "time_to_first_schedule_signal": _first_period_for_signals(target["timeline"], signals)},
        "Schedule performance is measured from extracted schedule-delay/regression signals; total slip and on-time rate are not extractable without deliverable primitives.",
        [_citation_for_signal(_report_for_signal(target["timeline"], signal), signal) for signal in signals[:6] if _report_for_signal(target["timeline"], signal)],
        values,
        float(len(signals)),
        low_confidence,
    )


def _cost_axis(target: Dict[str, object], cohort: Dict[str, Dict[str, object]], low_confidence: bool) -> PerformanceAxisResponse:
    signals = target["cost_signals"]
    eac_values = target["eac_values"]
    if not signals and not eac_values:
        return _not_extractable_axis("cost_performance", "No financial primitive, EAC value, or cost regression signal is extracted.")
    target_value: Dict[str, object] = {"cost_signal_count": len(signals)}
    if eac_values:
        target_value["latest_eac"] = eac_values[-1]
    if len(eac_values) >= 2:
        target_value["eac_drift"] = eac_values[-1] - eac_values[0]
    values = {contract_id: float(len(metrics["cost_signals"])) for contract_id, metrics in cohort.items()}
    return _measured_axis(
        "cost_performance",
        target_value,
        "Cost performance is measured from extracted cost variance, EAC, REA, or unbudgeted-effort primitives.",
        [_citation_for_signal(_report_for_signal(target["timeline"], signal), signal) for signal in signals[:6] if _report_for_signal(target["timeline"], signal)],
        values,
        float(len(signals)),
        low_confidence,
    )


def _scope_axis(target: Dict[str, object], cohort: Dict[str, Dict[str, object]], low_confidence: bool) -> PerformanceAxisResponse:
    signals = target["scope_signals"]
    if not signals:
        return _not_extractable_axis("scope_stability", "No modification, scope drift, or direction-change primitive is extracted.")
    values = {contract_id: float(len(metrics["scope_signals"])) for contract_id, metrics in cohort.items()}
    return _measured_axis(
        "scope_stability",
        {"scope_or_mod_signal_count": len(signals), "time_to_first_scope_signal": _first_period_for_signals(target["timeline"], signals)},
        "Scope stability is measured from extracted scope, modification, unauthorized-work, or superseded-direction primitives.",
        [_citation_for_signal(_report_for_signal(target["timeline"], signal), signal) for signal in signals[:6] if _report_for_signal(target["timeline"], signal)],
        values,
        float(len(signals)),
        low_confidence,
    )


def _execution_risk_axis(target: Dict[str, object], cohort: Dict[str, Dict[str, object]], low_confidence: bool) -> PerformanceAxisResponse:
    negative = target["negative_signals"]
    if not target["signals"]:
        return _not_extractable_axis("execution_and_risk", "No issue primitive or report signal is extracted.")
    values = {contract_id: float(len(metrics["negative_signals"])) for contract_id, metrics in cohort.items()}
    recurrence_count = len(_issue_patterns(target["timeline"])[0])
    party_counts = Counter(signal.responsible_party or "unclear" for signal in negative)
    return _measured_axis(
        "execution_and_risk",
        {
            "issue_signal_count": len(negative),
            "recurring_issue_family_count": recurrence_count,
            "responsible_party_distribution": dict(party_counts),
        },
        "Execution and risk is measured from issue signals, recurrence, and responsible-party labels extracted from report primitives.",
        [_citation_for_signal(_report_for_signal(target["timeline"], signal), signal) for signal in negative[:6] if _report_for_signal(target["timeline"], signal)],
        values,
        float(len(negative)),
        low_confidence,
    )


def _forecasting_axis(target: Dict[str, object], cohort: Dict[str, Dict[str, object]], low_confidence: bool) -> PerformanceAxisResponse:
    eac_values = target["eac_values"]
    if len(eac_values) < 2:
        return _not_extractable_axis("forecasting_accuracy", "EAC drift requires at least two extracted EAC values; issue-to-impact lag and percent-complete accuracy are not extractable.")
    values = {
        contract_id: float(metrics["eac_values"][-1] - metrics["eac_values"][0])
        for contract_id, metrics in cohort.items()
        if len(metrics["eac_values"]) >= 2
    }
    return _measured_axis(
        "forecasting_accuracy",
        {"eac_drift": eac_values[-1] - eac_values[0], "eac_observation_count": len(eac_values)},
        "Forecasting accuracy is measured only from extracted EAC drift; other forecasting primitives are unavailable.",
        [_citation_for_signal(_report_for_signal(target["timeline"], signal), signal) for signal in target["cost_signals"][:6] if _report_for_signal(target["timeline"], signal)],
        values,
        float(eac_values[-1] - eac_values[0]),
        low_confidence,
    )


def _quality_axis(target: Dict[str, object], cohort: Dict[str, Dict[str, object]], low_confidence: bool) -> PerformanceAxisResponse:
    negative = target["quality_negative"]
    positive = target["quality_positive"]
    if not negative and not positive:
        return _not_extractable_axis("quality", "No defect, rework, rejection, acceptance, or quality-control primitive is extracted.")
    values = {contract_id: float(len(metrics["quality_negative"])) for contract_id, metrics in cohort.items()}
    citations = [
        _citation_for_signal(_report_for_signal(target["timeline"], signal), signal)
        for signal in (negative + positive)[:6]
        if _report_for_signal(target["timeline"], signal)
    ]
    return _measured_axis(
        "quality",
        {"defect_or_rework_signal_count": len(negative), "quality_positive_signal_count": len(positive)},
        "Quality is measured from extracted quality-control, defect, rework, rejection, acceptance, or recovery primitives.",
        citations,
        values,
        float(len(negative)),
        low_confidence,
    )


def _small_business_axis() -> PerformanceAxisResponse:
    return PerformanceAxisResponse(
        axis="small_business_subcontracting",
        status="not_applicable",
        rationale="No small-business subcontracting threshold, goal, plan, or attainment primitive is extracted.",
        low_confidence=True,
    )


def _compliance_axis(target: Dict[str, object], cohort: Dict[str, Dict[str, object]], low_confidence: bool) -> PerformanceAxisResponse:
    signals = target["compliance_signals"]
    if not signals:
        return _not_extractable_axis("regulatory_compliance", "No compliance finding, corrective action, or incident primitive is extracted.")
    values = {contract_id: float(len(metrics["compliance_signals"])) for contract_id, metrics in cohort.items()}
    return _measured_axis(
        "regulatory_compliance",
        {"compliance_signal_count": len(signals)},
        "Regulatory compliance is measured from extracted compliance findings, corrective actions, or incidents.",
        [_citation_for_signal(_report_for_signal(target["timeline"], signal), signal) for signal in signals[:6] if _report_for_signal(target["timeline"], signal)],
        values,
        float(len(signals)),
        low_confidence,
    )


def _closeout_axis() -> PerformanceAxisResponse:
    return _not_extractable_axis("closeout", "No closeout, delivered-scope, descope, duration, or disputed-amount primitive is extracted.")


def _not_extractable_axis(axis: str, rationale: str) -> PerformanceAxisResponse:
    return PerformanceAxisResponse(axis=axis, status="not_extractable", rationale=rationale, low_confidence=True)


def _measured_axis(
    axis: str,
    target_value: Dict[str, object],
    rationale: str,
    citations: Sequence[PrimitiveCitationResponse],
    cohort_values: Dict[str, float],
    target_numeric: float,
    low_confidence: bool,
) -> PerformanceAxisResponse:
    cohort_distribution = _distribution(cohort_values.values()) if cohort_values else None
    return PerformanceAxisResponse(
        axis=axis,
        status="measured",
        target_value=target_value,
        cohort_distribution=cohort_distribution,
        target_percentile=_percentile_rank(cohort_values.values(), target_numeric) if cohort_values else None,
        low_confidence=low_confidence,
        rationale=rationale,
        citations=list(citations),
    )


def _predicted_cpars_from_axes(axes: Sequence[PerformanceAxisResponse]) -> Dict[str, PredictedCparsFactorResponse]:
    by_axis = {axis.axis: axis for axis in axes}
    mapping = {
        "Quality": "quality",
        "Schedule": "schedule_performance",
        "Cost Control": "cost_performance",
        "Management": "execution_and_risk",
        "Small Business Subcontracting": "small_business_subcontracting",
        "Regulatory Compliance": "regulatory_compliance",
    }
    return {
        factor: _predicted_factor(factor, by_axis.get(axis_key))
        for factor, axis_key in mapping.items()
    }


def _predicted_factor(factor: str, axis: Optional[PerformanceAxisResponse]) -> PredictedCparsFactorResponse:
    if axis is None or axis.status != "measured" or axis.target_percentile is None:
        return PredictedCparsFactorResponse(
            factor=factor,
            not_extractable=True,
            rationale=f"{factor} prediction is not extractable because the required measured primitive axis is absent.",
            citations=[],
        )
    percentile = axis.target_percentile
    if factor in {"Schedule", "Cost Control", "Management", "Quality", "Regulatory Compliance"}:
        if percentile >= 90:
            rating = "Unsatisfactory"
        elif percentile >= 75:
            rating = "Marginal"
        elif percentile >= 35:
            rating = "Satisfactory"
        elif percentile >= 10:
            rating = "Very Good"
        else:
            rating = "Exceptional"
    else:
        rating = None
    return PredictedCparsFactorResponse(
        factor=factor,
        rating=rating,
        not_extractable=rating is None,
        rationale=(
            f"Target is at the {percentile:.0f}th percentile for {axis.axis.replace('_', ' ')} "
            f"within the visible cohort; higher percentile indicates more negative extracted signals. "
            f"low_confidence={str(axis.low_confidence).lower()}."
        ),
        citations=axis.citations[:5],
    )


def _cohort_analysis(analyses: Sequence[ContractTimelineAnalysisResponse]) -> CohortAnalysisResponse:
    briefs = [_cohort_brief(analysis) for analysis in analyses]
    poor_ids = {brief.contract_id for brief in briefs if brief.performance_band == "poor"}
    well_ids = {brief.contract_id for brief in briefs if brief.performance_band in {"well_performing", "recovered"}}
    poor_patterns = _cohort_common_patterns(
        [analysis for analysis in analyses if analysis.contract_id in poor_ids],
        include_positive=False,
    )
    well_patterns = _cohort_common_patterns(
        [analysis for analysis in analyses if analysis.contract_id in well_ids],
        include_positive=True,
    )
    limitations = []
    if len(analyses) < 2:
        limitations.append("Cohort analysis needs at least two visible contracts to compare patterns.")
    if not any(analysis.cpars_ratings for analysis in analyses):
        limitations.append("CPARS quantitative correlation is limited because no CPARS ratings are imported.")

    return CohortAnalysisResponse(
        contract_count=len(analyses),
        contracts=briefs,
        poor_contract_common_patterns=poor_patterns,
        well_performing_common_patterns=well_patterns,
        delta_lessons=_delta_lessons(poor_patterns, well_patterns),
        qualitative_quantitative_correlations=_qualitative_quantitative_correlations(analyses),
        execution_correlations=_execution_correlations(analyses),
        limitations=limitations,
    )


def _contract_similarity_insights(
    db: Session,
    contract_id: str,
    user: CurrentUser,
) -> ContractSimilarityInsightsResponse:
    target = db.get(Contract, contract_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    target_analysis = _contract_timeline_analysis(db, contract_id)
    candidate_basis: Dict[str, List[str]] = defaultdict(list)
    candidate_scores: Dict[str, float] = {}
    limitations: List[str] = []

    for row in _similarity_link_rows(db, contract_id):
        related_id = _related_contract_id(row, contract_id)
        if not _can_view_related_contract(row, contract_id, user, db):
            continue
        shared_tags = []
        if row.metadata_json:
            shared_tags = [str(item) for item in row.metadata_json.get("shared_tags", [])]
        if shared_tags:
            candidate_basis[related_id].append(f"Shared extracted tags: {', '.join(shared_tags[:5])}.")
        else:
            candidate_basis[related_id].append(row.summary)
        if row.score is not None:
            candidate_scores[related_id] = max(candidate_scores.get(related_id, 0.0), row.score)

    embedding_scores = _embedding_contract_scores(db, contract_id)
    if embedding_scores:
        for related_id, score in embedding_scores.items():
            if related_id == contract_id:
                continue
            try:
                require_contract_view(user, db, related_id)
            except HTTPException:
                continue
            candidate_basis[related_id].append("Embedding similarity from indexed document chunks.")
            candidate_scores[related_id] = max(candidate_scores.get(related_id, 0.0), score)
    else:
        limitations.append("No chunk embeddings are available yet, so similarity falls back to semantic links and cohort metadata.")

    if not candidate_basis:
        try:
            cohort = build_cohort(db, contract_id)
        except ValueError:
            cohort = None
        if cohort is not None:
            for related_id in cohort.contract_ids:
                try:
                    require_contract_view(user, db, related_id)
                except HTTPException:
                    continue
                candidate_basis[related_id].append(_cohort_match_basis(cohort.match_criteria))
                candidate_scores.setdefault(related_id, 0.0)
            if not cohort.contract_ids:
                limitations.append("The cohort builder did not find comparable visible contracts.")

    ordered_candidate_ids = sorted(
        candidate_basis,
        key=lambda item: (-candidate_scores.get(item, 0.0), item),
    )[:8]
    candidate_analyses = [_contract_timeline_analysis(db, item) for item in ordered_candidate_ids]
    similar_contracts = [
        _similar_contract_insight_response(
            analysis,
            candidate_scores.get(analysis.contract_id),
            candidate_basis[analysis.contract_id],
        )
        for analysis in candidate_analyses
    ]
    shared_failure_points = _cohort_common_patterns([target_analysis, *candidate_analyses], include_positive=False)
    recommendations = _dedupe(
        [
            item
            for insight in similar_contracts
            for item in insight.recommendations
        ]
        + _recommendations_for_patterns(shared_failure_points)
    )[:10]
    if not similar_contracts:
        limitations.append("No visible similar contract has enough evidence for failure-point comparison yet.")
    if not recommendations:
        limitations.append("No recurring or comparable failure points are available for drafting guidance yet.")

    return ContractSimilarityInsightsResponse(
        contract_id=contract_id,
        target_contract_title=target.title,
        similar_contracts=similar_contracts,
        shared_failure_points=shared_failure_points,
        recommendations=recommendations,
        methodology=[
            "Use chunk-embedding similarity when indexed embeddings exist.",
            "Use stored semantic similarity links from extracted regression/report signals.",
            "Use cohort metadata matching as a fallback when semantic similarity is sparse.",
            "Translate observed failure patterns into contract-writing controls with cited source signals.",
        ],
        limitations=_dedupe(limitations),
    )


def _similar_contract_insight_response(
    analysis: ContractTimelineAnalysisResponse,
    score: Optional[float],
    match_basis: Sequence[str],
) -> SimilarContractInsightResponse:
    failure_points = analysis.recurring_issues or analysis.one_off_issues[:4]
    early_warnings = analysis.early_warning_signals[:4]
    return SimilarContractInsightResponse(
        contract_id=analysis.contract_id,
        contract_title=analysis.contract_title,
        similarity_score=score,
        match_basis=_dedupe(match_basis)[:4],
        failure_points=failure_points[:4],
        early_warnings=early_warnings,
        recommendations=_recommendations_for_patterns(failure_points, early_warnings)[:5],
    )


def _similarity_link_rows(db: Session, contract_id: str) -> List[ContractSimilarityLink]:
    return list(
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


def _related_contract_id(row: ContractSimilarityLink, current_contract_id: str) -> str:
    return row.target_contract_id if row.source_contract_id == current_contract_id else row.source_contract_id


def _embedding_contract_scores(db: Session, contract_id: str) -> Dict[str, float]:
    rows = list(
        db.execute(
            select(DocumentChunk.contract_id, ChunkEmbedding.embedding)
            .join(ChunkEmbedding, ChunkEmbedding.chunk_id == DocumentChunk.id)
            .where(DocumentChunk.contract_id.isnot(None))
        ).all()
    )
    target_vectors = [_vector_list(vector) for row_contract_id, vector in rows if row_contract_id == contract_id]
    target_average = _average_vector([vector for vector in target_vectors if vector])
    if not target_average:
        return {}

    vectors_by_contract: Dict[str, List[List[float]]] = defaultdict(list)
    for row_contract_id, vector in rows:
        if not row_contract_id or row_contract_id == contract_id:
            continue
        candidate_vector = _vector_list(vector)
        if candidate_vector:
            vectors_by_contract[str(row_contract_id)].append(candidate_vector)

    scores = {}
    for related_id, vectors in vectors_by_contract.items():
        candidate_average = _average_vector(vectors)
        score = _cosine_similarity(target_average, candidate_average)
        if score >= 0.68:
            scores[related_id] = score
    return dict(sorted(scores.items(), key=lambda item: item[1], reverse=True)[:12])


def _vector_list(vector: object) -> List[float]:
    if vector is None:
        return []
    try:
        return [float(item) for item in vector]  # type: ignore[operator]
    except (TypeError, ValueError):
        return []


def _average_vector(vectors: Sequence[Sequence[float]]) -> List[float]:
    if not vectors:
        return []
    dimension = min(len(vector) for vector in vectors if vector)
    if dimension == 0:
        return []
    totals = [0.0] * dimension
    count = 0
    for vector in vectors:
        if len(vector) < dimension:
            continue
        count += 1
        for index in range(dimension):
            totals[index] += float(vector[index])
    if count == 0:
        return []
    return [value / count for value in totals]


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    dimension = min(len(left), len(right))
    if dimension == 0:
        return 0.0
    dot = sum(left[index] * right[index] for index in range(dimension))
    left_norm = math.sqrt(sum(left[index] * left[index] for index in range(dimension)))
    right_norm = math.sqrt(sum(right[index] * right[index] for index in range(dimension)))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _cohort_match_basis(criteria: Dict[str, object]) -> str:
    if not criteria:
        return "Comparable contract from cohort builder."
    labels = []
    for key in ("naics_prefix", "contract_type", "agency_name", "competition_type"):
        if criteria.get(key):
            labels.append(f"{key.replace('_', ' ')} {criteria[key]}")
    if criteria.get("pop_band_pct"):
        labels.append("similar period of performance")
    if criteria.get("value_band_pct"):
        labels.append("similar obligated value")
    return f"Cohort metadata match: {', '.join(labels[:5])}." if labels else "Comparable contract from cohort builder."


def _recommendations_for_patterns(
    patterns: Sequence[ContractPatternResponse],
    early_warnings: Sequence[TimelineSignalResponse] = (),
) -> List[str]:
    recommendations = [_recommendation_for_text(pattern.title, pattern.examples) for pattern in patterns]
    recommendations.extend(
        _recommendation_for_text(signal.label, [signal.summary])
        for signal in early_warnings
        if signal.polarity in {"negative", "mixed"}
    )
    return _dedupe([item for item in recommendations if item])


def _recommendation_for_text(title: str, examples: Sequence[str]) -> str:
    text = " ".join([title, *examples]).lower()
    display_title = title.rstrip(".")
    if any(token in text for token in ("rfi", "approval", "submittal", "government response")):
        return "Add explicit government review turnaround times, escalation paths, and deemed-response rules for RFIs/submittals."
    if any(token in text for token in ("gfe", "gfi", "credential", "access", "cac", "account")):
        return "Include a GFE/GFI/access responsibility matrix with owner, due date, acceptance criteria, and schedule relief rules."
    if any(token in text for token in ("staff", "vacancy", "key personnel", "fte", "turnover")):
        return "Require a staffing ramp plan, named key-personnel backup coverage, and recurring vacancy reporting tied to remedies."
    if any(token in text for token in ("quality", "defect", "rework", "rejection", "qc")):
        return "Tie quality-control checkpoints to acceptance criteria, rework reporting, and corrective-action deadlines."
    if any(token in text for token in ("cost", "burn", "eac", "overrun", "invoice", "financial")):
        return "Require cost-performance reporting with variance thresholds, EAC updates, and corrective-action triggers."
    if any(token in text for token in ("schedule", "slip", "delay", "late", "critical path")):
        return "Add schedule-risk triggers for late deliverables, critical-path movement, mitigation dates, and recovery-plan approval."
    if any(token in text for token in ("scope", "modification", "change", "out of scope")):
        return "Clarify scope-control language, change-order authority, and required impact analysis before directed work proceeds."
    return f"Add a solicitation evaluation factor and post-award reporting requirement for recurring {display_title} risk."


def _dedupe(items: Sequence[str]) -> List[str]:
    result = []
    seen = set()
    for item in items:
        normalized = " ".join(str(item).split())
        if not normalized or normalized.lower() in seen:
            continue
        seen.add(normalized.lower())
        result.append(normalized)
    return result


def _timeline_documents(db: Session, contract_id: str) -> List[DocumentUpload]:
    rows = list(
        db.scalars(
            select(DocumentUpload).where(
                or_(DocumentUpload.contract_id == contract_id, DocumentUpload.id == contract_id)
            )
        ).all()
    )
    report_rows = [item for item in rows if _display_document_kind(item) != "source_contract"]
    if report_rows:
        rows = report_rows
    return sorted(
        rows,
        key=lambda item: (
            _report_period(db, item)[0] or _report_period(db, item)[1] or item.created_at.date(),
            item.created_at,
            item.title,
        ),
    )


def _timeline_signals_by_document(db: Session, contract_id: str) -> Dict[str, List[TimelineSignalResponse]]:
    by_document: Dict[str, List[TimelineSignalResponse]] = defaultdict(list)
    for finding in db.scalars(select(RegressionFinding).where(RegressionFinding.contract_id == contract_id)).all():
        evidence_text = " ".join(item for item in (finding.title, finding.summary, finding.quote or "") if item)
        label = _specific_signal_label(finding.title, evidence_text)
        signal = TimelineSignalResponse(
            id=finding.id,
            category="issue",
            label=label,
            summary=finding.summary,
            polarity="negative",
            severity=finding.severity,
            confidence=finding.confidence,
            document_id=finding.document_upload_id,
            quote=finding.quote,
            responsible_party=_responsible_party(evidence_text),
            recurrence_key=_recurrence_key(finding.finding_type, label),
        )
        if finding.document_upload_id:
            by_document[finding.document_upload_id].append(signal)

    for fact in db.scalars(select(DocumentReportFact).where(DocumentReportFact.contract_id == contract_id)).all():
        evidence_text = f"{fact.label} {fact.value_text} {fact.quote}"
        polarity = _polarity(evidence_text)
        category = "execution_pattern" if _is_execution_text(evidence_text) else "report_fact"
        label = _specific_signal_label(fact.label, evidence_text)
        responsible_party = "government" if fact.fact_type == "rfi_age" else _responsible_party(evidence_text)
        signal = TimelineSignalResponse(
            id=fact.id,
            category=category,
            label=label,
            summary=fact.value_text,
            polarity=polarity,
            confidence=fact.confidence,
            document_id=fact.document_upload_id,
            quote=fact.quote,
            responsible_party=responsible_party,
            recurrence_key=_recurrence_key(fact.fact_type, label),
        )
        if fact.document_upload_id:
            by_document[fact.document_upload_id].append(signal)

    for signal_row in db.scalars(select(PerformanceSignal).where(PerformanceSignal.contract_id == contract_id)).all():
        evidence_text = " ".join(item for item in (signal_row.label or "", signal_row.summary) if item)
        category = "execution_pattern" if _is_execution_text(signal_row.summary) else signal_row.signal_type
        label = _specific_signal_label(signal_row.label or signal_row.signal_type, evidence_text)
        signal = TimelineSignalResponse(
            id=signal_row.id,
            category=category,
            label=label,
            summary=signal_row.summary,
            polarity=_polarity(signal_row.summary),
            severity=signal_row.severity,
            confidence=signal_row.confidence,
            document_id=signal_row.document_upload_id,
            quote=_metadata_quote(signal_row.metadata_json),
            responsible_party=_responsible_party(evidence_text),
            recurrence_key=_recurrence_key(signal_row.signal_type, label),
        )
        if signal_row.document_upload_id:
            by_document[signal_row.document_upload_id].append(signal)

    for chunk in _execution_chunks(db, contract_id):
        signal = TimelineSignalResponse(
            id=f"execution:{chunk.id}",
            category="execution_pattern",
            label=_execution_label(chunk.text),
            summary=_execution_summary(chunk.text),
            polarity=_polarity(chunk.text),
            confidence=0.55,
            document_id=chunk.document_upload_id,
            quote=None,
            responsible_party=_responsible_party(chunk.text),
            recurrence_key=_recurrence_key("execution", _execution_label(chunk.text)),
        )
        by_document[chunk.document_upload_id].append(signal)

    return {key: sorted(value, key=lambda item: (item.category, item.label)) for key, value in by_document.items()}


def _execution_chunks(db: Session, contract_id: str) -> List[DocumentChunk]:
    document_ids = list(
        db.scalars(select(DocumentUpload.id).where(DocumentUpload.contract_id == contract_id)).all()
    )
    if not document_ids:
        return []
    chunks = list(db.scalars(select(DocumentChunk).where(DocumentChunk.document_upload_id.in_(document_ids))).all())
    return [chunk for chunk in chunks if _is_execution_text(chunk.text)][:40]


def _issue_patterns(timeline: Sequence[TimelineReportResponse]) -> Tuple[List[ContractPatternResponse], List[ContractPatternResponse]]:
    grouped: Dict[str, List[Tuple[TimelineReportResponse, TimelineSignalResponse]]] = defaultdict(list)
    for report in timeline:
        for signal in report.signals:
            if signal.polarity == "positive" or signal.category == "execution_pattern":
                continue
            grouped[signal.recurrence_key].append((report, signal))
    patterns = [_pattern_response(key, values) for key, values in grouped.items()]
    recurring = sorted([item for item in patterns if item.document_count >= 2], key=lambda item: (-item.document_count, item.title))
    one_off = sorted([item for item in patterns if item.document_count == 1], key=lambda item: item.title)
    return recurring[:20], one_off[:20]


def _pattern_response(
    key: str,
    values: Sequence[Tuple[TimelineReportResponse, TimelineSignalResponse]],
) -> ContractPatternResponse:
    reports = [report for report, _signal in values]
    signals = [signal for _report, signal in values]
    periods = [report.period_label for report in reports]
    return ContractPatternResponse(
        key=key,
        title=signals[0].label,
        count=len(signals),
        document_count=len({report.document_id for report in reports}),
        first_period_label=periods[0] if periods else None,
        last_period_label=periods[-1] if periods else None,
        examples=[signal.summary for signal in signals[:3]],
    )


def _early_warning_signals(
    timeline: Sequence[TimelineReportResponse],
    cpars_ratings: Sequence[CparsRatingResponse],
) -> List[TimelineSignalResponse]:
    degradation_index = None
    for index, report in enumerate(timeline):
        if any(signal.severity == "high" or signal.category in {"cost_regression", "schedule_regression"} for signal in report.signals):
            degradation_index = index
            break
    if degradation_index is None and any(_is_weak_cpars_rating(item.rating) for item in cpars_ratings):
        degradation_index = max(1, len(timeline) - 1)
    if degradation_index is None:
        return []
    warnings = []
    for report in timeline[:degradation_index]:
        warnings.extend(
            signal
            for signal in report.signals
            if signal.polarity in {"negative", "mixed"} and signal.category != "execution_pattern"
        )
    return warnings[:20]


def _cpars_ratings(db: Session, contract_id: str) -> List[CparsRatingResponse]:
    ratings: List[CparsRatingResponse] = []
    records = list(
        db.scalars(
            select(KnowledgeSourceRecord).where(
                KnowledgeSourceRecord.contract_id == contract_id,
                KnowledgeSourceRecord.source_name.ilike("%cpars%"),
            )
        ).all()
    )
    for record in records:
        raw = record.raw_json or {}
        for label in ("quality", "schedule", "cost_control", "management", "regulatory_compliance", "overall"):
            rating = raw.get(label) or raw.get(f"{label}_rating")
            if rating:
                ratings.append(
                    CparsRatingResponse(
                        label=label.replace("_", " ").title(),
                        rating=str(rating),
                        period_label=str(raw.get("period") or raw.get("evaluation_period") or ""),
                        summary=record.text or record.title,
                        source=record.source_name,
                    )
                )
    facts = list(
        db.scalars(
            select(DocumentReportFact).where(
                DocumentReportFact.contract_id == contract_id,
                DocumentReportFact.fact_type.ilike("%cpars%"),
            )
        ).all()
    )
    for fact in facts:
        ratings.append(
            CparsRatingResponse(
                label=fact.label,
                rating=fact.value_text,
                summary=fact.quote,
                source="document_fact",
            )
        )
    return ratings[:20]


def _cohort_brief(analysis: ContractTimelineAnalysisResponse) -> CohortContractBriefResponse:
    all_signals = [signal for report in analysis.timeline for signal in report.signals]
    has_high = any(signal.severity == "high" for signal in all_signals)
    has_weak_cpars = any(_is_weak_cpars_rating(item.rating) for item in analysis.cpars_ratings)
    has_recovered = any("recover" in signal.summary.lower() or "resolved" in signal.summary.lower() for signal in all_signals)
    if has_recovered and (analysis.positive_signals or analysis.recurring_issues):
        band = "recovered"
    elif has_high or has_weak_cpars or len(analysis.recurring_issues) >= 2:
        band = "poor"
    elif analysis.positive_signals and not analysis.recurring_issues:
        band = "well_performing"
    else:
        band = "mixed"
    return CohortContractBriefResponse(
        contract_id=analysis.contract_id,
        contract_title=analysis.contract_title,
        performance_band=band,
        document_count=len(analysis.timeline),
        recurring_issue_count=len(analysis.recurring_issues),
        positive_signal_count=len(analysis.positive_signals),
        execution_pattern_count=len(analysis.execution_patterns),
        cpars_rating_count=len(analysis.cpars_ratings),
    )


def _cohort_common_patterns(
    analyses: Sequence[ContractTimelineAnalysisResponse],
    include_positive: bool,
) -> List[ContractPatternResponse]:
    grouped: Dict[str, List[Tuple[ContractTimelineAnalysisResponse, TimelineSignalResponse]]] = defaultdict(list)
    for analysis in analyses:
        signals = [signal for report in analysis.timeline for signal in report.signals]
        for signal in signals:
            if include_positive:
                if signal.polarity != "positive" and signal.category != "execution_pattern":
                    continue
            elif signal.polarity == "positive":
                continue
            grouped[signal.recurrence_key].append((analysis, signal))
    patterns = []
    for key, values in grouped.items():
        contract_count = len({analysis.contract_id for analysis, _signal in values})
        if contract_count < 2 and len(analyses) > 1:
            continue
        signals = [signal for _analysis, signal in values]
        patterns.append(
            ContractPatternResponse(
                key=key,
                title=signals[0].label,
                count=len(signals),
                document_count=contract_count,
                examples=[signal.summary for signal in signals[:3]],
            )
        )
    return sorted(patterns, key=lambda item: (-item.document_count, -item.count, item.title))[:20]


def _delta_lessons(
    poor_patterns: Sequence[ContractPatternResponse],
    well_patterns: Sequence[ContractPatternResponse],
) -> List[str]:
    poor_keys = {item.key for item in poor_patterns}
    well_keys = {item.key for item in well_patterns}
    lessons = [
        f"Poor-performing contracts show recurring '{item.title}' signals that are not present in the well-performing set."
        for item in poor_patterns
        if item.key not in well_keys
    ]
    lessons.extend(
        f"Well-performing or recovered contracts show '{item.title}' signals that are missing from the poor-performing set."
        for item in well_patterns
        if item.key not in poor_keys
    )
    return lessons[:12]


def _qualitative_quantitative_correlations(
    analyses: Sequence[ContractTimelineAnalysisResponse],
) -> List[str]:
    correlations = []
    for analysis in analyses:
        weak_labels = [item.label for item in analysis.cpars_ratings if _is_weak_cpars_rating(item.rating)]
        if weak_labels and analysis.recurring_issues:
            correlations.append(
                f"{analysis.contract_title}: weak CPARS areas ({', '.join(weak_labels[:3])}) align with recurring report signals such as {analysis.recurring_issues[0].title}."
            )
    if not correlations:
        poor_issue_counts = [
            (analysis.contract_title, len(analysis.recurring_issues))
            for analysis in analyses
            if len(analysis.recurring_issues) >= 2
        ]
        correlations = [
            f"{title}: recurring qualitative issue count is {count}; import CPARS ratings to test quantitative degradation."
            for title, count in poor_issue_counts[:5]
        ]
    return correlations[:10]


def _execution_correlations(analyses: Sequence[ContractTimelineAnalysisResponse]) -> List[str]:
    labels = Counter(
        signal.label
        for analysis in analyses
        for signal in analysis.execution_patterns
    )
    return [
        f"Execution pattern '{label}' appears across {count} contract signal(s); compare this against performance bands before treating it as a lesson."
        for label, count in labels.most_common(10)
    ]


def _citations_for_pattern(
    timeline: Sequence[TimelineReportResponse],
    pattern: ContractPatternResponse,
) -> List[PrimitiveCitationResponse]:
    citations = []
    for report in timeline:
        for signal in report.signals:
            if signal.recurrence_key == pattern.key:
                citations.append(_citation_for_signal(report, signal))
    return citations


def _report_for_signal(
    timeline: Sequence[TimelineReportResponse],
    signal: TimelineSignalResponse,
) -> Optional[TimelineReportResponse]:
    return next((report for report in timeline if report.document_id == signal.document_id), None)


def _citation_for_signal(
    report: Optional[TimelineReportResponse],
    signal: TimelineSignalResponse,
) -> PrimitiveCitationResponse:
    return PrimitiveCitationResponse(
        primitive_id=signal.id,
        primitive_type=signal.category,
        document_id=signal.document_id,
        label=f"{report.period_label} · {signal.label}" if report is not None else signal.label,
        excerpt=_trim(signal.quote or signal.summary, 500),
    )


def _signals_by_label(signals: Sequence[TimelineSignalResponse]) -> Dict[str, List[TimelineSignalResponse]]:
    grouped: Dict[str, List[TimelineSignalResponse]] = defaultdict(list)
    for signal in signals:
        grouped[signal.label].append(signal)
    return dict(sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])))


def _first_period_for_signals(
    timeline: object,
    signals: Sequence[TimelineSignalResponse],
) -> Optional[str]:
    if not isinstance(timeline, list):
        return None
    signal_ids = {signal.id for signal in signals}
    for report in timeline:
        if not isinstance(report, TimelineReportResponse):
            continue
        if any(signal.id in signal_ids for signal in report.signals):
            return report.period_label
    return None


def _signal_text(signal: TimelineSignalResponse) -> str:
    return " ".join(
        item
        for item in (signal.label, signal.summary, signal.quote or "", signal.category)
        if item
    ).lower()


def _eac_values(signals: Sequence[TimelineSignalResponse]) -> List[float]:
    values = []
    for signal in signals:
        text = " ".join(item for item in (signal.summary, signal.quote or "") if item)
        for match in re.finditer(r"\bEAC\b[^0-9$-]{0,20}\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([KkMm])?", text):
            value = _number_with_suffix(match.group(1), match.group(2))
            if value is not None:
                values.append(value)
    return values


def _number_with_suffix(value: str, suffix: Optional[str]) -> Optional[float]:
    try:
        number = float(value.replace(",", ""))
    except ValueError:
        return None
    if suffix and suffix.lower() == "k":
        return number * 1_000
    if suffix and suffix.lower() == "m":
        return number * 1_000_000
    return number


def _distribution(values: Sequence[float]) -> Dict[str, Optional[float]]:
    ordered = sorted(values)
    if not ordered:
        return {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}
    return {
        "p10": _percentile_value(ordered, 10),
        "p25": _percentile_value(ordered, 25),
        "p50": _percentile_value(ordered, 50),
        "p75": _percentile_value(ordered, 75),
        "p90": _percentile_value(ordered, 90),
    }


def _percentile_value(ordered: Sequence[float], percentile: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (percentile / 100)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * weight)


def _percentile_rank(values: Sequence[float], target: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    below_or_equal = sum(1 for value in ordered if value <= target)
    return (below_or_equal / len(ordered)) * 100


def _period_label(db: Session, document: DocumentUpload) -> str:
    start, end = _report_period(db, document)
    if start and end:
        return f"{start} to {end}"
    if start:
        return str(start)
    if end:
        return str(end)
    return document.created_at.strftime("%Y-%m-%d")


def _report_period(db: Session, document: DocumentUpload) -> Tuple[Optional[date], Optional[date]]:
    if document.report_period_start or document.report_period_end:
        return document.report_period_start, document.report_period_end
    text = _document_text_sample(db, document.id)
    match = re.search(
        r"Reporting Period:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})\s*[–-]\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return _report_period_from_title(document)
    return _parse_day_month_year(match.group(1)), _parse_day_month_year(match.group(2))


def _report_period_from_title(document: DocumentUpload) -> Tuple[Optional[date], Optional[date]]:
    haystack = f"{document.title} {document.original_filename}"
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s*([0-9]{4})\b",
        haystack,
        re.IGNORECASE,
    )
    if not match:
        return None, None
    month = _month_number(match.group(1))
    year = int(match.group(2))
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1)
        end = date.fromordinal(end.toordinal() - 1)
    return start, end


def _month_number(value: str) -> int:
    months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    return months[value.lower()]


def _document_text_sample(db: Session, document_id: str) -> str:
    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_upload_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(3)
        ).all()
    )
    return "\n".join(chunk.text for chunk in chunks)


def _parse_day_month_year(value: str) -> Optional[date]:
    normalized = value.strip()
    for pattern in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(normalized, pattern).date()
        except ValueError:
            continue
    return None


def _display_document_kind(document: DocumentUpload) -> str:
    haystack = f"{document.original_filename} {document.title} {document.document_kind}".lower()
    if "_wsr-" in haystack or " wsr-" in haystack or "weekly status report" in haystack:
        return "weekly_report"
    if "_msr" in haystack or " msr" in haystack or "monthly status report" in haystack:
        return "monthly_report"
    return document.document_kind


def _recurrence_key(category: str, label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", f"{category}-{label}".lower()).strip("-")[:120] or "signal"


def _polarity(text: str) -> str:
    lower = text.lower()
    if _contains_any(lower, ("delay", "risk", "late", "overrun", "variance", "unbudgeted", "unauthorized", "defect", "missing", "open", "slip", "rework")):
        return "negative"
    if _contains_any(lower, ("resolved", "recovered", "on schedule", "ahead of schedule", "accepted", "approved", "completed", "effective", "worked well", "expedited")):
        return "positive"
    return "neutral"


def _is_execution_text(text: str) -> bool:
    return _contains_any(
        text.lower(),
        (
            "sequence",
            "sequencing",
            "phase",
            "phasing",
            "subcontractor",
            "quality control",
            "qc",
            "project management plan",
            "pmp",
            "staffing",
            "labor mix",
            "work package",
        ),
    )


def _execution_label(text: str) -> str:
    lower = text.lower()
    if "subcontractor" in lower:
        return "Subcontractor management"
    if "quality control" in lower or "qc" in lower:
        return "Quality control"
    if "sequence" in lower or "sequencing" in lower or "phase" in lower:
        return "Work sequencing"
    if "project management plan" in lower or "pmp" in lower:
        return "Project management plan adherence"
    if "staffing" in lower or "labor mix" in lower:
        return "Staffing and labor mix"
    return "Execution approach"


def _specific_signal_label(default: str, text: str) -> str:
    lower = text.lower()
    if _contains_any(lower, ("gfe", "government furnished equipment", "government-furnished equipment")):
        return "GFE availability delay"
    if _contains_any(lower, ("government action", "pending government", "cor approval", "ko approval", "government decision")):
        return "Government action delay"
    if _contains_any(lower, ("rfi", "request for information")):
        return "Aging RFI"
    if _contains_any(lower, ("subcontractor", "subcontract")):
        return "Subcontractor execution issue"
    if _contains_any(lower, ("quality control", "qc", "defect", "rework", "rejection")):
        return "Quality control or rework"
    if _contains_any(lower, ("staffing", "labor mix", "vacancy", "unfilled")):
        return "Staffing or labor mix"
    if _contains_any(lower, ("funding", "incremental funding", "funds")):
        return "Funding availability"
    return default


def _responsible_party(text: str) -> str:
    lower = text.lower()
    if _contains_any(lower, ("government action", "pending government", "gfe", "cor approval", "ko approval", "government decision")):
        return "government"
    if _contains_any(lower, ("subcontractor", "staffing", "quality control", "qc", "defect", "rework")):
        return "contractor"
    if _contains_any(lower, ("weather", "supply chain", "third-party", "third party")):
        return "external"
    return "unclear"


def _snippet_for_execution(text: str) -> str:
    lower = text.lower()
    for keyword in ("subcontractor", "quality control", "qc", "sequencing", "sequence", "phase", "project management plan", "pmp", "staffing", "labor mix"):
        index = lower.find(keyword)
        if index >= 0:
            return text[max(0, index - 160) : index + 360].strip()
    return text[:500]


def _execution_summary(text: str) -> str:
    label = _execution_label(text)
    lower = text.lower()
    if label == "Subcontractor management":
        if "authority" in lower or "authorized" in lower or "rfi" in lower:
            return "Subcontractor labor or authority depended on written government clarification."
        return "Subcontractor activity appears in the report history and may need review with schedule/cost outcomes."
    if label == "Quality control":
        if _polarity(text) == "positive":
            return "Quality control activity appears to support acceptance or recovery."
        return "Quality control, defect, or rework language appears in the report history."
    if label == "Work sequencing":
        return "Work sequencing or phasing depended on access, approvals, or planned next-period activity."
    if label == "Project management plan adherence":
        return "Program management or PMP-related activity appears in the report history."
    if label == "Staffing and labor mix":
        return "Staffing or labor mix appears as an execution factor in the report history."
    return "Execution approach appears in the report history."


def _metadata_quote(metadata: Optional[Dict[str, object]]) -> Optional[str]:
    if not metadata:
        return None
    evidence = metadata.get("evidence")
    if isinstance(evidence, list) and evidence:
        return str(evidence[0])
    if isinstance(evidence, str):
        return evidence
    return None


def _is_weak_cpars_rating(value: str) -> bool:
    return value.strip().lower() in {"unsatisfactory", "marginal", "poor", "red", "1", "2"}


def _contains_any(value: str, needles: Sequence[str]) -> bool:
    return any(needle in value for needle in needles)


def _trim(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 3].rstrip()}..."


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
