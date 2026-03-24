"""
Generates a test PDF for Diamond Miner that exercises:
  - Structural topology (REQUIRES, BLOCKS, PRODUCES, CONTRADICTS edges)
  - Deliberate contradictions for ContradictionHunterAgent
  - ISO 8601 and relative dates for ChronosAgent
  - STARTS_AFTER relationships with Negative Slack (schedule conflicts)
"""
import fitz


CONTENT = [
    {
        "heading": "Helix Infrastructure Modernisation Programme\nMaster Project Charter v2.1",
        "body": None,
        "is_title": True,
    },
    {
        "heading": "1. Executive Summary",
        "body": (
            "The Helix Programme replaces the organisation's legacy data infrastructure with a "
            "cloud-native architecture across three sequential phases: Foundation, Integration, "
            "and Production Deployment. The programme is governed by the Helix Steering Committee "
            "and is subject to mandatory regulatory approval from the Compliance Authority before "
            "any phase may proceed to production."
        ),
    },
    {
        "heading": "2. Phase 1 — Foundation (1 March 2026 to 30 April 2026)",
        "body": (
            "The Foundation Phase establishes the core data layer. "
            "Database Migration requires Legacy System Shutdown to be completed first, "
            "because the migration tooling cannot run against a live production database. "
            "Security Audit requires Database Migration to be complete, as the audit scope "
            "covers only the new schema and encrypted storage layer. "
            "The Compliance Authority requires Legacy System Shutdown to remain active throughout "
            "the audit window to preserve the official audit trail — therefore the Compliance "
            "Authority blocks Legacy System Shutdown during the audit period. "
            "Data Encryption Module produces the encryption key manifest consumed by Security Audit. "
            "The Foundation Phase is scheduled to begin on 1 March 2026 and end on 30 April 2026."
        ),
    },
    {
        "heading": "3. Structural Conflict — Audit Trail Paradox",
        "body": (
            "Security Audit requires Database Migration. "
            "Database Migration requires Legacy System Shutdown. "
            "Compliance Authority blocks Legacy System Shutdown. "
            "This creates a direct operational paradox: the audit cannot proceed without the migration, "
            "the migration cannot proceed without the shutdown, yet the Compliance Authority forbids "
            "the shutdown while the audit is in scope. "
            "The Helix Steering Committee has not resolved this conflict as of the date of this charter."
        ),
    },
    {
        "heading": "4. Phase 2 — Integration (1 May 2026 to 31 July 2026)",
        "body": (
            "The Integration Phase connects the migrated data layer to the application tier. "
            "API Gateway requires Phase 1 Foundation to be complete before deployment begins. "
            "Load Balancer requires API Gateway to be active before traffic routing is enabled. "
            "Network Upgrade modifies the API Gateway port configuration and must be applied "
            "before API Gateway is installed. "
            "However, Network Upgrade blocks API Gateway installation during its maintenance window "
            "because the port reassignment causes a service conflict on the target hosts. "
            "Integration Testing produces the system validation report required by Production Deployment. "
            "The Integration Phase is scheduled to start after the Foundation Phase ends. "
            "Phase 2 starts on 1 May 2026. Phase 1 ends on 30 April 2026."
        ),
    },
    {
        "heading": "5. Phase 3 — Production Deployment (15 June 2026 to 30 September 2026)",
        "body": (
            "Production Deployment requires Integration Testing to be complete and the system "
            "validation report to be signed off by the Quality Assurance Board. "
            "Regulatory Hold blocks Production Deployment whenever an open compliance finding "
            "is recorded by the Compliance Authority. "
            "The Quality Assurance Board requires Security Audit sign-off before approving "
            "the system validation report. "
            "Production Deployment is scheduled to start on 15 June 2026. "
            "Integration Testing ends on 31 July 2026. "
            "Production Deployment must start after Integration Testing ends."
        ),
    },
    {
        "heading": "6. Schedule Conflict — Negative Slack",
        "body": (
            "Production Deployment is scheduled to begin on 15 June 2026. "
            "Integration Testing is not scheduled to complete until 31 July 2026. "
            "Production Deployment must start after Integration Testing ends, "
            "creating a negative slack of 46 days: the deployment is planned to start "
            "46 days before its predecessor activity is complete. "
            "Similarly, Phase 2 Integration is planned to start on 1 May 2026. "
            "Phase 1 Foundation ends on 30 April 2026. This is a zero-slack dependency; "
            "any overrun in Phase 1 immediately delays Phase 2."
        ),
    },
    {
        "heading": "7. Resource Conflicts",
        "body": (
            "The Database Administration Team is assigned to both Database Migration in Phase 1 "
            "and to Integration Testing in Phase 2. "
            "Database Migration requires the Database Administration Team full-time from "
            "1 March 2026 to 30 April 2026. "
            "Integration Testing requires the Database Administration Team from 1 May 2026. "
            "The Network Engineering Team is assigned to Network Upgrade and to Load Balancer "
            "configuration. Network Upgrade blocks Load Balancer configuration because the "
            "routing tables cannot be finalised until the port reassignment is complete. "
            "The Security Team produces the encryption key manifest and also conducts Security Audit. "
            "Security Audit requires the encryption key manifest produced by the Security Team's "
            "Data Encryption Module, meaning the Security Team blocks itself if the encryption "
            "module is deprioritised."
        ),
    },
    {
        "heading": "8. Regulatory Dependencies",
        "body": (
            "The Compliance Authority requires formal sign-off at four mandatory checkpoints: "
            "before Legacy System Shutdown, before Database Migration, before API Gateway deployment, "
            "and before Production Deployment. "
            "Each checkpoint requires a completed audit package from the Security Team. "
            "Regulatory Hold is automatically triggered if any checkpoint is bypassed. "
            "Regulatory Hold blocks Production Deployment, blocks API Gateway deployment, "
            "and blocks Legacy System Shutdown concurrently. "
            "The Helix Steering Committee produces the programme authority required by the "
            "Compliance Authority to open each checkpoint. "
            "The Compliance Authority blocks all deployment activities until checkpoint approval "
            "is received, creating a hard sequential dependency across all three phases."
        ),
    },
    {
        "heading": "9. Risk Register",
        "body": (
            "Risk R-01: Legacy System Shutdown is blocked by Compliance Authority. Probability: High. "
            "Impact: blocks Database Migration and therefore the entire Foundation Phase. "
            "Risk R-02: Network Upgrade maintenance window overlaps with API Gateway installation. "
            "The Network Upgrade blocks API Gateway. If the maintenance window extends beyond "
            "its scheduled end date of 15 May 2026, API Gateway installation cannot begin until "
            "Network Upgrade completes, delaying the Integration Phase end date of 31 July 2026. "
            "Risk R-03: Security Team capacity is required simultaneously for Data Encryption Module "
            "and Security Audit. Data Encryption Module must produce its output before Security Audit "
            "begins. If the Security Team is not available from 1 March 2026, the entire audit "
            "schedule slips, pushing the Production Deployment start date beyond 15 June 2026. "
            "Risk R-04: Quality Assurance Board sign-off requires Security Audit completion. "
            "If Security Audit is delayed past 30 June 2026, the Quality Assurance Board cannot "
            "approve the system validation report in time for the Production Deployment gate."
        ),
    },
    {
        "heading": "10. Approval and Authority",
        "body": (
            "This charter is approved by the Helix Steering Committee effective 1 February 2026. "
            "The programme authority expires on 31 December 2026. "
            "All phase gate decisions require a quorum of the Helix Steering Committee plus "
            "written approval from the Compliance Authority. "
            "The Compliance Authority produces the gate approval notice consumed by each phase. "
            "The Helix Steering Committee requires the Compliance Authority gate approval notice "
            "before authorising budget release for each phase. "
            "Budget Release requires Helix Steering Committee approval. "
            "Phase 1 budget release is scheduled for 15 February 2026. "
            "Phase 2 budget release must start after Phase 1 budget release and is scheduled "
            "for 15 April 2026. Phase 1 budget release ends on 28 February 2026, so Phase 2 "
            "budget release starts after Phase 1 budget release ends — no negative slack here."
        ),
    },
]


def make_pdf(output_path: str):
    doc = fitz.open()
    font = "helv"
    margin = 72
    page_width = 595
    page_height = 842
    text_width = page_width - 2 * margin

    def new_page():
        p = doc.new_page(width=page_width, height=page_height)
        return p, margin  # returns page and current y position

    page, y = new_page()

    for section in CONTENT:
        heading = section["heading"]
        body = section.get("body")
        is_title = section.get("is_title", False)

        # Title block
        if is_title:
            for line in heading.split("\n"):
                rc = page.insert_textbox(
                    fitz.Rect(margin, y, page_width - margin, y + 60),
                    line,
                    fontname=font,
                    fontsize=18,
                    color=(1, 1, 1),
                    fill=(0.1, 0.1, 0.2),
                    align=fitz.TEXT_ALIGN_CENTER,
                )
                y += 40
            y += 20
            continue

        # Section heading
        if y > page_height - 150:
            page, y = new_page()

        rc = page.insert_textbox(
            fitz.Rect(margin, y, page_width - margin, y + 30),
            heading,
            fontname="hebo",  # helvetica bold
            fontsize=13,
            color=(0.05, 0.2, 0.5),
        )
        y += 28

        # Body text — wrap manually
        if body:
            words = body.split()
            line_buf = []
            for word in words:
                line_buf.append(word)
                test_line = " ".join(line_buf)
                # Rough character-width estimate (avg ~5.5px per char at fontsize 11)
                if len(test_line) * 5.5 >= text_width:
                    if y > page_height - 60:
                        page, y = new_page()
                    page.insert_text((margin, y), " ".join(line_buf[:-1]), fontname=font, fontsize=11)
                    y += 16
                    line_buf = [word]
            if line_buf:
                if y > page_height - 60:
                    page, y = new_page()
                page.insert_text((margin, y), " ".join(line_buf), fontname=font, fontsize=11)
                y += 16

        y += 18  # section gap

    doc.save(output_path)
    print(f"Saved: {output_path}  ({doc.page_count} pages)")
    doc.close()


if __name__ == "__main__":
    make_pdf("helix_programme_charter.pdf")
