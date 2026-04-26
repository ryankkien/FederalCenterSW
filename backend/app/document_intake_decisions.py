from __future__ import annotations

from typing import Optional, Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contract_analysis import classify_document
from app.contract_matching import ContractMatchContext, ContractMatchResult, match_contract
from app.models import Contract, DocumentClassificationDecision, DocumentMatchDecision, DocumentUpload


INLINE_DECISION_SOURCE = "deterministic"


def apply_inline_intake_decisions(
    db: Session,
    document: DocumentUpload,
    contracts: Optional[Sequence[Contract]] = None,
) -> ContractMatchResult:
    """Run cheap deterministic intake decisions before the async processor."""

    document_kind, modification_kind = classify_document(document, text="")
    _persist_classification_decision(db, document, document_kind, modification_kind)

    contract_match = match_contract(
        contracts if contracts is not None else _available_contracts(db),
        ContractMatchContext(
            filename=document.original_filename,
            title=document.title,
            notes=document.notes,
        ),
    )
    if contract_match.matched_contract_id:
        document.contract_id = contract_match.matched_contract_id
    document.match_status = contract_match.status
    _persist_match_decision(db, document, contract_match)
    return contract_match


def _available_contracts(db: Session) -> Sequence[Contract]:
    return list(db.scalars(select(Contract)).all())


def _persist_classification_decision(
    db: Session,
    document: DocumentUpload,
    document_kind: str,
    modification_kind: Optional[str],
) -> None:
    metadata = document.metadata_json or {}
    classification = metadata.get("classification", {}) if isinstance(metadata, dict) else {}
    db.add(
        DocumentClassificationDecision(
            id=str(uuid4()),
            document_upload_id=document.id,
            document_kind=document_kind,
            modification_kind=modification_kind,
            confidence=classification.get("confidence") or 0.6,
            rationale=(
                classification.get("rationale")
                or "Deterministic intake classifier matched filename, title, notes, or type cues."
            ),
            classifier_name=INLINE_DECISION_SOURCE,
            metadata_json={
                **classification,
                "source": INLINE_DECISION_SOURCE,
                "inline": True,
                "fields": ["original_filename", "title", "notes", "document_type"],
            },
        )
    )


def _persist_match_decision(
    db: Session,
    document: DocumentUpload,
    match: ContractMatchResult,
) -> None:
    db.add(
        DocumentMatchDecision(
            id=str(uuid4()),
            document_upload_id=document.id,
            contract_id=match.matched_contract_id,
            matched_contract_number=match.matched_contract_number,
            decision_status=match.status,
            decision_source=INLINE_DECISION_SOURCE,
            confidence=match.confidence,
            rationale=", ".join(match.hints[:5]) or None,
            metadata_json={
                "source": INLINE_DECISION_SOURCE,
                "inline": True,
                "match_source": match.source,
                "ai_hints": [hint.model_dump() for hint in match.ai_hints],
            },
        )
    )
