"""Build cohort definitions for contract performance analysis.

Given a target contract, finds comparable contracts using NAICS prefix, contract type,
obligated value band, POP length band, agency, and competition type.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Contract

_VALUE_BAND_PCT = 0.50    # ±50% of target obligated value
_POP_BAND_PCT = 0.25      # ±25% of target POP length in days
_NAICS_PREFIX_LEN = 4     # industry-group level (4-digit prefix match)
_LOW_CONFIDENCE_THRESHOLD = 20


@dataclass
class CohortDefinition:
    target_contract_id: str
    match_criteria: dict
    contract_ids: list[str]
    N: int
    low_confidence: bool


def build_cohort(db: Session, target_contract_id: str) -> CohortDefinition:
    """Find contracts comparable to the target and return a cohort definition."""
    target = db.get(Contract, target_contract_id)
    if target is None:
        raise ValueError(f"Contract {target_contract_id} not found")

    target_pop_days = _pop_days(target)
    target_value = _obligated_value(target)

    criteria: dict = {}
    query = db.query(Contract.id).filter(Contract.id != target_contract_id)

    if target.naics_code:
        prefix = target.naics_code[: _NAICS_PREFIX_LEN]
        query = query.filter(Contract.naics_code.like(f"{prefix}%"))
        criteria["naics_prefix"] = prefix

    if target.contract_type:
        query = query.filter(Contract.contract_type == target.contract_type)
        criteria["contract_type"] = target.contract_type

    if target.agency_name:
        query = query.filter(Contract.agency_name == target.agency_name)
        criteria["agency_name"] = target.agency_name

    if target.competition_type:
        query = query.filter(Contract.competition_type == target.competition_type)
        criteria["competition_type"] = target.competition_type

    rows = query.all()
    candidate_ids = [r[0] for r in rows]

    if target_pop_days and candidate_ids:
        candidate_ids = _filter_pop(db, candidate_ids, target_pop_days)
        criteria["pop_days"] = target_pop_days
        criteria["pop_band_pct"] = _POP_BAND_PCT

    if target_value and candidate_ids:
        candidate_ids = _filter_value(db, candidate_ids, target_value)
        criteria["obligated_value"] = target_value
        criteria["value_band_pct"] = _VALUE_BAND_PCT

    N = len(candidate_ids)
    return CohortDefinition(
        target_contract_id=target_contract_id,
        match_criteria=criteria,
        contract_ids=candidate_ids,
        N=N,
        low_confidence=N < _LOW_CONFIDENCE_THRESHOLD,
    )


def _pop_days(contract: Contract) -> int | None:
    if contract.period_start and contract.period_end:
        return (contract.period_end - contract.period_start).days
    return None


def _obligated_value(contract: Contract) -> float | None:
    if contract.metadata_json:
        val = contract.metadata_json.get("total_obligated")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return None


def _filter_pop(db: Session, candidate_ids: list[str], target_days: int) -> list[str]:
    lo = target_days * (1 - _POP_BAND_PCT)
    hi = target_days * (1 + _POP_BAND_PCT)
    rows = (
        db.query(Contract.id, Contract.period_start, Contract.period_end)
        .filter(Contract.id.in_(candidate_ids))
        .all()
    )
    result = []
    for cid, ps, pe in rows:
        if ps and pe:
            days = (pe - ps).days
            if lo <= days <= hi:
                result.append(cid)
        else:
            result.append(cid)
    return result


def _filter_value(db: Session, candidate_ids: list[str], target_value: float) -> list[str]:
    lo = target_value * (1 - _VALUE_BAND_PCT)
    hi = target_value * (1 + _VALUE_BAND_PCT)
    rows = (
        db.query(Contract.id, Contract.metadata_json)
        .filter(Contract.id.in_(candidate_ids))
        .all()
    )
    result = []
    for cid, meta in rows:
        val = None
        if meta:
            raw = meta.get("total_obligated")
            if raw is not None:
                try:
                    val = float(raw)
                except (TypeError, ValueError):
                    pass
        if val is None or (lo <= val <= hi):
            result.append(cid)
    return result
