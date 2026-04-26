from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.authz import visible_contract_ids
from app.config import get_ai_max_retries, get_ai_request_timeout_seconds, get_openai_api_key, get_openai_llm_model
from app.database import get_db
from app.models import (
    Contract,
    ContractHypothesis,
    DocumentReportFact,
    PerformanceSignal,
    RegressionFinding,
)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])
PORTFOLIO_LESSONS_RUN_TYPE = "portfolio_lessons"


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


class PortfolioLessonEvidenceResponse(BaseModel):
    type: str
    id: str
    contract_id: str
    document_id: Optional[str] = None
    theme_id: Optional[str] = None


class PortfolioLessonResponse(BaseModel):
    id: str
    title: str
    summary: str
    subject_type: str
    subject_label: str
    semantic_pattern: str
    confidence: str
    affected_contract_ids: List[str] = []
    theme_ids: List[str] = []
    evidence: List[PortfolioLessonEvidenceResponse] = []
    recommended_controls: List[str] = []
    limitations: List[str] = []


class PortfolioLessonsResponse(BaseModel):
    generated_at: datetime
    source: str
    lessons: List[PortfolioLessonResponse]
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


@router.get("/lessons", response_model=PortfolioLessonsResponse)
def get_portfolio_lessons(
    period: str = Query(default="last_30_days"),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioLessonsResponse:
    visible_ids = visible_contract_ids(user, db)
    stored = latest_stored_portfolio_lessons(db, period=period, visible_contract_ids=visible_ids)
    if stored is not None:
        return stored
    return build_portfolio_lessons_response(db, visible_ids, period=period, use_ai=False)


def run_portfolio_lessons_analysis(
    db: Session,
    *,
    period: str = "fy26",
    contract_ids: Optional[Sequence[str]] = None,
    use_ai: bool = True,
) -> Dict[str, object]:
    selected_ids = list(contract_ids or db.scalars(select(Contract.id)).all())
    run_id = str(uuid4())
    _insert_portfolio_lessons_run(db, run_id, period, selected_ids, status="running")
    try:
        response = build_portfolio_lessons_response(db, selected_ids, period=period, use_ai=use_ai)
        result = _portfolio_lessons_result(response, period, selected_ids)
        _complete_portfolio_lessons_run(db, run_id, result)
        return {"id": run_id, "status": "complete", "result": result}
    except Exception as exc:
        _fail_portfolio_lessons_run(db, run_id, exc)
        raise


def latest_stored_portfolio_lessons(
    db: Session,
    *,
    period: str,
    visible_contract_ids: Sequence[str],
) -> Optional[PortfolioLessonsResponse]:
    visible = set(visible_contract_ids)
    if not visible:
        return None
    try:
        rows = db.execute(
            text(
                """
                SELECT id, completed_at, result
                FROM analysis_runs
                WHERE run_type = :run_type
                  AND status = 'complete'
                ORDER BY completed_at DESC, created_at DESC
                LIMIT 10
                """
            ),
            {"run_type": PORTFOLIO_LESSONS_RUN_TYPE},
        ).mappings().all()
    except SQLAlchemyError:
        db.rollback()
        return None
    for row in rows:
        result = _json_value(row.get("result"))
        if not isinstance(result, dict) or result.get("period") != period:
            continue
        run_contract_ids = {str(item) for item in result.get("contract_ids", [])}
        if run_contract_ids and not run_contract_ids.issubset(visible):
            continue
        response = _portfolio_lessons_response_from_result(result, row.get("completed_at"))
        if response is not None:
            return response
    return None


def build_portfolio_lessons_response(
    db: Session,
    contract_ids: Sequence[str],
    *,
    period: str,
    use_ai: bool,
) -> PortfolioLessonsResponse:
    contracts_by_id = _contracts_by_id(db, contract_ids)
    observations = _filter_period(
        _observations(db, [contract_id for contract_id in contract_ids if contract_id in contracts_by_id]),
        period,
    )
    themes = [
        _theme_response(group, contracts_by_id, len(contracts_by_id))
        for group in _theme_groups(observations)
    ]
    limitations = []
    if not observations:
        limitations.append(
            "No processed regression findings, hypotheses, report facts, or performance signals are available for visible contracts yet."
        )
    if not contracts_by_id:
        limitations.append("No database-backed contract records are visible for this user yet.")
    if limitations:
        return PortfolioLessonsResponse(
            generated_at=datetime.now(timezone.utc),
            source="unavailable",
            lessons=[],
            limitations=limitations,
        )

    ai_lessons: List[PortfolioLessonResponse] = []
    ai_limitations: List[str] = []
    if use_ai:
        ai_lessons, ai_limitations = _ai_portfolio_lessons(themes, contracts_by_id)
    if ai_lessons:
        return PortfolioLessonsResponse(
            generated_at=datetime.now(timezone.utc),
            source="ai_from_backend_evidence",
            lessons=ai_lessons[:6],
            limitations=ai_limitations,
        )

    fallback_lessons = _deterministic_portfolio_lessons(themes, contracts_by_id)
    return PortfolioLessonsResponse(
        generated_at=datetime.now(timezone.utc),
        source="deterministic_from_backend_evidence",
        lessons=fallback_lessons[:6],
        limitations=ai_limitations
        + [
            "AI portfolio synthesis is unavailable or has not been run in the background, so lessons were assembled from backend evidence themes."
        ],
    )


def _contracts_by_id(db: Session, visible_ids: Sequence[str]) -> Dict[str, Contract]:
    if not visible_ids:
        return {}
    rows = db.scalars(select(Contract).where(Contract.id.in_(visible_ids))).all()
    return {row.id: row for row in rows}


def _portfolio_lessons_result(
    response: PortfolioLessonsResponse,
    period: str,
    contract_ids: Sequence[str],
) -> Dict[str, object]:
    return {
        "period": period,
        "contract_ids": list(contract_ids),
        "source": response.source,
        "generated_at": response.generated_at.isoformat(),
        "lessons": [_model_dump(lesson) for lesson in response.lessons],
        "limitations": response.limitations,
    }


def _portfolio_lessons_response_from_result(
    result: Dict[str, object],
    completed_at: object,
) -> Optional[PortfolioLessonsResponse]:
    lessons = result.get("lessons")
    if not isinstance(lessons, list):
        return None
    generated_at = _parse_datetime(result.get("generated_at")) or _parse_datetime(completed_at) or datetime.now(timezone.utc)
    return PortfolioLessonsResponse(
        generated_at=generated_at,
        source=str(result.get("source") or "stored_background_analysis"),
        lessons=[
            PortfolioLessonResponse(**lesson)
            for lesson in lessons
            if isinstance(lesson, dict)
        ],
        limitations=[
            str(item)
            for item in result.get("limitations", [])
            if str(item).strip()
        ],
    )


def _insert_portfolio_lessons_run(
    db: Session,
    run_id: str,
    period: str,
    contract_ids: Sequence[str],
    *,
    status: str,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO analysis_runs
                (id, run_type, target_contract_id, cohort_definition,
                 cohort_contract_ids, status, created_at, model)
            VALUES (:id, :run_type, NULL, {cohort_definition},
                    {cohort_contract_ids}, :status, :created_at, :model)
            """.format(
                cohort_definition=_json_sql_value(db, "cohort_definition"),
                cohort_contract_ids=_json_sql_value(db, "cohort_contract_ids"),
            )
        ),
        {
            "id": run_id,
            "run_type": PORTFOLIO_LESSONS_RUN_TYPE,
            "cohort_definition": json.dumps({"period": period, "scope": "portfolio_lessons"}),
            "cohort_contract_ids": json.dumps(list(contract_ids)),
            "status": status,
            "created_at": datetime.now(timezone.utc),
            "model": get_openai_llm_model() if get_openai_api_key() else "deterministic_v1",
        },
    )
    db.commit()


def _complete_portfolio_lessons_run(db: Session, run_id: str, result: Dict[str, object]) -> None:
    db.execute(
        text(
            """
            UPDATE analysis_runs
            SET status = 'complete', completed_at = :completed_at, result = {result}
            WHERE id = :id
            """.format(result=_json_sql_value(db, "result"))
        ),
        {
            "id": run_id,
            "completed_at": datetime.now(timezone.utc),
            "result": json.dumps(result),
        },
    )
    db.commit()


def _fail_portfolio_lessons_run(db: Session, run_id: str, error: Exception) -> None:
    db.execute(
        text(
            """
            UPDATE analysis_runs
            SET status = 'failed', completed_at = :completed_at, result = {result}
            WHERE id = :id
            """.format(result=_json_sql_value(db, "result"))
        ),
        {
            "id": run_id,
            "completed_at": datetime.now(timezone.utc),
            "result": json.dumps({"error": str(error)}),
        },
    )
    db.commit()


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


def _ai_portfolio_lessons(
    themes: Sequence[PortfolioThemeResponse],
    contracts_by_id: Dict[str, Contract],
) -> tuple[List[PortfolioLessonResponse], List[str]]:
    api_key = get_openai_api_key()
    if not api_key:
        return [], ["OPENAI_API_KEY is not configured for AI-authored portfolio lessons."]
    packet = _lesson_prompt_packet(themes, contracts_by_id)
    if not packet:
        return [], ["No compact evidence packet could be assembled for AI-authored portfolio lessons."]

    system = (
        "You are a federal contract portfolio analyst. Synthesize semantic lessons from "
        "backend evidence themes. Do not make unsupported character judgments about vendors. "
        "Write evidence-grounded execution patterns such as budget underestimation, EAC drift, "
        "staffing-to-schedule risk, GFE/GFI delay, quality rework, or acceptance bottlenecks. "
        "Every lesson must cite theme_ids and evidence ids from the supplied packet. "
        "Return JSON only with key lessons. Each lesson needs title, summary, subject_type, "
        "subject_label, semantic_pattern, confidence, affected_contract_ids, theme_ids, "
        "evidence, recommended_controls, and limitations."
    )
    user = json.dumps({"themes": packet}, default=str)
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            timeout=get_ai_request_timeout_seconds(),
            max_retries=get_ai_max_retries(),
        )
        response = client.chat.completions.create(
            model=get_openai_llm_model(),
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(_strip_json_fence(content))
    except Exception as exc:
        return [], [f"AI portfolio lesson synthesis failed: {str(exc)[:240]}"]

    allowed_theme_ids = {theme.id for theme in themes}
    allowed_contract_ids = set(contracts_by_id)
    allowed_evidence_ids = {
        evidence["id"]
        for theme in themes
        for evidence in _theme_evidence_refs(theme)
    }
    lessons: List[PortfolioLessonResponse] = []
    raw_lessons = data.get("lessons") if isinstance(data, dict) else None
    if not isinstance(raw_lessons, list):
        return [], ["AI portfolio lesson synthesis returned no lessons array."]
    for index, item in enumerate(raw_lessons):
        if not isinstance(item, dict):
            continue
        lesson = _lesson_from_payload(
            item,
            fallback_id=f"ai-portfolio-lesson-{index + 1}",
            allowed_theme_ids=allowed_theme_ids,
            allowed_contract_ids=allowed_contract_ids,
            allowed_evidence_ids=allowed_evidence_ids,
        )
        if lesson is not None:
            lessons.append(lesson)
    if not lessons:
        return [], ["AI portfolio lesson synthesis did not return cited lessons."]
    return lessons, []


def _deterministic_portfolio_lessons(
    themes: Sequence[PortfolioThemeResponse],
    contracts_by_id: Dict[str, Contract],
) -> List[PortfolioLessonResponse]:
    lessons: List[PortfolioLessonResponse] = []
    for theme in themes:
        contract_ids = [contract.id for contract in theme.contracts]
        if not contract_ids:
            continue
        subject_type, subject_label = _theme_subject(theme, contracts_by_id)
        pattern = _semantic_pattern_for_theme(theme)
        controls = _controls_for_pattern(pattern)
        evidence = [
            PortfolioLessonEvidenceResponse(**ref)
            for ref in _theme_evidence_refs(theme)[:8]
        ]
        confidence = "medium" if len(contract_ids) >= 3 and theme.evidence_count >= 3 else "low"
        lessons.append(
            PortfolioLessonResponse(
                id=f"lesson-{theme.id}",
                title=_lesson_title(pattern, subject_label),
                summary=_lesson_summary(theme, pattern, subject_type, subject_label),
                subject_type=subject_type,
                subject_label=subject_label,
                semantic_pattern=pattern,
                confidence=confidence,
                affected_contract_ids=contract_ids,
                theme_ids=[theme.id],
                evidence=evidence,
                recommended_controls=controls,
                limitations=_lesson_limitations(theme, confidence),
            )
        )
    lessons.sort(key=lambda item: (item.confidence != "medium", -len(item.affected_contract_ids), item.title))
    return lessons


def _lesson_prompt_packet(
    themes: Sequence[PortfolioThemeResponse],
    contracts_by_id: Dict[str, Contract],
) -> List[Dict[str, Any]]:
    packet: List[Dict[str, Any]] = []
    for theme in themes[:12]:
        contracts = []
        for item in theme.contracts[:8]:
            contract = contracts_by_id.get(item.id)
            contracts.append(
                {
                    "id": item.id,
                    "number": item.number,
                    "title": item.title,
                    "vendor_name": contract.vendor_name if contract else None,
                    "vendor_uei": contract.vendor_uei if contract else None,
                    "psc": item.psc,
                    "component": item.component,
                    "severity": item.severity,
                    "evidence_count": item.evidence_count,
                    "explanation": item.explanation,
                    "evidence": _contract_evidence_refs(theme.id, item),
                }
            )
        packet.append(
            {
                "id": theme.id,
                "title": theme.title,
                "severity": theme.severity,
                "psc": theme.psc,
                "component": theme.component,
                "flagged": theme.flagged,
                "total": theme.total,
                "insight": theme.insight,
                "evidence_count": theme.evidence_count,
                "contracts": contracts,
            }
        )
    return packet


def _lesson_from_payload(
    item: Dict[str, Any],
    *,
    fallback_id: str,
    allowed_theme_ids: set[str],
    allowed_contract_ids: set[str],
    allowed_evidence_ids: set[str],
) -> Optional[PortfolioLessonResponse]:
    title = _trim(str(item.get("title") or ""), 160)
    summary = _trim(str(item.get("summary") or ""), 900)
    if not title or not summary:
        return None
    theme_ids = [
        str(theme_id)
        for theme_id in item.get("theme_ids", [])
        if str(theme_id) in allowed_theme_ids
    ]
    affected_contract_ids = [
        str(contract_id)
        for contract_id in item.get("affected_contract_ids", [])
        if str(contract_id) in allowed_contract_ids
    ]
    evidence_rows: List[PortfolioLessonEvidenceResponse] = []
    for raw in item.get("evidence", []):
        if not isinstance(raw, dict):
            continue
        evidence_id = str(raw.get("id") or "")
        if evidence_id not in allowed_evidence_ids:
            continue
        evidence_rows.append(
            PortfolioLessonEvidenceResponse(
                type=str(raw.get("type") or "evidence"),
                id=evidence_id,
                contract_id=str(raw.get("contract_id") or ""),
                document_id=raw.get("document_id"),
                theme_id=str(raw.get("theme_id") or theme_ids[0] if theme_ids else ""),
            )
        )
    if not theme_ids or not affected_contract_ids or not evidence_rows:
        return None
    confidence = str(item.get("confidence") or "low").lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    return PortfolioLessonResponse(
        id=_slug(str(item.get("id") or title))[:120] or fallback_id,
        title=title,
        summary=summary,
        subject_type=_trim(str(item.get("subject_type") or "portfolio"), 40),
        subject_label=_trim(str(item.get("subject_label") or "Visible portfolio"), 160),
        semantic_pattern=_trim(str(item.get("semantic_pattern") or title), 120),
        confidence=confidence,
        affected_contract_ids=affected_contract_ids,
        theme_ids=theme_ids,
        evidence=evidence_rows[:12],
        recommended_controls=[
            _trim(str(value), 260)
            for value in item.get("recommended_controls", [])
            if str(value).strip()
        ][:6],
        limitations=[
            _trim(str(value), 260)
            for value in item.get("limitations", [])
            if str(value).strip()
        ][:6],
    )


def _theme_subject(
    theme: PortfolioThemeResponse,
    contracts_by_id: Dict[str, Contract],
) -> tuple[str, str]:
    vendors: Dict[str, int] = defaultdict(int)
    for item in theme.contracts:
        contract = contracts_by_id.get(item.id)
        vendor = (contract.vendor_name if contract else None) or ""
        if vendor:
            vendors[vendor] += 1
    if vendors:
        vendor, count = max(vendors.items(), key=lambda row: (row[1], row[0]))
        if count >= 2:
            return "contractor", vendor
    if theme.psc not in {"Multi", "Uncoded"}:
        return "category", theme.psc
    if theme.component not in {"Multi", "Unassigned"}:
        return "office", theme.component
    return "portfolio", "Visible portfolio"


def _semantic_pattern_for_theme(theme: PortfolioThemeResponse) -> str:
    text = f"{theme.id} {theme.title} {theme.insight}".lower()
    if "cost" in text or "eac" in text or "financial" in text or "budget" in text:
        return "budget underestimation or upward cost-pressure pattern"
    if "staff" in text or "personnel" in text or "vacancy" in text:
        return "staffing continuity pattern preceding execution risk"
    if "schedule" in text or "deliverable" in text or "late" in text or "slip" in text:
        return "deliverable slippage pattern"
    if "quality" in text or "rework" in text or "acceptance" in text:
        return "quality or acceptance rework pattern"
    if "gfe" in text or "gfi" in text or "access" in text or "credential" in text:
        return "government-furnished information or access delay pattern"
    if "license" in text or "export" in text:
        return "external dependency or licensing pattern"
    return "recurring portfolio execution pattern"


def _lesson_title(pattern: str, subject_label: str) -> str:
    return f"{subject_label}: {pattern.capitalize()}"


def _lesson_summary(
    theme: PortfolioThemeResponse,
    pattern: str,
    subject_type: str,
    subject_label: str,
) -> str:
    scope = f"{theme.flagged} of {theme.total} visible contracts"
    if subject_type == "contractor":
        return (
            f"{subject_label} appears in a {pattern} across {scope.lower()} tied to "
            f"{theme.title.lower()}. The evidence supports treating this as an execution pattern "
            "to review, not as a character judgment about the contractor."
        )
    return (
        f"{scope} show a {pattern} tied to {theme.title.lower()}. Use this as a portfolio lesson "
        "for contract management and future solicitation controls."
    )


def _lesson_limitations(theme: PortfolioThemeResponse, confidence: str) -> List[str]:
    limitations = []
    if confidence == "low":
        limitations.append("Small visible evidence set; treat as a review prompt until more comparable contracts are processed.")
    if theme.flagged < theme.total:
        limitations.append("Pattern applies only to the flagged visible contracts, not the entire category.")
    return limitations


def _controls_for_pattern(pattern: str) -> List[str]:
    if "budget" in pattern or "cost" in pattern:
        return [
            "Require EAC change rationale when forecast growth crosses the agreed variance threshold.",
            "Add monthly comparison of planned burn, actuals, ETC, and funding need by reporting period.",
            "Review whether proposal assumptions match observed staffing, travel, material, and subcontractor demand.",
        ]
    if "staffing" in pattern:
        return [
            "Require named key-person backup coverage and transition timing.",
            "Add vacancy aging thresholds that trigger COR and CO notification.",
            "Tie recovery plans to recurring staffing gaps before schedule slips accumulate.",
        ]
    if "deliverable" in pattern:
        return [
            "Add recovery-plan triggers after repeated late CDRLs or milestone slips.",
            "Clarify government review and acceptance windows so responsibility for delay is visible.",
            "Require period-labeled schedule variance explanations in recurring reports.",
        ]
    if "quality" in pattern or "rework" in pattern:
        return [
            "Define acceptance criteria and rework reporting requirements before award.",
            "Add quality gates for recurring defect or rejection patterns.",
        ]
    if "government-furnished" in pattern or "access" in pattern:
        return [
            "Create a GFE/GFI responsibility matrix with government response deadlines.",
            "Track access, credential, and information handoff blockers as reportable risks.",
        ]
    return [
        "Assign an owner, cadence, threshold, and escalation path for this recurring evidence pattern.",
        "Require recurring reports to separate contractor-caused and government-caused blockers.",
    ]


def _theme_evidence_refs(theme: PortfolioThemeResponse) -> List[Dict[str, str]]:
    refs: List[Dict[str, str]] = []
    for contract in theme.contracts:
        refs.extend(_contract_evidence_refs(theme.id, contract))
    return refs


def _contract_evidence_refs(theme_id: str, contract: PortfolioThemeContractResponse) -> List[Dict[str, str]]:
    refs: List[Dict[str, str]] = []
    for source_type, values in (
        ("finding", contract.finding_ids),
        ("signal", contract.signal_ids),
        ("hypothesis", contract.hypothesis_ids),
        ("fact", contract.fact_ids),
    ):
        for value in values:
            refs.append(
                {
                    "type": source_type,
                    "id": value,
                    "contract_id": contract.id,
                    "document_id": (contract.document_ids[0] if contract.document_ids else None),
                    "theme_id": theme_id,
                }
            )
    return refs


def _strip_json_fence(value: str) -> str:
    return re.sub(r"^```[a-zA-Z]*\n?|```$", "", value.strip(), flags=re.MULTILINE).strip()


def _json_sql_value(db: Session, parameter_name: str) -> str:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        return f"CAST(:{parameter_name} AS JSON)"
    return f":{parameter_name}"


def _json_value(value: object) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _model_dump(model: BaseModel) -> Dict[str, object]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def _parse_datetime(value: object) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


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
