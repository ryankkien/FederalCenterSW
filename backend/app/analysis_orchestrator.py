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

from sqlalchemy.orm import Session

from app.cohort_builder import CohortDefinition, build_cohort
from app.config import (
    get_ai_max_retries,
    get_ai_request_timeout_seconds,
    get_openai_api_key,
    get_openai_llm_model,
)
from app.models import AuditEvent, Contract

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
    target_primitives = _load_primitives(db, contract_id)
    cohort_primitives = {cid: _load_primitives(db, cid) for cid in cohort.contract_ids}
    cpars = _load_cpars(db, contract_id)

    prompt_user = _build_per_contract_prompt(
        contract, target_primitives, cpars, cohort, cohort_primitives
    )

    if run_id is None:
        run_id = str(uuid.uuid4())
        _insert_analysis_run(db, run_id, "per_contract", contract_id, cohort, status="running")
    else:
        _mark_analysis_run_running(db, run_id)

    result_json = _openai_json_response(
        _PER_CONTRACT_SYSTEM + "\n\n" + _AXES_DESCRIPTION,
        prompt_user,
    )
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
        primitives = _load_primitives(db, cid)
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

    result_json = _openai_json_response(_COHORT_SYSTEM, prompt_user)

    _complete_analysis_run(db, run_id, result_json)
    return {"id": run_id, "status": "complete", "result": result_json}


def _load_primitives(db: Session, contract_id: str) -> dict[str, list[dict]]:
    from sqlalchemy import text

    tables = {
        "deliverable": "contract_primitives_deliverable",
        "financial": "contract_primitives_financial",
        "decisions": "contract_primitives_decisions",
        "issues": "contract_primitives_issues",
        "personnel": "contract_primitives_personnel",
    }
    result = {}
    for key, table in tables.items():
        rows = db.execute(
            text(f"SELECT * FROM {table} WHERE contract_id = :cid ORDER BY period_label"),
            {"cid": contract_id},
        ).mappings().all()
        result[key] = [dict(r) for r in rows]
    return result


def _load_cpars(db: Session, contract_id: str) -> list[dict]:
    from sqlalchemy import text

    rows = db.execute(
        text(
            "SELECT * FROM cpars_ratings WHERE contract_id = :cid ORDER BY evaluation_date"
        ),
        {"cid": contract_id},
    ).mappings().all()
    return [dict(r) for r in rows]


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
) -> None:
    from sqlalchemy import text

    cd = cohort_definition or (_cohort_metadata(cohort) if cohort else None)
    cids = cohort_contract_ids or (cohort.contract_ids if cohort else None)
    db.execute(
        text(
            """
            INSERT INTO analysis_runs
                (id, run_type, target_contract_id, cohort_definition,
                 cohort_contract_ids, status, created_at, model)
            VALUES (:id, :run_type, :target_contract_id, {cohort_definition},
                    {cohort_contract_ids}, :status, :created_at, :model)
            """
            .format(
                cohort_definition=_json_sql_value(db, "cohort_definition"),
                cohort_contract_ids=_json_sql_value(db, "cohort_contract_ids"),
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
    from sqlalchemy import text

    row = db.execute(
        text("SELECT * FROM analysis_runs WHERE id = :id"),
        {"id": run_id},
    ).mappings().first()
    return dict(row) if row else None


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
