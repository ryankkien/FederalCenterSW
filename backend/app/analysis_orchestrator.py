from __future__ import annotations

"""Orchestrate per-contract and cohort contract performance analysis.

Loads five primitive tables (deliverable, financial, decisions, issue, personnel)
plus CPARS ratings, assembles them into the analysis prompt, calls OpenAI, and
stores the JSON result in analysis_runs.
"""

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
from app.models import Contract

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

    run_id = str(uuid.uuid4())
    _insert_analysis_run(db, run_id, "per_contract", contract_id, cohort)

    result_json = _openai_json_response(
        _PER_CONTRACT_SYSTEM + "\n\n" + _AXES_DESCRIPTION,
        prompt_user,
    )

    _complete_analysis_run(db, run_id, result_json)
    return {"id": run_id, "status": "complete", "result": result_json}


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
) -> None:
    from sqlalchemy import text

    cd = cohort_definition or (cohort.match_criteria if cohort else None)
    cids = cohort_contract_ids or (cohort.contract_ids if cohort else None)

    import json
    db.execute(
        text(
            """
            INSERT INTO analysis_runs
                (id, run_type, target_contract_id, cohort_definition,
                 cohort_contract_ids, status, created_at, model)
            VALUES (:id, :run_type, :target_contract_id, :cohort_definition::json,
                    :cohort_contract_ids::json, 'running', :created_at, :model)
            """
        ),
        {
            "id": run_id,
            "run_type": run_type,
            "target_contract_id": target_contract_id,
            "cohort_definition": json.dumps(cd) if cd else None,
            "cohort_contract_ids": json.dumps(cids) if cids else None,
            "created_at": datetime.now(timezone.utc),
            "model": get_openai_llm_model(),
        },
    )
    db.commit()


def _complete_analysis_run(db: Session, run_id: str, result: dict) -> None:
    from sqlalchemy import text
    import json

    db.execute(
        text(
            """
            UPDATE analysis_runs
            SET status = 'complete', completed_at = :completed_at, result = :result::json
            WHERE id = :id
            """
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
