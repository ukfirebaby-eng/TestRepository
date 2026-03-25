import json
import pytest
import numpy as np
from unittest.mock import MagicMock, patch


# ── Helpers ──────────────────────────────────────────────────────────────────

def _raw_issues():
    return {
        "friction_lines": [
            {"source": "node_a", "target": "node_b", "diamond": "Conflict A", "severity": 5, "probability": 4}
        ],
        "chronological_friction_lines": [],
        "hub_vulnerabilities": [],
        "risk_matrix": [],
    }


def _draft_report(issues=None):
    return {
        "overall_assessment": "High Risk",
        "generated_at": "2026-03-25T12:00:00Z",
        "summary_narrative": "One issue found.",
        "business_impact": "May cause delay.",
        "issues": issues or [
            {
                "severity": "critical",
                "title": "Launch before legal",
                "plain_english": "Legal review not complete.",
                "solution": "Delay launch.",
                "source_nodes": ["node_a", "node_b"],
            }
        ],
        "coverage_verified": True,
        "coverage_warning": None,
    }


def _make_openai_response(content: str):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = content
    return mock_response


# ── StorytellerAgent ──────────────────────────────────────────────────────────

class TestStorytellerAgent:
    def test_run_returns_dict(self):
        from core.agents import StorytellerAgent
        agent = StorytellerAgent()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(
            json.dumps(_draft_report())
        )
        with patch("core.agents._get_client", return_value=mock_client):
            result = agent.run(_raw_issues())
        assert isinstance(result, dict)

    def test_run_includes_required_keys(self):
        from core.agents import StorytellerAgent
        agent = StorytellerAgent()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(
            json.dumps(_draft_report())
        )
        with patch("core.agents._get_client", return_value=mock_client):
            result = agent.run(_raw_issues())
        for key in ["overall_assessment", "summary_narrative", "business_impact", "issues", "coverage_verified"]:
            assert key in result

    def test_run_injects_must_include_for_critical_issues(self):
        from core.agents import StorytellerAgent
        agent = StorytellerAgent()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(
            json.dumps(_draft_report())
        )
        raw = _raw_issues()
        raw["friction_lines"][0]["severity"] = 5  # Critical
        with patch("core.agents._get_client", return_value=mock_client):
            agent.run(raw)
        call_args = mock_client.chat.completions.create.call_args
        prompt_text = str(call_args)
        assert "MUST INCLUDE" in prompt_text

    def test_zero_issues_returns_no_issues_found_report(self):
        from core.agents import StorytellerAgent
        agent = StorytellerAgent()
        empty_raw = {"friction_lines": [], "chronological_friction_lines": [], "hub_vulnerabilities": [], "risk_matrix": []}
        result = agent.run(empty_raw)
        assert result["overall_assessment"] == "No Issues Found"
        assert result["issues"] == []
        assert result["coverage_verified"] is True


# ── CriticAgent ───────────────────────────────────────────────────────────────

class TestCriticAgent:
    def test_returns_report_unchanged_when_no_gaps(self):
        from core.agents import CriticAgent
        agent = CriticAgent()
        mock_client = MagicMock()
        # Critic returns empty list — no gaps
        mock_client.chat.completions.create.return_value = _make_openai_response("[]")
        with patch("core.agents._get_client", return_value=mock_client):
            result = agent.run(_draft_report(), _raw_issues())
        assert result["overall_assessment"] == "High Risk"

    def test_triggers_revision_when_gaps_found(self):
        from core.agents import StorytellerAgent, CriticAgent
        critic = CriticAgent()
        storyteller = MagicMock()
        revised = _draft_report()
        revised["overall_assessment"] = "Revised"
        storyteller.run.return_value = revised

        mock_client = MagicMock()
        # First critic call finds a gap; second finds none
        mock_client.chat.completions.create.side_effect = [
            _make_openai_response('[{"diamond": "Missing issue"}]'),
            _make_openai_response("[]"),
        ]
        with patch("core.agents._get_client", return_value=mock_client):
            result = critic.run(_draft_report(), _raw_issues(), storyteller=storyteller)

        assert storyteller.run.called
        assert result["overall_assessment"] == "Revised"

    def test_appends_coverage_warning_after_max_retries(self):
        from core.agents import StorytellerAgent, CriticAgent
        critic = CriticAgent()
        storyteller = MagicMock()
        storyteller.run.return_value = _draft_report()

        mock_client = MagicMock()
        # Critic always finds gaps across both retry attempts
        mock_client.chat.completions.create.side_effect = [
            _make_openai_response('[{"diamond": "Persistent gap"}]'),
            _make_openai_response('[{"diamond": "Persistent gap"}]'),
        ]
        with patch("core.agents._get_client", return_value=mock_client):
            result = critic.run(_draft_report(), _raw_issues(), storyteller=storyteller)

        assert result["coverage_verified"] is False
        assert result["coverage_warning"] is not None


# ── KDECoverageCheck ──────────────────────────────────────────────────────────

class TestKDECoverageCheck:
    def _make_vault_with_embeddings(self, source_embeddings, source_ids):
        mock_vault = MagicMock()
        mock_vault.conn.cursor.return_value.fetchall.return_value = [
            {"source_chunk_id": sid} for sid in source_ids
        ]
        mock_vault.collection.get.return_value = {
            "embeddings": source_embeddings,
            "ids": source_ids,
        }
        return mock_vault

    def test_coverage_verified_true_when_output_covers_source(self):
        from core.agents import KDECoverageCheck
        # Source and output are identical vectors — maximum similarity
        vecs = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        mock_vault = self._make_vault_with_embeddings(vecs, ["chunk_1", "chunk_2"])
        # Attach a mock embedding function to the vault's collection
        mock_vault.collection._embedding_function = MagicMock(
            return_value=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        )
        report = _draft_report(issues=[
            {"severity": "high", "title": "T", "plain_english": "covered text", "solution": "s", "source_nodes": []},
        ])
        checker = KDECoverageCheck(mock_vault)
        result = checker.check("doc_1", report)
        assert result["coverage_verified"] is True
        assert result["coverage_warning"] is None

    def test_coverage_warning_set_when_cluster_uncovered(self):
        from core.agents import KDECoverageCheck
        # Source has a vector in a very different direction from the output
        source_vecs = [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]  # second is orthogonal to output
        mock_vault = self._make_vault_with_embeddings(source_vecs, ["chunk_1", "chunk_2"])
        # Output embedding only covers the first vector direction
        mock_vault.collection._embedding_function = MagicMock(
            return_value=[[1.0, 0.0, 0.0]]
        )
        report = _draft_report(issues=[
            {"severity": "high", "title": "T", "plain_english": "covered", "solution": "s", "source_nodes": []},
        ])
        checker = KDECoverageCheck(mock_vault)
        result = checker.check("doc_1", report)
        assert result["coverage_verified"] is False
        assert result["coverage_warning"] is not None

    def test_returns_report_unchanged_when_no_source_chunks(self):
        from core.agents import KDECoverageCheck
        mock_vault = MagicMock()
        mock_vault.conn.cursor.return_value.fetchall.return_value = []
        mock_vault.collection.get.return_value = {"embeddings": [], "ids": []}
        checker = KDECoverageCheck(mock_vault)
        result = checker.check("doc_empty", _draft_report())
        assert result["coverage_verified"] is True
