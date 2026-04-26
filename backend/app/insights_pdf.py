from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.models import Contract, ContractHypothesis, HypothesisEvidence, RegressionFinding


INK = HexColor("#0A1929")
INK_SOFT = HexColor("#27384F")
INK_MUTE = HexColor("#4D5A72")
INK_FAINT = HexColor("#8492A6")
SURFACE_ALT = HexColor("#F4F6F9")
BORDER = HexColor("#CCD2DC")
BORDER_MD = HexColor("#A6B0C0")
ACCENT = HexColor("#11447A")

FLAG_FG = HexColor("#9B3A1E")
FLAG_BG = HexColor("#F7ECE9")
WARN_FG = HexColor("#7A5310")
WARN_BG = HexColor("#F8F1E2")
GOOD_FG = HexColor("#2F5D45")
GOOD_BG = HexColor("#E8F0EB")


def build_contract_insights_pdf(
    contract: Contract,
    findings: Sequence[RegressionFinding],
    hypotheses: Sequence[Tuple[ContractHypothesis, Sequence[HypothesisEvidence]]],
    analysis_log: Sequence[dict],
    *,
    document_titles: Optional[dict] = None,
    generated_at: Optional[datetime] = None,
) -> bytes:
    """Render a per-contract Insights report as a PDF byte string."""

    document_titles = document_titles or {}
    generated_at = generated_at or datetime.now(timezone.utc)

    buffer = BytesIO()
    page_width, page_height = LETTER
    margin = 0.75 * inch

    doc = BaseDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin + 0.25 * inch,
        title=f"Insights — {contract.contract_number}",
        author="FedCenter",
    )
    frame = Frame(
        margin,
        margin,
        page_width - 2 * margin,
        page_height - 2 * margin - 0.25 * inch,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        showBoundary=0,
    )
    contract_label = contract.contract_number or contract.id

    def _draw_footer(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(INK_FAINT)
        canvas.setFont("Courier", 8)
        footer = f"FedCenter Insights · Contract {contract_label} · page {_doc.page}"
        canvas.drawString(margin, margin * 0.5, footer)
        canvas.restoreState()

    doc.addPageTemplates([
        PageTemplate(id="default", frames=[frame], onPage=_draw_footer),
    ])

    styles = _styles()
    story: List[Any] = []
    story.extend(_masthead(contract, generated_at, styles))
    story.extend(_findings_section(findings, document_titles, styles))
    story.extend(_hypotheses_section(hypotheses, styles))
    story.extend(_analysis_log_section(analysis_log, styles))

    doc.build(story)
    return buffer.getvalue()


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "label": ParagraphStyle(
            "label",
            parent=base["Normal"],
            fontName="Courier-Bold",
            fontSize=8.5,
            textColor=INK_MUTE,
            spaceAfter=4,
            leading=10,
        ),
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=4,
            leading=24,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=9,
            textColor=INK_MUTE,
            spaceAfter=2,
            leading=12,
        ),
        "section": ParagraphStyle(
            "section",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=INK,
            spaceBefore=18,
            spaceAfter=4,
            leading=16,
        ),
        "section_sub": ParagraphStyle(
            "section_sub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=INK_MUTE,
            spaceAfter=10,
            leading=12,
        ),
        "claim": ParagraphStyle(
            "claim",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=INK,
            spaceAfter=6,
            leading=15,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            textColor=INK_SOFT,
            spaceAfter=4,
            leading=14,
        ),
        "body_mute": ParagraphStyle(
            "body_mute",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=INK_MUTE,
            spaceAfter=4,
            leading=13,
        ),
        "body_quote": ParagraphStyle(
            "body_quote",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9.5,
            textColor=INK_MUTE,
            leftIndent=10,
            spaceAfter=4,
            leading=12.5,
        ),
        "kicker": ParagraphStyle(
            "kicker",
            parent=base["Normal"],
            fontName="Courier-Bold",
            fontSize=8,
            textColor=INK_MUTE,
            spaceAfter=2,
            leading=10,
        ),
        "empty": ParagraphStyle(
            "empty",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=10.5,
            textColor=INK_FAINT,
            spaceAfter=10,
            leading=14,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=INK_SOFT,
            leading=12,
        ),
        "table_cell_mono": ParagraphStyle(
            "table_cell_mono",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=8.5,
            textColor=INK_MUTE,
            leading=11,
        ),
    }


def _masthead(contract: Contract, generated_at: datetime, styles: dict) -> List[Any]:
    metadata = contract.metadata_json if isinstance(contract.metadata_json, dict) else {}
    obligated = metadata.get("obligated_value")
    value_str: str
    if obligated in (None, ""):
        value_str = "Value TBD"
    else:
        try:
            value_str = f"${int(float(obligated)):,}"
        except (TypeError, ValueError):
            value_str = str(obligated)

    psc = contract.psc_code or "Uncoded PSC"
    naics = contract.naics_code or "—"
    component = contract.office_name or contract.agency_name or "Unassigned"
    title = contract.title or contract.contract_number or contract.id

    elements: List[Any] = [
        Paragraph("FEDCENTER · CONTRACT INSIGHTS REPORT", styles["label"]),
        Paragraph(f"{contract.contract_number}", styles["title"]),
        Paragraph(_html_escape(title), styles["body"]),
        Spacer(1, 6),
        Paragraph(
            f"PSC {_html_escape(psc)} · NAICS {_html_escape(naics)} · {_html_escape(component)} · {_html_escape(value_str)}",
            styles["meta"],
        ),
        Paragraph(
            f"Generated {generated_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            styles["meta"],
        ),
        Spacer(1, 4),
        _rule(),
    ]
    return elements


def _findings_section(
    findings: Sequence[RegressionFinding],
    document_titles: dict,
    styles: dict,
) -> List[Any]:
    elements: List[Any] = [
        Paragraph("Findings", styles["section"]),
        Paragraph(
            f"{len(findings)} extracted finding{'s' if len(findings) != 1 else ''} from regressions and lifecycle extraction",
            styles["section_sub"],
        ),
    ]
    if not findings:
        elements.append(Paragraph(
            "No extracted findings. Process documents or upload reports with extractable performance issues to populate this section.",
            styles["empty"],
        ))
        return elements

    for finding in findings:
        sev_label, sev_fg, sev_bg = _severity_palette(finding.severity)
        source_doc = document_titles.get(finding.document_upload_id) or finding.document_upload_id or "Unknown source"
        header_row = [
            _pill(sev_label, sev_fg, sev_bg),
            Paragraph(
                f"<font face='Courier' size='8' color='#4D5A72'>SOURCE → {_html_escape(str(source_doc))}</font>",
                styles["kicker"],
            ),
        ]
        header_table = Table(
            [header_row],
            colWidths=[1.0 * inch, None],
        )
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        block: List[Any] = [
            header_table,
            Paragraph(_html_escape(finding.title or "Untitled finding"), styles["claim"]),
            Paragraph(
                f"<b>Observed:</b> {_html_escape(finding.summary or '—')}",
                styles["body"],
            ),
        ]
        if finding.quote:
            block.append(Paragraph(f"“{_html_escape(finding.quote)}”", styles["body_quote"]))
        block.append(Spacer(1, 4))
        block.append(_card_divider(sev_fg))
        block.append(Spacer(1, 10))
        elements.append(KeepTogether(block))
    return elements


def _hypotheses_section(
    hypotheses: Sequence[Tuple[ContractHypothesis, Sequence[HypothesisEvidence]]],
    styles: dict,
) -> List[Any]:
    elements: List[Any] = [
        Paragraph("Hypotheses", styles["section"]),
        Paragraph(
            f"{len(hypotheses)} hypothes{'es' if len(hypotheses) != 1 else 'is'} tracked on this contract",
            styles["section_sub"],
        ),
    ]
    if not hypotheses:
        elements.append(Paragraph(
            "No hypotheses recorded. Hypotheses are proposed by the cross-contract agent or analysts during investigation.",
            styles["empty"],
        ))
        return elements

    for hypothesis, evidence in hypotheses:
        status_label, status_fg, status_bg = _hypothesis_status_palette(hypothesis.status)
        confidence = hypothesis.confidence
        conf_str = f" · confidence {int(confidence * 100)}%" if isinstance(confidence, (int, float)) else ""
        header_row = [
            _pill(status_label, status_fg, status_bg),
            Paragraph(
                f"<font face='Courier' size='8' color='#4D5A72'>{_html_escape(hypothesis.hypothesis_key or '')}{_html_escape(conf_str)}</font>",
                styles["kicker"],
            ),
        ]
        header_table = Table([header_row], colWidths=[1.0 * inch, None])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        block: List[Any] = [
            header_table,
            Paragraph(_html_escape(hypothesis.title or "Untitled hypothesis"), styles["claim"]),
        ]
        narrative = hypothesis.narrative or ""
        for chunk in _paragraphs(narrative):
            block.append(Paragraph(_html_escape(chunk), styles["body"]))

        if evidence:
            block.append(Spacer(1, 2))
            block.append(Paragraph("EVIDENCE", styles["kicker"]))
            for item in evidence:
                bullet = item.summary or item.quote or "(no summary)"
                block.append(Paragraph(f"• {_html_escape(_trim(bullet, 320))}", styles["body_mute"]))
                if item.quote and item.quote != item.summary:
                    block.append(Paragraph(f"“{_html_escape(_trim(item.quote, 240))}”", styles["body_quote"]))

        block.append(Spacer(1, 4))
        block.append(_card_divider(status_fg))
        block.append(Spacer(1, 10))
        elements.append(KeepTogether(block))
    return elements


def _analysis_log_section(analysis_log: Sequence[dict], styles: dict) -> List[Any]:
    elements: List[Any] = [
        Paragraph("Analysis history", styles["section"]),
        Paragraph(
            f"{len(analysis_log)} analysis run{'s' if len(analysis_log) != 1 else ''} · per-contract incremental + cross-contract pattern runs",
            styles["section_sub"],
        ),
    ]
    if not analysis_log:
        elements.append(Paragraph(
            "No analysis runs yet. Click 'Generate New Insights' from the Insights Library to run the first analysis on this contract.",
            styles["empty"],
        ))
        return elements

    header_row = [
        Paragraph("<b>DATE</b>", styles["kicker"]),
        Paragraph("<b>TYPE</b>", styles["kicker"]),
        Paragraph("<b>STATUS</b>", styles["kicker"]),
        Paragraph("<b>SUMMARY</b>", styles["kicker"]),
    ]
    rows: List[List[Any]] = [header_row]
    cross_contract_row_indices: List[int] = []

    for index, entry in enumerate(analysis_log, start=1):
        is_cross = entry.get("run_type") == "cross_contract"
        if is_cross:
            cross_contract_row_indices.append(index)
        completed_at = entry.get("completed_at") or entry.get("created_at")
        date_str = "In progress…"
        if isinstance(completed_at, datetime):
            date_str = completed_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
        elif isinstance(completed_at, str):
            date_str = completed_at[:16].replace("T", " ")

        if is_cross:
            investigated = len(entry.get("investigated_contract_ids") or [])
            type_label = f"Cross-contract\n{investigated} related contract{'s' if investigated != 1 else ''}"
        else:
            doc_count = entry.get("analyzed_doc_count") or 0
            incremental = " · incremental" if entry.get("prior_run_id") else " · baseline"
            type_label = f"Per-contract\n{doc_count} doc{'s' if doc_count != 1 else ''}{incremental}"

        status = entry.get("status") or "unknown"
        summary_text = entry.get("summary") or "—"
        summary_para = Paragraph(_html_escape(_trim(summary_text, 600)), styles["table_cell"])

        changes = entry.get("changes") or []
        if changes:
            change_lines = "<br/>".join(
                f"<font face='Courier' size='8' color='#4D5A72'>{_html_escape((ch.get('axis') or ''))} · {_html_escape((ch.get('change_type') or '').replace('_',' '))}</font>"
                for ch in changes[:6]
            )
            summary_para = Paragraph(
                f"{_html_escape(_trim(summary_text, 500))}<br/><br/>{change_lines}",
                styles["table_cell"],
            )

        rows.append([
            Paragraph(_html_escape(date_str), styles["table_cell_mono"]),
            Paragraph(_html_escape(type_label), styles["table_cell"]),
            Paragraph(_html_escape(status.upper()), styles["table_cell_mono"]),
            summary_para,
        ])

    table = Table(
        rows,
        colWidths=[1.05 * inch, 1.4 * inch, 0.85 * inch, None],
        repeatRows=1,
    )
    style_cmds: List[tuple] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("BACKGROUND", (0, 0), (-1, 0), SURFACE_ALT),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for row_index in cross_contract_row_indices:
        style_cmds.append(("LINEBEFORE", (0, row_index), (0, row_index), 2.5, ACCENT))
    table.setStyle(TableStyle(style_cmds))
    elements.append(table)
    return elements


def _pill(label: str, fg: HexColor, bg: HexColor) -> Table:
    cell = Paragraph(
        _html_escape(label.upper()),
        ParagraphStyle("pill", fontName="Courier-Bold", fontSize=8, textColor=fg, alignment=TA_LEFT),
    )
    table = Table([[cell]], colWidths=[0.95 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.5, fg),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _rule() -> Table:
    rule = Table([[""]], colWidths=[None], rowHeights=[1])
    rule.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1.4, INK),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return rule


def _card_divider(accent: HexColor) -> Table:
    rule = Table([[""]], colWidths=[None], rowHeights=[1])
    rule.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, BORDER),
        ("LINEBEFORE", (0, 0), (0, 0), 2, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return rule


def _severity_palette(severity: Optional[str]) -> Tuple[str, HexColor, HexColor]:
    normalized = (severity or "").strip().lower()
    if normalized in {"critical", "high", "severe"}:
        return "Critical", FLAG_FG, FLAG_BG
    if normalized in {"medium", "moderate", "watch", "warning", "low"}:
        return "Watch", WARN_FG, WARN_BG
    if normalized in {"healthy", "positive", "good"}:
        return "Healthy", GOOD_FG, GOOD_BG
    return (severity or "Unknown").title(), WARN_FG, WARN_BG


def _hypothesis_status_palette(status: Optional[str]) -> Tuple[str, HexColor, HexColor]:
    normalized = (status or "").strip().lower()
    if normalized == "supported":
        return "Supported", FLAG_FG, FLAG_BG
    if normalized == "investigating":
        return "Investigating", WARN_FG, WARN_BG
    if normalized == "contradicted":
        return "Contradicted", GOOD_FG, GOOD_BG
    if normalized == "closed":
        return "Closed", INK_MUTE, SURFACE_ALT
    return (status or "Proposed").title(), ACCENT, SURFACE_ALT


def _paragraphs(text: str) -> Iterable[str]:
    for chunk in (text or "").split("\n\n"):
        chunk = chunk.strip()
        if chunk:
            yield chunk


def _trim(value: str, limit: int) -> str:
    clean = " ".join(str(value or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _html_escape(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
