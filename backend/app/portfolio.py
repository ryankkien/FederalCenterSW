from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
from typing import Dict, Iterable, List, Optional, Sequence

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.analysis_orchestrator import run_incremental_contract_analysis
from app.auth import CurrentUser, get_current_user
from app.authz import visible_contract_ids
from app.database import SessionLocal, get_db
from app.models import (
    Contract,
    ContractHypothesis,
    DocumentReportFact,
    PerformanceSignal,
    RegressionFinding,
)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class PortfolioKpisResponse(BaseModel):
    flagged: int
    total_contracts: int
    theme_count: int
    aggregate_value_flagged: Decimal
    evidence_count: int
    source: str = "backend"


class PortfolioThemeContractResponse(BaseModel):
    id: str
    number: str
    title: str
    psc: Optional[str] = None
    component: Optional[str] = None
    value: str
    severity: str
    evidence_count: int
    document_ids: List[str] = []
    finding_ids: List[str] = []
    signal_ids: List[str] = []
    hypothesis_ids: List[str] = []
    fact_ids: List[str] = []
    explanation: str


class PortfolioThemeResponse(BaseModel):
    id: str
    title: str
    severity: str
    psc: str
    component: str
    flagged: int
    total: int
    valueFlagged: str
    value_flagged: Decimal
    metric: str
    value: str
    delta: str
    insight: str
    contracts: List[PortfolioThemeContractResponse]
    evidence_count: int


class PortfolioThemesResponse(BaseModel):
    generated_at: datetime
    kpis: PortfolioKpisResponse
    themes: List[PortfolioThemeResponse]
    limitations: List[str] = []


@dataclass
class EvidenceObservation:
    source: str
    source_id: str
    contract_id: str
    theme_key: str
    title: str
    summary: str
    severity: str
    document_id: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class ThemeGroup:
    key: str
    observations: List[EvidenceObservation] = field(default_factory=list)

    @property
    def contract_ids(self) -> List[str]:
        return sorted({item.contract_id for item in self.observations})


@router.get("/themes", response_model=PortfolioThemesResponse)
def get_portfolio_themes(
    period: str = Query(default="last_30_days"),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioThemesResponse:
    visible_ids = visible_contract_ids(user, db)
    contracts_by_id = _contracts_by_id(db, visible_ids)
    observations = _filter_period(
        _observations(db, [contract_id for contract_id in visible_ids if contract_id in contracts_by_id]),
        period,
    )
    groups = _theme_groups(observations)
    themes = [
        _theme_response(group, contracts_by_id, len(contracts_by_id))
        for group in groups
    ]
    flagged_contract_ids = {contract.id for theme in themes for contract in theme.contracts}
    aggregate_value = sum(
        (_contract_value(contracts_by_id[contract_id]) for contract_id in flagged_contract_ids if contract_id in contracts_by_id),
        Decimal("0"),
    )
    limitations = []
    if not observations:
        limitations.append(
            "No processed regression findings, hypotheses, report facts, or performance signals are available for visible contracts yet."
        )
    if not contracts_by_id:
        limitations.append("No database-backed contract records are visible for this user yet.")
    return PortfolioThemesResponse(
        generated_at=datetime.now(timezone.utc),
        kpis=PortfolioKpisResponse(
            flagged=len(flagged_contract_ids),
            total_contracts=len(contracts_by_id),
            theme_count=len(themes),
            aggregate_value_flagged=aggregate_value,
            evidence_count=len(observations),
        ),
        themes=themes,
        limitations=limitations,
    )


def _contracts_by_id(db: Session, visible_ids: Sequence[str]) -> Dict[str, Contract]:
    if not visible_ids:
        return {}
    rows = db.scalars(select(Contract).where(Contract.id.in_(visible_ids))).all()
    return {row.id: row for row in rows}


def _observations(db: Session, contract_ids: Sequence[str]) -> List[EvidenceObservation]:
    if not contract_ids:
        return []
    observations: List[EvidenceObservation] = []
    for finding in db.scalars(select(RegressionFinding).where(RegressionFinding.contract_id.in_(contract_ids))).all():
        if finding.status not in {"open", "active", "new"}:
            continue
        text = _join(finding.title, finding.summary, finding.quote)
        observations.append(
            EvidenceObservation(
                source="finding",
                source_id=finding.id,
                contract_id=finding.contract_id,
                theme_key=_theme_key(finding.finding_type, text),
                title=finding.title,
                summary=finding.summary,
                severity=_severity(finding.severity),
                document_id=finding.document_upload_id,
                created_at=finding.created_at,
            )
        )
    for hypothesis in db.scalars(select(ContractHypothesis).where(ContractHypothesis.contract_id.in_(contract_ids))).all():
        if hypothesis.status not in {"proposed", "investigating", "supported"}:
            continue
        text = _join(hypothesis.title, hypothesis.narrative, hypothesis.hypothesis_key)
        observations.append(
            EvidenceObservation(
                source="hypothesis",
                source_id=hypothesis.id,
                contract_id=hypothesis.contract_id,
                theme_key=_theme_key(hypothesis.hypothesis_key, text),
                title=hypothesis.title,
                summary=hypothesis.narrative,
                severity="watch",
                created_at=hypothesis.updated_at or hypothesis.created_at,
            )
        )
    for signal in db.scalars(select(PerformanceSignal).where(PerformanceSignal.contract_id.in_(contract_ids))).all():
        text = _join(signal.label, signal.summary, signal.signal_type)
        if _polarity(text) == "positive":
            continue
        observations.append(
            EvidenceObservation(
                source="signal",
                source_id=signal.id,
                contract_id=signal.contract_id,
                theme_key=_theme_key(signal.signal_type, text),
                title=signal.label or signal.signal_type.replace("_", " ").title(),
                summary=signal.summary,
                severity=_severity(signal.severity),
                document_id=signal.document_upload_id,
                created_at=signal.observed_at or signal.created_at,
            )
        )
    for fact in db.scalars(select(DocumentReportFact).where(DocumentReportFact.contract_id.in_(contract_ids))).all():
        text = _join(fact.label, fact.value_text, fact.quote, fact.fact_type)
        if not _is_actionable_fact(fact.fact_type, text):
            continue
        observations.append(
            EvidenceObservation(
                source="fact",
                source_id=fact.id,
                contract_id=fact.contract_id or "",
                theme_key=_theme_key(fact.fact_type, text),
                title=fact.label,
                summary=fact.value_text,
                severity="watch" if _polarity(text) != "positive" else "healthy",
                document_id=fact.document_upload_id,
                created_at=fact.created_at,
            )
        )
    return [item for item in observations if item.contract_id]


def _filter_period(observations: Sequence[EvidenceObservation], period: str) -> List[EvidenceObservation]:
    start = _period_start(period)
    if start is None:
        return list(observations)
    return [item for item in observations if item.created_at is None or _aware_datetime(item.created_at) >= start]


def _period_start(period: str) -> Optional[datetime]:
    now = datetime.now(timezone.utc)
    normalized = period.lower().replace(" ", "_").replace("-", "_")
    if normalized in {"last_7_days", "7_days"}:
        return now - timedelta(days=7)
    if normalized in {"last_30_days", "30_days"}:
        return now - timedelta(days=30)
    if normalized in {"last_90_days", "90_days"}:
        return now - timedelta(days=90)
    if normalized in {"fy26", "fy_26"}:
        return datetime(2025, 10, 1, tzinfo=timezone.utc)
    return None


def _aware_datetime(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _theme_groups(observations: Sequence[EvidenceObservation]) -> List[ThemeGroup]:
    by_key: Dict[str, ThemeGroup] = {}
    for item in observations:
        by_key.setdefault(item.theme_key, ThemeGroup(key=item.theme_key)).observations.append(item)
    groups = list(by_key.values())
    groups.sort(key=lambda item: (-len(item.contract_ids), -len(item.observations), item.key))
    return groups[:12]


def _theme_response(
    group: ThemeGroup,
    contracts_by_id: Dict[str, Contract],
    total_contracts: int,
) -> PortfolioThemeResponse:
    contract_ids = group.contract_ids
    contracts = [contracts_by_id[contract_id] for contract_id in contract_ids if contract_id in contracts_by_id]
    value_flagged = sum((_contract_value(contract) for contract in contracts), Decimal("0"))
    psc = _theme_psc(contracts)
    component = _theme_component(contracts)
    severity = _group_severity(group.observations)
    title = _theme_title(group.key, group.observations)
    total = _theme_total(contracts_by_id.values(), contracts, psc)
    evidence_count = len(group.observations)
    contract_responses = [
        _theme_contract_response(contract, group.observations)
        for contract in sorted(contracts, key=lambda item: item.contract_number)
    ]
    return PortfolioThemeResponse(
        id=group.key,
        title=title,
        severity=severity,
        psc=psc,
        component=component,
        flagged=len(contract_responses),
        total=total,
        valueFlagged=_format_compact_currency(value_flagged),
        value_flagged=value_flagged,
        metric="Evidence",
        value=str(evidence_count),
        delta=f"{len(contract_responses)} of {total} visible contracts",
        insight=(
            f"{len(contract_responses)} visible contract"
            f"{'' if len(contract_responses) == 1 else 's'} show {title.lower()} "
            f"based on {evidence_count} extracted finding"
            f"{'' if evidence_count == 1 else 's'}, signal"
            f"{'' if evidence_count == 1 else 's'}, or report fact"
            f"{'' if evidence_count == 1 else 's'}."
        ),
        contracts=contract_responses,
        evidence_count=evidence_count,
    )


def _theme_contract_response(
    contract: Contract,
    observations: Sequence[EvidenceObservation],
) -> PortfolioThemeContractResponse:
    scoped = [item for item in observations if item.contract_id == contract.id]
    document_ids = _unique(item.document_id for item in scoped if item.document_id)
    finding_ids = _unique(item.source_id for item in scoped if item.source == "finding")
    signal_ids = _unique(item.source_id for item in scoped if item.source == "signal")
    hypothesis_ids = _unique(item.source_id for item in scoped if item.source == "hypothesis")
    fact_ids = _unique(item.source_id for item in scoped if item.source == "fact")
    explanation = scoped[0].summary if scoped else "Evidence is available for this portfolio theme."
    return PortfolioThemeContractResponse(
        id=contract.id,
        number=contract.contract_number,
        title=contract.title,
        psc=contract.psc_code,
        component=contract.office_name or contract.agency_name,
        value=_format_currency(_contract_value(contract)),
        severity=_group_severity(scoped),
        evidence_count=len(scoped),
        document_ids=document_ids,
        finding_ids=finding_ids,
        signal_ids=signal_ids,
        hypothesis_ids=hypothesis_ids,
        fact_ids=fact_ids,
        explanation=_trim(explanation, 260),
    )


def _theme_key(kind: str, text: str) -> str:
    normalized = text.lower()
    if any(token in normalized for token in ("key personnel", "staff", "vacancy", "turnover", "substitution")):
        return "staffing-key-personnel"
    if any(token in normalized for token in ("cdrl", "schedule", "slip", "late", "delay", "critical path", "deliverable")):
        return "schedule-deliverable-slip"
    if any(token in normalized for token in ("odc", "travel", "cost", "eac", "invoice", "burn", "overrun", "funding")):
        return "cost-financial-drift"
    if any(token in normalized for token in ("quality", "defect", "rework", "acceptance", "rejection", "qc")):
        return "quality-rework"
    if any(token in normalized for token in ("access", "credential", "gfe", "gfi", "cac", "account")):
        return "access-gfe-delay"
    if any(token in normalized for token in ("safety", "incident", "osha", "injury")):
        return "safety-reporting-gap"
    if any(token in normalized for token in ("license", "export", "renewal", "vendor dependency")):
        return "vendor-license-dependency"
    return f"{_slug(kind) or 'evidence'}-{_slug(' '.join(normalized.split()[:5])) or 'theme'}"[:120]


def _theme_title(key: str, observations: Sequence[EvidenceObservation]) -> str:
    titles = {
        "staffing-key-personnel": "Key-personnel or staffing execution risk",
        "schedule-deliverable-slip": "Schedule and deliverable slip",
        "cost-financial-drift": "Cost or financial drift",
        "quality-rework": "Quality, rework, or acceptance risk",
        "access-gfe-delay": "Access, GFE, or credential delay",
        "safety-reporting-gap": "Safety reporting gap",
        "vendor-license-dependency": "Vendor license or external dependency risk",
    }
    if key in titles:
        return titles[key]
    if observations:
        return _trim(observations[0].title.rstrip("."), 90)
    return key.replace("-", " ").title()


def _theme_psc(contracts: Sequence[Contract]) -> str:
    values = [contract.psc_code for contract in contracts if contract.psc_code]
    if not values:
        return "Uncoded"
    unique = sorted(set(values))
    if len(unique) == 1:
        return unique[0]
    families = sorted({value[0] for value in unique if value})
    if len(families) == 1:
        return f"{families[0]}-codes"
    return "Multi"


def _theme_component(contracts: Sequence[Contract]) -> str:
    values = [contract.office_name or contract.agency_name for contract in contracts if contract.office_name or contract.agency_name]
    unique = sorted(set(values))
    if len(unique) == 1:
        return unique[0]
    return "Multi" if unique else "Unassigned"


def _theme_total(all_contracts: Iterable[Contract], contracts: Sequence[Contract], psc: str) -> int:
    all_rows = list(all_contracts)
    if psc.endswith("-codes") and psc[0]:
        count = len([contract for contract in all_rows if (contract.psc_code or "").startswith(psc[0])])
    elif psc not in {"Multi", "Uncoded"}:
        count = len([contract for contract in all_rows if contract.psc_code == psc])
    else:
        count = len(all_rows)
    return max(count, len(contracts))


def _group_severity(observations: Sequence[EvidenceObservation]) -> str:
    severities = {_severity(item.severity) for item in observations}
    if severities & {"critical"}:
        return "critical"
    if severities & {"watch"}:
        return "watch"
    return "healthy"


def _severity(value: Optional[str]) -> str:
    normalized = str(value or "").lower()
    if normalized in {"critical", "high", "severe"}:
        return "critical"
    if normalized in {"medium", "moderate", "watch", "warning", "low"}:
        return "watch"
    if normalized in {"positive", "good", "healthy"}:
        return "healthy"
    return "watch"


def _is_actionable_fact(fact_type: str, text: str) -> bool:
    normalized = f"{fact_type} {text}".lower()
    if _polarity(normalized) == "positive":
        return False
    return any(
        token in normalized
        for token in (
            "risk",
            "delay",
            "late",
            "slip",
            "cost",
            "overrun",
            "eac",
            "staff",
            "quality",
            "defect",
            "access",
            "safety",
            "cpars",
            "variance",
        )
    )


def _polarity(text: str) -> str:
    normalized = text.lower()
    if any(token in normalized for token in ("ahead of plan", "resolved", "recovered", "under budget", "on time", "excellent")):
        return "positive"
    if any(token in normalized for token in ("risk", "late", "delay", "slip", "overrun", "issue", "gap", "decline", "weak")):
        return "negative"
    return "mixed"


def _contract_value(contract: Contract) -> Decimal:
    metadata = contract.metadata_json if isinstance(contract.metadata_json, dict) else {}
    value = metadata.get("obligated_value")
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _format_currency(value: Decimal) -> str:
    return f"${int(value):,}" if value else "TBD"


def _format_compact_currency(value: Decimal) -> str:
    if value >= Decimal("1000000000"):
        return f"${value / Decimal('1000000000'):.1f}B"
    if value >= Decimal("1000000"):
        return f"${value / Decimal('1000000'):.0f}M"
    if value >= Decimal("1000"):
        return f"${value / Decimal('1000'):.0f}K"
    return f"${int(value)}"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _join(*values: Optional[str]) -> str:
    return " ".join(str(value) for value in values if value)


def _unique(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _trim(value: str, limit: int) -> str:
    clean = " ".join(str(value).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "..."


# ─── Generate Insights endpoints ─────────────────────────────────────────────

class GenerateStatusResponse(BaseModel):
    new_doc_count: int
    affected_contract_count: int


class GenerateInsightsResponse(BaseModel):
    queued: int


def _contracts_with_new_docs(
    db: Session, visible_ids: List[str]
) -> Dict[str, List[str]]:
    """Return {contract_id: [new_doc_id, ...]} for contracts with unanalyzed completed docs."""
    if not visible_ids:
        return {}
    result: Dict[str, List[str]] = {}
    for cid in visible_ids:
        rows = db.execute(
            text(
                """
                SELECT id FROM document_uploads
                WHERE contract_id = :cid
                  AND processing_status = 'completed'
                  AND created_at > COALESCE(
                      (SELECT MAX(ar.completed_at) FROM analysis_runs ar
                       WHERE ar.target_contract_id = :cid
                         AND ar.run_type = 'per_contract'
                         AND ar.status = 'complete'),
                      '1970-01-01T00:00:00+00:00'
                  )
                ORDER BY created_at ASC
                """
            ),
            {"cid": cid},
        ).all()
        if rows:
            result[cid] = [str(r[0]) for r in rows]
    return result


@router.get("/generate-status", response_model=GenerateStatusResponse)
def get_generate_status(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GenerateStatusResponse:
    visible_ids = visible_contract_ids(user, db)
    contracts_new_docs = _contracts_with_new_docs(db, visible_ids)
    total_docs = sum(len(v) for v in contracts_new_docs.values())
    return GenerateStatusResponse(
        new_doc_count=total_docs,
        affected_contract_count=len(contracts_new_docs),
    )


@router.post("/generate-insights", response_model=GenerateInsightsResponse, status_code=202)
def post_generate_insights(
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GenerateInsightsResponse:
    visible_ids = visible_contract_ids(user, db)
    contracts_new_docs = _contracts_with_new_docs(db, visible_ids)
    for cid, doc_ids in contracts_new_docs.items():
        background_tasks.add_task(_portfolio_analysis_task, cid, doc_ids)
    return GenerateInsightsResponse(queued=len(contracts_new_docs))


def _portfolio_analysis_task(contract_id: str, new_doc_ids: List[str]) -> None:
    db = SessionLocal()
    try:
        run_incremental_contract_analysis(db, contract_id, new_doc_ids)
    except Exception:
        pass
    finally:
        db.close()
