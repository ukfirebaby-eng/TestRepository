"""
Programmatic Word document builder for narrative report export.
Uses python-docx directly instead of docxtpl to avoid template tag parsing issues.
"""

from io import BytesIO
from typing import Any, Dict, List

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT


NAVY = RGBColor(0x1E, 0x3A, 0x5F)
CHARCOAL = RGBColor(0x1F, 0x29, 0x37)
MUTED = RGBColor(0x6B, 0x72, 0x80)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SEVERITY_COLOURS = {
    "critical": RGBColor(0xDC, 0x26, 0x26),
    "high": RGBColor(0xD9, 0x77, 0x06),
    "medium": RGBColor(0x25, 0x63, 0xEB),
    "low": RGBColor(0x16, 0xA3, 0x4A),
}


def _style_heading(heading, level: int = 2):
    for run in heading.runs:
        run.font.color.rgb = NAVY
        run.font.name = "Segoe UI"
        if level == 1:
            run.font.size = Pt(22)
        elif level == 2:
            run.font.size = Pt(16)
        else:
            run.font.size = Pt(13)


def _add_styled_table(doc: Document, headers: List[str], rows: List[List[str]]):
    """Adds a table with navy header row and alternating row shading."""
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"

    # Header row
    hdr = table.rows[0].cells
    for i, text in enumerate(headers):
        hdr[i].text = text
        for p in hdr[i].paragraphs:
            for r in p.runs:
                r.font.bold = True
                r.font.size = Pt(9)
                r.font.name = "Segoe UI"
                r.font.color.rgb = NAVY

    # Data rows
    for row_data in rows:
        row = table.add_row()
        for i, text in enumerate(row_data):
            if i < len(row.cells):
                row.cells[i].text = str(text)
                for p in row.cells[i].paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(10)
                        r.font.name = "Georgia"

    return table


def build_narrative_docx(payload: Dict[str, Any]) -> BytesIO:
    """Builds a complete Word document from a ReportAssembler payload and returns BytesIO."""
    meta = payload["metadata"]
    doc = Document()

    # Page setup (A4, 25mm margins)
    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    style = doc.styles["Normal"]
    style.font.name = "Georgia"
    style.font.size = Pt(11)
    style.font.color.rgb = CHARCOAL
    style.paragraph_format.line_spacing = 1.5

    # ── Cover ──
    eyebrow = doc.add_paragraph()
    run = eyebrow.add_run("Diamond Miner \u2014 Risk Intelligence")
    run.font.size = Pt(9)
    run.font.color.rgb = MUTED
    run.font.name = "Segoe UI"
    run.font.all_caps = True

    title = doc.add_heading("Full Narrative Report", level=1)
    _style_heading(title, 1)

    summary_line = doc.add_paragraph()
    summary_line.space_after = Pt(6)
    parts = [
        f"Assessment: {meta.get('overall_assessment', 'N/A')}",
        f"Document: {meta.get('document_name', 'N/A')}",
        f"Generated: {meta.get('generated_at', 'N/A')}",
        f"Issues: {meta.get('total_issues', 0)}",
    ]
    run = summary_line.add_run("  |  ".join(parts))
    run.font.size = Pt(10)
    run.font.name = "Segoe UI"
    run.font.color.rgb = MUTED

    # ── Executive Summary ──
    doc.add_page_break()
    _style_heading(doc.add_heading("Executive Summary", level=2))
    p = doc.add_paragraph(payload.get("executive_summary", "No executive summary available."))
    p.style = doc.styles["Normal"]

    # ── Key Findings ──
    key_findings = payload.get("key_findings", [])
    if key_findings:
        doc.add_page_break()
        _style_heading(doc.add_heading("Key Findings", level=2))
        rows = [
            [f.get("severity", "").upper(), f.get("finding", "")]
            for f in key_findings
        ]
        _add_styled_table(doc, ["Severity", "Finding"], rows)

    # ── Chapters ──
    for chapter in payload.get("chapters", []):
        doc.add_page_break()
        _style_heading(doc.add_heading(chapter.get("title", "Chapter"), level=2))
        p = doc.add_paragraph(chapter.get("narrative", ""))
        p.style = doc.styles["Normal"]

    # ── Appendix A: Issue Register ──
    issue_register = payload.get("issue_register", [])
    if issue_register:
        doc.add_page_break()
        _style_heading(doc.add_heading("Appendix A: Issue Register", level=2))
        rows = [
            [
                i.get("severity", "").upper(),
                i.get("type", ""),
                i.get("source", ""),
                i.get("target", ""),
                i.get("description", ""),
            ]
            for i in issue_register
        ]
        _add_styled_table(doc, ["Severity", "Type", "Source", "Target", "Description"], rows)

    # ── Appendix B: Methodology ──
    doc.add_page_break()
    _style_heading(doc.add_heading("Appendix B: Methodology", level=2))
    p = doc.add_paragraph(payload.get("methodology", ""))
    p.style = doc.styles["Normal"]

    # ── Footer ──
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = fp.add_run("Diamond Miner \u2014 Confidential")
        run.font.size = Pt(8)
        run.font.color.rgb = MUTED
        run.font.name = "Segoe UI"

    # Write to BytesIO
    file_stream = BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream
