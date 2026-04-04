# Full Narrative Report Export — Design Spec

**Date:** 2026-04-04
**Status:** Approved
**Audience:** C-suite / Board members

## Overview

Add server-side document export to Diamond Miner's Full Narrative Report. Two formats: PDF (via WeasyPrint) and Word .docx (via docxtpl). Both use a template-driven architecture where design lives in template files, not Python code, and both consume the same structured data payload.

## Architecture

### New Components

**`core/report_assembler.py` — ReportAssembler class**

Single class with one public method: `assemble(document_id) -> dict`.

Gathers data from the vault and structures it into a unified report payload:

```python
{
    "metadata": {
        "document_name": str,
        "generated_at": str,       # ISO 8601
        "model_used": str,
        "overall_assessment": str,  # "Critical Risk" | "High Risk" | "Moderate Risk" | "Low Risk" | "No Issues Found"
        "total_issues": int,
        "critical_count": int,
    },
    "executive_summary": str,       # From cached executive summary, fallback to narrative summary_narrative
    "risk_heatmap": [               # 5x5 grid: list of {severity, probability, count}
        {"severity": 1, "probability": 1, "count": 0},
        ...
    ],
    "key_findings": [               # Severity >= 3 only, sorted critical-first
        {
            "severity": str,        # "critical" | "high" | "medium"
            "title": str,
            "impact": str,
            "recommendation": str,
        }
    ],
    "chapters": [                   # From cached narrative report
        {"title": str, "narrative": str}
    ],
    "issue_register": [             # Full flat list of all issues
        {
            "type": str,            # "structural" | "chronological" | "hub_vulnerability"
            "source": str,
            "target": str,
            "description": str,
            "severity": int,
            "probability": int,
        }
    ],
    "methodology": str,             # Static text, not LLM-generated
}
```

Data sources:
- `vault.get_narrative_report(document_id)` — chapters, overall_assessment, summary_narrative
- `vault.get_executive_summary(document_id)` — preferred executive summary (fallback to narrative's summary_narrative)
- `vault.get_friction_lines(document_id)` — structural friction
- `vault.get_chronological_friction_lines(document_id)` — chronological friction
- `vault.get_hub_vulnerabilities(document_id)` — hub vulnerabilities
- `vault.get_risk_matrix_data(document_id)` — severity/probability data for heatmap
- `vault.conn` direct query: `SELECT name FROM documents WHERE id = ?` — document name (no dedicated method exists; a simple cursor query is sufficient)

### Templates

**`templates/narrative_report.html`** — Jinja2 HTML template for PDF rendering

- Full HTML document with embedded CSS
- Print CSS rules: `@page { size: A4; margin: 25mm; }`
- Page breaks between major sections: `page-break-before: always`
- Footer via CSS `@bottom-center` / `@bottom-right` running elements
- Risk heatmap as a styled `<table>` with background colours per cell
- Key findings as a styled `<table>` with severity badge pills
- Issue register as a compact `<table>` in the appendix

**`templates/narrative_report.docx`** — Word template with Jinja2 tags

- Pre-designed in Microsoft Word with correct styles applied
- Jinja2 tags: `{{ metadata.document_name }}`, `{% for chapter in chapters %}`, etc.
- Risk heatmap as a Word table with cell shading
- Key findings as a Word table with coloured text for severity
- Designed with 1.5 line spacing, ragged-right alignment, matching the PDF spec

### API Endpoints

**`GET /api/v1/export/pdf/{document_id}`**

```python
async def export_pdf(document_id: str):
    # 404 if document doesn't exist
    # 409 if narrative report not yet generated
    assembler = ReportAssembler(vault)
    payload = assembler.assemble(document_id)
    
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("narrative_report.html")
    html_string = template.render(**payload)
    
    pdf_bytes = await asyncio.to_thread(
        weasyprint.HTML(string=html_string).write_pdf
    )
    
    file_stream = BytesIO(pdf_bytes)
    return StreamingResponse(
        file_stream,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Diamond_Miner_Report_{document_id}.pdf"}
    )
```

**`GET /api/v1/export/docx/{document_id}`**

```python
async def export_docx(document_id: str):
    # 404 if document doesn't exist
    # 409 if narrative report not yet generated
    assembler = ReportAssembler(vault)
    payload = assembler.assemble(document_id)
    
    template = DocxTemplate("templates/narrative_report.docx")
    await asyncio.to_thread(template.render, payload)
    
    file_stream = BytesIO()
    template.save(file_stream)
    file_stream.seek(0)
    
    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=Diamond_Miner_Report_{document_id}.docx"}
    )
```

Both endpoints:
- Return 404 if `document_id` not in documents table
- Return 409 with `{"detail": "Generate the narrative report first."}` if no cached narrative
- Run rendering in `asyncio.to_thread()` to avoid blocking the async event loop
- Stream from `BytesIO` — nothing written to disk

### Frontend Changes

In `static/index.html`:

**Replace `downloadNarrativePdf()`:**
```javascript
async function downloadNarrativePdf() {
    const documentId = _currentNarrativeDocumentId;
    if (!documentId) return;
    const res = await fetch(`/api/v1/export/pdf/${documentId}`);
    if (!res.ok) { showToast('PDF export failed.', 'error'); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Diamond_Miner_Report_${documentId}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
}
```

**Add `downloadNarrativeDocx()`** — identical pattern, hitting `/api/v1/export/docx/`.

**Add Word download button** next to the existing PDF button in the narrative page header:
```html
<button class="rp-btn" onclick="downloadNarrativeDocx()">&#8681; Download Word</button>
```

## Visual Design

### Typography
- **Headings:** Segoe UI / Helvetica (sans-serif), navy #1E3A5F, bold
  - H1: 22pt, H2: 16pt, H3: 13pt
- **Body prose:** Georgia / Times New Roman (serif), charcoal #1F2937, 11pt
- **Labels & metadata:** Segoe UI, 9pt, grey #6B7280, uppercase with letter-spacing

### Colour Palette
| Colour | Hex | Usage |
|--------|-----|-------|
| Navy | #1E3A5F | Headings, rules, branding |
| Critical | #DC2626 | Critical severity badges and heatmap cells |
| High | #D97706 | High severity badges and heatmap cells |
| Medium | #2563EB | Medium severity badges and heatmap cells |
| Low | #16A34A | Low severity badges and heatmap cells |
| Background | #F9FAFB | Summary card backgrounds |
| Body text | #1F2937 | Narrative prose |
| Muted | #6B7280 | Labels, metadata, footers |

### Page Layout (PDF)
- A4 portrait, 25mm margins all sides
- 1.5 line height for body prose, 1.3 for tables
- Left-aligned (ragged right) text
- Each major section starts on a new page (`page-break-before: always`)
- 2px navy rule below section headings
- Footer: "Diamond Miner — Confidential" (left), page number (right)

### Severity Badges
Inline coloured pill labels in tables:
- Critical: white text on #DC2626 background, border-radius 3px, padding 2px 8px
- High: white text on #D97706 background
- Medium: white text on #2563EB background
- Low: white text on #16A34A background

### Risk Heatmap Table
- 5 columns (severity 1-5) x 5 rows (probability 1-5)
- Cell background colour gradient: green (#DCFCE7) for low-low, amber (#FEF3C7) for mid, red (#FEE2E2) for high-high
- Cell content: count of issues in that bucket (integer), or empty if zero
- Row/column headers in navy, bold, sans-serif

## Document Structure

| Section | Page Break | Content Source |
|---------|-----------|---------------|
| Cover / Header | — | metadata dict |
| Executive Summary | No (flows from cover) | executive_summary field |
| Risk Heat Map | Yes | risk_heatmap grid data |
| Key Findings | Yes | key_findings table (severity >= 3) |
| Chapter 1..N | Yes (each) | chapters array |
| Appendix A: Issue Register | Yes | issue_register array |
| Appendix B: Methodology | Yes | Static text |

### Cover Page Elements
- "Diamond Miner — Risk Intelligence" eyebrow label
- "Full Narrative Report" title
- 2px navy rule
- Four summary cards in a row: Assessment (colour-coded), Document name, Date generated, Issues found

### Methodology Text (Static)
Brief explanation of:
- Knowledge graph extraction (DeconstructorAgent)
- Contradiction detection (ContradictionHunterAgent)
- Fragility analysis (FragilityAgent)
- Temporal analysis (ChronosAgent)
- Monte Carlo simulation (MonteCarloForecaster)

Written in plain English, no technical jargon. Approximately 200 words. Stored as a constant in `core/report_assembler.py`.

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Narrative not generated | 409: "Generate the narrative report first." |
| Document not found | 404: "Document not found." |
| No executive summary cached | Fall back to narrative's `summary_narrative` field |
| No risk matrix data | Render empty heatmap with note: "Risk simulation not yet run." |
| WeasyPrint rendering failure | 500 with descriptive error mentioning system dependencies |
| Large report (many chapters) | Handled by `asyncio.to_thread()` — no blocking |

## New Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `weasyprint` | 68.1 | HTML/CSS to PDF rendering |
| `docxtpl` | 0.20.2 | Word template rendering |
| `jinja2` | (already transitive via FastAPI) | HTML template rendering |

**System dependencies for WeasyPrint (Windows):**
- GTK3 runtime (includes Cairo, Pango, GDK-PixBuf)
- Install via `pip install weasyprint` which documents the system requirements

## Files Created / Modified

| File | Action |
|------|--------|
| `core/report_assembler.py` | **Create** — ReportAssembler class |
| `templates/narrative_report.html` | **Create** — Jinja2 HTML template with print CSS |
| `templates/narrative_report.docx` | **Create** — Word template with Jinja2 tags |
| `api.py` | **Modify** — add two GET export endpoints |
| `static/index.html` | **Modify** — replace downloadNarrativePdf, add downloadNarrativeDocx, add Word button |
| `requirements.txt` | **Modify** — add weasyprint, docxtpl |

## Out of Scope

- Changes to the narrative generation pipeline (OutlineAgent, RecursiveDraftingAgent, CriticAgent, KDECoverageCheck)
- Changes to the executive summary generation pipeline
- Email delivery of reports
- Scheduled/automatic report generation
- Custom branding or white-labelling
