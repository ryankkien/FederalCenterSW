from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from app.ai.providers import AIContractHint, AIProvider, NullAIProvider


CONTRACT_NUMBER_PATTERNS = (
    re.compile(r"\b[A-Z]\d{7}[A-Z]\d{4}\b", re.IGNORECASE),
    re.compile(r"\b[A-Z]\d{5}-\d{2}-[A-Z]-\d{4}\b", re.IGNORECASE),
)
FIELD_ORDER = ("filename", "title", "notes", "email_subject", "email_body", "text")


class ContractCandidate(BaseModel):
    contract_id: str
    contract_number: str
    title: Optional[str] = None


class ContractMatchContext(BaseModel):
    filename: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    text: Optional[str] = None


class ContractMatchResult(BaseModel):
    status: str
    source: str
    matched_contract_id: Optional[str] = None
    matched_contract_number: Optional[str] = None
    confidence: float = 0.0
    hints: List[str] = Field(default_factory=list)
    ai_hints: List[AIContractHint] = Field(default_factory=list)


def match_contract(
    contracts: Sequence[object],
    context: ContractMatchContext,
    ai_provider: Optional[AIProvider] = None,
) -> ContractMatchResult:
    candidates = candidate_contracts(contracts)
    if not candidates:
        return ContractMatchResult(status="unmatched", source="none", hints=contract_number_hints_from_context(context))

    normalized_to_candidate = {
        normalize_contract_number(candidate.contract_number): candidate for candidate in candidates
    }

    deterministic_result = _deterministic_match(context, normalized_to_candidate)
    if deterministic_result.status == "matched":
        return deterministic_result
    if deterministic_result.status == "ambiguous":
        return deterministic_result

    provider = ai_provider or NullAIProvider()
    if not provider.status.available:
        return deterministic_result

    ai_hints = provider.suggest_contract_matches(
        context=_context_text(context),
        candidate_contract_numbers=[candidate.contract_number for candidate in candidates],
    )
    matched_ai_hints = [
        hint
        for hint in ai_hints
        if hint.contract_number
        and normalize_contract_number(hint.contract_number) in normalized_to_candidate
    ]
    if not matched_ai_hints:
        deterministic_result.ai_hints = ai_hints
        return deterministic_result

    matched_ai_hints.sort(key=lambda hint: hint.confidence, reverse=True)
    best = matched_ai_hints[0]
    candidate = normalized_to_candidate[normalize_contract_number(best.contract_number or "")]
    return ContractMatchResult(
        status="matched",
        source="ai",
        matched_contract_id=candidate.contract_id,
        matched_contract_number=candidate.contract_number,
        confidence=best.confidence,
        hints=deterministic_result.hints,
        ai_hints=ai_hints,
    )


def candidate_contracts(contracts: Sequence[object]) -> List[ContractCandidate]:
    candidates = []
    for contract in contracts:
        contract_number = _string_attr(
            contract,
            "contract_number",
            "number",
            "contract_id",
            "contractId",
        )
        contract_id = _string_attr(contract, "id", "contract_id", "contractId") or contract_number
        if not contract_number or not contract_id:
            continue
        candidates.append(
            ContractCandidate(
                contract_id=contract_id,
                contract_number=contract_number.strip().upper(),
                title=_string_attr(contract, "title", "name"),
            )
        )
    return candidates


def extract_contract_number_hints(value: str) -> List[str]:
    hints = []
    for pattern in CONTRACT_NUMBER_PATTERNS:
        for match in pattern.findall(value or ""):
            cleaned = match.strip().upper()
            if cleaned not in hints:
                hints.append(cleaned)
    return hints


def normalize_contract_number(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _deterministic_match(
    context: ContractMatchContext,
    normalized_to_candidate: Dict[str, ContractCandidate],
) -> ContractMatchResult:
    all_hints = []
    for field_name in FIELD_ORDER:
        value = getattr(context, field_name) or ""
        field_hints = extract_contract_number_hints(value)
        for hint in field_hints:
            if hint not in all_hints:
                all_hints.append(hint)
        matches = _matches_for_hints(field_hints, normalized_to_candidate)
        if len(matches) == 1:
            candidate = matches[0]
            return ContractMatchResult(
                status="matched",
                source="deterministic",
                matched_contract_id=candidate.contract_id,
                matched_contract_number=candidate.contract_number,
                confidence=1.0,
                hints=all_hints,
            )
        if len(matches) > 1:
            return ContractMatchResult(
                status="ambiguous",
                source="deterministic",
                confidence=0.0,
                hints=all_hints,
            )

        exact_matches = _exact_candidate_mentions(value, normalized_to_candidate)
        if len(exact_matches) == 1:
            candidate = exact_matches[0]
            return ContractMatchResult(
                status="matched",
                source="deterministic",
                matched_contract_id=candidate.contract_id,
                matched_contract_number=candidate.contract_number,
                confidence=1.0,
                hints=all_hints,
            )
        if len(exact_matches) > 1:
            return ContractMatchResult(
                status="ambiguous",
                source="deterministic",
                confidence=0.0,
                hints=all_hints,
            )

    return ContractMatchResult(status="unmatched", source="none", hints=all_hints)


def contract_number_hints_from_context(context: ContractMatchContext) -> List[str]:
    all_hints = []
    for field_name in FIELD_ORDER:
        value = getattr(context, field_name) or ""
        for hint in extract_contract_number_hints(value):
            if hint not in all_hints:
                all_hints.append(hint)
    return all_hints


def _matches_for_hints(
    hints: Sequence[str],
    normalized_to_candidate: Dict[str, ContractCandidate],
) -> List[ContractCandidate]:
    matches = []
    seen = set()
    for hint in hints:
        normalized = normalize_contract_number(hint)
        candidate = normalized_to_candidate.get(normalized)
        if candidate and candidate.contract_id not in seen:
            matches.append(candidate)
            seen.add(candidate.contract_id)
    return matches


def _exact_candidate_mentions(
    value: str,
    normalized_to_candidate: Dict[str, ContractCandidate],
) -> List[ContractCandidate]:
    normalized_value = normalize_contract_number(value)
    if not normalized_value:
        return []

    matches = []
    for normalized_number, candidate in normalized_to_candidate.items():
        if normalized_number and normalized_number in normalized_value:
            matches.append(candidate)
    return matches


def _context_text(context: ContractMatchContext) -> str:
    values = []
    for field_name in FIELD_ORDER:
        value = getattr(context, field_name) or ""
        if value.strip():
            values.append(f"{field_name}: {value.strip()}")
    return "\n\n".join(values)


def _string_attr(item: object, *names: str) -> Optional[str]:
    for name in names:
        value = item.get(name) if isinstance(item, dict) else getattr(item, name, None)
        if value is not None and str(value).strip():
            return str(value)
    return None
