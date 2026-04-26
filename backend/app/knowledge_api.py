from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.authz import require_contract_view, visible_contract_ids
from app.database import get_db
from app.knowledge import live_contract_article_data, run_knowledge_ingestion
from app.models import (
    Contract,
    ContractorProfile,
    KnowledgeCitation,
    KnowledgeEdge,
    KnowledgeIngestionRun,
    KnowledgeNode,
    KnowledgeSourceRecord,
)

router = APIRouter(prefix="/api", tags=["knowledge"])


class KnowledgeIngestionRequest(BaseModel):
    scope: str = Field(default="visible", max_length=80)
    contract_ids: List[str] = []
    vendor_ueis: List[str] = []
    sources: List[str] = ["open"]
    limit: int = Field(default=100, ge=1, le=1000)


class KnowledgeIngestionRunResponse(BaseModel):
    id: str
    scope: str
    status: str
    sources_requested: List[str] = []
    contract_ids: List[str] = []
    vendor_ueis: List[str] = []
    limit: Optional[int] = None
    source_record_count: int = 0
    node_count: int = 0
    edge_count: int = 0
    citation_count: int = 0
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = {}


class WikiCitationResponse(BaseModel):
    id: str
    label: str
    excerpt: str
    url: Optional[str] = None
    source_path: Optional[str] = None
    document_id: Optional[str] = None
    source_record_id: Optional[str] = None
    external_source_ref_id: Optional[str] = None


class WikiNodeSummary(BaseModel):
    id: str
    node_type: str
    title: str
    summary: str
    contract_id: Optional[str] = None
    vendor_uei: Optional[str] = None
    security_level: str = "standard"
    status: str = "active"
    citation_count: int = 0


class WikiSectionResponse(BaseModel):
    title: str
    body: str


class WikiArticleResponse(WikiNodeSummary):
    body: str
    sections: List[WikiSectionResponse] = []
    citations: List[WikiCitationResponse] = []
    related_nodes: List[WikiNodeSummary] = []
    limitations: List[str] = []
    metadata: Dict[str, Any] = {}


class WikiRunDetailResponse(KnowledgeIngestionRunResponse):
    source_records: List[Dict[str, Any]] = []


@router.post(
    "/knowledge/ingestion-runs",
    response_model=KnowledgeIngestionRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_knowledge_ingestion_run(
    payload: KnowledgeIngestionRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeIngestionRunResponse:
    if user.role != "official":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Official access required")
    visible_ids = visible_contract_ids(user, db)
    contract_ids = payload.contract_ids or visible_ids
    allowed_contract_ids = [contract_id for contract_id in contract_ids if contract_id in visible_ids]
    if payload.contract_ids and len(allowed_contract_ids) != len(payload.contract_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    result = run_knowledge_ingestion(
        db,
        scope=payload.scope,
        contract_ids=allowed_contract_ids,
        vendor_ueis=payload.vendor_ueis,
        sources=payload.sources,
        limit=payload.limit,
    )
    db.commit()
    db.refresh(result.run)
    return _run_response(
        result.run,
        source_record_count=result.source_record_count,
        node_count=result.node_count,
        edge_count=result.edge_count,
        citation_count=result.citation_count,
    )


@router.get("/wiki/search", response_model=List[WikiNodeSummary])
def search_wiki(
    q: str = "",
    types: List[str] = Query(default=[]),
    contract_id: Optional[str] = None,
    vendor_uei: Optional[str] = None,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[WikiNodeSummary]:
    visible_ids = visible_contract_ids(user, db)
    if contract_id:
        require_contract_view(user, db, contract_id)
        visible_ids = [contract_id]
    visible_vendors = _visible_vendor_keys(db, visible_ids)
    visibility_terms = [KnowledgeNode.contract_id.in_(visible_ids)] if visible_ids else []
    if visible_vendors:
        visibility_terms.append(KnowledgeNode.vendor_uei.in_(visible_vendors))
    if user.role == "official":
        visibility_terms.append(KnowledgeNode.contract_id.is_(None))
    statement = select(KnowledgeNode)
    filters = [or_(*visibility_terms)] if visibility_terms else [KnowledgeNode.id == "__none__"]
    if types:
        filters.append(KnowledgeNode.node_type.in_(types))
    if vendor_uei:
        if vendor_uei not in visible_vendors:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contractor not found")
        filters.append(KnowledgeNode.vendor_uei == vendor_uei)
    normalized = q.strip().lower()
    if normalized:
        pattern = f"%{normalized}%"
        filters.append(
            or_(
                KnowledgeNode.title.ilike(pattern),
                KnowledgeNode.summary.ilike(pattern),
                KnowledgeNode.body.ilike(pattern),
                KnowledgeNode.slug.ilike(pattern),
            )
        )
    nodes = list(db.scalars(statement.where(*filters).order_by(KnowledgeNode.updated_at.desc())).all())
    responses = [_node_summary(db, node) for node in nodes]
    if not responses:
        responses = _fallback_contract_summaries(db, visible_ids, normalized, types)
    return responses[:100]


@router.get("/wiki/contracts/{contract_id}", response_model=WikiArticleResponse)
def get_contract_wiki_article(
    contract_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WikiArticleResponse:
    require_contract_view(user, db, contract_id)
    node = db.scalars(
        select(KnowledgeNode).where(KnowledgeNode.node_type == "contract", KnowledgeNode.contract_id == contract_id)
    ).first()
    if node is not None:
        return _article_response(db, node, user)
    data = live_contract_article_data(db, contract_id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return WikiArticleResponse(
        id=f"contract:{contract_id}",
        node_type="contract",
        title=data["title"],
        summary=data["summary"],
        body=data["body"],
        contract_id=contract_id,
        security_level="standard",
        sections=[WikiSectionResponse(**section) for section in data["sections"]],
        limitations=data["limitations"],
    )


@router.get("/wiki/contractors/{vendor_uei}", response_model=WikiArticleResponse)
def get_contractor_wiki_article(
    vendor_uei: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WikiArticleResponse:
    visible_ids = visible_contract_ids(user, db)
    visible_vendors = _visible_vendor_keys(db, visible_ids)
    if vendor_uei not in visible_vendors:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contractor not found")
    node = db.scalars(
        select(KnowledgeNode).where(KnowledgeNode.node_type == "contractor", KnowledgeNode.vendor_uei == vendor_uei)
    ).first()
    if node is not None:
        return _article_response(db, node, user)
    profile = db.scalars(select(ContractorProfile).where(ContractorProfile.vendor_uei == vendor_uei)).first()
    if profile is None:
        contracts = _visible_contracts(db, visible_ids)
        contract = next((item for item in contracts if item.vendor_uei == vendor_uei), None)
        if contract is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contractor not found")
        return WikiArticleResponse(
            id=f"contractor:{vendor_uei}",
            node_type="contractor",
            title=contract.vendor_name or vendor_uei,
            summary="Contractor profile has not been built yet.",
            body="Run knowledge ingestion to build a cited contractor profile.",
            vendor_uei=vendor_uei,
            security_level="controlled",
            sections=[
                WikiSectionResponse(
                    title="Profile Pending",
                    body="Run knowledge ingestion to aggregate public award records and contract evidence labels.",
                )
            ],
            limitations=["No contractor profile node exists yet."],
        )
    return WikiArticleResponse(
        id=f"contractor:{vendor_uei}",
        node_type="contractor",
        title=profile.vendor_name,
        summary=profile.summary,
        body=profile.summary,
        vendor_uei=vendor_uei,
        security_level="controlled",
        sections=[
            WikiSectionResponse(title="Evidence Labels", body=_labels_text(profile.evidence_labels or {})),
            WikiSectionResponse(
                title="Limitations",
                body=" ".join((profile.metadata_json or {}).get("limitations", [])) or "No limitations recorded.",
            ),
        ],
        limitations=(profile.metadata_json or {}).get("limitations", []),
        metadata={"evidence_labels": profile.evidence_labels or {}},
    )


@router.get("/wiki/nodes/{node_id}", response_model=WikiArticleResponse)
def get_wiki_node(
    node_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WikiArticleResponse:
    if node_id.startswith("contract:"):
        return get_contract_wiki_article(node_id.split(":", 1)[1], user, db)
    if node_id.startswith("contractor:"):
        return get_contractor_wiki_article(node_id.split(":", 1)[1], user, db)
    node = db.get(KnowledgeNode, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wiki node not found")
    _require_node_view(user, db, node)
    return _article_response(db, node, user)


@router.get("/wiki/runs/{run_id}", response_model=WikiRunDetailResponse)
def get_wiki_run(
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WikiRunDetailResponse:
    if user.role != "official":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Official access required")
    run = db.get(KnowledgeIngestionRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge run not found")
    records = list(
        db.scalars(
            select(KnowledgeSourceRecord)
            .where(KnowledgeSourceRecord.ingestion_run_id == run.id)
            .order_by(KnowledgeSourceRecord.updated_at.desc())
        ).all()
    )
    response = _run_response(run)
    return WikiRunDetailResponse(
        **response.model_dump(),
        source_records=[
            {
                "id": record.id,
                "source_name": record.source_name,
                "source_key": record.source_key,
                "status": record.status,
                "title": record.title,
                "url": record.url,
                "unavailable_reason": record.unavailable_reason,
                "contract_id": record.contract_id,
                "vendor_uei": record.vendor_uei,
            }
            for record in records
        ],
    )


def _article_response(db: Session, node: KnowledgeNode, user: CurrentUser) -> WikiArticleResponse:
    _require_node_view(user, db, node)
    metadata = node.metadata_json or {}
    return WikiArticleResponse(
        **_node_summary(db, node).model_dump(),
        body=node.body,
        sections=[WikiSectionResponse(**section) for section in metadata.get("sections", [])],
        citations=_node_citations(db, node.id),
        related_nodes=_related_nodes(db, node, user),
        limitations=metadata.get("limitations", []),
        metadata=metadata,
    )


def _node_summary(db: Session, node: KnowledgeNode) -> WikiNodeSummary:
    citation_count = len(
        list(db.scalars(select(KnowledgeCitation.id).where(KnowledgeCitation.node_id == node.id)).all())
    )
    return WikiNodeSummary(
        id=node.id,
        node_type=node.node_type,
        title=node.title,
        summary=node.summary,
        contract_id=node.contract_id,
        vendor_uei=node.vendor_uei,
        security_level=node.security_level,
        status=node.status,
        citation_count=citation_count,
    )


def _node_citations(db: Session, node_id: str) -> List[WikiCitationResponse]:
    rows = list(
        db.scalars(
            select(KnowledgeCitation)
            .where(KnowledgeCitation.node_id == node_id)
            .order_by(KnowledgeCitation.created_at.asc())
        ).all()
    )
    return [
        WikiCitationResponse(
            id=row.id,
            label=row.label,
            excerpt=row.excerpt,
            url=row.url,
            source_path=row.source_path,
            document_id=row.document_upload_id,
            source_record_id=row.source_record_id,
            external_source_ref_id=row.external_source_ref_id,
        )
        for row in rows
    ]


def _related_nodes(db: Session, node: KnowledgeNode, user: CurrentUser) -> List[WikiNodeSummary]:
    rows = list(
        db.scalars(
            select(KnowledgeEdge).where(
                or_(KnowledgeEdge.source_node_id == node.id, KnowledgeEdge.target_node_id == node.id)
            )
        ).all()
    )
    related = []
    for edge in rows:
        related_id = edge.target_node_id if edge.source_node_id == node.id else edge.source_node_id
        related_node = db.get(KnowledgeNode, related_id)
        if related_node is None:
            continue
        try:
            _require_node_view(user, db, related_node)
        except HTTPException:
            continue
        related.append(_node_summary(db, related_node))
    return related[:12]


def _require_node_view(user: CurrentUser, db: Session, node: KnowledgeNode) -> None:
    if node.contract_id:
        require_contract_view(user, db, node.contract_id)
        return
    if node.vendor_uei and node.vendor_uei in _visible_vendor_keys(db, visible_contract_ids(user, db)):
        return
    if node.node_type == "source" and node.source_record_id:
        record = db.get(KnowledgeSourceRecord, node.source_record_id)
        if record is not None and record.contract_id:
            require_contract_view(user, db, record.contract_id)
            return
    if user.role != "official":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wiki node not found")


def _fallback_contract_summaries(
    db: Session,
    visible_ids: List[str],
    normalized_query: str,
    types: List[str],
) -> List[WikiNodeSummary]:
    if types and "contract" not in types:
        return []
    rows = _visible_contracts(db, visible_ids)
    responses = []
    for contract in rows:
        haystack = f"{contract.title} {contract.contract_number} {contract.vendor_name or ''}".lower()
        if normalized_query and normalized_query not in haystack:
            continue
        responses.append(
            WikiNodeSummary(
                id=f"contract:{contract.id}",
                node_type="contract",
                title=contract.title,
                summary=f"{contract.contract_number} · {contract.status} · {contract.vendor_name or 'contractor pending'}",
                contract_id=contract.id,
                vendor_uei=contract.vendor_uei,
                security_level=contract.security_level,
                status=contract.status,
            )
        )
    return responses


def _visible_vendor_keys(db: Session, visible_ids: List[str]) -> List[str]:
    keys = []
    for contract in _visible_contracts(db, visible_ids):
        if contract.vendor_uei:
            keys.append(contract.vendor_uei)
        elif contract.vendor_name:
            keys.append(_slug(contract.vendor_name)[:32])
    return sorted(set(keys))


def _visible_contracts(db: Session, visible_ids: List[str]) -> List[Contract]:
    if not visible_ids:
        return []
    return list(db.scalars(select(Contract).where(Contract.id.in_(visible_ids))).all())


def _run_response(
    run: KnowledgeIngestionRun,
    source_record_count: int = 0,
    node_count: int = 0,
    edge_count: int = 0,
    citation_count: int = 0,
) -> KnowledgeIngestionRunResponse:
    metadata = run.metadata_json or {}
    return KnowledgeIngestionRunResponse(
        id=run.id,
        scope=run.scope,
        status=run.status,
        sources_requested=run.sources_requested or [],
        contract_ids=run.contract_ids or [],
        vendor_ueis=run.vendor_ueis or [],
        limit=run.limit,
        source_record_count=source_record_count or int(metadata.get("source_records_seen") or 0),
        node_count=node_count or int(metadata.get("nodes_written") or 0),
        edge_count=edge_count or int(metadata.get("edges_written") or 0),
        citation_count=citation_count or int(metadata.get("citations_written") or 0),
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        metadata=metadata,
    )


def _labels_text(labels: Dict[str, Any]) -> str:
    return " ".join(f"{key.replace('_', ' ')}: {value}." for key, value in labels.items())


def _slug(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unknown"
