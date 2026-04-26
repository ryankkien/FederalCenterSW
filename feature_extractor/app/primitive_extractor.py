"""Extract structured primitives (deliverable, financial, decisions, issues, personnel)
from federal contract documents using an LLM.

Each primitive type is extracted by a targeted prompt against the full document text
(or summary if text exceeds token limits). Results are written to the corresponding
contract_primitives_* tables and a primitive_extraction_runs audit record.
"""

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any

import psycopg

from app.models import LLMClient

# Document classifications → which primitive types to extract
_CLASSIFICATION_MAP: dict[str, list[str]] = {
    "weekly_report": ["deliverable", "financial", "issue", "personnel"],
    "monthly_report": ["deliverable", "financial", "issue", "personnel"],
    "source_contract": ["deliverable", "decisions"],
    "task_order": ["deliverable", "decisions"],
    "modification": ["decisions"],
    "gao_oig_report": ["issue"],
    "cpars": ["cpars"],
}

_PERIOD_SYSTEM = """You are a federal contract document analyst. Given document text, identify the
reporting period it covers. Return a JSON object with a single key "period_label" whose value is
a string in YYYY-MM format for monthly periods or YYYY-QN format for quarterly periods
(e.g. "2024-03" or "2024-Q1"). If the period cannot be determined, return {"period_label": null}.
Output only the JSON object, no preamble."""

_DELIVERABLE_SYSTEM = """You are a federal contract document analyst extracting deliverable records.
Given document text, extract every deliverable, CDRL item, or data item mentioned.

Return a JSON object with key "results" containing an array. Each element:
{
  "deliverable_name": "string or null",
  "cdrl_item": "e.g. A001, B002, or null",
  "planned_due_date": "YYYY-MM-DD or null",
  "actual_delivery_date": "YYYY-MM-DD or null",
  "status": "on_time | late | pending | rejected | null",
  "acceptance_status": "accepted | rejected | pending | null",
  "days_late": integer_or_null
}

If no deliverables are found, return {"results": []}.
Output only the JSON object, no preamble or markdown."""

_FINANCIAL_SYSTEM = """You are a federal contract document analyst extracting financial data.
Given document text, extract earned value management (EVM) and cost/schedule metrics for each
reporting period mentioned.

Return a JSON object with key "results" containing an array. Each element:
{
  "period_end_date": "YYYY-MM-DD or null",
  "planned_value": dollar_number_or_null,
  "earned_value": dollar_number_or_null,
  "actual_cost": dollar_number_or_null,
  "budget_at_completion": dollar_number_or_null,
  "estimate_at_completion": dollar_number_or_null,
  "estimate_to_complete": dollar_number_or_null,
  "cost_variance": dollar_number_or_null,
  "schedule_variance": dollar_number_or_null,
  "cpi": decimal_or_null,
  "spi": decimal_or_null,
  "percent_complete": decimal_0_to_100_or_null,
  "cumulative_obligations": dollar_number_or_null
}

Extract numeric values as plain numbers (no $ signs or commas).
If no financial data is found, return {"results": []}.
Output only the JSON object, no preamble or markdown."""

_DECISIONS_SYSTEM = """You are a federal contract document analyst extracting contract decisions
and modifications.

Return a JSON object with key "results" containing an array. Each element:
{
  "decision_type": "modification | approval | waiver | deviation | direction | null",
  "mod_number": "e.g. P00001 or null",
  "mod_reason": "string or null",
  "value_change": dollar_number_or_null,
  "pop_change_days": integer_or_null,
  "scope_change_description": "string or null",
  "decision_date": "YYYY-MM-DD or null",
  "deciding_party": "string or null"
}

If no decisions are found, return {"results": []}.
Output only the JSON object, no preamble or markdown."""

_ISSUE_SYSTEM = """You are a federal contract document analyst extracting issues, risks, and
action items from contract performance reports.

Return a JSON object with key "results" containing an array. Each element:
{
  "issue_id": "string identifier if present, else null",
  "category": "schedule_risk | cost_risk | technical | staffing | gfe_delay | compliance | quality | scope | other | null",
  "description": "concise description of the issue",
  "severity": "high | medium | low | null",
  "responsible_party": "contractor | government | third_party | null",
  "date_opened": "YYYY-MM-DD or null",
  "date_resolved": "YYYY-MM-DD or null",
  "status": "open | resolved | escalated | null"
}

GFE = government-furnished equipment/information; classify as gfe_delay if relevant.
If no issues are found, return {"results": []}.
Output only the JSON object, no preamble or markdown."""

_PERSONNEL_SYSTEM = """You are a federal contract document analyst extracting personnel and
staffing information from contract documents.

Return a JSON object with key "results" containing an array. Each element:
{
  "role": "PM | deputy_PM | COR | ACOR | key_person | labor_category | subcontractor | other | null",
  "name": "person name or null",
  "labor_category": "string or null",
  "fte_planned": decimal_or_null,
  "fte_actual": decimal_or_null,
  "staffing_gap_flag": true_or_false
}

If no personnel data is found, return {"results": []}.
Output only the JSON object, no preamble or markdown."""

_CPARS_SYSTEM = """You are a federal contract document analyst extracting CPARS (Contractor
Performance Assessment Reporting System) ratings.

Return a JSON object with key "results" containing an array. Each element:
{
  "evaluation_period": "e.g. FY2023 or 2023-01 to 2023-12 or null",
  "evaluation_date": "YYYY-MM-DD or null",
  "quality_rating": "Exceptional | Very Good | Satisfactory | Marginal | Unsatisfactory | null",
  "schedule_rating": "Exceptional | Very Good | Satisfactory | Marginal | Unsatisfactory | null",
  "cost_control_rating": "Exceptional | Very Good | Satisfactory | Marginal | Unsatisfactory | null",
  "management_rating": "Exceptional | Very Good | Satisfactory | Marginal | Unsatisfactory | null",
  "small_business_rating": "Exceptional | Very Good | Satisfactory | Marginal | Unsatisfactory | Not Applicable | null",
  "regulatory_compliance_rating": "Exceptional | Very Good | Satisfactory | Marginal | Unsatisfactory | null",
  "overall_rating": "Exceptional | Very Good | Satisfactory | Marginal | Unsatisfactory | null",
  "narrative": "brief summary of key narrative themes, or null"
}

If no CPARS ratings are found, return {"results": []}.
Output only the JSON object, no preamble or markdown."""

_SYSTEM_MAP = {
    "deliverable": _DELIVERABLE_SYSTEM,
    "financial": _FINANCIAL_SYSTEM,
    "decisions": _DECISIONS_SYSTEM,
    "issue": _ISSUE_SYSTEM,
    "personnel": _PERSONNEL_SYSTEM,
    "cpars": _CPARS_SYSTEM,
}

# Approximate character limit before switching to summary
_TEXT_CHAR_LIMIT = 60_000


def run(
    conn: psycopg.Connection,
    doc_id: str,
    contract_id: str | None,
    doc_classification: str,
    pages: list[str],
    final_summary: str,
    llm: LLMClient,
) -> tuple[str | None, dict[str, int]]:
    """Extract primitives for a document and write to the DB.

    Returns (run_id, counts) where counts maps primitive_type → rows inserted.
    """
    primitive_types = _CLASSIFICATION_MAP.get(doc_classification, [])
    if not primitive_types:
        return None, {}

    full_text = "\n\n".join(pages)
    document_text = full_text if len(full_text) <= _TEXT_CHAR_LIMIT else final_summary

    period_label = _extract_period_label(document_text, llm)

    run_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO primitive_extraction_runs
                (id, contract_id, doc_upload_id, period_label, extracted_at, model, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (run_id, contract_id, doc_id, period_label,
             datetime.now(timezone.utc), llm.model_name, "pending"),
        )
    conn.commit()

    counts: dict[str, int] = {}
    all_succeeded = True

    for ptype in primitive_types:
        try:
            n = _extract_and_store(conn, run_id, doc_id, contract_id, ptype, document_text, llm)
            counts[ptype] = n
        except Exception:
            all_succeeded = False
            counts[ptype] = 0

    final_status = "success" if all_succeeded else "partial"
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE primitive_extraction_runs SET status = %s, extracted_at = %s WHERE id = %s",
            (final_status, datetime.now(timezone.utc), run_id),
        )
    conn.commit()

    return run_id, counts


def _extract_period_label(text: str, llm: LLMClient) -> str | None:
    try:
        result = llm.complete_json(
            system=_PERIOD_SYSTEM,
            user=f"Document text:\n\n{text[:8000]}",
            max_tokens=64,
        )
        return result.get("period_label")
    except Exception:
        return None


def _extract_and_store(
    conn: psycopg.Connection,
    run_id: str,
    doc_id: str,
    contract_id: str | None,
    primitive_type: str,
    text: str,
    llm: LLMClient,
) -> int:
    system = _SYSTEM_MAP[primitive_type]
    result = llm.complete_json(
        system=system,
        user=f"Document text:\n\n{text}",
        max_tokens=4096,
    )
    items = result.get("results", [])
    if not items:
        return 0

    if primitive_type == "deliverable":
        return _store_deliverables(conn, run_id, doc_id, contract_id, items)
    if primitive_type == "financial":
        return _store_financial(conn, run_id, doc_id, contract_id, items)
    if primitive_type == "decisions":
        return _store_decisions(conn, run_id, doc_id, contract_id, items)
    if primitive_type == "issue":
        return _store_issues(conn, run_id, doc_id, contract_id, items)
    if primitive_type == "personnel":
        return _store_personnel(conn, run_id, doc_id, contract_id, items)
    if primitive_type == "cpars":
        return _store_cpars(conn, doc_id, contract_id, items)
    return 0


def _parse_date(val: Any) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None


def _parse_numeric(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _store_deliverables(
    conn: psycopg.Connection, run_id: str, doc_id: str, contract_id: str | None, items: list[dict]
) -> int:
    rows = []
    for item in items:
        rows.append((
            str(uuid.uuid4()), run_id, doc_id,
            json.dumps([doc_id]),
            None,  # period_label set on run, not repeated here
            item.get("deliverable_name"),
            item.get("cdrl_item"),
            _parse_date(item.get("planned_due_date")),
            _parse_date(item.get("actual_delivery_date")),
            item.get("status"),
            item.get("acceptance_status"),
            item.get("days_late"),
        ))
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO contract_primitives_deliverable
                (id, extraction_run_id, contract_id, source_doc_ids, period_label,
                 deliverable_name, cdrl_item, planned_due_date, actual_delivery_date,
                 status, acceptance_status, days_late)
            VALUES (%s, %s, %s, %s::json, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def _store_financial(
    conn: psycopg.Connection, run_id: str, doc_id: str, contract_id: str | None, items: list[dict]
) -> int:
    rows = []
    for item in items:
        rows.append((
            str(uuid.uuid4()), run_id, doc_id,
            json.dumps([doc_id]),
            None,
            _parse_date(item.get("period_end_date")),
            _parse_numeric(item.get("planned_value")),
            _parse_numeric(item.get("earned_value")),
            _parse_numeric(item.get("actual_cost")),
            _parse_numeric(item.get("budget_at_completion")),
            _parse_numeric(item.get("estimate_at_completion")),
            _parse_numeric(item.get("estimate_to_complete")),
            _parse_numeric(item.get("cost_variance")),
            _parse_numeric(item.get("schedule_variance")),
            _parse_numeric(item.get("cpi")),
            _parse_numeric(item.get("spi")),
            _parse_numeric(item.get("percent_complete")),
            _parse_numeric(item.get("cumulative_obligations")),
        ))
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO contract_primitives_financial
                (id, extraction_run_id, contract_id, source_doc_ids, period_label,
                 period_end_date, planned_value, earned_value, actual_cost,
                 budget_at_completion, estimate_at_completion, estimate_to_complete,
                 cost_variance, schedule_variance, cpi, spi,
                 percent_complete, cumulative_obligations)
            VALUES (%s, %s, %s, %s::json, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def _store_decisions(
    conn: psycopg.Connection, run_id: str, doc_id: str, contract_id: str | None, items: list[dict]
) -> int:
    rows = []
    for item in items:
        rows.append((
            str(uuid.uuid4()), run_id, doc_id,
            json.dumps([doc_id]),
            None,
            item.get("decision_type"),
            item.get("mod_number"),
            item.get("mod_reason"),
            _parse_numeric(item.get("value_change")),
            item.get("pop_change_days"),
            item.get("scope_change_description"),
            _parse_date(item.get("decision_date")),
            item.get("deciding_party"),
        ))
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO contract_primitives_decisions
                (id, extraction_run_id, contract_id, source_doc_ids, period_label,
                 decision_type, mod_number, mod_reason, value_change,
                 pop_change_days, scope_change_description, decision_date, deciding_party)
            VALUES (%s, %s, %s, %s::json, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def _store_issues(
    conn: psycopg.Connection, run_id: str, doc_id: str, contract_id: str | None, items: list[dict]
) -> int:
    rows = []
    for item in items:
        rows.append((
            str(uuid.uuid4()), run_id, doc_id,
            json.dumps([doc_id]),
            None,
            item.get("issue_id"),
            item.get("category"),
            item.get("description"),
            item.get("severity"),
            item.get("responsible_party"),
            _parse_date(item.get("date_opened")),
            _parse_date(item.get("date_resolved")),
            item.get("status"),
            False,
        ))
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO contract_primitives_issues
                (id, extraction_run_id, contract_id, source_doc_ids, period_label,
                 issue_id, category, description, severity, responsible_party,
                 date_opened, date_resolved, status, recurrence_flag)
            VALUES (%s, %s, %s, %s::json, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def _store_personnel(
    conn: psycopg.Connection, run_id: str, doc_id: str, contract_id: str | None, items: list[dict]
) -> int:
    rows = []
    for item in items:
        rows.append((
            str(uuid.uuid4()), run_id, doc_id,
            json.dumps([doc_id]),
            None,
            item.get("role"),
            item.get("name"),
            item.get("labor_category"),
            _parse_numeric(item.get("fte_planned")),
            _parse_numeric(item.get("fte_actual")),
            bool(item.get("staffing_gap_flag", False)),
        ))
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO contract_primitives_personnel
                (id, extraction_run_id, contract_id, source_doc_ids, period_label,
                 role, name, labor_category, fte_planned, fte_actual, staffing_gap_flag)
            VALUES (%s, %s, %s, %s::json, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def _store_cpars(
    conn: psycopg.Connection, doc_id: str, contract_id: str | None, items: list[dict]
) -> int:
    rows = []
    for item in items:
        rows.append((
            str(uuid.uuid4()), contract_id, doc_id,
            item.get("evaluation_period"),
            _parse_date(item.get("evaluation_date")),
            item.get("quality_rating"),
            item.get("schedule_rating"),
            item.get("cost_control_rating"),
            item.get("management_rating"),
            item.get("small_business_rating"),
            item.get("regulatory_compliance_rating"),
            item.get("overall_rating"),
            item.get("narrative"),
        ))
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO cpars_ratings
                (id, contract_id, doc_upload_id, evaluation_period, evaluation_date,
                 quality_rating, schedule_rating, cost_control_rating, management_rating,
                 small_business_rating, regulatory_compliance_rating, overall_rating, narrative)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    conn.commit()
    return len(rows)
