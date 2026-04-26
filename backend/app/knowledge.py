from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.ai.providers import AIProvider, get_ai_provider
from app.knowledge_sources import KnowledgeSourceDocument, collect_contract_source_documents, normalize_sources
from app.models import (
    BaselineObligation,
    Contract,
    ContractHypothesis,
    ContractTopic,
    ContractorProfile,
    DocumentReportFact,
    DocumentUpload,
    ExternalSourceRef,
    HypothesisEvidence,
    KnowledgeCitation,
    KnowledgeEdge,
    KnowledgeIngestionRun,
    KnowledgeNode,
    KnowledgeSourceRecord,
    RegressionFinding,
    TopicEvidence,
)


DEFAULT_KNOWLEDGE_LIMIT = 100


@dataclass(frozen=True)
class KnowledgeBuildResult:
    run: KnowledgeIngestionRun
    source_record_count: int
    node_count: int
    edge_count: int
    citation_count: int


def run_knowledge_ingestion(
    db: Session,
    scope: str = "visible",
    contract_ids: Optional[Sequence[str]] = None,
    vendor_ueis: Optional[Sequence[str]] = None,
    sources: Optional[Sequence[str]] = None,
    limit: int = DEFAULT_KNOWLEDGE_LIMIT,
    ai_provider: Optional[AIProvider] = None,
) -> KnowledgeBuildResult:
    provider = ai_provider or get_ai_provider()
    normalized_sources = normalize_sources(sources)
    selected_contracts = _contracts_for_request(db, scope, contract_ids, vendor_ueis)
    run = KnowledgeIngestionRun(
        id=str(uuid4()),
        scope=scope,
        status="running",
        sources_requested=normalized_sources,
        contract_ids=[contract.id for contract in selected_contracts],
        vendor_ueis=[item for item in (vendor_ueis or []) if item],
        limit=limit,
        model_name=provider.status.name,
        prompt_version="knowledge_index_v1",
        metadata_json={"source_policy": "local_fixtures_and_synthetic_default"},
    )
    db.add(run)
    db.flush()

    source_records: List[KnowledgeSourceRecord] = []
    try:
        for contract in selected_contracts:
            for document in collect_contract_source_documents(contract, normalized_sources, limit):
                source_records.append(_upsert_source_record(db, run, document, contract))
        created = build_knowledge_index(db, selected_contracts, provider)
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.metadata_json = {
            **(run.metadata_json or {}),
            "contracts_indexed": len(selected_contracts),
            "source_records_seen": len(source_records),
            "nodes_written": created["nodes"],
            "edges_written": created["edges"],
            "citations_written": created["citations"],
        }
        db.flush()
        return KnowledgeBuildResult(
            run=run,
            source_record_count=len(source_records),
            node_count=created["nodes"],
            edge_count=created["edges"],
            citation_count=created["citations"],
        )
    except Exception as error:
        run.status = "failed"
        run.error_message = str(error)[:2000]
        run.completed_at = datetime.now(timezone.utc)
        db.flush()
        raise


def build_knowledge_index(
    db: Session,
    contracts: Sequence[Contract],
    ai_provider: Optional[AIProvider] = None,
) -> Dict[str, int]:
    provider = ai_provider or get_ai_provider()
    counts = {"nodes": 0, "edges": 0, "citations": 0}
    contractor_nodes: Dict[str, KnowledgeNode] = {}
    for contract in contracts:
        contract_node = _build_contract_node(db, contract, provider)
        counts["nodes"] += 1
        counts["citations"] += _rewrite_contract_citations(db, contract_node, contract)
        contractor_node = _build_contractor_node(db, contract, provider)
        if contractor_node is not None:
            contractor_nodes[contractor_node.slug] = contractor_node
            counts["nodes"] += 1
            counts["citations"] += _rewrite_contractor_citations(db, contractor_node)
            counts["edges"] += _upsert_edge(db, contract_node, contractor_node, "performed_by", "Contractor")
        counts["nodes"] += _build_document_nodes(db, contract_node, contract)
        counts["nodes"] += _build_topic_nodes(db, contract_node, contract)
        counts["nodes"] += _build_source_nodes(db, contract_node, contract)
    _link_contracts_by_vendor(db, contracts)
    db.flush()
    return counts


def live_contract_article_data(db: Session, contract_id: str) -> Dict[str, Any]:
    contract = db.get(Contract, contract_id)
    if contract is None:
        document = db.get(DocumentUpload, contract_id)
        if document is None:
            return {}
        return {
            "title": document.title,
            "summary": f"{document.document_type} uploaded for review.",
            "body": document.notes or document.title,
            "sections": [{"title": "Uploaded Document", "body": document.notes or document.title}],
            "limitations": ["This is a provisional upload-level article because no contract record exists yet."],
        }
    payload = _contract_payload(db, contract)
    return {
        "title": contract.title,
        "summary": _contract_summary(payload),
        "body": _contract_body(payload),
        "sections": _contract_sections(payload),
        "limitations": _contract_limitations(payload),
    }


def contractor_key(contract: Contract) -> Optional[str]:
    if contract.vendor_uei:
        return contract.vendor_uei
    if contract.vendor_name:
        return _slug(contract.vendor_name)[:32]
    return None


def source_record_text_hash(text: Optional[str], raw_json: Optional[Dict[str, Any]]) -> Optional[str]:
    value = text or repr(raw_json or {})
    if not value.strip():
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def citation_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _contracts_for_request(
    db: Session,
    scope: str,
    contract_ids: Optional[Sequence[str]],
    vendor_ueis: Optional[Sequence[str]],
) -> List[Contract]:
    statement = select(Contract)
    filters = []
    if contract_ids:
        filters.append(Contract.id.in_([item for item in contract_ids if item]))
    if vendor_ueis:
        filters.append(Contract.vendor_uei.in_([item for item in vendor_ueis if item]))
    if filters:
        statement = statement.where(or_(*filters))
    elif scope not in {"all", "visible", "fixtures"}:
        statement = statement.where(Contract.id == scope)
    return list(db.scalars(statement.order_by(Contract.updated_at.desc())).all())


def _upsert_source_record(
    db: Session,
    run: KnowledgeIngestionRun,
    document: KnowledgeSourceDocument,
    contract: Contract,
) -> KnowledgeSourceRecord:
    source_key = document.source_key[:500]
    row = db.scalars(
        select(KnowledgeSourceRecord).where(
            KnowledgeSourceRecord.source_name == document.source_name,
            KnowledgeSourceRecord.source_key == source_key,
        )
    ).first()
    if row is None:
        row = KnowledgeSourceRecord(
            id=str(uuid4()),
            source_name=document.source_name,
            source_key=source_key,
        )
        db.add(row)
    row.ingestion_run_id = run.id
    row.source_type = document.source_type
    row.status = document.status
    row.unavailable_reason = document.unavailable_reason
    row.url = document.url
    row.title = document.title[:500]
    row.text = document.text
    row.raw_json = document.raw_json
    row.content_hash = source_record_text_hash(document.text, document.raw_json)
    row.source_timestamp = document.source_timestamp
    row.contract_id = document.contract_id or contract.id
    row.vendor_uei = document.vendor_uei or contract.vendor_uei
    row.metadata_json = document.metadata
    return row


def _build_contract_node(db: Session, contract: Contract, provider: AIProvider) -> KnowledgeNode:
    payload = _contract_payload(db, contract)
    ai_result = provider.build_contract_onboarding(payload) if provider.status.available else None
    ai_data = ai_result.data if ai_result and isinstance(ai_result.data, dict) else {}
    summary = _safe_ai_text(ai_data.get("summary")) or _contract_summary(payload)
    sections = _safe_ai_sections(ai_data.get("sections")) or _contract_sections(payload)
    body = "\n\n".join(f"## {section['title']}\n{section['body']}" for section in sections)
    node = _upsert_node(
        db,
        "contract",
        f"contract-{contract.id}",
        contract.title,
        summary,
        body,
        contract_id=contract.id,
        vendor_uei=contract.vendor_uei,
        security_level=contract.security_level,
        status=contract.status,
        model_name=provider.status.name,
        prompt_version=ai_result.prompt_version if ai_result else "deterministic_contract_onboarding_v1",
        metadata={
            "sections": sections,
            "limitations": _contract_limitations(payload),
            "evidence_labels": payload["evidence_labels"],
            "contract_number": contract.contract_number,
            "vendor_name": contract.vendor_name,
        },
    )
    return node


def _build_contractor_node(db: Session, contract: Contract, provider: AIProvider) -> Optional[KnowledgeNode]:
    key = contractor_key(contract)
    if key is None:
        return None
    payload = _contractor_payload(db, contract)
    ai_result = provider.build_contractor_profile(payload) if provider.status.available else None
    ai_data = ai_result.data if ai_result and isinstance(ai_result.data, dict) else {}
    summary = _safe_ai_text(ai_data.get("summary")) or payload["summary"]
    profile = _upsert_contractor_profile(db, key, payload, summary)
    sections = _safe_ai_sections(ai_data.get("sections")) or _contractor_sections(payload)
    body = "\n\n".join(f"## {section['title']}\n{section['body']}" for section in sections)
    return _upsert_node(
        db,
        "contractor",
        f"contractor-{_slug(key)}",
        payload["vendor_name"],
        summary,
        body,
        vendor_uei=key,
        security_level="controlled",
        model_name=provider.status.name,
        prompt_version=ai_result.prompt_version if ai_result else "deterministic_contractor_profile_v1",
        metadata={
            "profile_id": profile.id,
            "sections": sections,
            "evidence_labels": payload["evidence_labels"],
            "limitations": payload["limitations"],
        },
    )


def _build_document_nodes(db: Session, contract_node: KnowledgeNode, contract: Contract) -> int:
    count = 0
    documents = _documents(db, contract.id)
    for document in documents[:50]:
        node = _upsert_node(
            db,
            "document",
            f"document-{document.id}",
            document.title,
            f"{document.document_kind} · {document.processing_status} · {document.original_filename}",
            document.notes or f"{document.document_type} uploaded as {document.original_filename}.",
            contract_id=contract.id,
            security_level=document.security_level,
            status=document.processing_status,
            metadata={"document_id": document.id, "document_kind": document.document_kind},
        )
        _upsert_edge(db, contract_node, node, "has_document", "Document")
        _replace_citations(
            db,
            node,
            [
                {
                    "document_upload_id": document.id,
                    "label": document.original_filename,
                    "excerpt": document.notes or document.title,
                    "source_path": document.blob_path,
                }
            ],
        )
        count += 1
    return count


def _build_topic_nodes(db: Session, contract_node: KnowledgeNode, contract: Contract) -> int:
    topics = list(db.scalars(select(ContractTopic).where(ContractTopic.contract_id == contract.id)).all())
    count = 0
    for topic in topics[:50]:
        evidence = list(db.scalars(select(TopicEvidence).where(TopicEvidence.topic_id == topic.id)).all())
        body = " ".join(item.quote or item.summary or "" for item in evidence).strip() or topic.description or topic.title
        node = _upsert_node(
            db,
            "topic",
            f"topic-{topic.id}",
            topic.title,
            topic.description or "Contract topic indexed from report evidence.",
            body,
            contract_id=contract.id,
            security_level="controlled",
            status=topic.status,
            metadata={"topic_id": topic.id, "topic_key": topic.topic_key},
        )
        _upsert_edge(db, contract_node, node, "has_topic", "Topic")
        _replace_citations(
            db,
            node,
            [
                {
                    "document_upload_id": item.document_upload_id,
                    "label": item.evidence_type,
                    "excerpt": item.quote or item.summary or topic.title,
                }
                for item in evidence
            ],
        )
        count += 1
    return count


def _build_source_nodes(db: Session, contract_node: KnowledgeNode, contract: Contract) -> int:
    records = list(
        db.scalars(
            select(KnowledgeSourceRecord)
            .where(KnowledgeSourceRecord.contract_id == contract.id)
            .order_by(KnowledgeSourceRecord.updated_at.desc())
        ).all()
    )
    count = 0
    for record in records[:80]:
        node = _upsert_node(
            db,
            "source",
            f"source-{record.id}",
            record.title or record.source_name,
            record.unavailable_reason or _trim(record.text or record.url or record.source_name, 300),
            record.text or record.unavailable_reason or record.url or record.source_name,
            contract_id=contract.id,
            vendor_uei=record.vendor_uei,
            security_level="standard",
            status=record.status,
            source_record_id=record.id,
            metadata={"source_name": record.source_name, "source_key": record.source_key},
        )
        _upsert_edge(db, contract_node, node, "supported_by_source", record.source_name)
        _replace_citations(
            db,
            node,
            [
                {
                    "source_record_id": record.id,
                    "label": record.title or record.source_name,
                    "excerpt": record.unavailable_reason or _trim(record.text or record.url or record.source_name, 900),
                    "url": record.url,
                }
            ],
        )
        count += 1
    return count


def _contract_payload(db: Session, contract: Contract) -> Dict[str, Any]:
    documents = _documents(db, contract.id)
    facts = list(db.scalars(select(DocumentReportFact).where(DocumentReportFact.contract_id == contract.id)).all())
    obligations = list(db.scalars(select(BaselineObligation).where(BaselineObligation.contract_id == contract.id)).all())
    regressions = _regressions(db, contract.id)
    hypotheses = list(db.scalars(select(ContractHypothesis).where(ContractHypothesis.contract_id == contract.id)).all())
    sources = list(db.scalars(select(KnowledgeSourceRecord).where(KnowledgeSourceRecord.contract_id == contract.id)).all())
    labels = _evidence_labels(db, contract.id)
    return {
        "contract": {
            "id": contract.id,
            "contract_number": contract.contract_number,
            "title": contract.title,
            "agency_name": contract.agency_name,
            "office_name": contract.office_name,
            "vendor_name": contract.vendor_name,
            "vendor_uei": contract.vendor_uei,
            "naics_code": contract.naics_code,
            "psc_code": contract.psc_code,
            "period_start": str(contract.period_start) if contract.period_start else None,
            "period_end": str(contract.period_end) if contract.period_end else None,
            "status": contract.status,
        },
        "documents": [_document_brief(item) for item in documents[:20]],
        "facts": [_fact_brief(item) for item in facts[:50]],
        "obligations": [_obligation_brief(item) for item in obligations[:30]],
        "regressions": [_regression_brief(item) for item in regressions[:30]],
        "hypotheses": [_hypothesis_brief(item) for item in hypotheses[:20]],
        "sources": [_source_brief(item) for item in sources[:30]],
        "evidence_labels": labels,
    }


def _contractor_payload(db: Session, contract: Contract) -> Dict[str, Any]:
    key = contractor_key(contract)
    if contract.vendor_uei:
        contracts = list(db.scalars(select(Contract).where(Contract.vendor_uei == contract.vendor_uei)).all())
    elif contract.vendor_name:
        contracts = list(db.scalars(select(Contract).where(Contract.vendor_name == contract.vendor_name)).all())
    else:
        contracts = [contract]
    contract_ids = [item.id for item in contracts]
    source_records = []
    if key:
        source_records = list(db.scalars(select(KnowledgeSourceRecord).where(KnowledgeSourceRecord.vendor_uei == key)).all())
    labels = _contractor_labels(db, contract_ids, source_records)
    vendor_name = contract.vendor_name or contract.vendor_uei or "Unknown contractor"
    return {
        "vendor_uei": key,
        "vendor_name": vendor_name,
        "contracts": [
            {
                "id": item.id,
                "contract_number": item.contract_number,
                "title": item.title,
                "status": item.status,
                "psc_code": item.psc_code,
                "naics_code": item.naics_code,
            }
            for item in contracts
        ],
        "source_records": [_source_brief(item) for item in source_records[:40]],
        "evidence_labels": labels,
        "summary": _contractor_summary(vendor_name, labels, len(contracts)),
        "limitations": _contractor_limitations(source_records),
    }


def _contract_summary(payload: Dict[str, Any]) -> str:
    contract = payload["contract"]
    labels = payload["evidence_labels"]
    return (
        f"{contract['contract_number']} has {len(payload['documents'])} indexed document(s), "
        f"{labels['unresolved_issue_count']} unresolved issue(s), and "
        f"{labels['supported_hypothesis_count']} supported hypothesis item(s)."
    )


def _contract_body(payload: Dict[str, Any]) -> str:
    return "\n\n".join(f"## {section['title']}\n{section['body']}" for section in _contract_sections(payload))


def _contract_sections(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    contract = payload["contract"]
    labels = payload["evidence_labels"]
    documents = payload["documents"]
    regressions = payload["regressions"]
    hypotheses = payload["hypotheses"]
    sources = payload["sources"]
    obligations = payload["obligations"]
    facts = payload["facts"]
    return [
        {
            "title": "Onboarding Brief",
            "body": (
                f"{contract['title']} ({contract['contract_number']}) is a {contract['status']} contract. "
                f"Contractor: {contract.get('vendor_name') or 'not recorded'}. "
                f"Agency/office: {contract.get('agency_name') or 'not recorded'} / {contract.get('office_name') or 'not recorded'}."
            ),
        },
        {
            "title": "Latest Updates",
            "body": _join_or_empty(
                [
                    f"{item['title']} ({item['kind']}): {item['status']}"
                    for item in documents[:8]
                ],
                "No weekly or monthly update documents are indexed yet.",
            ),
        },
        {
            "title": "Baseline And Obligations",
            "body": _join_or_empty(
                [f"{item['type']}: {item['title']} - {item['reference']}" for item in obligations[:8]],
                "No interpreted baseline obligations are available yet.",
            ),
        },
        {
            "title": "Performance Evidence Labels",
            "body": (
                f"Schedule variance events: {labels['schedule_variance_events']}. "
                f"Funding variance events: {labels['funding_variance_events']}. "
                f"Delivery issue events: {labels['delivery_issue_events']}. "
                f"Unresolved issues: {labels['unresolved_issue_count']}. "
                f"Contradiction evidence items: {labels['contradiction_count']}."
            ),
        },
        {
            "title": "Open Issues And Hypotheses",
            "body": _join_or_empty(
                [f"{item['title']}: {item['summary']} ({item['status']})" for item in regressions[:8]]
                + [f"{item['title']}: {item['status']}" for item in hypotheses[:8]],
                "No open regressions or hypotheses are indexed yet.",
            ),
        },
        {
            "title": "Report Facts",
            "body": _join_or_empty(
                [f"{item['label']}: {item['value']}" for item in facts[:12]],
                "No structured report facts are indexed yet.",
            ),
        },
        {
            "title": "Official Context",
            "body": _join_or_empty(
                [f"{item['source']}: {item['title']} ({item['status']})" for item in sources[:10]],
                "No external official source records have been mined yet.",
            ),
        },
    ]


def _contract_limitations(payload: Dict[str, Any]) -> List[str]:
    limitations = []
    if not payload["sources"]:
        limitations.append("No official external source records have been mined for this contract.")
    if not payload["documents"]:
        limitations.append("No weekly/monthly update documents are linked to this contract.")
    if not any(item["source"] == "cpars" and item["status"] == "available" for item in payload["sources"]):
        limitations.append("CPARS performance narratives are absent unless authorized exports are imported.")
    return limitations


def _contractor_sections(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    labels = payload["evidence_labels"]
    contracts = payload["contracts"]
    return [
        {
            "title": "Portfolio",
            "body": _join_or_empty(
                [f"{item['contract_number']}: {item['title']} ({item['status']})" for item in contracts[:12]],
                "No linked contracts are available for this contractor.",
            ),
        },
        {
            "title": "Evidence Labels",
            "body": (
                f"Indexed awards: {labels['award_count']}. "
                f"Total obligated from mined public award records: {labels['total_obligated']}. "
                f"Schedule variance events: {labels['schedule_variance_events']}. "
                f"Funding variance events: {labels['funding_variance_events']}. "
                f"Unresolved issues: {labels['unresolved_issue_count']}. "
                f"Contradiction evidence items: {labels['contradiction_count']}."
            ),
        },
        {
            "title": "Limitations",
            "body": _join_or_empty(payload["limitations"], "No current limitations recorded."),
        },
    ]


def _evidence_labels(db: Session, contract_id: str) -> Dict[str, int]:
    regressions = _regressions(db, contract_id)
    hypotheses = list(db.scalars(select(ContractHypothesis).where(ContractHypothesis.contract_id == contract_id)).all())
    hypothesis_ids = [item.id for item in hypotheses]
    contradiction_count = 0
    if hypothesis_ids:
        contradiction_count = len(
            list(
                db.scalars(
                    select(HypothesisEvidence.id).where(
                        HypothesisEvidence.hypothesis_id.in_(hypothesis_ids),
                        HypothesisEvidence.evidence_type == "contradicting",
                    )
                ).all()
            )
        )
    return {
        "schedule_variance_events": sum(1 for item in regressions if item.finding_type == "schedule_regression"),
        "funding_variance_events": sum(1 for item in regressions if item.finding_type == "cost_regression"),
        "delivery_issue_events": sum(1 for item in regressions if item.finding_type in {"late_deliverable", "missing_government_action"}),
        "unresolved_issue_count": sum(1 for item in regressions if item.status in {"open", "investigating"}),
        "supported_hypothesis_count": sum(1 for item in hypotheses if item.status == "supported"),
        "contradiction_count": contradiction_count,
    }


def _contractor_labels(
    db: Session,
    contract_ids: Sequence[str],
    source_records: Sequence[KnowledgeSourceRecord],
) -> Dict[str, Any]:
    regressions = []
    hypotheses = []
    if contract_ids:
        regressions = list(db.scalars(select(RegressionFinding).where(RegressionFinding.contract_id.in_(contract_ids))).all())
        hypotheses = list(db.scalars(select(ContractHypothesis).where(ContractHypothesis.contract_id.in_(contract_ids))).all())
    award_records = [
        record.raw_json or {}
        for record in source_records
        if record.source_name == "usaspending" and record.status == "available"
    ]
    total = 0.0
    for record in award_records:
        try:
            total += float(record.get("Award Amount") or 0)
        except (TypeError, ValueError):
            continue
    hypothesis_ids = [item.id for item in hypotheses]
    contradiction_count = 0
    if hypothesis_ids:
        contradiction_count = len(
            list(
                db.scalars(
                    select(HypothesisEvidence.id).where(
                        HypothesisEvidence.hypothesis_id.in_(hypothesis_ids),
                        HypothesisEvidence.evidence_type == "contradicting",
                    )
                ).all()
            )
        )
    return {
        "award_count": len(award_records),
        "total_obligated": round(total, 2),
        "schedule_variance_events": sum(1 for item in regressions if item.finding_type == "schedule_regression"),
        "funding_variance_events": sum(1 for item in regressions if item.finding_type == "cost_regression"),
        "delivery_issue_events": sum(1 for item in regressions if item.finding_type in {"late_deliverable", "missing_government_action"}),
        "unresolved_issue_count": sum(1 for item in regressions if item.status in {"open", "investigating"}),
        "supported_hypothesis_count": sum(1 for item in hypotheses if item.status == "supported"),
        "contradiction_count": contradiction_count,
    }


def _contractor_summary(vendor_name: str, labels: Dict[str, Any], contract_count: int) -> str:
    return (
        f"{vendor_name} is linked to {contract_count} visible contract(s), "
        f"{labels['award_count']} mined public award record(s), "
        f"{labels['unresolved_issue_count']} unresolved issue(s), and "
        f"{labels['schedule_variance_events']} schedule variance event(s)."
    )


def _contractor_limitations(source_records: Sequence[KnowledgeSourceRecord]) -> List[str]:
    limitations = ["Labels are evidence counters, not moral judgments or responsibility determinations."]
    if not any(record.source_name == "cpars" and record.status == "available" for record in source_records):
        limitations.append("No authorized CPARS import records are available for this contractor profile.")
    if not any(record.source_name == "usaspending" and record.status == "available" for record in source_records):
        limitations.append("No public USAspending award records are linked to this contractor profile.")
    return limitations


def _upsert_contractor_profile(
    db: Session,
    key: str,
    payload: Dict[str, Any],
    summary: str,
) -> ContractorProfile:
    profile = db.scalars(select(ContractorProfile).where(ContractorProfile.vendor_uei == key)).first()
    if profile is None:
        profile = ContractorProfile(
            id=str(uuid5(NAMESPACE_URL, f"contractor-profile:{key}")),
            vendor_uei=key,
            vendor_name=payload["vendor_name"],
            summary=summary,
        )
        db.add(profile)
    labels = payload["evidence_labels"]
    profile.vendor_name = payload["vendor_name"]
    profile.summary = summary
    profile.evidence_labels = labels
    profile.award_count = int(labels.get("award_count") or 0)
    profile.total_obligated = float(labels.get("total_obligated") or 0)
    profile.unresolved_issue_count = int(labels.get("unresolved_issue_count") or 0)
    profile.contradiction_count = int(labels.get("contradiction_count") or 0)
    profile.metadata_json = {"limitations": payload["limitations"]}
    return profile


def _upsert_node(
    db: Session,
    node_type: str,
    slug: str,
    title: str,
    summary: str,
    body: str,
    contract_id: Optional[str] = None,
    vendor_uei: Optional[str] = None,
    security_level: str = "standard",
    status: str = "active",
    source_record_id: Optional[str] = None,
    model_name: Optional[str] = None,
    prompt_version: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> KnowledgeNode:
    node = db.scalars(
        select(KnowledgeNode).where(KnowledgeNode.node_type == node_type, KnowledgeNode.slug == slug)
    ).first()
    if node is None:
        node = KnowledgeNode(id=str(uuid4()), node_type=node_type, slug=slug, title=title, summary=summary, body=body)
        db.add(node)
    node.title = title[:500]
    node.summary = summary or title
    node.body = body or summary or title
    node.contract_id = contract_id
    node.vendor_uei = vendor_uei
    node.security_level = security_level or "standard"
    node.status = status or "active"
    node.source_record_id = source_record_id
    node.model_name = model_name
    node.prompt_version = prompt_version
    node.metadata_json = metadata or {}
    return node


def _upsert_edge(
    db: Session,
    source: KnowledgeNode,
    target: KnowledgeNode,
    edge_type: str,
    label: Optional[str] = None,
    weight: Optional[float] = None,
) -> int:
    db.flush()
    if source.id == target.id:
        return 0
    edge = db.scalars(
        select(KnowledgeEdge).where(
            KnowledgeEdge.source_node_id == source.id,
            KnowledgeEdge.target_node_id == target.id,
            KnowledgeEdge.edge_type == edge_type,
        )
    ).first()
    if edge is None:
        edge = KnowledgeEdge(
            id=str(uuid4()),
            source_node_id=source.id,
            target_node_id=target.id,
            edge_type=edge_type,
        )
        db.add(edge)
        created = 1
    else:
        created = 0
    edge.label = label
    edge.weight = weight
    return created


def _replace_citations(db: Session, node: KnowledgeNode, rows: Sequence[Dict[str, Any]]) -> int:
    db.flush()
    db.execute(delete(KnowledgeCitation).where(KnowledgeCitation.node_id == node.id))
    count = 0
    for row in rows:
        excerpt = str(row.get("excerpt") or "").strip()
        if not excerpt:
            continue
        source_record_id = row.get("source_record_id")
        if source_record_id:
            source_record = db.get(KnowledgeSourceRecord, source_record_id)
            if source_record is not None and source_record.text and excerpt not in source_record.text:
                excerpt = _trim(source_record.text, 900)
        db.add(
            KnowledgeCitation(
                id=str(uuid4()),
                node_id=node.id,
                source_record_id=source_record_id,
                document_upload_id=row.get("document_upload_id"),
                external_source_ref_id=row.get("external_source_ref_id"),
                label=str(row.get("label") or "Evidence")[:300],
                excerpt=excerpt[:2000],
                url=row.get("url"),
                source_path=row.get("source_path"),
                quote_hash=citation_hash(excerpt),
                metadata_json=row.get("metadata"),
            )
        )
        count += 1
    return count


def _rewrite_contract_citations(db: Session, node: KnowledgeNode, contract: Contract) -> int:
    rows: List[Dict[str, Any]] = []
    for document in _documents(db, contract.id)[:12]:
        rows.append(
            {
                "document_upload_id": document.id,
                "label": document.title,
                "excerpt": document.notes or document.title,
                "source_path": document.blob_path,
            }
        )
    for finding in _regressions(db, contract.id)[:12]:
        rows.append(
            {
                "document_upload_id": finding.document_upload_id,
                "label": finding.title,
                "excerpt": finding.quote or finding.summary,
            }
        )
    for source in db.scalars(select(KnowledgeSourceRecord).where(KnowledgeSourceRecord.contract_id == contract.id)).all():
        rows.append(
            {
                "source_record_id": source.id,
                "label": source.title or source.source_name,
                "excerpt": source.unavailable_reason or _trim(source.text or source.source_name, 900),
                "url": source.url,
            }
        )
    return _replace_citations(db, node, rows)


def _rewrite_contractor_citations(db: Session, node: KnowledgeNode) -> int:
    rows = []
    if node.vendor_uei:
        for source in db.scalars(select(KnowledgeSourceRecord).where(KnowledgeSourceRecord.vendor_uei == node.vendor_uei)).all():
            rows.append(
                {
                    "source_record_id": source.id,
                    "label": source.title or source.source_name,
                    "excerpt": source.unavailable_reason or _trim(source.text or source.source_name, 900),
                    "url": source.url,
                }
            )
    return _replace_citations(db, node, rows)


def _link_contracts_by_vendor(db: Session, contracts: Sequence[Contract]) -> None:
    by_vendor: Dict[str, List[Contract]] = {}
    for contract in contracts:
        key = contractor_key(contract)
        if key:
            by_vendor.setdefault(key, []).append(contract)
    for vendor_contracts in by_vendor.values():
        if len(vendor_contracts) < 2:
            continue
        nodes = [
            db.scalars(
                select(KnowledgeNode).where(KnowledgeNode.node_type == "contract", KnowledgeNode.slug == f"contract-{contract.id}")
            ).first()
            for contract in vendor_contracts
        ]
        nodes = [node for node in nodes if node is not None]
        for index, source in enumerate(nodes):
            for target in nodes[index + 1 :]:
                _upsert_edge(db, source, target, "same_contractor", "Same contractor", 0.7)
                _upsert_edge(db, target, source, "same_contractor", "Same contractor", 0.7)


def _documents(db: Session, contract_id: str) -> List[DocumentUpload]:
    return list(
        db.scalars(
            select(DocumentUpload)
            .where(DocumentUpload.contract_id == contract_id)
            .order_by(DocumentUpload.created_at.desc())
        ).all()
    )


def _regressions(db: Session, contract_id: str) -> List[RegressionFinding]:
    return list(
        db.scalars(
            select(RegressionFinding)
            .where(RegressionFinding.contract_id == contract_id)
            .order_by(RegressionFinding.created_at.desc())
        ).all()
    )


def _document_brief(document: DocumentUpload) -> Dict[str, Any]:
    return {
        "id": document.id,
        "title": document.title,
        "kind": document.document_kind,
        "status": document.processing_status,
        "filename": document.original_filename,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }


def _fact_brief(fact: DocumentReportFact) -> Dict[str, Any]:
    return {"type": fact.fact_type, "label": fact.label, "value": fact.value_text, "quote": fact.quote}


def _obligation_brief(obligation: BaselineObligation) -> Dict[str, Any]:
    return {
        "type": obligation.obligation_type,
        "title": obligation.title,
        "reference": obligation.reference_text or obligation.description,
    }


def _regression_brief(item: RegressionFinding) -> Dict[str, Any]:
    return {
        "type": item.finding_type,
        "title": item.title,
        "summary": item.summary,
        "status": item.status,
        "severity": item.severity,
        "quote": item.quote,
    }


def _hypothesis_brief(item: ContractHypothesis) -> Dict[str, Any]:
    return {"title": item.title, "status": item.status, "narrative": item.narrative}


def _source_brief(item: KnowledgeSourceRecord) -> Dict[str, Any]:
    return {
        "source": item.source_name,
        "title": item.title,
        "url": item.url,
        "status": item.status,
        "unavailable_reason": item.unavailable_reason,
    }


def _safe_ai_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()[:2000]
    return ""


def _safe_ai_sections(value: object) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    sections = []
    for item in value:
        if not isinstance(item, dict):
            continue
        title = _safe_ai_text(item.get("title"))
        body = _safe_ai_text(item.get("body"))
        if title and body:
            sections.append({"title": title[:120], "body": body[:4000]})
    return sections[:10]


def _join_or_empty(items: Iterable[str], empty: str) -> str:
    values = [item for item in items if item]
    return " ".join(values) if values else empty


def _trim(value: str, length: int) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized[:length]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unknown"
