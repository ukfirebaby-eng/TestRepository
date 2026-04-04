"""
One-off script: generates templates/narrative_report.docx — a docxtpl-compatible
Word template with Jinja2 tags and pre-applied styles matching the PDF design spec.

Run once:  python templates/create_docx_template.py
"""

from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
import os

NAVY = RGBColor(0x1E, 0x3A, 0x5F)
CHARCOAL = RGBColor(0x1F, 0x29, 0x37)
MUTED = RGBColor(0x6B, 0x72, 0x80)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
CRITICAL_RED = RGBColor(0xDC, 0x26, 0x26)

doc = Document()

# ── Page setup (A4, 25mm margins) ──
for section in doc.sections:
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

style = doc.styles['Normal']
style.font.name = 'Georgia'
style.font.size = Pt(11)
style.font.color.rgb = CHARCOAL
style.paragraph_format.line_spacing = 1.5

# ── Cover ──
eyebrow = doc.add_paragraph()
run = eyebrow.add_run('Diamond Miner \u2014 Risk Intelligence')
run.font.size = Pt(9)
run.font.color.rgb = MUTED
run.font.name = 'Segoe UI'
run.font.all_caps = True

title = doc.add_heading('Full Narrative Report', level=1)
for run in title.runs:
    run.font.color.rgb = NAVY
    run.font.name = 'Segoe UI'
    run.font.size = Pt(22)

# Summary line with Jinja2 tags
summary_line = doc.add_paragraph()
summary_line.space_after = Pt(6)
run = summary_line.add_run('Assessment: {{ metadata.overall_assessment }}  |  Document: {{ metadata.document_name }}  |  Generated: {{ metadata.generated_at }}  |  Issues: {{ metadata.total_issues }}')
run.font.size = Pt(10)
run.font.name = 'Segoe UI'
run.font.color.rgb = MUTED

# ── Executive Summary ──
doc.add_page_break()
h2 = doc.add_heading('Executive Summary', level=2)
for run in h2.runs:
    run.font.color.rgb = NAVY
    run.font.name = 'Segoe UI'
p = doc.add_paragraph('{{ executive_summary }}')
p.style = doc.styles['Normal']

# ── Key Findings ──
doc.add_page_break()
h2 = doc.add_heading('Key Findings', level=2)
for run in h2.runs:
    run.font.color.rgb = NAVY
    run.font.name = 'Segoe UI'

# Key findings table with Jinja2 loop
tbl_note = doc.add_paragraph()
run = tbl_note.add_run('{%tr for f in key_findings %}')
run.font.size = Pt(1)
run.font.color.rgb = WHITE

table = doc.add_table(rows=1, cols=3)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.style = 'Table Grid'
hdr = table.rows[0].cells
for i, text in enumerate(['Severity', 'Finding', 'Impact']):
    hdr[i].text = text
    for p in hdr[i].paragraphs:
        for r in p.runs:
            r.font.bold = True
            r.font.size = Pt(9)
            r.font.name = 'Segoe UI'
            r.font.color.rgb = NAVY

row = table.add_row()
row.cells[0].text = '{{ f.severity }}'
row.cells[1].text = '{{ f.title }}'
row.cells[2].text = '{{ f.impact }}'

tbl_end = doc.add_paragraph()
run = tbl_end.add_run('{%tr endfor %}')
run.font.size = Pt(1)
run.font.color.rgb = WHITE

# ── Chapters (Jinja2 loop) ──
doc.add_page_break()
ch_note = doc.add_paragraph()
run = ch_note.add_run('{% for chapter in chapters %}')
run.font.size = Pt(1)
run.font.color.rgb = WHITE

h2 = doc.add_heading('{{ chapter.title }}', level=2)
for run in h2.runs:
    run.font.color.rgb = NAVY
    run.font.name = 'Segoe UI'

p = doc.add_paragraph('{{ chapter.narrative }}')
p.style = doc.styles['Normal']

ch_end = doc.add_paragraph()
run = ch_end.add_run('{% endfor %}')
run.font.size = Pt(1)
run.font.color.rgb = WHITE

# ── Appendix A: Issue Register ──
doc.add_page_break()
h2 = doc.add_heading('Appendix A: Issue Register', level=2)
for run in h2.runs:
    run.font.color.rgb = NAVY
    run.font.name = 'Segoe UI'

ir_start = doc.add_paragraph()
run = ir_start.add_run('{%tr for issue in issue_register %}')
run.font.size = Pt(1)
run.font.color.rgb = WHITE

ir_table = doc.add_table(rows=1, cols=5)
ir_table.alignment = WD_TABLE_ALIGNMENT.CENTER
ir_table.style = 'Table Grid'
ir_hdr = ir_table.rows[0].cells
for i, text in enumerate(['Severity', 'Type', 'Source', 'Target', 'Description']):
    ir_hdr[i].text = text
    for p in ir_hdr[i].paragraphs:
        for r in p.runs:
            r.font.bold = True
            r.font.size = Pt(9)
            r.font.name = 'Segoe UI'
            r.font.color.rgb = NAVY

ir_row = ir_table.add_row()
ir_row.cells[0].text = '{{ issue.severity }}'
ir_row.cells[1].text = '{{ issue.type }}'
ir_row.cells[2].text = '{{ issue.source }}'
ir_row.cells[3].text = '{{ issue.target }}'
ir_row.cells[4].text = '{{ issue.description }}'

ir_end = doc.add_paragraph()
run = ir_end.add_run('{%tr endfor %}')
run.font.size = Pt(1)
run.font.color.rgb = WHITE

# ── Appendix B: Methodology ──
doc.add_page_break()
h2 = doc.add_heading('Appendix B: Methodology', level=2)
for run in h2.runs:
    run.font.color.rgb = NAVY
    run.font.name = 'Segoe UI'

p = doc.add_paragraph('{{ methodology }}')
p.style = doc.styles['Normal']

# ── Footer ──
for section in doc.sections:
    footer = section.footer
    footer.is_linked_to_previous = False
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = fp.add_run('Diamond Miner \u2014 Confidential')
    run.font.size = Pt(8)
    run.font.color.rgb = MUTED
    run.font.name = 'Segoe UI'

# Save
output_path = os.path.join(os.path.dirname(__file__), 'narrative_report.docx')
doc.save(output_path)
print(f"Template saved to {output_path}")
