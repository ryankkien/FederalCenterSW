from collections import Counter, defaultdict
from datetime import datetime
import re
from typing import Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai.providers import get_ai_provider
from app.auth import CurrentUser, get_current_user
from app.authz import require_contract_view, visible_contract_ids
from app.blob_storage import BlobStorage, get_blob_storage
from app.contract_analysis import create_investigation_run
from app.database import get_db
from app.models import (
    BaselineObligation,
    BaselineRevision,
    Contract,
    ContractBaseline,
    ContractHypothesis,
    ContractSimilarityLink,
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
    return _contract_timeline_analysis(db, contract_id)


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


def _contract_timeline_analysis(db: Session, contract_id: str) -> ContractTimelineAnalysisResponse:
    contract = db.get(Contract, contract_id)
    documents = _timeline_documents(db, contract_id)
    signals_by_document = _timeline_signals_by_document(db, contract_id)
    timeline = [
        TimelineReportResponse(
            document_id=document.id,
            title=document.title,
            document_kind=document.document_kind,
            period_label=_period_label(document),
            report_period_start=str(document.report_period_start) if document.report_period_start else None,
            report_period_end=str(document.report_period_end) if document.report_period_end else None,
            created_at=document.created_at,
            processing_status=document.processing_status,
            signals=signals_by_document.get(document.id, []),
        )
        for document in documents
    ]
    all_signals = [signal for report in timeline for signal in report.signals]
    recurring, one_off = _issue_patterns(timeline)
    cpars_ratings = _cpars_ratings(db, contract_id)
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
        limitations=limitations,
    )


def _require_official_analysis(user: CurrentUser) -> None:
    if user.role != "official":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Official access required")


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


def _timeline_documents(db: Session, contract_id: str) -> List[DocumentUpload]:
    rows = list(
        db.scalars(
            select(DocumentUpload).where(
                or_(DocumentUpload.contract_id == contract_id, DocumentUpload.id == contract_id)
            )
        ).all()
    )
    return sorted(
        rows,
        key=lambda item: (
            item.report_period_start or item.report_period_end or item.created_at.date(),
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
        signal = TimelineSignalResponse(
            id=fact.id,
            category=category,
            label=label,
            summary=fact.value_text,
            polarity=polarity,
            confidence=fact.confidence,
            document_id=fact.document_upload_id,
            quote=fact.quote,
            responsible_party=_responsible_party(evidence_text),
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
            summary=_trim(_snippet_for_execution(chunk.text), 500),
            polarity=_polarity(chunk.text),
            confidence=0.55,
            document_id=chunk.document_upload_id,
            quote=_trim(_snippet_for_execution(chunk.text), 500),
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


def _period_label(document: DocumentUpload) -> str:
    if document.report_period_start and document.report_period_end:
        return f"{document.report_period_start} to {document.report_period_end}"
    if document.report_period_start:
        return str(document.report_period_start)
    if document.report_period_end:
        return str(document.report_period_end)
    return document.created_at.strftime("%Y-%m-%d")


def _recurrence_key(category: str, label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", f"{category}-{label}".lower()).strip("-")[:120] or "signal"


def _polarity(text: str) -> str:
    lower = text.lower()
    if _contains_any(lower, ("resolved", "recovered", "on schedule", "ahead of schedule", "accepted", "approved", "completed", "effective", "worked well", "expedited")):
        return "positive"
    if _contains_any(lower, ("delay", "risk", "late", "overrun", "variance", "unbudgeted", "unauthorized", "defect", "missing", "open", "slip", "rework")):
        return "negative"
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
