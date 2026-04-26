import os
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.authz import require_contract_ai_query
from app.contracts import CitationResponse, topics_for_contract
from app.database import get_db
from app.models import BaselineObligation, ContractHypothesis, DocumentUpload, HypothesisEvidence, RegressionFinding

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentQueryRequest(BaseModel):
    contract_id: str
    question: str = Field(min_length=1, max_length=2000)
    generate: bool = False
    scope_status: Literal["ready", "pending", "unmatched"] = "ready"


class AgentQueryResponse(BaseModel):
    contract_id: str
    question: str
    answer: str
    citations: List[CitationResponse]
    limitations: List[str] = []
    generated: bool


class DraftRequest(BaseModel):
    contract_id: str
    draft_type: str = Field(min_length=1, max_length=120)
    prompt: Optional[str] = Field(default=None, max_length=2000)
    generate: bool = False
    scope_status: Literal["ready", "pending", "unmatched"] = "ready"


class DraftResponse(BaseModel):
    contract_id: str
    draft_type: str
    text: str
    citations: List[CitationResponse]
    limitations: List[str] = []
    generated: bool


@router.post("/query", response_model=AgentQueryResponse)
def query_agent(
    payload: AgentQueryRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentQueryResponse:
    _reject_unready_scope(payload.scope_status)
    require_contract_ai_query(user, db, payload.contract_id)
    if payload.generate and not _provider_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI generation provider is not configured",
        )

    citations = _citations_for_contract(db, payload.contract_id)
    counts = _analysis_counts(db, payload.contract_id)
    limitations = []
    if citations:
        answer = (
            "The current knowledge base has citation-backed material for this contract. "
            f"Retrieved baseline obligations ({counts['baseline_obligations']}), regression findings "
            f"({counts['regression_findings']}), active hypotheses ({counts['active_hypotheses']}), "
            f"and topics ({counts['topics']}) before falling back to raw evidence."
        )
    else:
        answer = "No citable contract analysis material is available for this scope yet."
        limitations.append(
            "The contract knowledge base has not produced baseline obligations, findings, hypotheses, topics, or evidence yet."
        )

    return AgentQueryResponse(
        contract_id=payload.contract_id,
        question=payload.question,
        answer=answer,
        citations=citations,
        limitations=limitations,
        generated=payload.generate and _provider_available(),
    )


@router.post("/drafts", response_model=DraftResponse)
def create_draft(
    payload: DraftRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DraftResponse:
    _reject_unready_scope(payload.scope_status)
    require_contract_ai_query(user, db, payload.contract_id)
    if payload.generate and not _provider_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI generation provider is not configured",
        )

    citations = _citations_for_contract(db, payload.contract_id)
    if citations:
        text = (
            f"Draft {payload.draft_type}: cite retrieved baseline obligations, regression findings, "
            "active hypotheses, and topic evidence before making any performance finding. "
            "Treat hypotheses as tentative unless their status is supported."
        )
        limitations = ["V1 draft output is retrieval scaffolding, not a final generated narrative."]
    else:
        text = "No citable draft text can be produced because this contract has no available citations."
        limitations = ["No citation-backed topics, evidence, or signals are available for this contract."]

    return DraftResponse(
        contract_id=payload.contract_id,
        draft_type=payload.draft_type,
        text=text,
        citations=citations,
        limitations=limitations,
        generated=payload.generate and _provider_available(),
    )


def _citations_for_contract(db: Session, contract_id: str) -> List[CitationResponse]:
    citations: List[CitationResponse] = []
    citations.extend(_regression_citations(db, contract_id))
    citations.extend(_hypothesis_citations(db, contract_id))
    citations.extend(_baseline_citations(db, contract_id))
    for topic in topics_for_contract(db, contract_id):
        citations.extend(topic.citations)
    return _dedupe_citations(citations)


def _regression_citations(db: Session, contract_id: str) -> List[CitationResponse]:
    rows = list(
        db.scalars(
            select(RegressionFinding)
            .where(RegressionFinding.contract_id == contract_id)
            .order_by(RegressionFinding.created_at.desc())
        ).all()
    )
    return [
        citation
        for citation in (
            _document_citation(db, row.document_upload_id, row.quote or row.summary) for row in rows
        )
        if citation is not None
    ]


def _hypothesis_citations(db: Session, contract_id: str) -> List[CitationResponse]:
    hypotheses = list(
        db.scalars(
            select(ContractHypothesis).where(
                ContractHypothesis.contract_id == contract_id,
                ContractHypothesis.status.in_(("proposed", "investigating", "supported")),
            )
        ).all()
    )
    if not hypotheses:
        return []
    hypothesis_ids = [row.id for row in hypotheses]
    evidence_rows = list(
        db.scalars(
            select(HypothesisEvidence)
            .where(HypothesisEvidence.hypothesis_id.in_(hypothesis_ids))
            .order_by(HypothesisEvidence.created_at.desc())
        ).all()
    )
    return [
        citation
        for citation in (
            _document_citation(db, row.document_upload_id, row.quote or row.summary) for row in evidence_rows
        )
        if citation is not None
    ]


def _baseline_citations(db: Session, contract_id: str) -> List[CitationResponse]:
    rows = list(
        db.scalars(
            select(BaselineObligation)
            .where(BaselineObligation.contract_id == contract_id)
            .order_by(BaselineObligation.created_at.asc())
        ).all()
    )
    return [
        citation
        for citation in (
            _document_citation(db, row.source_document_upload_id, row.reference_text or row.description)
            for row in rows
        )
        if citation is not None
    ]


def _document_citation(
    db: Session,
    document_id: Optional[str],
    excerpt: Optional[str],
) -> Optional[CitationResponse]:
    if not document_id:
        return None
    document = db.get(DocumentUpload, document_id)
    if document is None:
        return None
    return CitationResponse(
        document_id=document.id,
        title=document.title,
        source_path=document.blob_path,
        excerpt=(excerpt or document.notes or document.title)[:1200],
    )


def _dedupe_citations(citations: List[CitationResponse]) -> List[CitationResponse]:
    seen = set()
    deduped: List[CitationResponse] = []
    for citation in citations:
        key = (citation.document_id, citation.excerpt)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)
    return deduped[:25]


def _analysis_counts(db: Session, contract_id: str) -> dict:
    topics = topics_for_contract(db, contract_id)
    return {
        "baseline_obligations": len(
            list(
                db.scalars(
                    select(BaselineObligation.id).where(BaselineObligation.contract_id == contract_id)
                ).all()
            )
        ),
        "regression_findings": len(
            list(
                db.scalars(
                    select(RegressionFinding.id).where(RegressionFinding.contract_id == contract_id)
                ).all()
            )
        ),
        "active_hypotheses": len(
            list(
                db.scalars(
                    select(ContractHypothesis.id).where(
                        ContractHypothesis.contract_id == contract_id,
                        ContractHypothesis.status.in_(("proposed", "investigating", "supported")),
                    )
                ).all()
            )
        ),
        "topics": len(topics),
    }


def _provider_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_ENDPOINT"))


def _reject_unready_scope(scope_status: str) -> None:
    if scope_status in {"pending", "unmatched"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Contract scope is {scope_status}; AI knowledge base query is not ready",
        )
