import pytest
from api import assemble_narrative


def _make_raw_issues(friction=None, chron=None, hubs=None):
    return {
        "friction_lines": friction or [],
        "chronological_friction_lines": chron or [],
        "hub_vulnerabilities": hubs or [],
    }


class TestAssembleNarrative:
    def test_overall_assessment_from_max_severity(self):
        """Highest severity in the flat list determines the overall_assessment."""
        raw_issues = _make_raw_issues(
            friction=[{"severity": 3, "diamond": "low issue"}],
            chron=[{"severity": 5, "diamond": "critical issue"}],
            hubs=[{"severity": 2, "insight": "hub issue"}],
        )
        chapters = [{"title": "Ch1", "narrative": "text", "indices": [0, 1, 2]}]
        result = assemble_narrative(chapters, raw_issues)
        assert result["overall_assessment"] == "Critical Risk"

    def test_overall_assessment_high_risk(self):
        raw_issues = _make_raw_issues(friction=[{"severity": 4, "diamond": "high issue"}])
        chapters = [{"title": "Ch1", "narrative": "text", "indices": [0]}]
        result = assemble_narrative(chapters, raw_issues)
        assert result["overall_assessment"] == "High Risk"

    def test_overall_assessment_moderate_risk(self):
        raw_issues = _make_raw_issues(friction=[{"severity": 3, "diamond": "mod issue"}])
        chapters = [{"title": "Ch1", "narrative": "text", "indices": [0]}]
        result = assemble_narrative(chapters, raw_issues)
        assert result["overall_assessment"] == "Moderate Risk"

    def test_overall_assessment_low_risk(self):
        raw_issues = _make_raw_issues(friction=[{"severity": 2, "diamond": "low issue"}])
        chapters = [{"title": "Ch1", "narrative": "text", "indices": [0]}]
        result = assemble_narrative(chapters, raw_issues)
        assert result["overall_assessment"] == "Low Risk"

    def test_issues_list_built_from_indices(self):
        """Chapter indices correctly map back to raw issues in the flat list."""
        friction = [{"severity": 3, "diamond": "issue A"}]
        chron = [{"severity": 4, "diamond": "issue B"}]
        hubs = [{"severity": 5, "insight": "issue C"}]
        raw_issues = _make_raw_issues(friction=friction, chron=chron, hubs=hubs)
        # flat order: friction[0]=idx0, chron[0]=idx1, hubs[0]=idx2
        chapters = [
            {"title": "Ch1", "narrative": "text", "indices": [0, 2]},
            {"title": "Ch2", "narrative": "text", "indices": [1]},
        ]
        result = assemble_narrative(chapters, raw_issues)
        assert len(result["issues"]) == 3
        assert result["issues"][0]["diamond"] == "issue A"
        assert result["issues"][1]["insight"] == "issue C"
        assert result["issues"][2]["diamond"] == "issue B"

    def test_no_issues_returns_no_issues_found(self):
        """Empty raw_issues yields 'No Issues Found' regardless of chapters."""
        raw_issues = _make_raw_issues()
        chapters = [{"title": "Ch1", "narrative": "text", "indices": []}]
        result = assemble_narrative(chapters, raw_issues)
        assert result["overall_assessment"] == "No Issues Found"
        assert result["issues"] == []

    def test_return_shape(self):
        """Result always has the expected keys."""
        raw_issues = _make_raw_issues(friction=[{"severity": 3, "diamond": "x"}])
        chapters = [{"title": "Ch1", "narrative": "text", "indices": [0]}]
        result = assemble_narrative(chapters, raw_issues)
        for key in ("overall_assessment", "generated_at", "executive_summary",
                    "chapters", "issues", "coverage_verified", "coverage_warning"):
            assert key in result
        assert result["coverage_verified"] is False
        assert result["executive_summary"] == ""
        assert result["coverage_warning"] is None
