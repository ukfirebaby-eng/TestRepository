"""
Tests for the LangGraph workflow: state initialisation, node logic and routing.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from eryc.database.connection import open_connection
from eryc.database.migrations import apply_migrations
from eryc.workflow.state import EDICState, initial_state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_state() -> EDICState:
    return initial_state(
        thread_id="thread_test",
        run_id="run_test",
        user_id="user_test",
        query="What actions have been recorded?",
        filters={
            "workspace_id": "ws1",
            "collection_ids": None,
        },
    )


# ---------------------------------------------------------------------------
# State initialisation tests
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_required_fields_present(self, base_state: EDICState) -> None:
        assert base_state["thread_id"] == "thread_test"
        assert base_state["run_id"] == "run_test"
        assert base_state["user_id"] == "user_test"
        assert base_state["query"] == "What actions have been recorded?"
        assert base_state["workspace_id"] == "ws1"

    def test_defaults_are_safe(self, base_state: EDICState) -> None:
        assert base_state["retrieval_round"] == 0
        assert base_state["tool_calls_used"] == 0
        assert base_state["candidate_chunks"] == []
        assert base_state["context_chunks"] == []
        assert base_state["citations"] == []
        assert base_state["errors"] == []
        assert base_state["evidence_verdict"] is None

    def test_started_at_is_iso_format(self, base_state: EDICState) -> None:
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}T", base_state["started_at"])


# ---------------------------------------------------------------------------
# Evidence judge tests
# ---------------------------------------------------------------------------


class TestEvidenceJudge:
    def _run_judge(self, state: Dict[str, Any]) -> Dict[str, Any]:
        from eryc.workflow.nodes import evidence_judge
        return evidence_judge(state)

    def test_enough_when_many_candidates(self) -> None:
        state = {"candidate_chunks": [{}] * 5, "retrieval_round": 1}
        result = self._run_judge(state)
        assert result["evidence_verdict"] == "enough"

    def test_needs_more_when_empty_and_rounds_remain(self) -> None:
        state = {"candidate_chunks": [], "retrieval_round": 1}
        result = self._run_judge(state)
        assert result["evidence_verdict"] == "needs_more"

    def test_insufficient_when_empty_and_rounds_exhausted(self) -> None:
        state = {"candidate_chunks": [], "retrieval_round": 3}
        result = self._run_judge(state)
        assert result["evidence_verdict"] == "insufficient"


# ---------------------------------------------------------------------------
# Grounding validation tests
# ---------------------------------------------------------------------------


class TestGroundingValidate:
    def _run_validator(self, state: Dict[str, Any]) -> Dict[str, Any]:
        from eryc.workflow.nodes import grounding_validate
        return grounding_validate(state)

    def test_insufficient_verdict_returns_safe_no_answer(self) -> None:
        state = {
            "evidence_verdict": "insufficient",
            "final_answer": None,
            "citations": [],
        }
        result = self._run_validator(state)
        assert result["grounding_report"]["verdict"] == "insufficient"
        assert "sufficient evidence" in result["final_answer"].lower()

    def test_pass_verdict_for_covered_answer(self) -> None:
        citations = [{"citation_id": f"c{i}"} for i in range(5)]
        state = {
            "evidence_verdict": "enough",
            "final_answer": "Short answer.",
            "citations": citations,
        }
        result = self._run_validator(state)
        assert result["grounding_report"]["verdict"] == "pass"
        assert "completed_at" in result

    def test_grounding_report_contains_required_fields(self) -> None:
        state = {
            "evidence_verdict": "enough",
            "final_answer": "An answer with some text.",
            "citations": [{"citation_id": "c1"}],
        }
        result = self._run_validator(state)
        report = result["grounding_report"]
        assert "verdict" in report
        assert "citation_coverage" in report
        assert "unsupported_claims" in report


# ---------------------------------------------------------------------------
# Rule-based query classifier tests
# ---------------------------------------------------------------------------


class TestQueryClassifierRules:
    def _classify(self, query: str) -> Dict[str, Any]:
        from eryc.workflow.nodes import _classify_with_rules
        return _classify_with_rules(query)

    def test_timeline_keywords(self) -> None:
        result = self._classify("Build the timeline of contacts.")
        assert result["query_class"] == "timeline_query"

    def test_conflict_keywords(self) -> None:
        result = self._classify("Do these records contradict each other?")
        assert result["query_class"] == "consistency_check"

    def test_policy_keywords(self) -> None:
        result = self._classify("Which policy governs emergency placement?")
        assert result["query_class"] == "authoritative_lookup"

    def test_evidence_state_keywords(self) -> None:
        result = self._classify("Summarise what is evidenced so far.")
        assert result["query_class"] == "evidence_state"

    def test_fallback_to_semantic(self) -> None:
        result = self._classify("Tell me about the documents.")
        assert result["query_class"] == "semantic"


# ---------------------------------------------------------------------------
# Retrieval planner tests
# ---------------------------------------------------------------------------


class TestPlanRetrieval:
    def _plan(self, query_class: str) -> Dict[str, Any]:
        from eryc.workflow.nodes import plan_retrieval

        state = {
            "query_class": query_class,
            "filters": {"workspace_id": "ws1"},
            "temporal_filter": None,
        }
        return plan_retrieval(state)

    def test_keyword_exact_uses_lexical_mode(self) -> None:
        result = self._plan("keyword_exact")
        assert result["retrieval_mode"] == "lexical"

    def test_authoritative_lookup_uses_lexical_mode(self) -> None:
        result = self._plan("authoritative_lookup")
        assert result["retrieval_mode"] == "lexical"

    def test_semantic_uses_hybrid_mode(self) -> None:
        result = self._plan("semantic")
        assert result["retrieval_mode"] == "hybrid"

    def test_plan_includes_k_values(self) -> None:
        result = self._plan("semantic")
        assert result["lexical_k"] > 0
        assert result["semantic_k"] > 0


# ---------------------------------------------------------------------------
# Answer composer fallback tests
# ---------------------------------------------------------------------------


class TestAnswerComposeFallback:
    def test_empty_context_returns_no_evidence_message(self) -> None:
        from eryc.workflow.nodes import answer_compose

        state = {
            "query": "What happened?",
            "context_chunks": [],
            "response_options": {},
            "run_id": "run_test",
        }
        result = answer_compose(state)
        assert "No relevant evidence" in result["final_answer"]
        assert result["citations"] == []

    def test_fallback_includes_chunk_previews(self) -> None:
        from eryc.workflow.nodes import _compose_fallback

        chunks = [
            {
                "chunk_id": "c1",
                "canonical_title": "Test Doc",
                "text_preview": "Some preview text here",
            }
        ]
        answer, cited_ids = _compose_fallback("What happened?", chunks)
        assert "Test Doc" in answer
        assert "c1" in cited_ids
