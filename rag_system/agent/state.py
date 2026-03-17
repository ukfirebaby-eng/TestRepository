"""LangGraph state definition for the RAG agent."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from rag_system.models import Chunk, Citation


class RAGState(TypedDict, total=False):
    """State passed between LangGraph nodes.

    All fields are optional (total=False) to allow partial updates in each node.
    """

    # Request context
    tenant_id: str
    user_id: str
    session_id: str
    original_query: str
    retrieval_mode: str  # balanced_hybrid | lexical_first | semantic_first
    request_filters: dict[str, Any]

    # Query analysis
    rewritten_queries: list[str]
    query_classification: dict[str, Any]
    # Keys: type (keyword|semantic|multi_hop|temporal|ambiguous),
    #       requires_exact_match, is_temporal, is_multi_hop, is_ambiguous

    # Retrieval state
    retrieval_attempts: list[dict[str, Any]]
    candidate_chunks: list[Chunk]
    reranked_chunks: list[Chunk]
    evidence_summary: str
    evidence_sufficient: bool

    # Answer generation
    draft_answer: str
    validated_answer: str
    citations: list[Citation]
    confidence: float

    # Budget tracking
    cost_counters: dict[str, int]   # llm_tokens, embedding_calls, rerank_calls
    latency_counters: dict[str, float]  # per-stage ms
    max_steps_remaining: int  # countdown; starts at max_retrieval_rounds

    # Flags and errors
    policy_flags: list[str]
    used_retry_loop: bool
    error: str | None


def initial_state(
    query: str,
    tenant_id: str,
    user_id: str = "anonymous",
    session_id: str = "",
    retrieval_mode: str = "balanced_hybrid",
    filters: dict[str, Any] | None = None,
    max_steps: int = 3,
) -> RAGState:
    """Create the initial RAGState for a new query."""
    import uuid

    return RAGState(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id or str(uuid.uuid4()),
        original_query=query,
        retrieval_mode=retrieval_mode,
        request_filters=filters or {},
        rewritten_queries=[],
        query_classification={},
        retrieval_attempts=[],
        candidate_chunks=[],
        reranked_chunks=[],
        evidence_summary="",
        evidence_sufficient=False,
        draft_answer="",
        validated_answer="",
        citations=[],
        confidence=1.0,
        cost_counters={"llm_tokens": 0, "embedding_calls": 0, "rerank_calls": 0},
        latency_counters={},
        max_steps_remaining=max_steps,
        policy_flags=[],
        used_retry_loop=False,
        error=None,
    )
