"""
EDICState — LangGraph state model for the ERYC evidence-grounded query workflow.

Phase D-1 of the implementation backlog.

The state captures everything needed to track a query from ingress through
classification, retrieval, evidence judgement, answer composition and
grounding validation.  It is serialisable so LangGraph can checkpoint it
between nodes (spec §6.2).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict


class EDICState(TypedDict, total=False):
    """
    Full state for a single EDIC (Evidence-grounded Document Intelligence Console)
    query run.

    Fields are grouped to mirror the categories described in spec §6.2.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    thread_id: str
    run_id: str
    user_id: str
    workspace_id: str
    allowed_sensitivity_levels: List[str]

    # ------------------------------------------------------------------
    # Raw request
    # ------------------------------------------------------------------
    query: str
    filters: Dict[str, Any]  # The QueryFilters dict from the API request.
    response_options: Dict[str, Any]

    # ------------------------------------------------------------------
    # Analysis (query classifier output)
    # ------------------------------------------------------------------
    query_class: Optional[str]  # One of the QueryClass enum values.
    exact_terms: List[str]
    entities: List[Dict[str, Any]]
    temporal_filter: Optional[Dict[str, Any]]  # {"from": ..., "to": ...}

    # ------------------------------------------------------------------
    # Retrieval plan
    # ------------------------------------------------------------------
    retrieval_mode: str  # "lexical" | "semantic" | "hybrid"
    lexical_k: int
    semantic_k: int
    rerank_top_n: int

    # ------------------------------------------------------------------
    # Retrieval execution history
    # ------------------------------------------------------------------
    retrieval_round: int
    tool_calls_used: int
    retrieval_attempts: List[Dict[str, Any]]  # Persisted per-round records.

    # ------------------------------------------------------------------
    # Candidate and context sets
    # ------------------------------------------------------------------
    candidate_chunks: List[Dict[str, Any]]  # Serialised CandidateChunk dicts.
    context_chunks: List[Dict[str, Any]]     # Post-expansion context.

    # ------------------------------------------------------------------
    # Answer state
    # ------------------------------------------------------------------
    draft_answer: Optional[str]
    final_answer: Optional[str]
    citations: List[Dict[str, Any]]         # Serialised Citation dicts.
    grounding_report: Optional[Dict[str, Any]]

    # ------------------------------------------------------------------
    # Evidence verdict (set by the evidence judge)
    # ------------------------------------------------------------------
    evidence_verdict: Optional[str]  # "enough" | "needs_more" | "insufficient"

    # ------------------------------------------------------------------
    # Operational state
    # ------------------------------------------------------------------
    errors: List[str]
    started_at: str
    completed_at: Optional[str]
    diagnostics: Dict[str, Any]


def initial_state(
    *,
    thread_id: str,
    run_id: str,
    user_id: str,
    query: str,
    filters: Dict[str, Any],
    response_options: Optional[Dict[str, Any]] = None,
) -> EDICState:
    """
    Build the initial :class:`EDICState` for a new query run.

    All optional lists and counters are initialised to safe defaults so
    that downstream nodes do not need to guard against missing keys.
    """
    from datetime import datetime, timezone

    workspace_id = filters.get("workspace_id", "")

    return EDICState(
        thread_id=thread_id,
        run_id=run_id,
        user_id=user_id,
        workspace_id=workspace_id,
        allowed_sensitivity_levels=["standard", "restricted", "confidential"],
        query=query,
        filters=filters,
        response_options=response_options or {},
        query_class=None,
        exact_terms=[],
        entities=[],
        temporal_filter=None,
        retrieval_mode="hybrid",
        lexical_k=20,
        semantic_k=20,
        rerank_top_n=30,
        retrieval_round=0,
        tool_calls_used=0,
        retrieval_attempts=[],
        candidate_chunks=[],
        context_chunks=[],
        draft_answer=None,
        final_answer=None,
        citations=[],
        grounding_report=None,
        evidence_verdict=None,
        errors=[],
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=None,
        diagnostics={},
    )
