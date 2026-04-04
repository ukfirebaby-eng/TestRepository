"""
ReportAssembler — gathers vault data into a unified report payload dict
consumed by both the PDF (WeasyPrint) and Word (docxtpl) export templates.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from core.vault import HybridVault


METHODOLOGY_TEXT = (
    "This report was produced by Diamond Miner's automated risk intelligence pipeline. "
    "The uploaded document was first parsed into a knowledge graph of entities and "
    "relationships using the Deconstructor Agent. The Contradiction Hunter then scanned "
    "every pair of connected nodes for logical conflicts — cases where one requirement "
    "blocks or undermines another. The Fragility Analyser identified hub nodes with "
    "disproportionate dependency counts, highlighting single points of failure. "
    "The Chronological Analyser extracted temporal markers (dates, durations, milestones) "
    "and detected schedule overlaps where a successor task is due to start before its "
    "predecessor finishes. Finally, a Monte Carlo Forecaster ran 5,000 randomised "
    "timeline simulations to estimate the probability distribution of overall programme "
    "delay. All findings were reviewed by a Critic Agent for completeness and a "
    "semantic coverage check verified that every source issue appears in the final narrative."
)

SEVERITY_LABELS = {5: "critical", 4: "high", 3: "medium", 2: "low", 1: "low"}


class ReportAssembler:
    """Single entry point: assemble(document_id) -> dict."""

    def __init__(self, vault: HybridVault):
        self.vault = vault

    def assemble(self, document_id: str) -> Dict[str, Any]:
        narrative = self.vault.get_narrative_report(document_id)
        if narrative is None:
            raise ValueError("Narrative report not yet generated.")

        executive = self.vault.get_executive_summary(document_id)

        # Resolve executive summary text: prefer cached executive, fall back to narrative's summary
        exec_text = ""
        if executive and executive.get("summary_narrative"):
            exec_text = executive["summary_narrative"]
        elif narrative.get("executive_summary"):
            exec_text = narrative["executive_summary"]
        elif narrative.get("summary_narrative"):
            exec_text = narrative["summary_narrative"]

        # Gather raw issues
        friction = self.vault.get_friction_lines(document_id)
        chrono = self.vault.get_chronological_friction_lines(document_id)
        hub_vulns = self.vault.get_hub_vulnerabilities(document_id)
        risk_matrix = self.vault.get_risk_matrix_data(document_id)

        # Document name
        cursor = self.vault.conn.cursor()
        cursor.execute("SELECT name FROM documents WHERE id = ?", (document_id,))
        row = cursor.fetchone()
        document_name = row["name"] if row else document_id

        # Build issue register (flat list of all issues)
        issue_register = self._build_issue_register(friction, chrono, hub_vulns)

        # Build risk heatmap (5x5 grid)
        risk_heatmap = self._build_risk_heatmap(risk_matrix)

        # Build key findings (severity >= 3, sorted critical-first)
        key_findings = self._build_key_findings(friction, chrono)

        # Severity counts
        total_issues = len(issue_register)
        critical_count = sum(1 for i in issue_register if i.get("severity") == "critical")

        # Overall assessment from narrative
        overall_assessment = narrative.get("overall_assessment", "No Issues Found")

        # Chapters
        chapters = narrative.get("chapters", [])

        return {
            "metadata": {
                "document_name": document_name,
                "generated_at": datetime.now(timezone.utc).strftime("%d %B %Y"),
                "generated_at_iso": datetime.now(timezone.utc).isoformat(),
                "overall_assessment": overall_assessment,
                "total_issues": total_issues,
                "critical_count": critical_count,
            },
            "executive_summary": exec_text,
            "risk_heatmap": risk_heatmap,
            "key_findings": key_findings,
            "chapters": chapters,
            "issue_register": issue_register,
            "methodology": METHODOLOGY_TEXT,
        }

    def _build_issue_register(
        self,
        friction: List[Dict],
        chrono: List[Dict],
        hub_vulns: List[Dict],
    ) -> List[Dict[str, Any]]:
        register: List[Dict[str, Any]] = []

        for item in friction:
            register.append({
                "type": "structural",
                "source": item.get("source", ""),
                "target": item.get("target", ""),
                "description": item.get("diamond", ""),
                "severity": SEVERITY_LABELS.get(item.get("severity", 3), "medium"),
                "severity_num": item.get("severity", 3),
                "probability": item.get("probability", 3),
            })

        for item in chrono:
            register.append({
                "type": "chronological",
                "source": item.get("source", ""),
                "target": item.get("target", ""),
                "description": item.get("diamond", ""),
                "severity": SEVERITY_LABELS.get(item.get("severity", 3), "medium"),
                "severity_num": item.get("severity", 3),
                "probability": item.get("probability", 3),
            })

        for item in hub_vulns:
            register.append({
                "type": "hub_vulnerability",
                "source": item.get("name", item.get("id", "")),
                "target": "",
                "description": f"Hub node with {item.get('dependency_count', 0)} dependencies",
                "severity": "high",
                "severity_num": 4,
                "probability": 4,
            })

        # Sort critical-first
        register.sort(key=lambda x: -x.get("severity_num", 0))
        return register

    def _build_risk_heatmap(self, risk_matrix: List[Dict]) -> List[Dict[str, Any]]:
        grid: Dict[tuple, int] = {}
        for s in range(1, 6):
            for p in range(1, 6):
                grid[(s, p)] = 0

        for item in risk_matrix:
            sev = max(1, min(5, item.get("severity", 3)))
            prob = max(1, min(5, item.get("probability", 3)))
            grid[(sev, prob)] += 1

        return [
            {"severity": s, "probability": p, "count": grid[(s, p)]}
            for s in range(1, 6)
            for p in range(1, 6)
        ]

    def _build_key_findings(
        self,
        friction: List[Dict],
        chrono: List[Dict],
    ) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []

        for item in friction + chrono:
            sev = item.get("severity", 3)
            if sev < 3:
                continue
            diamond = item.get("diamond", "")
            # Extract a short title from the first sentence of the diamond text
            title = diamond.split(".")[0].strip()[:120] if diamond else "Unnamed finding"
            findings.append({
                "severity": SEVERITY_LABELS.get(sev, "medium"),
                "severity_num": sev,
                "title": title,
                "impact": diamond,
                "recommendation": "",
            })

        findings.sort(key=lambda x: -x.get("severity_num", 0))
        return findings
