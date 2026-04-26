"""Cross-contract insight agent.

Runs after a per-contract incremental analysis. The agent uses OpenAI tool calling
to discover related contracts/documents (via vector search and similarity links),
prunes candidates, and submits one insight that's persisted as a ContractHypothesis
row (which the portfolio themes endpoint surfaces as a theme).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.analysis_orchestrator import (
    _complete_analysis_run,
    _fail_analysis_run,
    _insert_analysis_run,
    _json_sql_value,
    _openai_tool_call,
    get_latest_analysis_run,
)
from app.embedding_search import search_similar_chunks
from app.models import Contract, ContractHypothesis


_CROSS_CONTRACT_SYSTEM = """ROLE You are a federal-contract pattern analyst. A target \
contract has just had its analysis updated with new documents. Your job is to find ONE \
high-value cross-contract insight: a pattern the target shares with related contracts \
that a CO/COR would act on.

PROCESS
1. Review the target's latest summary and recent changes (provided in the user message).
2. Use list_similar_contracts and vector_search_chunks to gather candidates.
3. PRUNE aggressively. Investigate at most 5 contracts in depth via fetch_contract_brief.
4. Form ONE insight that ties the target to >= 2 related contracts with concrete evidence.
5. Call submit_insight exactly once with quotes drawn from the briefs/snippets you saw.

HARD RULES
- Cite contract_ids and document_upload_ids you actually retrieved. No fabrication.
- If no genuine cross-contract pattern emerges, do not call submit_insight; respond
  with a short message explaining why and stop.
- Severity: critical = active risk in >= 3 contracts, watch = pattern in 2 contracts,
  healthy = success pattern worth replicating.
"""


TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "vector_search_chunks",
            "description": (
                "Semantic search over document chunks across the portfolio. "
                "Returns up to k matching chunks with snippet, contract_number, "
                "and cosine distance (lower = more similar)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "minimum": 1, "maximum": 25},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_similar_contracts",
            "description": (
                "Fetch contracts already linked to the target via "
                "contract_similarity_links plus contracts in the same PSC bucket."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_contract_brief",
            "description": (
                "Concise brief on a contract: number, title, PSC, NAICS, agency, "
                "obligated value, latest analysis summary, and 5 most recent open findings."
            ),
            "parameters": {
                "type": "object",
                "properties": {"contract_id": {"type": "string"}},
                "required": ["contract_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_insight",
            "description": (
                "Submit the final cross-contract insight and terminate. Call exactly once. "
                "Only include related_contract_ids you actually investigated."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 220},
                    "narrative": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "watch", "healthy"],
                    },
                    "hypothesis_key": {
                        "type": "string",
                        "description": "Short slug, <=140 chars",
                    },
                    "related_contract_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "contract_id": {"type": "string"},
                                "document_upload_id": {"type": "string"},
                                "quote": {"type": "string"},
                            },
                            "required": ["contract_id", "quote"],
                        },
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                },
                "required": [
                    "title",
                    "narrative",
                    "severity",
                    "hypothesis_key",
                    "related_contract_ids",
                ],
            },
        },
    },
]


def _build_seed_message(contract: Contract, latest_run: Optional[dict]) -> str:
    summary = ""
    changes: list[dict] = []
    if latest_run and isinstance(latest_run.get("result"), dict):
        result = latest_run["result"]
        summary = result.get("summary") or ""
        raw_changes = result.get("changes")
        if isinstance(raw_changes, list):
            changes = raw_changes
    parts = [
        f"target.contract_id: {contract.id}",
        f"target.contract_number: {contract.contract_number}",
        f"target.title: {contract.title}",
        f"target.psc: {contract.psc_code or '(none)'}",
        f"target.naics: {contract.naics_code or '(none)'}",
        f"target.agency: {contract.agency_name or '(none)'}",
        "",
        "target.latest_analysis_summary:",
        summary or "(no prior analysis available)",
    ]
    if changes:
        parts.append("")
        parts.append("target.recent_changes:")
        parts.append(json.dumps(changes, default=str)[:2000])
    return "\n".join(parts)


def _list_similar_contracts(
    db: Session,
    target_contract_id: str,
    *,
    visible_ids: Sequence[str],
    limit: int,
) -> list[dict]:
    if not visible_ids:
        return []
    visible_set = set(visible_ids)
    target = db.get(Contract, target_contract_id)
    if target is None:
        return []

    rows = db.execute(
        text(
            """
            SELECT source_contract_id, target_contract_id, link_type, score,
                   summary, metadata_json
            FROM contract_similarity_links
            WHERE source_contract_id = :cid OR target_contract_id = :cid
            ORDER BY score DESC NULLS LAST
            LIMIT 100
            """
        ),
        {"cid": target_contract_id},
    ).mappings().all()

    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        other = (
            row["target_contract_id"]
            if row["source_contract_id"] == target_contract_id
            else row["source_contract_id"]
        )
        if other in seen or other == target_contract_id or other not in visible_set:
            continue
        meta = row["metadata_json"]
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        shared_tags = (meta or {}).get("shared_tags") or []
        contract = db.get(Contract, other)
        if contract is None:
            continue
        seen.add(other)
        out.append(
            {
                "contract_id": other,
                "contract_number": contract.contract_number,
                "title": contract.title,
                "psc_code": contract.psc_code,
                "naics_code": contract.naics_code,
                "link_type": row["link_type"],
                "score": float(row["score"]) if row["score"] is not None else None,
                "shared_tags": shared_tags,
                "source": "similarity_link",
            }
        )
        if len(out) >= limit:
            return out

    # Augment with same-PSC peers if we still have room
    if len(out) < limit and target.psc_code:
        psc_prefix = target.psc_code[:1]
        peer_rows = db.execute(
            text(
                """
                SELECT id, contract_number, title, psc_code, naics_code, agency_name
                FROM contracts
                WHERE id <> :cid
                  AND psc_code LIKE :prefix
                ORDER BY contract_number ASC
                LIMIT 50
                """
            ),
            {"cid": target_contract_id, "prefix": f"{psc_prefix}%"},
        ).mappings().all()
        for row in peer_rows:
            cid = row["id"]
            if cid in seen or cid not in visible_set:
                continue
            seen.add(cid)
            out.append(
                {
                    "contract_id": cid,
                    "contract_number": row["contract_number"],
                    "title": row["title"],
                    "psc_code": row["psc_code"],
                    "naics_code": row["naics_code"],
                    "link_type": "psc_peer",
                    "score": None,
                    "shared_tags": [],
                    "source": "psc_bucket",
                }
            )
            if len(out) >= limit:
                break

    return out


def _fetch_contract_brief(
    db: Session,
    contract_id: str,
    *,
    visible_ids: Sequence[str],
) -> dict:
    if visible_ids and contract_id not in set(visible_ids):
        return {"error": "contract_not_visible"}
    contract = db.get(Contract, contract_id)
    if contract is None:
        return {"error": "contract_not_found"}

    latest = get_latest_analysis_run(db, contract_id)
    summary = None
    if latest and isinstance(latest.get("result"), dict):
        summary = latest["result"].get("summary")

    findings = []
    try:
        rows = db.execute(
            text(
                """
                SELECT id, title, summary, severity, finding_type, document_upload_id,
                       created_at
                FROM regression_findings
                WHERE contract_id = :cid AND status = 'open'
                ORDER BY created_at DESC
                LIMIT 5
                """
            ),
            {"cid": contract_id},
        ).mappings().all()
        findings = [dict(r) for r in rows]
    except SQLAlchemyError:
        db.rollback()

    metadata = contract.metadata_json if isinstance(contract.metadata_json, dict) else {}
    return {
        "contract_id": contract.id,
        "contract_number": contract.contract_number,
        "title": contract.title,
        "psc_code": contract.psc_code,
        "naics_code": contract.naics_code,
        "agency_name": contract.agency_name,
        "obligated_value": metadata.get("obligated_value"),
        "latest_analysis_summary": summary,
        "recent_open_findings": findings,
    }


def _persist_insight(
    db: Session,
    target_contract_id: str,
    run_id: str,
    payload: dict,
) -> str:
    base_key = (payload.get("hypothesis_key") or "cross-contract-insight")[:140]
    base_key = re.sub(r"[^a-zA-Z0-9_-]+", "-", base_key).strip("-") or "cross-contract-insight"
    candidates = [base_key, f"{base_key}-{datetime.now(timezone.utc):%Y%m%d}"]
    candidates.append(f"{base_key}-{run_id[:6]}")

    last_error: Optional[Exception] = None
    for key in candidates:
        hyp_id = str(uuid.uuid4())
        hypothesis = ContractHypothesis(
            id=hyp_id,
            contract_id=target_contract_id,
            hypothesis_key=key[:140],
            title=(payload.get("title") or "Cross-contract insight")[:240],
            narrative=payload.get("narrative") or "",
            status="proposed",
            confidence=payload.get("confidence"),
            created_by_id="cross-contract-agent",
            metadata_json={
                "source": "cross_contract_agent",
                "severity": payload.get("severity"),
                "related_contract_ids": payload.get("related_contract_ids", []),
                "evidence": payload.get("evidence", []),
                "analysis_run_id": run_id,
            },
        )
        try:
            db.add(hypothesis)
            db.commit()
            return hyp_id
        except IntegrityError as exc:
            db.rollback()
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to persist cross-contract insight")


def _dispatch_tool(
    name: str,
    args: dict,
    *,
    db: Session,
    target_contract_id: str,
    visible_contract_ids: Sequence[str],
    investigated: set[str],
) -> Any:
    if name == "vector_search_chunks":
        query = (args.get("query") or "").strip()
        if not query:
            return {"error": "empty_query"}
        k = int(args.get("k") or 10)
        rows = search_similar_chunks(
            db,
            query,
            k=max(1, min(25, k)),
            exclude_contract_id=target_contract_id,
            visible_contract_ids=visible_contract_ids,
        )
        for r in rows:
            cid = r.get("contract_id")
            if cid:
                investigated.add(cid)
        return {"results": rows}

    if name == "list_similar_contracts":
        limit = int(args.get("limit") or 15)
        rows = _list_similar_contracts(
            db,
            target_contract_id,
            visible_ids=visible_contract_ids,
            limit=max(1, min(30, limit)),
        )
        for r in rows:
            investigated.add(r["contract_id"])
        return {"results": rows}

    if name == "fetch_contract_brief":
        cid = (args.get("contract_id") or "").strip()
        if not cid:
            return {"error": "missing_contract_id"}
        brief = _fetch_contract_brief(db, cid, visible_ids=visible_contract_ids)
        if "error" not in brief:
            investigated.add(cid)
        return brief

    return {"error": f"unknown_tool:{name}"}


def _summarize_tool_calls(tool_calls) -> list[dict]:
    summary = []
    for call in tool_calls or []:
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {"_raw": call.function.arguments}
        summary.append({"name": call.function.name, "args": args})
    return summary


def run_cross_contract_agent(
    db: Session,
    target_contract_id: str,
    *,
    visible_contract_ids: Iterable[str],
    triggering_run_id: Optional[str] = None,
    max_iterations: int = 6,
) -> dict:
    """Run the cross-contract agent for `target_contract_id` and persist results."""
    target = db.get(Contract, target_contract_id)
    if target is None:
        raise ValueError(f"Contract {target_contract_id} not found")

    visible_list: list[str] = list(visible_contract_ids)
    latest = get_latest_analysis_run(db, target_contract_id)
    seed = _build_seed_message(target, latest)

    run_id = str(uuid.uuid4())
    metadata = {"triggering_run_id": triggering_run_id} if triggering_run_id else None
    _insert_analysis_run(
        db,
        run_id,
        "cross_contract",
        target_contract_id,
        cohort_definition=metadata,
        status="running",
    )

    messages: list[dict] = [
        {"role": "system", "content": _CROSS_CONTRACT_SYSTEM},
        {"role": "user", "content": seed},
    ]
    transcript: list[dict] = []
    investigated: set[str] = set()
    insight_payload: Optional[dict] = None

    try:
        for _ in range(max_iterations):
            response = _openai_tool_call(messages, tools=TOOLS)
            choice = response.choices[0].message
            messages.append(choice.model_dump(exclude_none=True))
            transcript.append(
                {
                    "role": "assistant",
                    "content": choice.content,
                    "tool_calls": _summarize_tool_calls(getattr(choice, "tool_calls", None)),
                }
            )

            tool_calls = getattr(choice, "tool_calls", None) or []
            if not tool_calls:
                break

            for call in tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                if name == "submit_insight":
                    insight_payload = args
                    tool_result: Any = {"ok": True}
                else:
                    tool_result = _dispatch_tool(
                        name,
                        args,
                        db=db,
                        target_contract_id=target_contract_id,
                        visible_contract_ids=visible_list,
                        investigated=investigated,
                    )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(tool_result, default=str)[:8000],
                    }
                )
                transcript.append(
                    {
                        "role": "tool",
                        "name": name,
                        "args": args,
                        "result_preview": str(tool_result)[:400],
                    }
                )

            if insight_payload is not None:
                break
    except Exception as exc:
        _fail_analysis_run(db, run_id, exc)
        raise

    cohort_ids = sorted(investigated)
    if cohort_ids:
        db.execute(
            text(
                "UPDATE analysis_runs SET cohort_contract_ids = "
                + _json_sql_value(db, "cids")
                + " WHERE id = :id"
            ),
            {"id": run_id, "cids": json.dumps(cohort_ids)},
        )
        db.commit()

    if insight_payload is not None:
        try:
            hyp_id = _persist_insight(db, target_contract_id, run_id, insight_payload)
        except Exception as exc:
            _fail_analysis_run(db, run_id, exc)
            raise
        result = {
            "status": "complete",
            "insight_hypothesis_id": hyp_id,
            "investigated_contract_ids": cohort_ids,
            "submitted": insight_payload,
            "transcript": transcript,
        }
    else:
        result = {
            "status": "no_insight",
            "investigated_contract_ids": cohort_ids,
            "transcript": transcript,
        }

    _complete_analysis_run(db, run_id, result)
    return {"id": run_id, **result}
