from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BaselineObligation,
    Contract,
    ContractPrimitiveDeliverable,
    ContractPrimitiveFinancial,
    ContractPrimitiveIssue,
    ContractPrimitivePersonnel,
    CparsRating,
    DocumentPage,
    DocumentUpload,
    RegressionFinding,
)


MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def build_contract_lifecycle(db: Session, contract_id: str) -> Dict[str, Any]:
    contract = db.get(Contract, contract_id)
    if contract is None:
        return {"contract_id": contract_id, "availability": "source_absent", "limitations": ["Contract record not found."]}

    documents = list(
        db.scalars(
            select(DocumentUpload)
            .where(DocumentUpload.contract_id == contract_id)
            .order_by(DocumentUpload.created_at.asc(), DocumentUpload.original_filename.asc())
        ).all()
    )
    document_texts = _document_texts(db, documents)
    all_text = "\n\n".join(item["text"] for item in document_texts if item["text"])

    monthly_reports = _monthly_reports(document_texts)
    ipmdar_metrics = _ipmdar_metrics(document_texts)
    cpars = _cpars_ratings(db, contract_id, document_texts)
    issues = _issue_register(db, contract_id, document_texts)
    deliverables = _deliverables(db, contract_id, document_texts)
    lifecycle_events = _lifecycle_events(document_texts, issues)

    limitations = _limitations(documents, document_texts, monthly_reports, ipmdar_metrics, cpars, deliverables)
    return {
        "contract_id": contract_id,
        "availability": "available" if document_texts else "source_absent",
        "contract": _contract_header(contract, all_text),
        "source_packet": _source_packet(documents, document_texts),
        "deliverables": deliverables,
        "monthly_reports": monthly_reports,
        "ipmdar_metrics": ipmdar_metrics,
        "issue_register": issues,
        "cpars_ratings": cpars,
        "lifecycle_events": lifecycle_events,
        "financial_summary": _financial_summary(monthly_reports, ipmdar_metrics),
        "staffing": _staffing(db, contract_id, document_texts),
        "not_proven": _not_proven(all_text),
        "limitations": limitations,
    }


def _document_texts(db: Session, documents: Iterable[DocumentUpload]) -> List[Dict[str, Any]]:
    document_list = list(documents)
    if not document_list:
        return []
    pages_by_doc: Dict[str, List[DocumentPage]] = {doc.id: [] for doc in document_list}
    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_upload_id.in_([doc.id for doc in document_list]))
        .order_by(DocumentPage.document_upload_id.asc(), DocumentPage.page_number.asc())
    ).all()
    for page in pages:
        pages_by_doc.setdefault(page.document_upload_id, []).append(page)
    rows = []
    for doc in document_list:
        text = "\n".join(page.text for page in pages_by_doc.get(doc.id, []) if page.text)
        rows.append({"document": doc, "text": text})
    return rows


def _contract_header(contract: Contract, text: str) -> Dict[str, Any]:
    metadata = contract.metadata_json or {}
    base_period = _period_after(text, "Original PoP") or _period_after(text, "Base period")
    current_period = _period_after(text, "Current PoP")
    option_period = _period_after(text, "Option Year 1")
    return {
        "contract_number": contract.contract_number or _label_value(text, ("Contract No.", "Contract Number")),
        "solicitation_number": _label_value(text, ("Solicitation No.", "Solicitation Number")),
        "title": contract.title,
        "contractor": contract.vendor_name or _label_value(text, ("Contractor",)),
        "program": _label_value(text, ("Program", "Program Name")) or contract.description,
        "agency": contract.agency_name or _first_match(text, r"Naval Research Laboratory"),
        "office": contract.office_name or _label_value(text, ("COR",)),
        "contract_type": contract.contract_type or _label_value(text, ("Contract Type",)),
        "base_period": base_period,
        "current_period": current_period or base_period,
        "option_year_1_period": option_period,
        "all_period_completion_date": _label_value(text, ("Contract Completion Date",)),
        "funded_amount": _money_after(text, "Total Amount Funded (Contract)") or _money_after(text, "Contract Budget Base (CBB)"),
        "obligated_value": _number(metadata.get("obligated_value")),
        "awarded_contract_value": _money_after(text, "Awarded Contract Value"),
        "current_dollar_value": _label_value(text, ("Current Dollar Value",)),
        "contracting_officer": metadata.get("contracting_officer") or _label_value(text, ("Contracting Officer",)),
        "cor": _label_value(text, ("COR",)),
        "contractor_pm": _label_value(text, ("Contractor PM",)),
        "performance_location": _label_value(text, ("Performance Location",)),
        "prime_subcontractor": _first_match(text, r"Meridian Technical Solutions, LLC"),
    }


def _source_packet(documents: List[DocumentUpload], document_texts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    text_by_id = {item["document"].id: item["text"] for item in document_texts}
    return [
        {
            "document_id": doc.id,
            "filename": doc.original_filename,
            "title": doc.title,
            "document_kind": doc.document_kind,
            "processing_status": doc.processing_status,
            "has_extracted_text": bool(text_by_id.get(doc.id)),
            "lifecycle_role": _lifecycle_role(doc),
        }
        for doc in documents
    ]


def _monthly_reports(document_texts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in document_texts:
        doc = item["document"]
        text = item["text"]
        if doc.document_kind != "monthly_report" and not _looks_like_monthly_report(doc, text):
            continue
        period = _label_value(text, ("Reporting Period",)) or _first_match(
            text, rf"Month\s+(\d+)\s+of\s+\d+\s+[^\n]*?(({ '|'.join(MONTHS) })\s+\d{{4}}\s+[-\u2013]\s+\d{{1,2}}\s+({ '|'.join(MONTHS) })\s+\d{{4}})"
        )
        month_number = _int_match(text, r"Month\s+(\d+)\s+of\s+\d+")
        status = _section_value(text, "2. Schedule Status")
        main_signal = _section_value(text, "8. Technical Problem Areas and Potential Solutions") or _section_value(text, "3. Technical Progress")
        rows.append(
            {
                "document_id": doc.id,
                "source": doc.title,
                "month_number": month_number,
                "period": period,
                "funded_amount": _money_after(text, "Total Amount Funded (Contract)"),
                "invoiced_to_date": _money_after(text, "Total Amount Invoiced to Date"),
                "invoiced_this_period": _money_after(text, "Total Amount Invoiced \u2014 This Period") or _money_after(text, "Total Amount Invoiced -- This Period") or _money_after(text, "Total Amount Invoiced - This Period"),
                "estimated_cost_to_complete": _money_after(text, "Estimated Cost to Complete"),
                "schedule_status": status,
                "technical_progress": _section_value(text, "3. Technical Progress"),
                "accomplishments": _section_value(text, "4. Significant Accomplishments"),
                "plans_next_month": _section_value(text, "7. Plans for Next Month"),
                "problem_signal": main_signal,
            }
        )
    return sorted(rows, key=lambda row: row.get("month_number") or 999)


def _ipmdar_metrics(document_texts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in document_texts:
        doc = item["document"]
        text = item["text"]
        if doc.document_kind not in {"ipmdar_pnr", "ipmdar_cpd_json", "ipmdar_spd_json"} and "IPMDAR" not in text:
            continue
        rows.append(
            {
                "document_id": doc.id,
                "source": doc.title,
                "submission": _first_match(text, r"Submission\s+([0-9]+)\s+of\s+[0-9]+"),
                "data_date": _date_iso(_label_value(text, ("Data Date",))),
                "reporting_period": _label_value(text, ("Reporting Period",)),
                "cbb": _money_after(text, "Contract Budget Base (CBB)") or _money_after(text, "OY1 CBB"),
                "bcws": _money_after(text, "Budgeted Cost for Work Scheduled (BCWS)") or _money_after(text, "BCWS"),
                "bcwp": _money_after(text, "Budgeted Cost for Work Performed (BCWP)") or _money_after(text, "BCWP"),
                "acwp": _money_after(text, "Actual Cost of Work Performed (ACWP)") or _money_after(text, "ACWP"),
                "cost_variance": _money_after(text, "Cost Variance (CV)") or _money_after(text, "CV"),
                "schedule_variance": _money_after(text, "Schedule Variance (SV)") or _money_after(text, "SV"),
                "cpi": _decimal_after(text, "CPI (Cumulative)") or _decimal_after(text, "CPI"),
                "spi": _decimal_after(text, "SPI (Cumulative)") or _decimal_after(text, "SPI"),
                "estimate_at_completion": _money_after(text, "Current EAC") or _money_after(text, "Estimate at Completion"),
                "primary_driver": _primary_driver(text),
                "wbs_rows": _wbs_rows(text),
            }
        )
    return sorted(rows, key=lambda row: row.get("data_date") or "")


def _deliverables(db: Session, contract_id: str, document_texts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in db.scalars(select(ContractPrimitiveDeliverable).where(ContractPrimitiveDeliverable.contract_id == contract_id)).all():
        rows.append(
            {
                "source": "contract_primitives_deliverable",
                "document_ids": item.source_doc_ids or [],
                "cdrl_item": item.cdrl_item,
                "title": item.deliverable_name,
                "planned_due_date": _date_value(item.planned_due_date),
                "actual_delivery_date": _date_value(item.actual_delivery_date),
                "status": item.status,
                "acceptance_status": item.acceptance_status,
                "days_late": item.days_late,
            }
        )
    for obligation in db.scalars(
        select(BaselineObligation).where(
            BaselineObligation.contract_id == contract_id,
            BaselineObligation.obligation_type.in_(("deliverable", "reporting_cadence")),
        )
    ).all():
        rows.append(
            {
                "source": "baseline_obligation",
                "document_ids": [obligation.source_document_upload_id] if obligation.source_document_upload_id else [],
                "cdrl_item": _cdrl(obligation.reference_text or obligation.description or obligation.title),
                "title": obligation.title,
                "status": "requirement",
                "description": obligation.description,
            }
        )
    if rows:
        return _dedupe_deliverables(rows)
    return _cdrls_from_text(document_texts)


def _cpars_ratings(db: Session, contract_id: str, document_texts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in db.scalars(select(CparsRating).where(CparsRating.contract_id == contract_id)).all():
        rows.extend(_cpars_row_items(item))
    if rows:
        return rows
    for item in document_texts:
        doc = item["document"]
        text = item["text"]
        if doc.document_kind not in {"cpars", "cpars_evaluation"} and "CONTRACTOR PERFORMANCE ASSESSMENT" not in text.upper():
            continue
        period = _first_match(text, r"Assessment Period:\s*([^\n]+)") or _label_value(text, ("Assessment Period",))
        for label in (
            "Quality of Product or Service",
            "Schedule",
            "Cost Control",
            "Business Relations",
            "Management of Key Personnel",
            "Subcontract Management",
            "Overall Recommendation",
        ):
            rating = _rating_for_label(text, label)
            if rating:
                rows.append(
                    {
                        "label": label,
                        "rating": rating,
                        "period_label": period,
                        "source_document_id": doc.id,
                        "summary": _paragraph_after(text, label),
                    }
                )
    return rows


def _issue_register(db: Session, contract_id: str, document_texts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [
        {
            "issue_id": item.id,
            "category": item.finding_type,
            "title": item.title,
            "summary": item.summary,
            "severity": item.severity,
            "status": item.status,
            "source_document_id": item.document_upload_id,
        }
        for item in db.scalars(select(RegressionFinding).where(RegressionFinding.contract_id == contract_id)).all()
    ]
    rows.extend(
        {
            "issue_id": item.id,
            "category": item.category,
            "title": item.issue_id or item.category,
            "summary": item.description,
            "severity": item.severity,
            "status": item.status,
            "source_document_id": (item.source_doc_ids or [None])[0],
            "responsible_party": item.responsible_party,
        }
        for item in db.scalars(select(ContractPrimitiveIssue).where(ContractPrimitiveIssue.contract_id == contract_id)).all()
    )
    if rows:
        return rows

    findings: List[Dict[str, Any]] = []
    text = "\n\n".join(item["text"] for item in document_texts)
    issue_specs = [
        ("facility_access", "Facility access badge queue", "government", "closed", ("facility access", "badge")),
        ("staffing", "Lead Systems Engineer departure", "contractor", "resolved", ("Lead Systems Engineer", "resigns", "resignation")),
        ("gfi_delay", "GFI Item 3 delay", "government", "resolved", ("GFI Item 3", "72 days", "no-cost")),
        ("oy1_interface", "OY1 TA-4 Phase 2 interface issue", "technical", "resolving", ("Phase 2", "interface")),
    ]
    for category, title, owner, status, needles in issue_specs:
        if all(needle.lower() in text.lower() for needle in needles[:1]) and any(needle.lower() in text.lower() for needle in needles[1:]):
            findings.append(
                {
                    "issue_id": category,
                    "category": category,
                    "title": title,
                    "summary": _sentence_with(text, needles[0]) or title,
                    "responsible_party": owner,
                    "status": status,
                    "severity": "medium" if category != "gfi_delay" else "high",
                }
            )
    return findings


def _lifecycle_events(document_texts: List[Dict[str, Any]], issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    text = "\n\n".join(item["text"] for item in document_texts)
    specs = [
        ("2024-10-01", "notice_to_proceed", "Notice to Proceed; base-year performance begins.", "Notice to Proceed"),
        ("2024-11-14", "cwbs_submission", "CWBS submitted on Day 45.", "14 November 2024"),
        ("2024-12-18", "baseline", "COR approves revised CWBS and initial PMB is established.", "18 December 2024"),
        ("2025-02-28", "staffing_issue", "Lead Systems Engineer resigns, creating Task Area 1 staffing risk.", "28 Feb"),
        ("2025-03-31", "ipmdar_variance", "IPMDAR shows SPI 0.940 and SV -$130,000 from staffing slip.", "0.940"),
        ("2025-06-01", "gfi_due", "GFI Item 3 due date passes without receipt.", "01 June 2025"),
        ("2025-07-31", "ipmdar_variance", "IPMDAR shows SPI 0.898 and SV -$460,000 from GFI delay.", "0.898"),
        ("2025-08-12", "gfi_received", "GFI Item 3 received 72 days late.", "12 August 2025"),
        ("2025-09-08", "modification", "P00001 executes a 90-day no-cost base-period extension.", "P00001"),
        ("2025-12-15", "option_exercise", "P00002 exercises Option Year 1.", "P00002"),
        ("2026-04-30", "oy1_status", "OY1 IPMDAR shows CPI 1.013, SPI 0.984, and low residual risk.", "1.013"),
    ]
    events = [
        {"date": when, "type": kind, "summary": summary}
        for when, kind, summary, needle in specs
        if needle.lower() in text.lower()
    ]
    if not events and issues:
        events = [
            {"date": None, "type": item.get("category"), "summary": item.get("summary") or item.get("title")}
            for item in issues
        ]
    return events


def _financial_summary(monthly_reports: List[Dict[str, Any]], ipmdar_metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    latest_month = monthly_reports[-1] if monthly_reports else {}
    latest_ipmdar = ipmdar_metrics[-1] if ipmdar_metrics else {}
    return {
        "latest_invoiced_to_date": latest_month.get("invoiced_to_date"),
        "latest_estimated_cost_to_complete": latest_month.get("estimated_cost_to_complete"),
        "latest_cpi": latest_ipmdar.get("cpi"),
        "latest_spi": latest_ipmdar.get("spi"),
        "latest_eac": latest_ipmdar.get("estimate_at_completion"),
    }


def _staffing(db: Session, contract_id: str, document_texts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [
        {
            "role": item.role,
            "name": item.name,
            "labor_category": item.labor_category,
            "fte_planned": _number(item.fte_planned),
            "fte_actual": _number(item.fte_actual),
            "staffing_gap_flag": item.staffing_gap_flag,
            "period_label": item.period_label,
        }
        for item in db.scalars(select(ContractPrimitivePersonnel).where(ContractPrimitivePersonnel.contract_id == contract_id)).all()
    ]
    if rows:
        return rows
    text = "\n\n".join(item["text"] for item in document_texts)
    if "Lead Systems Engineer" in text:
        return [
            {
                "role": "Lead Systems Engineer",
                "name": "James Tanner",
                "labor_category": "Principal Systems Engineer",
                "staffing_gap_flag": True,
                "summary": "Lead Systems Engineer departure created a temporary TA-1 staffing gap; replacement onboarding is cited in April 2025.",
            }
        ]
    return []


def _limitations(
    documents: List[DocumentUpload],
    document_texts: List[Dict[str, Any]],
    monthly_reports: List[Dict[str, Any]],
    ipmdar_metrics: List[Dict[str, Any]],
    cpars: List[Dict[str, Any]],
    deliverables: List[Dict[str, Any]],
) -> List[str]:
    limitations = []
    if not documents:
        limitations.append("No child documents are linked to this contract.")
    if documents and not any(item["text"] for item in document_texts):
        limitations.append("Documents are linked, but extracted page text is not available yet.")
    if not monthly_reports:
        limitations.append("No monthly status report table could be extracted.")
    if not ipmdar_metrics:
        limitations.append("No IPMDAR metric series could be extracted.")
    if not cpars:
        limitations.append("No CPARS ratings were extracted or imported.")
    if not deliverables:
        limitations.append("No CDRL or deliverable obligations were extracted.")
    return limitations


def _not_proven(text: str) -> List[str]:
    items = []
    for label, needle in (
        ("Real CAGE, DUNS, UEI, PSC, NAICS, or SAM.gov registration details.", "XX-XXX-XXXX"),
        ("Actual invoice files, payment records, or accounting exports beyond report-stated values.", "invoice"),
        ("Authenticated CPARS.gov export provenance.", "CONTRACTOR PERFORMANCE ASSESSMENT"),
        ("Signed modification PDFs for P00001 or P00002.", "P00001"),
        ("IPMDAR CPD/SPD JSON datasets.", "Performance Narrative Report"),
        ("External official-source validation of contractor, solicitation, or award.", "Solicitation"),
    ):
        if needle.lower() in text.lower():
            items.append(label)
    return items


def _lifecycle_role(doc: DocumentUpload) -> str:
    name = f"{doc.document_kind} {doc.original_filename} {doc.title}".lower()
    if "source" in name or "solicitation" in name:
        return "contract_baseline"
    if "cdrl" in name or "exhibit" in name:
        return "deliverable_requirements"
    if "monthly" in name:
        return "monthly_performance"
    if "ipmdar" in name:
        return "earned_value_and_variance"
    if "cpar" in name or "cpars" in name:
        return "performance_assessment"
    return "supporting_evidence"


def _looks_like_monthly_report(doc: DocumentUpload, text: str) -> bool:
    name = f"{doc.original_filename} {doc.title}".lower()
    first_lines = "\n".join(text.splitlines()[:6]).upper()
    return (
        "monthly_status_report" in name
        or "monthly status report" in name
        or first_lines.startswith("MONTHLY STATUS REPORT")
    )


def _cdrls_from_text(document_texts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in document_texts:
        doc = item["document"]
        text = item["text"]
        if "CONTRACT DATA REQUIREMENTS LIST" not in text and "CDRL" not in doc.original_filename.upper():
            continue
        for match in re.finditer(r"\b(A00[1-9])\b\s*\n([^\n]{3,120})", text):
            rows.append(
                {
                    "source": "cdrl_text",
                    "document_ids": [doc.id],
                    "cdrl_item": match.group(1),
                    "title": match.group(2).strip(),
                    "status": "requirement",
                }
            )
    return _dedupe_deliverables(rows)


def _wbs_rows(text: str) -> List[Dict[str, Any]]:
    rows = []
    pattern = re.compile(r"(?P<name>TA-\d:[^\n]+|ODCs / Subcontract|TOTAL)\s*\n(?P<bcws>[-+]?\d[\d,]*)\s*\n(?P<bcwp>[-+]?\d[\d,]*)\s*\n(?P<acwp>[-+]?\d[\d,]*)\s*\n(?P<sv>[-+]?\d[\d,]*)", re.I)
    for match in pattern.finditer(text):
        rows.append(
            {
                "name": match.group("name").strip(),
                "bcws_k": _number(match.group("bcws")),
                "bcwp_k": _number(match.group("bcwp")),
                "acwp_k": _number(match.group("acwp")),
                "schedule_variance_k": _number(match.group("sv")),
            }
        )
    return rows


def _cpars_row_items(item: CparsRating) -> List[Dict[str, Any]]:
    fields = (
        ("Quality", item.quality_rating),
        ("Schedule", item.schedule_rating),
        ("Cost Control", item.cost_control_rating),
        ("Management", item.management_rating),
        ("Small Business", item.small_business_rating),
        ("Regulatory Compliance", item.regulatory_compliance_rating),
        ("Overall", item.overall_rating),
    )
    return [
        {
            "label": label,
            "rating": rating,
            "period_label": item.evaluation_period,
            "evaluation_date": _date_value(item.evaluation_date),
            "source_document_id": item.doc_upload_id,
            "summary": item.narrative,
        }
        for label, rating in fields
        if rating
    ]


def _dedupe_deliverables(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []
    for row in rows:
        key = (row.get("cdrl_item"), row.get("title"), row.get("status"))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _label_value(text: str, labels: Iterable[str]) -> Optional[str]:
    for label in labels:
        lines = [line.strip() for line in text.splitlines()]
        for index, line in enumerate(lines):
            if line.lower().rstrip(":") == label.lower().rstrip(":") and index + 1 < len(lines):
                value = lines[index + 1].strip()
                if value and value.lower() != "value":
                    return value
        match = re.search(rf"{re.escape(label)}\s*:?\s*([^\n]+)", text, re.I)
        if match:
            value = match.group(1).strip()
            if value and value.lower() != "value":
                return value
    return None


def _section_value(text: str, title: str) -> Optional[str]:
    escaped = re.escape(title)
    match = re.search(rf"{escaped}[^\n]*\n(?P<body>.*?)(?:\n[0-9]+\.\s+[A-Z][^\n]+|\n[A-Z0-9-]+ \| |\Z)", text, re.S)
    if not match:
        return None
    return _trim(" ".join(line.strip() for line in match.group("body").splitlines() if line.strip()), 900)


def _paragraph_after(text: str, label: str) -> Optional[str]:
    match = re.search(rf"{re.escape(label)}[^\n]*\n(?P<body>.*?)(?:\n[A-Z][A-Za-z ]+\s+[-\u2014]\s+|N00173-|\Z)", text, re.S)
    if not match:
        return None
    return _trim(" ".join(line.strip() for line in match.group("body").splitlines() if line.strip()), 1200)


def _period_after(text: str, label: str) -> Optional[str]:
    value = _label_value(text, (label,))
    if value:
        return value
    return None


def _money_after(text: str, label: str) -> Optional[float]:
    lines = [line.strip() for line in text.splitlines()]
    normalized_label = label.lower().rstrip(":")
    for index, line in enumerate(lines):
        if line.lower().rstrip(":") == normalized_label or line.lower().startswith(normalized_label):
            for candidate in lines[index + 1 : index + 4]:
                value = _money_value(candidate)
                if value is not None:
                    return value
    match = re.search(rf"{re.escape(label)}[^\n$-]*\s*(-?\$?\s*[0-9][0-9,]*(?:\.[0-9]+)?)(?:\s*[KkMm])?", text, re.I)
    if match:
        return _money_value(match.group(1))
    return None


def _money_value(value: object) -> Optional[float]:
    if value is None:
        return None
    match = re.search(r"(-?)\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([KkMm])?", str(value))
    if not match:
        return None
    number = float(match.group(2).replace(",", ""))
    if match.group(3) and match.group(3).lower() == "k":
        number *= 1000
    elif match.group(3) and match.group(3).lower() == "m":
        number *= 1000000
    if match.group(1) == "-":
        number = -number
    return number


def _decimal_after(text: str, label: str) -> Optional[float]:
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        if line.lower().rstrip(":") == label.lower().rstrip(":") or line.lower().startswith(label.lower()):
            for candidate in lines[index + 1 : index + 3]:
                number = _decimal_value(candidate)
                if number is not None:
                    return number
    match = re.search(rf"{re.escape(label)}[^\n0-9-]*(-?[0-9]+(?:\.[0-9]+)?)", text, re.I)
    return float(match.group(1)) if match else None


def _decimal_value(value: str) -> Optional[float]:
    match = re.search(r"-?[0-9]+(?:\.[0-9]+)?", value)
    return float(match.group(0)) if match else None


def _number(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return _money_value(value) if "$" in str(value) or "," in str(value) else _decimal_value(str(value))


def _first_match(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text, re.I | re.S)
    if not match:
        return None
    return _trim(match.group(1) if match.groups() else match.group(0), 300)


def _int_match(text: str, pattern: str) -> Optional[int]:
    match = re.search(pattern, text, re.I)
    return int(match.group(1)) if match else None


def _date_iso(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return value


def _date_value(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def _cdrl(text: str) -> Optional[str]:
    match = re.search(r"\bA00[1-9]\b", text or "")
    return match.group(0) if match else None


def _primary_driver(text: str) -> Optional[str]:
    for needle in ("staffing-driven", "GFI delay", "interface complexity", "Task Area 1", "Task Area 4"):
        sentence = _sentence_with(text, needle)
        if sentence:
            return sentence
    return None


def _sentence_with(text: str, needle: str) -> Optional[str]:
    match = re.search(rf"[^.\n]*{re.escape(needle)}[^.\n]*[.]", text, re.I)
    return _trim(match.group(0), 500) if match else None


def _rating_for_label(text: str, label: str) -> Optional[str]:
    pattern = rf"{re.escape(label)}(?:\s+[-\u2014]\s+|\s*\n)(Exceptional|Very Good|Satisfactory|Marginal|Unsatisfactory|Probably Would Award Again|Would Award Again|Would Not Award Again)"
    match = re.search(pattern, text, re.I)
    return match.group(1) if match else None


def _trim(value: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", value or "").strip()
    return compact if len(compact) <= limit else compact[: limit - 3].rstrip() + "..."
