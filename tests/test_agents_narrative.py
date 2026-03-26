import json
import pytest
from unittest.mock import MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_openai_response(content: str):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = content
    return mock_response


def _raw_issues_with_many():
    """Returns a raw_issues dict with issues spread across all three lists."""
    return {
        "friction_lines": [
            {"source": "node_a", "target": "node_b", "diamond": "Conflict A", "severity": 5, "probability": 4},
            {"source": "node_c", "target": "node_d", "diamond": "Conflict B", "severity": 3, "probability": 2},
            {"source": "node_e", "target": "node_f", "diamond": "Conflict C", "severity": 4, "probability": 3},
        ],
        "chronological_friction_lines": [
            {"source": "node_g", "target": "node_h", "diamond": "Schedule clash X", "severity": 3, "probability": 3},
            {"source": "node_i", "target": "node_j", "diamond": "Schedule clash Y", "severity": 2, "probability": 2},
        ],
        "hub_vulnerabilities": [
            {"hub_node": "hub_1", "insight": "Hub failure Z", "severity": 4, "probability": 3},
            {"hub_node": "hub_2", "insight": "Hub failure W", "severity": 2, "probability": 1},
            {"hub_node": "hub_3", "insight": "Hub failure V", "severity": 3, "probability": 2},
        ],
    }


def _empty_raw_issues():
    return {
        "friction_lines": [],
        "chronological_friction_lines": [],
        "hub_vulnerabilities": [],
    }


# ── TestOutlineAgent ──────────────────────────────────────────────────────────

class TestOutlineAgent:

    def test_returns_grouped_chapters(self):
        """All issue indices present, no duplicates, 3–6 groups."""
        from core.agents import OutlineAgent

        raw = _raw_issues_with_many()
        total_issues = (
            len(raw["friction_lines"])
            + len(raw["chronological_friction_lines"])
            + len(raw["hub_vulnerabilities"])
        )  # 8 issues total → indices 0..7

        llm_response = json.dumps([
            {"title": "Structural Conflicts", "indices": [0, 1, 2]},
            {"title": "Schedule Clashes", "indices": [3, 4]},
            {"title": "Hub Vulnerabilities", "indices": [5, 6, 7]},
        ])

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(llm_response)

        agent = OutlineAgent()
        with patch("core.agents._get_client", return_value=mock_client):
            result = agent.run(raw)

        # Must be a list of dicts with title and indices
        assert isinstance(result, list)
        assert all(isinstance(ch, dict) for ch in result)
        assert all("title" in ch and "indices" in ch for ch in result)

        # 3–6 groups
        assert 3 <= len(result) <= 6

        # All indices present exactly once
        all_returned_indices = [idx for ch in result for idx in ch["indices"]]
        assert sorted(all_returned_indices) == list(range(total_issues)), (
            "Every issue index must appear exactly once across all chapters"
        )
        assert len(all_returned_indices) == len(set(all_returned_indices)), (
            "No index should appear in more than one chapter"
        )

    def test_fallback_on_single_group(self):
        """When LLM returns JSON parse error, agent returns list of length 1 (caller handles fallback)."""
        from core.agents import OutlineAgent

        raw = _raw_issues_with_many()

        # LLM returns garbage that cannot be parsed
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(
            "Sorry, I cannot group these issues right now."
        )

        agent = OutlineAgent()
        with patch("core.agents._get_client", return_value=mock_client):
            result = agent.run(raw)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "title" in result[0]
        assert "indices" in result[0]

        # Fallback chapter should contain all indices
        total = (
            len(raw["friction_lines"])
            + len(raw["chronological_friction_lines"])
            + len(raw["hub_vulnerabilities"])
        )
        assert sorted(result[0]["indices"]) == list(range(total))

    def test_empty_raw_issues(self):
        """Returns empty list WITHOUT calling LLM when all issue lists are empty."""
        from core.agents import OutlineAgent

        mock_client = MagicMock()

        agent = OutlineAgent()
        with patch("core.agents._get_client", return_value=mock_client):
            result = agent.run(_empty_raw_issues())

        assert result == []
        mock_client.chat.completions.create.assert_not_called()
