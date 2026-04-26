from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contract_analysis import handle_cpars_document, handle_modification_document
from app.models import (
    BaselineObligation,
    ContractPrimitiveDecision,
    ContractPrimitiveDeliverable,
    ContractPrimitiveFinancial,
    ContractPrimitiveIssue,
    ContractPrimitivePersonnel,
    CparsRating,
    DocumentPage,
    DocumentReportFact,
    DocumentUpload,
    PrimitiveExtractionRun,
    RegressionFinding,
)


REPORT_KINDS = {"weekly_report", "monthly_report", "status_report", "biweekly_report", "ipmdar_pnr"}
SOURCE_KINDS = {"source_contract", "task_order"}


def backfill_contract_primitives(
    db: Session,
    *,
    contract_id: Optional[str] = None,
    document_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict[str, int]:
    """Populate typed primitive rows from already processed backend evidence.

    The function is intentionally conservative: it only writes rows grounded in
    uploaded document text, existing report facts, baseline obligations, or
    regression findings. If a document has already produced typed primitive rows,
    it is skipped so repeated runs are idempotent.
    """
    statement = select(DocumentUpload).order_by(DocumentUpload.created_at.asc())
    if contract_id:
        statement = statement.where(DocumentUpload.contract_id == contract_id)
    if document_id:
        statement = statement.where(DocumentUpload.id == document_id)
    if limit:
        statement = statement.limit(limit)

    totals = {
        "documents_seen": 0,
        "documents_backfilled": 0,
        "deliverable": 0,
        "financial": 0,
        "decisions": 0,
        "issues": 0,
        "personnel": 0,
        "cpars": 0,
        "skipped_existing": 0,
        "skipped_unlinked": 0,
    }
    for document in db.scalars(statement).all():
        totals["documents_seen"] += 1
        if not document.contract_id:
            totals["skipped_unlinked"] += 1
            continue
        if _has_existing_typed_rows(db, document.id):
            totals["skipped_existing"] += 1
            continue
        counts = backfill_document_primitives(db, document)
        if sum(counts.values()) > 0:
            totals["documents_backfilled"] += 1
        for key, count in counts.items():
            totals[key] += count
    return totals


def backfill_document_primitives(db: Session, document: DocumentUpload) -> dict[str, int]:
    text = _document_text(db, document.id)
    kind = (document.document_kind or "").lower()
    period_label = _period_label(document)
    run = PrimitiveExtractionRun(
        id=str(uuid4()),
        contract_id=document.contract_id,
        doc_upload_id=document.id,
        period_label=period_label,
        extracted_at=datetime.now(timezone.utc),
        model="backend_deterministic_v1",
        status="pending",
    )
    db.add(run)
    db.flush()

    counts = {
        "deliverable": 0,
        "financial": 0,
        "decisions": 0,
        "issues": 0,
        "personnel": 0,
        "cpars": 0,
    }
    if kind in SOURCE_KINDS:
        counts["deliverable"] += _backfill_source_deliverables(db, run, document)
    if kind in REPORT_KINDS:
        counts["deliverable"] += _backfill_report_deliverables(db, run, document, text)
        counts["financial"] += _backfill_financial(db, run, document, text)
        counts["issues"] += _backfill_issues(db, run, document)
        counts["personnel"] += _backfill_personnel(db, run, document, text)
    if kind == "modification":
        before = _decision_count(db, document.contract_id)
        handle_modification_document(db, document.contract_id, document, text, [], processing_run_id=None)
        db.flush()
        counts["decisions"] += max(0, _decision_count(db, document.contract_id) - before)
    if kind in {"cpars", "cpars_evaluation"}:
        before = _cpars_count(db, document.contract_id)
        handle_cpars_document(db, document.contract_id, document, text)
        db.flush()
        counts["cpars"] += max(0, _cpars_count(db, document.contract_id) - before)

    run.status = "success" if sum(counts.values()) > 0 else "no_rows"
    db.flush()
    return counts


def _has_existing_typed_rows(db: Session, document_id: str) -> bool:
    run_ids = list(
        db.scalars(select(PrimitiveExtractionRun.id).where(PrimitiveExtractionRun.doc_upload_id == document_id)).all()
    )
    if not run_ids:
        return False
    models = (
        ContractPrimitiveDeliverable,
        ContractPrimitiveFinancial,
        ContractPrimitiveDecision,
        ContractPrimitiveIssue,
        ContractPrimitivePersonnel,
    )
    return any(
        db.scalars(select(model.id).where(model.extraction_run_id.in_(run_ids)).limit(1)).first()
        for model in models
    )


def _document_text(db: Session, document_id: str) -> str:
    pages = db.scalars(
        select(DocumentPage).where(DocumentPage.document_upload_id == document_id).order_by(DocumentPage.page_number.asc())
    ).all()
    return "\n\n".join(page.text for page in pages if page.text)


def _period_label(document: DocumentUpload) -> Optional[str]:
    if document.report_period_start and document.report_period_end:
        return f"{document.report_period_start} to {document.report_period_end}"
    if document.report_period_start:
        return str(document.report_period_start)
    return document.created_at.date().isoformat() if document.created_at else None


def _source_doc_ids(document: DocumentUpload) -> list[str]:
    return [document.id]


def _backfill_source_deliverables(db: Session, run: PrimitiveExtractionRun, document: DocumentUpload) -> int:
    obligations = db.scalars(
        select(BaselineObligation)
        .where(
            BaselineObligation.contract_id == document.contract_id,
            BaselineObligation.obligation_type.in_(("deliverable", "reporting_cadence")),
        )
        .order_by(BaselineObligation.created_at.asc())
    ).all()
    count = 0
    for obligation in obligations:
        name = obligation.title or "Contract deliverable requirement"
        db.add(
            ContractPrimitiveDeliverable(
                id=str(uuid4()),
                extraction_run_id=run.id,
                contract_id=document.contract_id,
                source_doc_ids=[obligation.source_document_upload_id or document.id],
                period_label=run.period_label,
                deliverable_name=name,
                cdrl_item=_cdrl(obligation.reference_text or obligation.description or name),
                status="requirement",
                acceptance_status=None,
            )
        )
        count += 1
    return count


def _backfill_report_deliverables(db: Session, run: PrimitiveExtractionRun, document: DocumentUpload, text: str) -> int:
    facts = list(_facts_for_document(db, document.id))
    candidates = [
        fact for fact in facts
        if _has_any(f"{fact.fact_type} {fact.label} {fact.value_text}", ("deliver", "cdrl", "schedule", "late", "accepted", "rejected"))
    ]
    if not candidates and _has_any(text, ("deliver", "cdrl", "status report", "submitted")):
        candidates = [None]
    count = 0
    for fact in candidates[:12]:
        blob = f"{fact.label} {fact.value_text} {fact.quote}" if fact else text[:500]
        status = "late" if _has_any(blob, ("late", "slip", "delayed", "overdue")) else "reported"
        db.add(
            ContractPrimitiveDeliverable(
                id=str(uuid4()),
                extraction_run_id=run.id,
                contract_id=document.contract_id,
                source_doc_ids=_source_doc_ids(document),
                period_label=run.period_label,
                deliverable_name=(fact.label if fact else document.title)[:300],
                cdrl_item=_cdrl(blob),
                actual_delivery_date=document.report_period_end,
                status=status,
                acceptance_status=_acceptance_status(blob),
                days_late=_days_late(blob),
            )
        )
        count += 1
    return count


def _backfill_financial(db: Session, run: PrimitiveExtractionRun, document: DocumentUpload, text: str) -> int:
    facts = list(_facts_for_document(db, document.id))
    financial_facts = [
        fact for fact in facts
        if _has_any(f"{fact.fact_type} {fact.label} {fact.value_text}", ("cost", "eac", "cpi", "spi", "variance", "invoice", "burn", "obligation"))
    ]
    parsed = _financial_values(" ".join([text[:4000], *(fact.value_text for fact in financial_facts)]))
    if not financial_facts and not any(value is not None for value in parsed.values()):
        return 0
    db.add(
        ContractPrimitiveFinancial(
            id=str(uuid4()),
            extraction_run_id=run.id,
            contract_id=document.contract_id,
            source_doc_ids=_source_doc_ids(document),
            period_label=run.period_label,
            period_end_date=document.report_period_end,
            **parsed,
        )
    )
    return 1


def _backfill_issues(db: Session, run: PrimitiveExtractionRun, document: DocumentUpload) -> int:
    findings = db.scalars(
        select(RegressionFinding).where(RegressionFinding.document_upload_id == document.id).order_by(RegressionFinding.created_at.asc())
    ).all()
    count = 0
    for finding in findings:
        db.add(
            ContractPrimitiveIssue(
                id=str(uuid4()),
                extraction_run_id=run.id,
                contract_id=document.contract_id,
                source_doc_ids=_source_doc_ids(document),
                period_label=run.period_label,
                issue_id=finding.id,
                category=finding.finding_type,
                description=finding.summary,
                severity=finding.severity,
                responsible_party=_responsible_party(" ".join([finding.title, finding.summary, finding.quote or ""])),
                status=finding.status,
            )
        )
        count += 1
    return count


def _backfill_personnel(db: Session, run: PrimitiveExtractionRun, document: DocumentUpload, text: str) -> int:
    facts = list(_facts_for_document(db, document.id))
    personnel = [
        fact for fact in facts
        if _has_any(f"{fact.fact_type} {fact.label} {fact.value_text}", ("staff", "personnel", "fte", "vacancy", "labor", "program manager", "subcontract"))
    ]
    if not personnel and not _has_any(text, ("staff", "personnel", "fte", "vacancy", "labor", "program manager")):
        return 0
    count = 0
    for fact in (personnel or [None])[:8]:
        blob = f"{fact.label} {fact.value_text}" if fact else text[:500]
        db.add(
            ContractPrimitivePersonnel(
                id=str(uuid4()),
                extraction_run_id=run.id,
                contract_id=document.contract_id,
                source_doc_ids=_source_doc_ids(document),
                period_label=run.period_label,
                role=_role(blob),
                labor_category=(fact.label if fact else "Personnel signal")[:200],
                fte_planned=_decimal_match(blob, "planned"),
                fte_actual=_decimal_match(blob, "actual"),
                staffing_gap_flag=_has_any(blob, ("gap", "vacancy", "shortfall", "below plan", "understaff")),
            )
        )
        count += 1
    return count


def _facts_for_document(db: Session, document_id: str) -> Iterable[DocumentReportFact]:
    return db.scalars(
        select(DocumentReportFact).where(DocumentReportFact.document_upload_id == document_id).order_by(DocumentReportFact.created_at.asc())
    ).all()


def _financial_values(text: str) -> dict[str, Optional[Decimal]]:
    return {
        "planned_value": _money_after(text, ("planned value", "bcws", "pv")),
        "earned_value": _money_after(text, ("earned value", "bcwp", "ev")),
        "actual_cost": _money_after(text, ("actual cost", "acwp", "ac")),
        "budget_at_completion": _money_after(text, ("budget at completion", "bac")),
        "estimate_at_completion": _money_after(text, ("estimate at completion", "eac")),
        "estimate_to_complete": _money_after(text, ("estimate to complete", "etc")),
        "cost_variance": _money_after(text, ("cost variance", "cv")),
        "schedule_variance": _money_after(text, ("schedule variance", "sv")),
        "cpi": _decimal_after(text, ("cpi",)),
        "spi": _decimal_after(text, ("spi",)),
        "percent_complete": _decimal_after(text, ("percent complete", "% complete")),
        "cumulative_obligations": _money_after(text, ("cumulative obligations", "obligated")),
    }


def _money_after(text: str, labels: tuple[str, ...]) -> Optional[Decimal]:
    for label in labels:
        match = re.search(rf"\b{re.escape(label)}\b[^0-9$-]{{0,30}}\$?\s*(-?[0-9][0-9,]*(?:\.[0-9]+)?)\s*([KkMm])?", text, re.I)
        if match:
            return _number(match.group(1), match.group(2))
    return None


def _decimal_after(text: str, labels: tuple[str, ...]) -> Optional[Decimal]:
    for label in labels:
        match = re.search(rf"\b{re.escape(label)}\b[^0-9.-]{{0,20}}(-?[0-9]+(?:\.[0-9]+)?)", text, re.I)
        if match:
            return Decimal(match.group(1))
    return None


def _decimal_match(text: str, label: str) -> Optional[Decimal]:
    match = re.search(rf"\b{label}\b[^0-9.]{{0,20}}([0-9]+(?:\.[0-9]+)?)\s*FTE", text, re.I)
    return Decimal(match.group(1)) if match else None


def _number(value: str, suffix: Optional[str]) -> Decimal:
    result = Decimal(value.replace(",", ""))
    if suffix and suffix.lower() == "k":
        result *= Decimal("1000")
    if suffix and suffix.lower() == "m":
        result *= Decimal("1000000")
    return result


def _cdrl(text: str) -> Optional[str]:
    match = re.search(r"\b[A-Z]\d{3}\b", text or "")
    return match.group(0) if match else None


def _acceptance_status(text: str) -> Optional[str]:
    lowered = text.lower()
    if "reject" in lowered:
        return "rejected"
    if "accept" in lowered or "approved" in lowered:
        return "accepted"
    return None


def _days_late(text: str) -> Optional[int]:
    match = re.search(r"\b([0-9]{1,3})\s+days?\s+(?:late|delayed|slip)", text, re.I)
    return int(match.group(1)) if match else None


def _responsible_party(text: str) -> Optional[str]:
    lowered = text.lower()
    if any(token in lowered for token in ("government", "cor", "gfe", "gfi")):
        return "government"
    if any(token in lowered for token in ("contractor", "vendor", "subcontractor")):
        return "contractor"
    return None


def _role(text: str) -> Optional[str]:
    lowered = text.lower()
    if "program manager" in lowered or re.search(r"\bpm\b", lowered):
        return "PM"
    if "cor" in lowered:
        return "COR"
    if "subcontract" in lowered:
        return "subcontractor"
    if "key personnel" in lowered:
        return "key_person"
    return "labor_category"


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(needle in lowered for needle in needles)


def _decision_count(db: Session, contract_id: Optional[str]) -> int:
    if not contract_id:
        return 0
    return len(db.scalars(select(ContractPrimitiveDecision.id).where(ContractPrimitiveDecision.contract_id == contract_id)).all())


def _cpars_count(db: Session, contract_id: Optional[str]) -> int:
    if not contract_id:
        return 0
    return len(db.scalars(select(CparsRating.id).where(CparsRating.contract_id == contract_id)).all())
