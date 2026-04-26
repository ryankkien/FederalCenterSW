from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BaselineObligation,
    BaselineRevision,
    Contract,
    ContractBaseline,
    ContractHypothesis,
    ContractSimilarityLink,
    DocumentSemanticLink,
    ExternalSourceRef,
    HypothesisEvidence,
    InvestigationRun,
    RegressionFinding,
)


BASELINE_DOCUMENT_KINDS = {"source_contract", "task_order", "modification", "email_context"}
REPORT_DOCUMENT_KINDS = {"weekly_report", "monthly_report"}
OFFICIAL_DOMAIN_SUFFIXES = (".gov", ".mil")
OFFICIAL_DOMAINS = {
    "acquisition.gov",
    "congress.gov",
    "federalregister.gov",
    "gao.gov",
    "oversight.gov",
}


def apply_contract_analysis_pipeline(
    session: Session,
    document: object,
    contract_id: Optional[str],
    text: str,
    chunk_rows: Sequence[object],
    processing_run_id: Optional[str] = None,
) -> None:
    """Run deterministic v1 contract analysis against already-extracted text."""

    if not contract_id:
        classify_document(document, text)
        return

    document_kind, modification_kind = classify_document(document, text)
    if document_kind in BASELINE_DOCUMENT_KINDS:
        update_contract_baseline_from_document(
            session,
            contract_id,
            document,
            text,
            chunk_rows,
            processing_run_id=processing_run_id,
        )
    if document_kind in REPORT_DOCUMENT_KINDS or document_kind == "modification":
        findings = detect_regression_findings(
            session,
            contract_id,
            document,
            text,
            chunk_rows,
            document_kind=document_kind,
            modification_kind=modification_kind,
            processing_run_id=processing_run_id,
        )
        for finding in findings:
            upsert_hypothesis_from_finding(session, finding)
        if findings:
            update_semantic_links(session, contract_id)


def classify_document(document: object, text: str = "") -> Tuple[str, Optional[str]]:
    existing_kind = (_string_attr(document, "document_kind") or "").strip().lower()
    haystack = " ".join(
        value
        for value in (
            _string_attr(document, "original_filename"),
            _string_attr(document, "title"),
            _string_attr(document, "document_type"),
            _string_attr(document, "notes", "description"),
            existing_kind,
            text[:5000],
        )
        if value
    ).lower()

    if _contains_any(haystack, ("rfp", "request for proposal", "source contract", "pws", "sow")):
        document_kind = "source_contract"
    elif _contains_any(haystack, ("task order", "to 000", "delivery order")):
        document_kind = "task_order"
    elif _contains_any(haystack, ("modification", " mod ", "p000", "amendment")):
        document_kind = "modification"
    elif _contains_any(haystack, ("weekly status report", "weekly report", "_wsr-", " wsr-")):
        document_kind = "weekly_report"
    elif _contains_any(haystack, ("monthly status report", "monthly report", "_msr", " msr")):
        document_kind = "monthly_report"
    elif _contains_any(haystack, ("gao", "oig", "inspector general")):
        document_kind = "gao_oig_report"
    elif _contains_any(haystack, ("federal register", "far ", "cfr ", "regulation", "policy")):
        document_kind = "policy_or_regulation"
    elif _contains_any(haystack, ("email", "message-id", "from:", "subject:")):
        document_kind = "email_context"
    elif existing_kind in {
        "source_contract",
        "task_order",
        "modification",
        "weekly_report",
        "monthly_report",
        "gao_oig_report",
        "policy_or_regulation",
        "email_context",
        "other",
    }:
        document_kind = existing_kind
    else:
        document_kind = "other"

    modification_kind = classify_modification_kind(haystack) if document_kind == "modification" else None
    _set_attr(document, "document_kind", document_kind)
    metadata = _metadata(document)
    metadata["classification"] = {
        "document_kind": document_kind,
        "modification_kind": modification_kind,
        "classifier": "deterministic_v1",
    }
    _set_attr(document, "metadata_json", metadata)
    return document_kind, modification_kind


def classify_modification_kind(value: str) -> str:
    text = value.lower()
    if _contains_any(text, ("funding only", "incremental funding", "obligate funds", "funding action")):
        return "funding_only"
    if _contains_any(text, ("period of performance", "pop", "extend", "extension")):
        return "pop_change"
    if _contains_any(text, ("scope", "pws", "sow", "work statement")):
        return "scope_change"
    if _contains_any(text, ("labor category", "labor mix", "staffing", "fte")):
        return "labor_change"
    if _contains_any(text, ("cdrl", "deliverable", "did", "reporting")):
        return "cdrl_change"
    if _contains_any(text, ("clause", "far ", "dfars")):
        return "clause_update"
    if _contains_any(text, ("equitable adjustment", "rea", "settlement")):
        return "equitable_adjustment"
    if _contains_any(text, ("administrative", "correct", "typo", "address change")):
        return "administrative"
    return "unclear"


def update_contract_baseline_from_document(
    session: Session,
    contract_id: str,
    document: Optional[object],
    text: str,
    chunk_rows: Sequence[object],
    processing_run_id: Optional[str] = None,
) -> ContractBaseline:
    baseline = session.scalars(
        select(ContractBaseline).where(ContractBaseline.contract_id == contract_id)
    ).first()
    source_document_id = _string_attr(document, "id")
    if baseline is None:
        baseline = ContractBaseline(
            id=str(uuid4()),
            contract_id=contract_id,
            source_document_upload_id=source_document_id,
            summary=_baseline_summary(text),
            current_revision_number=0,
            confidence=0.55,
            metadata_json={"source": "deterministic_v1"},
        )
        session.add(baseline)
        session.flush()
    else:
        baseline.summary = _baseline_summary(text) or baseline.summary
        if source_document_id and baseline.source_document_upload_id is None:
            baseline.source_document_upload_id = source_document_id

    obligations = extract_baseline_obligations(text)
    created_count = 0
    for obligation in obligations:
        if _baseline_obligation_exists(session, baseline.id, source_document_id, obligation):
            continue
        quote = obligation.get("reference_text")
        chunk = _chunk_for_quote(chunk_rows, quote)
        evidence_hash = hashlib.sha256((quote or obligation["description"]).encode("utf-8")).hexdigest()
        session.add(
            BaselineObligation(
                id=str(uuid4()),
                baseline_id=baseline.id,
                contract_id=contract_id,
                source_document_upload_id=source_document_id,
                chunk_id=_string_attr(chunk, "id") if chunk is not None else None,
                page_id=_page_id_for_chunk(chunk),
                processing_run_id=processing_run_id,
                obligation_type=obligation["obligation_type"],
                title=obligation["title"][:220],
                description=obligation["description"],
                reference_text=quote,
                confidence=obligation.get("confidence", 0.55),
                evidence_hash=evidence_hash,
                metadata_json={"extractor": "deterministic_v1"},
            )
        )
        created_count += 1

    if created_count or baseline.current_revision_number == 0:
        revision_number = baseline.current_revision_number + 1
        baseline.current_revision_number = revision_number
        session.add(
            BaselineRevision(
                id=str(uuid4()),
                baseline_id=baseline.id,
                contract_id=contract_id,
                source_document_upload_id=source_document_id,
                processing_run_id=processing_run_id,
                revision_number=revision_number,
                change_type="baseline_extract",
                summary=f"Added {created_count} baseline obligation(s) from contract source text.",
                created_by_id="agent",
                metadata_json={"document_kind": _string_attr(document, "document_kind")},
            )
        )
    return baseline


def extract_baseline_obligations(text: str) -> List[Dict[str, Any]]:
    lines = _meaningful_lines(text)
    obligations: List[Dict[str, Any]] = []

    for line in lines:
        lower = line.lower()
        if _contains_any(lower, ("service area", "support services", "pws section", "sow", "scope")):
            obligations.append(_obligation("scope", "Scope boundary", line))
        if _contains_any(lower, ("cdrl", "data item", "weekly", "monthly", "status report", "ipmr")):
            obligations.append(_obligation("reporting_cadence", "Reporting deliverable", line))
        if _contains_any(lower, ("cor", "contracting officer", "ko", "written direction")):
            obligations.append(_obligation("authority_rule", "Direction authority", line))
        if _contains_any(lower, ("period of performance", "base pop", "base period", "option year")):
            obligations.append(_obligation("period_of_performance", "Period of performance", line))
        if _contains_any(lower, ("ceiling value", "cost", "schedule", "milestone", "target")):
            obligations.append(_obligation("cost_schedule_expectation", "Cost or schedule expectation", line))
        if _contains_any(lower, ("deliverable", "submission", "format", "did")):
            obligations.append(_obligation("deliverable", "Deliverable requirement", line))

    if not any(item["obligation_type"] == "authority_rule" for item in obligations):
        if "cor" in text.lower() or "contracting officer" in text.lower():
            obligations.append(
                _obligation(
                    "authority_rule",
                    "Direction authority",
                    "Contract work direction should be traceable to the COR or Contracting Officer.",
                )
            )
    if not obligations and text.strip():
        obligations.append(_obligation("scope", "Source contract text", _trim(text.strip(), 800)))

    return _dedupe_obligations(obligations)


def detect_regression_findings(
    session: Session,
    contract_id: str,
    document: object,
    text: str,
    chunk_rows: Sequence[object],
    document_kind: Optional[str] = None,
    modification_kind: Optional[str] = None,
    processing_run_id: Optional[str] = None,
) -> List[RegressionFinding]:
    lower = text.lower()
    if document_kind is None:
        document_kind, modification_kind = classify_document(document, text)
    if document_kind == "modification" and modification_kind == "funding_only":
        return []

    findings: List[RegressionFinding] = []
    if _scope_drift_detected(lower):
        findings.append(
            _create_regression_finding(
                session,
                contract_id,
                document,
                chunk_rows,
                finding_type="scope_drift",
                title="Possible scope drift from informal or non-COR direction",
                summary=(
                    "The report describes work, requests, or planning activity tied to informal "
                    "direction, unclear PWS scope, or work later described as not authorized."
                ),
                severity="high",
                confidence=0.78,
                quote=_snippet(text, ("verbal", "informal", "not authorized", "not in pws scope", "out-of-scope")),
                processing_run_id=processing_run_id,
            )
        )
    if _unauthorized_work_detected(lower):
        findings.append(
            _create_regression_finding(
                session,
                contract_id,
                document,
                chunk_rows,
                finding_type="unauthorized_work_risk",
                title="Unauthorized work risk",
                summary=(
                    "The document indicates contractor activity or requested activity may require "
                    "formal COR/KO direction before work proceeds."
                ),
                severity="high",
                confidence=0.74,
                quote=_snippet(text, ("pending cor", "requires cor", "written cor", "not authorized")),
                processing_run_id=processing_run_id,
            )
        )
    if _rfi_delay_detected(lower):
        findings.append(
            _create_regression_finding(
                session,
                contract_id,
                document,
                chunk_rows,
                finding_type="missing_government_action",
                title="Government action delay",
                summary=(
                    "Open RFIs or pending government decisions appear to be aging beyond a normal "
                    "weekly-report cycle and may require COR/KO action."
                ),
                severity="medium",
                confidence=0.72,
                quote=_snippet(text, ("days open", "pending items", "government action required", "rfi-")),
                processing_run_id=processing_run_id,
            )
        )
    if _schedule_regression_detected(lower):
        findings.append(
            _create_regression_finding(
                session,
                contract_id,
                document,
                chunk_rows,
                finding_type="schedule_regression",
                title="Schedule regression risk",
                summary=(
                    "The document links an unresolved decision, RFI, or dependency to schedule "
                    "slip, critical path risk, missed SLA, or delayed deliverables."
                ),
                severity="medium",
                confidence=0.7,
                quote=_snippet(text, ("schedule risk", "critical path", "slip", "delayed", "missed")),
                processing_run_id=processing_run_id,
            )
        )
    if _cost_regression_detected(lower):
        findings.append(
            _create_regression_finding(
                session,
                contract_id,
                document,
                chunk_rows,
                finding_type="cost_regression",
                title="Cost regression or unfavorable variance",
                summary=(
                    "The document reports unfavorable cost variance, EAC growth, unbudgeted labor, "
                    "or REA exposure tied to contract direction or scope issues."
                ),
                severity="medium",
                confidence=0.7,
                quote=_snippet(text, ("cost variance", "unbudgeted", "eac", "cv", "rea")),
                processing_run_id=processing_run_id,
            )
        )
    if _prior_direction_contradiction_detected(lower):
        findings.append(
            _create_regression_finding(
                session,
                contract_id,
                document,
                chunk_rows,
                finding_type="prior_direction_contradiction",
                title="Prior direction contradicted or superseded",
                summary=(
                    "The document describes prior verbal or informal direction later superseded by "
                    "written COR direction, creating rework or disposition risk."
                ),
                severity="medium",
                confidence=0.68,
                quote=_snippet(text, ("superseded", "verbal vs. written", "written cor direction", "controlling")),
                processing_run_id=processing_run_id,
            )
        )
    if _reporting_defect_detected(lower):
        findings.append(
            _create_regression_finding(
                session,
                contract_id,
                document,
                chunk_rows,
                finding_type="cdrl_mismatch",
                title="CDRL or reporting-format mismatch",
                summary=(
                    "The document references uncertainty or mismatch in required report, "
                    "deliverable, DID, CDRL, or government format."
                ),
                severity="low",
                confidence=0.62,
                quote=_snippet(text, ("cdrl", "deliverable format", "template", "did", "format")),
                processing_run_id=processing_run_id,
            )
        )

    return [finding for finding in findings if finding is not None]


def upsert_hypothesis_from_finding(
    session: Session,
    finding: RegressionFinding,
) -> Optional[ContractHypothesis]:
    key, title, narrative = _hypothesis_descriptor(finding.finding_type)
    if not key:
        return None

    hypothesis = session.scalars(
        select(ContractHypothesis).where(
            ContractHypothesis.contract_id == finding.contract_id,
            ContractHypothesis.hypothesis_key == key,
        )
    ).first()
    if hypothesis is None:
        hypothesis = ContractHypothesis(
            id=str(uuid4()),
            contract_id=finding.contract_id,
            hypothesis_key=key,
            title=title,
            narrative=narrative,
            status="proposed",
            confidence=0.35,
            created_by_id="agent",
            metadata_json={"source": "regression_finding"},
        )
        session.add(hypothesis)
        session.flush()

    existing_evidence = session.scalars(
        select(HypothesisEvidence).where(
            HypothesisEvidence.hypothesis_id == hypothesis.id,
            HypothesisEvidence.regression_finding_id == finding.id,
        )
    ).first()
    if existing_evidence is None:
        session.add(
            HypothesisEvidence(
                id=str(uuid4()),
                hypothesis_id=hypothesis.id,
                regression_finding_id=finding.id,
                document_upload_id=finding.document_upload_id,
                chunk_id=finding.chunk_id,
                page_id=getattr(finding, "page_id", None),
                processing_run_id=getattr(finding, "processing_run_id", None),
                evidence_type="supporting",
                quote=finding.quote,
                summary=finding.summary,
                confidence=finding.confidence,
                evidence_hash=getattr(finding, "evidence_hash", None),
                metadata_json={"finding_type": finding.finding_type},
            )
        )
    refresh_hypothesis_status(session, hypothesis)
    return hypothesis


def refresh_hypothesis_status(session: Session, hypothesis: ContractHypothesis) -> ContractHypothesis:
    evidence_rows = list(
        session.scalars(
            select(HypothesisEvidence).where(HypothesisEvidence.hypothesis_id == hypothesis.id)
        ).all()
    )
    supporting = [row for row in evidence_rows if row.evidence_type == "supporting"]
    contradicting = [row for row in evidence_rows if row.evidence_type == "contradicting"]

    if hypothesis.status == "closed":
        return hypothesis
    contradiction_confidence = max((row.confidence or 0.0 for row in contradicting), default=0.0)
    if contradicting and (contradiction_confidence >= 0.7 or len(contradicting) >= len(supporting)):
        hypothesis.status = "contradicted"
        hypothesis.confidence = 0.2
    elif len(supporting) >= 2:
        hypothesis.status = "supported"
        hypothesis.confidence = min(0.9, 0.62 + (0.04 * len(supporting)))
    elif supporting:
        hypothesis.status = "investigating"
        hypothesis.confidence = max(hypothesis.confidence or 0.0, 0.5)
    else:
        hypothesis.status = "proposed"
        hypothesis.confidence = hypothesis.confidence or 0.25
    return hypothesis


def update_semantic_links(session: Session, contract_id: Optional[str] = None) -> None:
    contract_ids = _contract_ids_with_findings(session)
    if contract_id and contract_id not in contract_ids:
        contract_ids.append(contract_id)

    tags_by_contract = {item: _contract_tags(session, item) for item in contract_ids}
    for index, source_contract_id in enumerate(contract_ids):
        for target_contract_id in contract_ids[index + 1 :]:
            source_tags = tags_by_contract.get(source_contract_id, set())
            target_tags = tags_by_contract.get(target_contract_id, set())
            shared = sorted(source_tags & target_tags)
            if not shared:
                continue
            union = source_tags | target_tags
            score = len(shared) / max(len(union), 1)
            _upsert_contract_similarity_link(
                session,
                source_contract_id,
                target_contract_id,
                shared,
                score,
            )

    _update_document_semantic_links(session)


def is_official_external_source(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    domain = parsed.netloc.lower().split("@")[-1].split(":")[0].strip(".")
    if not domain:
        return False
    if domain in OFFICIAL_DOMAINS:
        return True
    if any(domain.endswith(suffix) for suffix in OFFICIAL_DOMAIN_SUFFIXES):
        return True
    return any(domain.endswith(f".{official}") for official in OFFICIAL_DOMAINS)


def create_external_source_ref(
    session: Session,
    url: str,
    contract_id: Optional[str] = None,
    investigation_run_id: Optional[str] = None,
    hypothesis_id: Optional[str] = None,
    title: Optional[str] = None,
    citation_text: Optional[str] = None,
) -> ExternalSourceRef:
    if not is_official_external_source(url):
        raise ValueError("External research source is not in the official-source allowlist")
    domain = urlparse(url).netloc.lower().split("@")[-1].split(":")[0].strip(".")
    row = ExternalSourceRef(
        id=str(uuid4()),
        contract_id=contract_id,
        investigation_run_id=investigation_run_id,
        hypothesis_id=hypothesis_id,
        url=url,
        title=title,
        source_domain=domain,
        source_type="official",
        citation_text=citation_text,
        is_official=True,
        confidence=0.5,
        evidence_hash=hashlib.sha256((url + (citation_text or "")).encode("utf-8")).hexdigest(),
        metadata_json={"validator": "official_source_allowlist_v1"},
    )
    session.add(row)
    return row


def create_investigation_run(
    session: Session,
    hypothesis: ContractHypothesis,
    question: str,
    created_by_id: Optional[str] = None,
    external_sources: Optional[Sequence[Dict[str, str]]] = None,
) -> InvestigationRun:
    sources = list(external_sources or [])
    for source in sources:
        if not is_official_external_source(source.get("url", "")):
            raise ValueError("External research source is not in the official-source allowlist")

    run = InvestigationRun(
        id=str(uuid4()),
        contract_id=hypothesis.contract_id,
        hypothesis_id=hypothesis.id,
        question=question,
        status="completed",
        sources_checked=sources,
        result_summary=(
            "Investigation logged. V1 records the question and official sources; "
            "contract-file evidence remains authoritative for findings."
        ),
        confidence=0.5 if sources else 0.35,
        created_by_id=created_by_id,
        metadata_json={"research_policy": "official_sources_only_v1"},
    )
    session.add(run)
    session.flush()
    for source in sources:
        create_external_source_ref(
            session,
            url=source["url"],
            contract_id=hypothesis.contract_id,
            investigation_run_id=run.id,
            hypothesis_id=hypothesis.id,
            title=source.get("title"),
            citation_text=source.get("citation_text"),
        )
    return run


def seed_contract_from_markdown(
    session: Session,
    markdown_text: str,
    source_name: Optional[str] = None,
) -> Optional[Contract]:
    metadata = parse_contract_markdown_metadata(markdown_text)
    contract_number = metadata.get("contract_number")
    if not contract_number:
        return None

    contract = session.scalars(
        select(Contract).where(Contract.contract_number == contract_number)
    ).first()
    if contract is None:
        contract = Contract(
            id=contract_number[:36],
            contract_number=contract_number,
            title=metadata.get("title") or contract_number,
            description=metadata.get("description"),
            vendor_name=metadata.get("contractor"),
            vendor_uei=metadata.get("contractor_uei"),
            metadata_json={"fixture_source": source_name, "contract_type": metadata.get("contract_type")},
        )
        session.add(contract)
        session.flush()
    else:
        contract.title = metadata.get("title") or contract.title
        contract.vendor_name = metadata.get("contractor") or contract.vendor_name
        contract.vendor_uei = metadata.get("contractor_uei") or contract.vendor_uei

    baseline = update_contract_baseline_from_document(session, contract.id, None, markdown_text, [])
    baseline.metadata_json = {
        **(baseline.metadata_json or {}),
        "fixture_source": source_name,
        "seeded_from_markdown": True,
    }
    return contract


def seed_natalie_fixture_contracts(
    session: Session,
    fixture_root: Path = Path("testdocs/natalies/reports_markdown"),
) -> List[Contract]:
    contracts = []
    if not fixture_root.exists():
        return contracts
    for path in sorted(fixture_root.glob("*.md")):
        contract = seed_contract_from_markdown(
            session,
            path.read_text(encoding="utf-8"),
            source_name=str(path),
        )
        if contract is not None:
            contracts.append(contract)
    return contracts


def parse_contract_markdown_metadata(markdown_text: str) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    title_match = re.search(r"#\s+Contract\s+([A-Z0-9-]+)\s+[—-]\s+(.+)", markdown_text)
    if title_match:
        metadata["contract_number"] = title_match.group(1).strip().upper()
        metadata["description"] = title_match.group(2).strip()

    field_map = {
        "Contract Title": "title",
        "Contractor": "contractor",
        "Contractor UEI": "contractor_uei",
        "Contract Type": "contract_type",
        "Ceiling Value": "ceiling_value",
        "Base PoP": "base_pop",
        "Base Period of Performance": "base_pop",
        "COR": "cor",
        "KO": "ko",
        "CDRL Reference": "cdrl",
    }
    for label, key in field_map.items():
        pattern = rf"\*\*{re.escape(label)}:\*\*\s*(.+)"
        match = re.search(pattern, markdown_text)
        if match:
            metadata[key] = match.group(1).strip()
    return metadata


def _create_regression_finding(
    session: Session,
    contract_id: str,
    document: object,
    chunk_rows: Sequence[object],
    finding_type: str,
    title: str,
    summary: str,
    severity: str,
    confidence: float,
    quote: str,
    processing_run_id: Optional[str] = None,
) -> Optional[RegressionFinding]:
    document_id = _string_attr(document, "id")
    quote_hash = hashlib.sha256((quote or summary).encode("utf-8")).hexdigest()
    existing = _existing_finding(session, document_id, finding_type, quote_hash)
    if existing is not None:
        return existing

    chunk = _chunk_for_quote(chunk_rows, quote)
    obligation = _baseline_obligation_for_finding(session, contract_id, finding_type)
    finding = RegressionFinding(
        id=str(uuid4()),
        contract_id=contract_id,
        document_upload_id=document_id,
        chunk_id=_string_attr(chunk, "id") if chunk is not None else None,
        page_id=_page_id_for_chunk(chunk),
        processing_run_id=processing_run_id,
        baseline_obligation_id=obligation.id if obligation is not None else None,
        finding_type=finding_type,
        title=title,
        summary=summary,
        severity=severity,
        status="open",
        confidence=confidence,
        quote=quote,
        evidence_hash=quote_hash,
        metadata_json={
            "quote_hash": quote_hash,
            "detector": "deterministic_v1",
            "baseline_obligation_type": obligation.obligation_type if obligation else None,
        },
    )
    session.add(finding)
    session.flush()
    return finding


def _existing_finding(
    session: Session,
    document_id: Optional[str],
    finding_type: str,
    quote_hash: str,
) -> Optional[RegressionFinding]:
    if not document_id:
        return None
    rows = list(
        session.scalars(
            select(RegressionFinding).where(
                RegressionFinding.document_upload_id == document_id,
                RegressionFinding.finding_type == finding_type,
            )
        ).all()
    )
    for row in rows:
        metadata = row.metadata_json or {}
        if metadata.get("quote_hash") == quote_hash:
            return row
    return None


def _baseline_obligation_for_finding(
    session: Session,
    contract_id: str,
    finding_type: str,
) -> Optional[BaselineObligation]:
    preferred = {
        "scope_drift": ("scope", "authority_rule"),
        "unauthorized_work_risk": ("authority_rule", "scope"),
        "missing_government_action": ("authority_rule", "reporting_cadence"),
        "schedule_regression": ("cost_schedule_expectation", "period_of_performance"),
        "cost_regression": ("cost_schedule_expectation", "scope"),
        "prior_direction_contradiction": ("authority_rule", "scope"),
        "cdrl_mismatch": ("reporting_cadence", "deliverable"),
    }.get(finding_type, ())
    for obligation_type in preferred:
        row = session.scalars(
            select(BaselineObligation).where(
                BaselineObligation.contract_id == contract_id,
                BaselineObligation.obligation_type == obligation_type,
            )
        ).first()
        if row is not None:
            return row
    return session.scalars(
        select(BaselineObligation).where(BaselineObligation.contract_id == contract_id)
    ).first()


def _baseline_obligation_exists(
    session: Session,
    baseline_id: str,
    source_document_id: Optional[str],
    obligation: Dict[str, Any],
) -> bool:
    rows = list(
        session.scalars(
            select(BaselineObligation).where(
                BaselineObligation.baseline_id == baseline_id,
                BaselineObligation.obligation_type == obligation["obligation_type"],
            )
        ).all()
    )
    for row in rows:
        if (
            row.source_document_upload_id == source_document_id
            and row.title == obligation["title"][:220]
            and row.reference_text == obligation.get("reference_text")
        ):
            return True
    return False


def _update_document_semantic_links(session: Session) -> None:
    rows = list(session.scalars(select(RegressionFinding)).all())
    for index, source in enumerate(rows):
        for target in rows[index + 1 :]:
            if not source.document_upload_id or not target.document_upload_id:
                continue
            if source.document_upload_id == target.document_upload_id:
                continue
            if source.finding_type != target.finding_type:
                continue
            source_id, target_id = sorted([source.document_upload_id, target.document_upload_id])
            existing = session.scalars(
                select(DocumentSemanticLink).where(
                    DocumentSemanticLink.source_document_upload_id == source_id,
                    DocumentSemanticLink.target_document_upload_id == target_id,
                    DocumentSemanticLink.link_type == source.finding_type,
                )
            ).first()
            if existing is not None:
                continue
            session.add(
                DocumentSemanticLink(
                    id=str(uuid4()),
                    source_document_upload_id=source_id,
                    target_document_upload_id=target_id,
                    link_type=source.finding_type,
                    summary=f"Both documents contain {source.finding_type.replace('_', ' ')} evidence.",
                    score=0.75,
                    metadata_json={"created_by": "semantic_linker_v1"},
                )
            )


def _upsert_contract_similarity_link(
    session: Session,
    source_contract_id: str,
    target_contract_id: str,
    shared_tags: Sequence[str],
    score: float,
) -> None:
    source_id, target_id = sorted([source_contract_id, target_contract_id])
    link_type = "shared_regression_patterns"
    existing = session.scalars(
        select(ContractSimilarityLink).where(
            ContractSimilarityLink.source_contract_id == source_id,
            ContractSimilarityLink.target_contract_id == target_id,
            ContractSimilarityLink.link_type == link_type,
        )
    ).first()
    summary = "Shared pattern(s): " + ", ".join(shared_tags)
    if existing is not None:
        existing.summary = summary
        existing.score = max(existing.score or 0.0, score)
        existing.metadata_json = {"shared_tags": list(shared_tags)}
        return
    session.add(
        ContractSimilarityLink(
            id=str(uuid4()),
            source_contract_id=source_id,
            target_contract_id=target_id,
            link_type=link_type,
            summary=summary,
            score=score,
            metadata_json={"shared_tags": list(shared_tags), "created_by": "semantic_linker_v1"},
        )
    )


def _contract_ids_with_findings(session: Session) -> List[str]:
    ids = list(session.scalars(select(RegressionFinding.contract_id).distinct()).all())
    return sorted(str(item) for item in ids if item)


def _contract_tags(session: Session, contract_id: str) -> Set[str]:
    rows = list(
        session.scalars(
            select(RegressionFinding).where(RegressionFinding.contract_id == contract_id)
        ).all()
    )
    tags = {row.finding_type for row in rows}
    for row in rows:
        text = " ".join([row.title, row.summary, row.quote or ""]).lower()
        if "rfi" in text:
            tags.add("rfi_delay")
        if "verbal" in text or "informal" in text or "tenant" in text:
            tags.add("tenant_direction")
        if "cost" in text or "variance" in text or "eac" in text:
            tags.add("cost_pressure")
    return tags


def _hypothesis_descriptor(finding_type: str) -> Tuple[Optional[str], str, str]:
    if finding_type in {"scope_drift", "unauthorized_work_risk", "prior_direction_contradiction"}:
        return (
            "non-cor-direction-scope-ambiguity",
            "Tenant or informal direction may be bypassing COR authority",
            (
                "Repeated evidence suggests informal stakeholder direction or ambiguous PWS scope "
                "may be causing work authorization risk, rework, or scope drift."
            ),
        )
    if finding_type in {"missing_government_action", "schedule_regression"}:
        return (
            "aging-rfis-government-action-delay",
            "Aging RFIs or government actions may be delaying performance",
            (
                "Reports indicate unresolved RFIs or government decisions may be accumulating "
                "and affecting schedule, cost, or delivery commitments."
            ),
        )
    if finding_type == "cost_regression":
        return (
            "cost-variance-out-of-scope-or-superseded-direction",
            "Cost variance may be tied to out-of-scope or superseded direction",
            (
                "Cost growth appears linked to unbudgeted labor, rework, REA exposure, or direction "
                "that may sit outside the current baseline."
            ),
        )
    if finding_type == "cdrl_mismatch":
        return (
            "reporting-deliverable-alignment",
            "Reporting or deliverable requirements may be misaligned",
            (
                "Evidence points to uncertainty in CDRL, DID, reporting template, or deliverable "
                "format expectations."
            ),
        )
    return None, "", ""


def _scope_drift_detected(text: str) -> bool:
    return (
        _contains_any(text, ("out-of-scope", "out of scope", "not in pws scope", "not in scope"))
        or (
            _contains_any(
                text,
                ("verbal", "informal", "tenant command", "directly", "directed", "direction"),
            )
            and _contains_any(
                text,
                (
                    "scope",
                    "pws",
                    "cor",
                    "pending cor",
                    "not authorized",
                    "requires",
                    "confirmation",
                    "modification",
                    "add ",
                    "additional",
                    "expand",
                ),
            )
        )
    )


def _unauthorized_work_detected(text: str) -> bool:
    return _contains_any(
        text,
        (
            "not authorized",
            "pending cor direction",
            "requires cor approval",
            "requires cor direction",
            "written cor direction",
            "non-cor direction",
        ),
    )


def _rfi_delay_detected(text: str) -> bool:
    if "rfi" not in text:
        return False
    for value in re.findall(r"(\d+)\s+days?\s+open", text):
        try:
            if int(value) >= 14:
                return True
        except ValueError:
            continue
    return _contains_any(text, ("government action required", "pending government", "rfis open"))


def _schedule_regression_detected(text: str) -> bool:
    return _contains_any(
        text,
        ("schedule risk", "critical path", "schedule slip", "slippage", "delayed deliverable", "missed sla"),
    ) or (_rfi_delay_detected(text) and _contains_any(text, ("schedule", "critical", "milestone", "delay")))


def _cost_regression_detected(text: str) -> bool:
    return _contains_any(
        text,
        ("cost variance", "unbudgeted", "eac", "cv %", "over cbb", "burn rate", "rea", "cost regression"),
    )


def _prior_direction_contradiction_detected(text: str) -> bool:
    return _contains_any(
        text,
        ("superseded", "verbal vs. written", "written cor direction is controlling", "controlling direction"),
    ) or (
        _contains_any(text, ("verbal", "informal"))
        and _contains_any(text, ("written cor", "subsequent cor", "later determined"))
    )


def _reporting_defect_detected(text: str) -> bool:
    return _contains_any(
        text,
        (
            "cdrl mismatch",
            "deliverable format",
            "report format",
            "template will be issued",
            "template references",
            "did",
        ),
    )


def _chunk_for_quote(chunk_rows: Sequence[object], quote: Optional[str]) -> Optional[object]:
    if not chunk_rows:
        return None
    if quote:
        for chunk in chunk_rows:
            if quote in (_string_attr(chunk, "text") or ""):
                return chunk
    return chunk_rows[0]


def _page_id_for_chunk(chunk: Optional[object]) -> Optional[str]:
    if chunk is None:
        return None
    metadata = getattr(chunk, "metadata_json", None) or {}
    if isinstance(metadata, dict):
        page_ids = metadata.get("page_ids")
        if isinstance(page_ids, list) and page_ids:
            return str(page_ids[0])
    return _string_attr(chunk, "page_id")


def _snippet(text: str, keywords: Sequence[str], size: int = 420) -> str:
    lower = text.lower()
    indexes = [lower.find(keyword.lower()) for keyword in keywords if lower.find(keyword.lower()) >= 0]
    start = max(0, (min(indexes) if indexes else 0) - 140)
    end = min(len(text), start + size)
    return _trim(text[start:end].strip(), size)


def _baseline_summary(text: str) -> str:
    lines = _meaningful_lines(text)
    if not lines:
        return "No baseline text is available yet."
    return _trim(" ".join(lines[:4]), 1200)


def _meaningful_lines(text: str) -> List[str]:
    lines = []
    for line in text.splitlines():
        cleaned = re.sub(r"\s+", " ", line.strip(" -*\t|"))
        if cleaned and len(cleaned) > 6:
            lines.append(cleaned)
    return lines


def _obligation(obligation_type: str, title: str, reference_text: str) -> Dict[str, Any]:
    return {
        "obligation_type": obligation_type,
        "title": title,
        "description": reference_text,
        "reference_text": reference_text,
        "confidence": 0.6,
    }


def _dedupe_obligations(items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for item in items:
        key = (item["obligation_type"], item["reference_text"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:60]


def _contains_any(value: str, needles: Sequence[str]) -> bool:
    return any(needle in value for needle in needles)


def _metadata(item: object) -> Dict[str, Any]:
    metadata = getattr(item, "metadata_json", None)
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}


def _set_attr(item: object, name: str, value: object) -> None:
    if hasattr(item, name):
        setattr(item, name, value)


def _string_attr(item: object, *names: str) -> Optional[str]:
    if item is None:
        return None
    for name in names:
        value = item.get(name) if isinstance(item, dict) else getattr(item, name, None)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _trim(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."
