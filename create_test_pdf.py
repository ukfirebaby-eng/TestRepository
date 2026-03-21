"""
Generates a synthetic test PDF with two known logical contradictions,
designed to exercise the Diamond Miner contradiction detection pipeline.

Contradiction A — Change Advisory Board:
  - Security patches REQUIRE immediate production deployment
  - Production deployment REQUIRES CAB approval
  - CAB BLOCKS all approvals during the system freeze period
  → A security patch that arrives during a freeze cannot be deployed,
    yet must be deployed immediately.

Contradiction B — Database incident response:
  - Resolving a live incident REQUIRES an emergency schema change
  - Schema changes REQUIRE DBA authorisation
  - The DBA team BLOCKS schema authorisations during active incident response
  → The fix for an incident cannot be authorised while the incident is ongoing.
"""

import fitz  # PyMuPDF

PARAGRAPHS = [
    # ── Contradiction A ──────────────────────────────────────────────────────

    # A1: patch deployment requires CAB approval
    (
        "Change Management Policy — Section 4.2",
        "Deploying any software update or patch to the production environment "
        "requires written approval from the Change Advisory Board (CAB) prior to "
        "execution. No production deployment may proceed without a CAB-approved "
        "change record. The CAB approval process requires a minimum 48-hour review "
        "window before any change can be authorised."
    ),

    # A2: CAB blocks approvals during freeze
    (
        "System Freeze Policy — Section 2.1",
        "The Change Advisory Board blocks all change approvals and deployment "
        "authorisations during the quarterly system freeze period, which runs from "
        "the 1st to the 15th of each quarter. During this window, the CAB is "
        "suspended and requires no quorum. All pending change requests are blocked "
        "and deferred until the freeze period ends."
    ),

    # A3: security patches require immediate deployment — no exceptions
    (
        "Security Operations Policy — Section 7.4",
        "All critical security patches rated CVSS 9.0 or above require immediate "
        "deployment to all production systems within 24 hours of vendor release. "
        "This requirement admits no exceptions. Delayed application of critical "
        "security patches violates the organisation's regulatory compliance "
        "obligations and requires a formal breach notification to the regulator."
    ),

    # ── Contradiction B ──────────────────────────────────────────────────────

    # B1: schema changes require DBA authorisation
    (
        "Database Governance Policy — Section 3.1",
        "All schema changes to production databases require prior written "
        "authorisation from the Database Administration (DBA) team. The DBA team "
        "requires a full impact assessment before authorising any schema "
        "modification. Schema changes that have not received DBA authorisation are "
        "blocked from execution by the deployment pipeline."
    ),

    # B2: DBA blocks authorisations during active incidents
    (
        "Incident Response Procedure — Section 5.3",
        "The Database Administration team is prohibited from processing "
        "authorisation requests during active incident response. While the DBA team "
        "is managing a live incident, the team blocks all schema change "
        "authorisations. No authorisation requests will be reviewed or approved "
        "until the incident is formally closed."
    ),

    # B3: resolving a DB incident requires a schema change
    (
        "Database Incident Playbook — Section 8.2",
        "Resolving a live database performance incident caused by a missing index "
        "requires an emergency schema change to add the index to the affected table. "
        "The on-call engineer requires DBA authorisation before applying the schema "
        "change. Without this schema change, the incident cannot be resolved and "
        "the affected service remains degraded."
    ),
]


def build_pdf(output_path: str) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4

    x0, y = 60, 60
    x1 = 535
    font_title = "helv"
    font_body = "helv"

    # Document title
    page.insert_text(
        (x0, y),
        "Synthetic Contradiction Test Document",
        fontname=font_title,
        fontsize=16,
        color=(0, 0, 0),
    )
    y += 10
    page.draw_line((x0, y), (x1, y), color=(0.3, 0.3, 0.3), width=0.5)
    y += 20

    subtitle = (
        "This document contains two engineered logical contradictions "
        "for validation of the contradiction detection pipeline."
    )
    y = _insert_wrapped(page, subtitle, x0, x1, y, font_body, 10, (0.4, 0.4, 0.4))
    y += 24

    for section_title, body in PARAGRAPHS:
        # Section heading
        page.insert_text(
            (x0, y),
            section_title,
            fontname=font_title,
            fontsize=11,
            color=(0.1, 0.1, 0.6),
        )
        y += 16

        # Body text
        y = _insert_wrapped(page, body, x0, x1, y, font_body, 10, (0, 0, 0))
        y += 20

        if y > 780:
            page = doc.new_page(width=595, height=842)
            y = 60

    doc.save(output_path)
    doc.close()
    print(f"[*] Test PDF written to: {output_path}")
    print()
    print("Expected contradictions:")
    print("  A) Security patch (REQUIRES immediate deployment)")
    print("     × CAB (BLOCKS deployments during freeze)")
    print()
    print("  B) Incident resolution (REQUIRES schema change)")
    print("     × DBA team (BLOCKS schema authorisations during incidents)")


def _insert_wrapped(page, text, x0, x1, y, fontname, fontsize, color):
    """Naive word-wrap for PyMuPDF text insertion."""
    words = text.split()
    line = ""
    line_height = fontsize + 4
    max_chars_per_line = int((x1 - x0) / (fontsize * 0.52))

    for word in words:
        test = (line + " " + word).strip()
        if len(test) > max_chars_per_line and line:
            page.insert_text((x0, y), line, fontname=fontname,
                             fontsize=fontsize, color=color)
            y += line_height
            line = word
        else:
            line = test

    if line:
        page.insert_text((x0, y), line, fontname=fontname,
                         fontsize=fontsize, color=color)
        y += line_height

    return y


if __name__ == "__main__":
    build_pdf("test_contradictions.pdf")
