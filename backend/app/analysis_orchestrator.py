"""Orchestrate per-contract and cohort contract performance analysis.

Loads five primitive tables (deliverable, financial, decisions, issue, personnel)
plus CPARS ratings, assembles them into the analysis prompt, calls OpenAI, and
stores the JSON result in analysis_runs.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.cohort_builder import CohortDefinition, build_cohort
from app.config import (
    get_ai_max_retries,
    get_ai_request_timeout_seconds,
    get_openai_api_key,
    get_openai_llm_model,
)
from app.models import (
    AuditEvent,
    BaselineObligation,
    Contract,
    DocumentReportFact,
    DocumentUpload,
    KnowledgeSourceRecord,
    PerformanceSignal,
    RegressionFinding,
)

_PER_CONTRACT_SYSTEM = """ROLE You are a contract performance analyst. You evaluate a target federal \
contract against a cohort of comparable contracts using structured primitive records. You never \
read raw contract documents or reports — only the extracted primitives. Every claim you produce \
must cite the primitive record(s) it came from.

NOTE Use axes such as schedule performance and cost performance to contextualize qualitative \
lessons that were the root cause of a bigger issue.

HARD RULES
- Generate only from primitive records. Do not infer values from absent data.
- Every output claim includes citations to the primitive record IDs it derives from.
- If a required primitive is missing or sparse, return "not_extractable" for that axis.
- Keep measured (axis values, percentiles) strictly separate from predicted (CPARS mappings).
- If cohort.N < 20, set low_confidence: true on every percentile.

OUTPUT Return JSON with keys: cohort_definition, cohort_N, axes (array), \
cpars_predicted (object), summary (≤200 words, every sentence cited)."""

_AXES_DESCRIPTION = """
AXES TO COMPUTE For each axis return: target value, cohort distribution (p10/p25/p50/p75/p90), \
target percentile, supporting citations.
1. Schedule performance — total slip, deliverable-level slip, on-time delivery rate, \
time-to-first-slip. Source: deliverable.
2. Cost performance — actual/planned burn ratio at equivalent % POP, final cost variance, \
burn-rate volatility. Source: financial.
3. Scope stability — mod count, mod-driven value growth %, time-to-first-mod, mod-reason \
distribution. Source: decisions.
4. Execution and risk — issue count by category, recurrence rate (same issue ≥3 reports), \
avg time-to-resolution, escalation rate, responsible-party distribution. Source: issue.
5. Forecasting accuracy — EAC drift, lag between issue-onset and cost/schedule impact, \
% complete accuracy. Source: financial + issue + deliverable.
6. Quality — defect/rework rate, deliverable acceptance rate, technical rejections. Source: \
deliverable + issue.
7. Small Business Subcontracting — goal attainment vs. plan, reporting timeliness. Source: \
decisions + financial. Mark not_applicable if below threshold.
8. Regulatory Compliance — finding count, corrective action plans, incident count. Source: \
issue (filter category=compliance).
9. Closeout — delivered scope vs. SOW, descope rate, closeout duration, disputed amounts. \
Source: deliverable + decisions + financial.

CPARS MAPPING Predict an adjectival rating for: Quality, Schedule, Cost Control, Management, \
Small Business Subcontracting, Regulatory Compliance. Label as predicted."""

_COHORT_SYSTEM = """ROLE You are a contract performance analyst performing cross-contract pattern \
analysis. You receive per-contract analysis outputs for a cohort of comparable contracts and \
identify lessons — patterns of success and failure.

HARD RULES
- Find what poorly-performing contracts have in common (be specific: what caused delays, \
what caused cost overruns).
- Find what well-performing contracts have in common (be specific: what expedited work, \
which approaches were effective).
- Identify the delta between the two — that is where the lessons are.
- Identify recurring qualitative signals (e.g., GFE delays) that correlate with quantitative \
degradation.
- Identify whether contractor execution patterns (phasing, subcontractor approach, QC methods) \
correlate with performance outcomes.

OUTPUT Return JSON with keys: cohort_N, performance_groups (high/low performers with \
contract_ids), common_failure_patterns (list of specific findings), \
common_success_patterns (list), delta_lessons (list — the unique contribution), \
qualitative_quantitative_correlations (list), summary (≤300 words)."""

_INCREMENTAL_SYSTEM = """ROLE You are a contract performance analyst performing an INCREMENTAL \
update. New performance documents have been filed since the prior analysis of this contract. \
Your job: (1) identify what has changed, improved, or degraded; (2) note newly-emerged risks \
or issues; (3) note any resolutions; (4) produce a self-contained updated analysis.

HARD RULES
- Derive claims only from the provided primitive records (prior summary and new primitives).
- Every output claim cites the primitive record ID(s) it derives from.
- If a new primitive contradicts the prior summary, flag it explicitly as a change.
- If no meaningful change is detected for an axis, carry it forward from the prior analysis.
- If cohort.N < 20, set low_confidence: true on every percentile.

OUTPUT Return JSON with the same keys as per-contract analysis: cohort_definition, cohort_N, \
axes (array), cpars_predicted (object), summary (≤200 words, all sentences cited), PLUS:
- prior_run_id: ID of the prior analysis run
- new_doc_ids: list of document_upload IDs analyzed in this run
- changes: list of {axis, change_type (improved|degraded|new_risk|resolved), description}"""


def run_per_contract_analysis(
    db: Session,
    contract_id: str,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run per-contract analysis. Returns the analysis_run record dict."""
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise ValueError(f"Contract {contract_id} not found")

    cohort = build_cohort(db, contract_id)
    target_primitives = _compact_primitives(_load_primitives(db, contract_id), limit_per_bucket=45)
    cohort_primitives = {
        cid: _compact_primitives(_load_primitives(db, cid), limit_per_bucket=12)
        for cid in cohort.contract_ids
    }
    cpars = _load_cpars(db, contract_id)

    prompt_user = _build_per_contract_prompt(
        contract, target_primitives, cpars, cohort, cohort_primitives
    )

    if run_id is None:
        run_id = str(uuid.uuid4())
        _insert_analysis_run(db, run_id, "per_contract", contract_id, cohort, status="running")
    else:
        _mark_analysis_run_running(db, run_id)

    try:
        result_json = _openai_json_response(
            _PER_CONTRACT_SYSTEM + "\n\n" + _AXES_DESCRIPTION,
            prompt_user,
        )
    except Exception as exc:
        _fail_analysis_run(db, run_id, exc)
        raise
    result_json = _tag_low_confidence(result_json, cohort)

    _complete_analysis_run(db, run_id, result_json)
    return {"id": run_id, "status": "complete", "result": result_json}


def enqueue_per_contract_analysis_after_extraction(
    db: Session,
    contract_id: str,
    *,
    document_upload_id: str | None = None,
    extraction_run_id: str | None = None,
) -> dict[str, Any]:
    """Queue per-contract analysis when extracted primitives are newer than analysis."""
    if db.get(Contract, contract_id) is None:
        raise ValueError(f"Contract {contract_id} not found")

    latest_primitive_update = _latest_primitive_update(db, contract_id)
    if latest_primitive_update is None:
        _log_analysis_audit_event(
            db,
            "analysis.per_contract.auto_skipped",
            contract_id,
            document_upload_id=document_upload_id,
            metadata={
                "status": "skipped",
                "reason": "no_primitive_update",
                "extraction_run_id": extraction_run_id,
            },
        )
        db.commit()
        return {"status": "skipped", "reason": "no_primitive_update", "run_id": None}

    existing_run = _analysis_run_newer_than(db, contract_id, latest_primitive_update)
    if existing_run is not None:
        _log_analysis_audit_event(
            db,
            "analysis.per_contract.auto_skipped",
            contract_id,
            document_upload_id=document_upload_id,
            entity_id=existing_run["id"],
            metadata={
                "status": "skipped",
                "reason": "debounced",
                "analysis_run_id": existing_run["id"],
                "analysis_created_at": str(existing_run["created_at"]),
                "latest_primitive_update": str(latest_primitive_update),
                "extraction_run_id": extraction_run_id,
            },
        )
        db.commit()
        return {
            "status": "skipped",
            "reason": "debounced",
            "run_id": existing_run["id"],
        }

    cohort = build_cohort(db, contract_id)
    run_id = str(uuid.uuid4())
    _insert_analysis_run(db, run_id, "per_contract", contract_id, cohort, status="queued")
    _log_analysis_audit_event(
        db,
        "analysis.per_contract.auto_enqueued",
        contract_id,
        document_upload_id=document_upload_id,
        entity_id=run_id,
        metadata={
            "status": "queued",
            "analysis_run_id": run_id,
            "latest_primitive_update": str(latest_primitive_update),
            "extraction_run_id": extraction_run_id,
            "cohort_N": cohort.N,
            "low_confidence": cohort.low_confidence,
        },
    )
    db.commit()
    return {
        "status": "queued",
        "run_id": run_id,
        "cohort_N": cohort.N,
        "low_confidence": cohort.low_confidence,
    }


def execute_enqueued_per_contract_analysis(
    db: Session,
    run_id: str,
    contract_id: str,
    *,
    document_upload_id: str | None = None,
    extraction_run_id: str | None = None,
) -> dict[str, Any]:
    """Run a queued per-contract analysis row and record audit visibility."""
    try:
        result = run_per_contract_analysis(db, contract_id, run_id=run_id)
    except Exception as exc:
        _fail_analysis_run(db, run_id, exc)
        _log_analysis_audit_event(
            db,
            "analysis.per_contract.auto_failed",
            contract_id,
            document_upload_id=document_upload_id,
            entity_id=run_id,
            metadata={
                "status": "failed",
                "analysis_run_id": run_id,
                "extraction_run_id": extraction_run_id,
                "error": str(exc),
            },
        )
        db.commit()
        raise

    _log_analysis_audit_event(
        db,
        "analysis.per_contract.auto_completed",
        contract_id,
        document_upload_id=document_upload_id,
        entity_id=run_id,
        metadata={
            "status": "complete",
            "analysis_run_id": run_id,
            "extraction_run_id": extraction_run_id,
            "low_confidence": result.get("result", {}).get("low_confidence"),
        },
    )
    db.commit()
    return result


def run_cohort_analysis(
    db: Session,
    contract_ids: list[str],
    cohort_definition: dict | None = None,
) -> dict[str, Any]:
    """Run cross-contract cohort analysis. Returns the analysis_run record dict."""
    per_contract_results = []
    for cid in contract_ids:
        primitives = _compact_primitives(_load_primitives(db, cid), limit_per_bucket=20)
        cpars = _load_cpars(db, cid)
        per_contract_results.append({
            "contract_id": cid,
            "primitives": primitives,
            "cpars": cpars,
        })

    prompt_user = _build_cohort_prompt(contract_ids, per_contract_results)

    run_id = str(uuid.uuid4())
    _insert_analysis_run(
        db, run_id, "cohort", None,
        cohort=None,
        cohort_definition=cohort_definition or {"contract_ids": contract_ids},
        cohort_contract_ids=contract_ids,
    )

    try:
        result_json = _openai_json_response(_COHORT_SYSTEM, prompt_user)
    except Exception as exc:
        _fail_analysis_run(db, run_id, exc)
        raise

    _complete_analysis_run(db, run_id, result_json)
    return {"id": run_id, "status": "complete", "result": result_json}


def _load_primitives(db: Session, contract_id: str) -> dict[str, list[dict]]:
    tables = {
        "deliverable": "contract_primitives_deliverable",
        "financial": "contract_primitives_financial",
        "decisions": "contract_primitives_decisions",
        "issues": "contract_primitives_issues",
        "personnel": "contract_primitives_personnel",
    }
    result = {}
    for key, table in tables.items():
        try:
            rows = db.execute(
                text(f"SELECT * FROM {table} WHERE contract_id = :cid ORDER BY period_label"),
                {"cid": contract_id},
            ).mappings().all()
        except SQLAlchemyError:
            db.rollback()
            rows = []
        result[key] = [dict(r) for r in rows]
    if any(result.values()):
        return result
    return _load_legacy_extracted_primitives(db, contract_id)


def _load_cpars(db: Session, contract_id: str) -> list[dict]:
    try:
        rows = db.execute(
            text(
                "SELECT * FROM cpars_ratings WHERE contract_id = :cid ORDER BY evaluation_date"
            ),
            {"cid": contract_id},
        ).mappings().all()
        ratings = [dict(r) for r in rows]
    except SQLAlchemyError:
        db.rollback()
        ratings = []
    ratings.extend(_load_legacy_cpars_exports(db, contract_id))
    return ratings


def _load_legacy_extracted_primitives(db: Session, contract_id: str) -> dict[str, list[dict]]:
    """Use already-extracted evidence as primitive input until typed primitive tables are populated."""
    documents = {
        document.id: document
        for document in db.scalars(
            select(DocumentUpload)
            .where(DocumentUpload.contract_id == contract_id)
            .order_by(DocumentUpload.report_period_start, DocumentUpload.created_at)
        ).all()
    }
    primitives: dict[str, list[dict]] = {
        "deliverable": [],
        "financial": [],
        "decisions": [],
        "issues": [],
        "personnel": [],
    }

    facts = db.scalars(
        select(DocumentReportFact)
        .where(DocumentReportFact.contract_id == contract_id)
        .order_by(DocumentReportFact.created_at)
    ).all()
    for fact in facts:
        record = _legacy_record(
            primitive_source="document_report_fact",
            primitive_id=fact.id,
            contract_id=contract_id,
            document=documents.get(fact.document_upload_id),
            label=fact.label,
            category=fact.fact_type,
            text_value=fact.value_text,
            quote=fact.quote,
            confidence=fact.confidence,
            metadata=fact.value_json or fact.metadata_json or {},
        )
        _append_legacy_primitive(primitives, record)

    findings = db.scalars(
        select(RegressionFinding)
        .where(RegressionFinding.contract_id == contract_id)
        .order_by(RegressionFinding.created_at)
    ).all()
    for finding in findings:
        record = _legacy_record(
            primitive_source="regression_finding",
            primitive_id=finding.id,
            contract_id=contract_id,
            document=documents.get(finding.document_upload_id),
            label=finding.title,
            category=finding.finding_type,
            text_value=finding.summary,
            quote=finding.quote,
            confidence=finding.confidence,
            metadata={"severity": finding.severity, "status": finding.status},
        )
        _append_legacy_primitive(primitives, record)

    signals = db.scalars(
        select(PerformanceSignal)
        .where(PerformanceSignal.contract_id == contract_id)
        .order_by(PerformanceSignal.created_at)
    ).all()
    for signal in signals:
        record = _legacy_record(
            primitive_source="performance_signal",
            primitive_id=signal.id,
            contract_id=contract_id,
            document=documents.get(signal.document_upload_id),
            label=signal.label or signal.signal_type,
            category=signal.signal_type,
            text_value=signal.summary,
            quote=None,
            confidence=signal.confidence,
            metadata={"severity": signal.severity, **(signal.metadata_json or {})},
        )
        _append_legacy_primitive(primitives, record)

    obligations = db.scalars(
        select(BaselineObligation)
        .where(BaselineObligation.contract_id == contract_id)
        .order_by(BaselineObligation.created_at)
    ).all()
    for obligation in obligations:
        record = _legacy_record(
            primitive_source="baseline_obligation",
            primitive_id=obligation.id,
            contract_id=contract_id,
            document=documents.get(obligation.source_document_upload_id),
            label=obligation.title,
            category=obligation.obligation_type,
            text_value=obligation.description,
            quote=obligation.reference_text,
            confidence=obligation.confidence,
            metadata={},
        )
        _append_legacy_primitive(primitives, record)

    return primitives


def _legacy_record(
    *,
    primitive_source: str,
    primitive_id: str,
    contract_id: str,
    document: DocumentUpload | None,
    label: str,
    category: str,
    text_value: str,
    quote: str | None,
    confidence: float | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": primitive_id,
        "primitive_source": primitive_source,
        "contract_id": contract_id,
        "doc_upload_id": document.id if document else None,
        "document_title": document.title if document else None,
        "document_kind": document.document_kind if document else None,
        "period_label": _document_period_label(document),
        "category": category,
        "label": label,
        "text_value": _truncate_text(text_value, 800),
        "quote": _truncate_text(quote, 500) if quote else None,
        "confidence": confidence,
        "metadata": _compact_metadata(metadata),
    }


def _append_legacy_primitive(primitives: dict[str, list[dict]], record: dict[str, Any]) -> None:
    text_blob = " ".join(
        str(record.get(key) or "").lower()
        for key in ("category", "label", "text_value", "quote")
    )
    if _has_any(text_blob, ("cost", "fund", "eac", "burn", "variance", "rea", "budget")):
        primitives["financial"].append(record)
    if _has_any(text_blob, ("deliver", "cdrl", "acceptance", "quality", "defect", "rework", "reject")):
        primitives["deliverable"].append(record)
    if _has_any(text_blob, ("decision", "mod", "scope", "approval", "authority", "cor", "ko", "clause")):
        primitives["decisions"].append(record)
    if _has_any(text_blob, ("staff", "labor", "subcontract", "personnel", "program manager", "fte")):
        primitives["personnel"].append(record)
    if _has_any(text_blob, ("issue", "risk", "delay", "rfi", "aging", "regression", "slip", "late", "open")):
        primitives["issues"].append(record)
    if not any(record in rows for rows in primitives.values()):
        primitives["issues"].append(record)


def _has_any(text_blob: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text_blob for needle in needles)


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _compact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in ("severity", "status", "responsible_party", "days_open", "amount", "rating"):
        if key in metadata:
            compact[key] = metadata[key]
    return compact


def _document_period_label(document: DocumentUpload | None) -> str | None:
    if document is None:
        return None
    if document.report_period_start and document.report_period_end:
        return f"{document.report_period_start} to {document.report_period_end}"
    if document.report_period_start:
        return str(document.report_period_start)
    return document.created_at.date().isoformat()


def _load_legacy_cpars_exports(db: Session, contract_id: str) -> list[dict]:
    rows = db.scalars(
        select(KnowledgeSourceRecord)
        .where(KnowledgeSourceRecord.contract_id == contract_id)
        .order_by(KnowledgeSourceRecord.created_at)
    ).all()
    ratings = []
    rating_keys = {
        "quality": "quality_rating",
        "schedule": "schedule_rating",
        "cost_control": "cost_control_rating",
        "management": "management_rating",
        "small_business": "small_business_rating",
        "regulatory_compliance": "regulatory_compliance_rating",
        "overall": "overall_rating",
    }
    for row in rows:
        source_name = (row.source_name or "").lower()
        if "cpars" not in source_name and "cpars" not in (row.source_key or "").lower():
            continue
        raw = row.raw_json or {}
        for source_key, output_key in rating_keys.items():
            rating = raw.get(source_key) or raw.get(output_key)
            if rating:
                ratings.append(
                    {
                        "id": f"{row.id}:{source_key}",
                        "contract_id": contract_id,
                        "doc_upload_id": None,
                        "evaluation_period": raw.get("period") or raw.get("evaluation_period"),
                        "evaluation_date": raw.get("evaluation_date"),
                        output_key: rating,
                        "narrative": raw.get("narrative") or row.text,
                        "source_primitive_id": row.id,
                    }
                )
    return ratings


def _build_per_contract_prompt(
    contract: Contract,
    target_primitives: dict,
    cpars: list[dict],
    cohort: CohortDefinition,
    cohort_primitives: dict[str, dict],
) -> str:
    import json

    parts = [
        f"target.contract_id: {contract.id}",
        f"target.contract_number: {contract.contract_number}",
        f"cohort.definition: {json.dumps(cohort.match_criteria)}",
        f"cohort.N: {cohort.N}",
        "",
        "target.primitives:",
        json.dumps(target_primitives, default=str),
        "",
        "target.cpars:",
        json.dumps(cpars, default=str),
        "",
        "cohort.primitives (keyed by contract_id):",
        json.dumps(cohort_primitives, default=str),
    ]
    return "\n".join(parts)


def _compact_primitives(
    primitives: dict[str, list[dict]],
    *,
    limit_per_bucket: int,
) -> dict[str, list[dict]]:
    return {key: rows[:limit_per_bucket] for key, rows in primitives.items()}


def _build_cohort_prompt(
    contract_ids: list[str],
    per_contract_results: list[dict],
) -> str:
    import json

    return (
        f"cohort.N: {len(contract_ids)}\n\n"
        "per_contract_results:\n"
        + json.dumps(per_contract_results, default=str)
    )


def _insert_analysis_run(
    db: Session,
    run_id: str,
    run_type: str,
    target_contract_id: str | None,
    cohort: CohortDefinition | None = None,
    cohort_definition: dict | None = None,
    cohort_contract_ids: list[str] | None = None,
    status: str = "running",
    analyzed_doc_ids: list[str] | None = None,
) -> None:
    from sqlalchemy import text

    cd = cohort_definition or (_cohort_metadata(cohort) if cohort else None)
    cids = cohort_contract_ids or (cohort.contract_ids if cohort else None)
    db.execute(
        text(
            """
            INSERT INTO analysis_runs
                (id, run_type, target_contract_id, cohort_definition,
                 cohort_contract_ids, status, created_at, model, analyzed_doc_ids)
            VALUES (:id, :run_type, :target_contract_id, {cohort_definition},
                    {cohort_contract_ids}, :status, :created_at, :model, {analyzed_doc_ids})
            """
            .format(
                cohort_definition=_json_sql_value(db, "cohort_definition"),
                cohort_contract_ids=_json_sql_value(db, "cohort_contract_ids"),
                analyzed_doc_ids=_json_sql_value(db, "analyzed_doc_ids"),
            )
        ),
        {
            "id": run_id,
            "run_type": run_type,
            "target_contract_id": target_contract_id,
            "cohort_definition": json.dumps(cd) if cd else None,
            "cohort_contract_ids": json.dumps(cids) if cids else None,
            "status": status,
            "created_at": datetime.now(timezone.utc),
            "model": get_openai_llm_model(),
            "analyzed_doc_ids": json.dumps(analyzed_doc_ids) if analyzed_doc_ids else None,
        },
    )
    db.commit()


def _mark_analysis_run_running(db: Session, run_id: str) -> None:
    from sqlalchemy import text

    db.execute(
        text(
            """
            UPDATE analysis_runs
            SET status = 'running', model = :model
            WHERE id = :id
            """
        ),
        {"id": run_id, "model": get_openai_llm_model()},
    )
    db.commit()


def _complete_analysis_run(db: Session, run_id: str, result: dict) -> None:
    from sqlalchemy import text

    db.execute(
        text(
            """
            UPDATE analysis_runs
            SET status = 'complete', completed_at = :completed_at, result = {result}
            WHERE id = :id
            """
            .format(result=_json_sql_value(db, "result"))
        ),
        {
            "id": run_id,
            "completed_at": datetime.now(timezone.utc),
            "result": json.dumps(result),
        },
    )
    db.commit()


def _fail_analysis_run(db: Session, run_id: str, error: Exception) -> None:
    from sqlalchemy import text

    result = {"error": str(error)}
    db.execute(
        text(
            """
            UPDATE analysis_runs
            SET status = 'failed', completed_at = :completed_at, result = {result}
            WHERE id = :id
            """
            .format(result=_json_sql_value(db, "result"))
        ),
        {
            "id": run_id,
            "completed_at": datetime.now(timezone.utc),
            "result": json.dumps(result),
        },
    )
    db.commit()


def get_analysis_run(db: Session, run_id: str) -> dict | None:
    try:
        row = db.execute(
            text("SELECT * FROM analysis_runs WHERE id = :id"),
            {"id": run_id},
        ).mappings().first()
    except SQLAlchemyError:
        db.rollback()
        return None
    return _analysis_run_dict(row) if row else None


def get_latest_analysis_run(db: Session, contract_id: str) -> dict | None:
    try:
        row = db.execute(
            text(
                """
                SELECT * FROM analysis_runs
                WHERE target_contract_id = :contract_id AND run_type = 'per_contract'
                  AND status = 'complete'
                ORDER BY completed_at DESC, created_at DESC
                LIMIT 1
                """
            ),
            {"contract_id": contract_id},
        ).mappings().first()
    except SQLAlchemyError:
        db.rollback()
        return None
    return _analysis_run_dict(row) if row else None


def _analysis_run_dict(row: Any) -> dict:
    data = dict(row)
    for key in ("cohort_definition", "cohort_contract_ids", "result"):
        value = data.get(key)
        if isinstance(value, str):
            try:
                data[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return data


def _latest_primitive_update(db: Session, contract_id: str) -> datetime | None:
    from sqlalchemy import text

    return db.execute(
        text(
            """
            SELECT MAX(extracted_at)
            FROM primitive_extraction_runs
            WHERE contract_id = :contract_id
              AND status IN ('success', 'partial')
            """
        ),
        {"contract_id": contract_id},
    ).scalar_one_or_none()


def _analysis_run_newer_than(
    db: Session,
    contract_id: str,
    latest_primitive_update: datetime,
) -> dict | None:
    from sqlalchemy import text

    row = db.execute(
        text(
            """
            SELECT id, created_at, status
            FROM analysis_runs
            WHERE run_type = 'per_contract'
              AND target_contract_id = :contract_id
              AND created_at >= :latest_primitive_update
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {
            "contract_id": contract_id,
            "latest_primitive_update": latest_primitive_update,
        },
    ).mappings().first()
    return dict(row) if row else None


def _cohort_metadata(cohort: CohortDefinition | None) -> dict | None:
    if cohort is None:
        return None
    return {
        **cohort.match_criteria,
        "N": cohort.N,
        "low_confidence": cohort.low_confidence,
    }


def _tag_low_confidence(result: dict, cohort: CohortDefinition) -> dict:
    result["cohort_N"] = result.get("cohort_N", cohort.N)
    result["low_confidence"] = cohort.low_confidence
    result.setdefault("cohort_definition", _cohort_metadata(cohort) or {})
    axes = result.get("axes")
    if isinstance(axes, list):
        for axis in axes:
            if isinstance(axis, dict):
                axis["low_confidence"] = cohort.low_confidence
    return result


def _log_analysis_audit_event(
    db: Session,
    event_type: str,
    contract_id: str,
    *,
    document_upload_id: str | None = None,
    entity_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEvent(
            id=str(uuid.uuid4()),
            actor_id="feature-extractor",
            actor_role="service",
            event_type=event_type,
            entity_type="analysis_run",
            entity_id=entity_id or contract_id,
            contract_id=contract_id,
            document_upload_id=document_upload_id,
            metadata_json=metadata or {},
        )
    )


def _json_sql_value(db: Session, parameter_name: str) -> str:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        return f"CAST(:{parameter_name} AS JSON)"
    return f":{parameter_name}"


def _parse_json(text: str) -> dict:
    import json
    import re

    cleaned = re.sub(r"^```[a-z]*\n?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw": text}


def _openai_json_response(system: str, user: str) -> dict:
    api_key = get_openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for orchestrated performance analysis")
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError("openai package is required for orchestrated performance analysis") from error

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
    return _parse_json(content)


def _openai_tool_call(messages: list[dict], *, tools: list[dict]) -> Any:
    """Single tool-calling round. Returns the raw OpenAI ChatCompletion response."""
    api_key = get_openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for the cross-contract agent")
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError("openai package is required for the cross-contract agent") from error

    client = OpenAI(
        api_key=api_key,
        timeout=get_ai_request_timeout_seconds(),
        max_retries=get_ai_max_retries(),
    )
    return client.chat.completions.create(
        model=get_openai_llm_model(),
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )


def _load_primitives_for_docs(
    db: Session, contract_id: str, doc_ids: list[str]
) -> dict[str, list[dict]]:
    """Load primitives filtered to specific document upload IDs.

    Falls back to all primitives if the filtered result is empty (e.g., primitives tables
    not yet populated for these docs).
    """
    all_primitives = _load_primitives(db, contract_id)
    if not doc_ids:
        return all_primitives
    doc_id_set = set(doc_ids)
    filtered = {
        key: [row for row in rows if row.get("doc_upload_id") in doc_id_set]
        for key, rows in all_primitives.items()
    }
    if not any(filtered.values()):
        return all_primitives
    return filtered


def _build_incremental_prompt(
    contract: Contract,
    new_primitives: dict,
    cpars: list[dict],
    cohort: "CohortDefinition",
    prior_summary: str,
    prior_run_id: str,
    new_doc_ids: list[str],
) -> str:
    parts = [
        f"target.contract_id: {contract.id}",
        f"target.contract_number: {contract.contract_number}",
        f"cohort.N: {cohort.N}",
        "",
        f"prior_analysis.run_id: {prior_run_id}",
        "prior_analysis.summary:",
        prior_summary,
        "",
        f"new_documents.count: {len(new_doc_ids)}",
        "new_documents.primitives:",
        json.dumps(new_primitives, default=str),
        "",
        "target.cpars:",
        json.dumps(cpars, default=str),
    ]
    return "\n".join(parts)


def run_incremental_contract_analysis(
    db: Session,
    contract_id: str,
    new_doc_ids: list[str],
) -> dict[str, Any]:
    """Incremental analysis: compare new documents against the prior analysis result.

    If no prior completed analysis exists, runs a full baseline analysis instead.
    Always stores analyzed_doc_ids in the resulting analysis_runs row.
    """
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise ValueError(f"Contract {contract_id} not found")

    prior_run = get_latest_analysis_run(db, contract_id)
    cohort = build_cohort(db, contract_id)
    cpars = _load_cpars(db, contract_id)

    run_id = str(uuid.uuid4())

    if prior_run:
        prior_summary = (
            (prior_run.get("result") or {}).get("summary")
            or "No prior summary available."
        )
        prior_run_id = prior_run["id"]
        new_primitives = _load_primitives_for_docs(db, contract_id, new_doc_ids)
        new_primitives_compact = _compact_primitives(new_primitives, limit_per_bucket=45)
        prompt_user = _build_incremental_prompt(
            contract, new_primitives_compact, cpars, cohort,
            prior_summary, prior_run_id, new_doc_ids,
        )
        system_prompt = _INCREMENTAL_SYSTEM + "\n\n" + _AXES_DESCRIPTION
    else:
        all_primitives = _compact_primitives(_load_primitives(db, contract_id), limit_per_bucket=45)
        prompt_user = _build_per_contract_prompt(contract, all_primitives, cpars, cohort, {})
        system_prompt = _PER_CONTRACT_SYSTEM + "\n\n" + _AXES_DESCRIPTION
        prior_run_id = None

    _insert_analysis_run(
        db, run_id, "per_contract", contract_id, cohort,
        status="running", analyzed_doc_ids=new_doc_ids,
    )
    try:
        result_json = _openai_json_response(system_prompt, prompt_user)
    except Exception as exc:
        _fail_analysis_run(db, run_id, exc)
        raise
    result_json = _tag_low_confidence(result_json, cohort)
    result_json["new_doc_ids"] = new_doc_ids
    if prior_run_id:
        result_json["prior_run_id"] = prior_run_id
    _complete_analysis_run(db, run_id, result_json)
    return {"id": run_id, "status": "complete", "result": result_json}


def get_analysis_log(db: Session, contract_id: str, limit: int = 20) -> list[dict]:
    """Return per_contract analysis runs for a contract, newest first."""
    try:
        rows = db.execute(
            text(
                """
                SELECT * FROM analysis_runs
                WHERE target_contract_id = :cid
                  AND run_type IN ('per_contract', 'cross_contract')
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"cid": contract_id, "limit": limit},
        ).mappings().all()
    except SQLAlchemyError:
        db.rollback()
        return []
    return [_analysis_run_dict(row) for row in rows]
