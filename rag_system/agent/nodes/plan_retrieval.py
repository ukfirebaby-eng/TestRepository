"""Retrieval planning node: determine search mode and parameters."""

from __future__ import annotations

from rag_system.agent.state import RAGState


def plan_retrieval_node(state: RAGState) -> RAGState:
    """Determine the retrieval mode based on query classification.

    Rules:
    - keyword / exact: lexical_first
    - temporal: balanced_hybrid (freshness ordering handled by filters)
    - multi_hop: semantic_first (need conceptual matching)
    - semantic: balanced_hybrid or override from request
    - ambiguous: balanced_hybrid
    """
    classification = state.get("query_classification", {})
    query_type = classification.get("type", "semantic")
    request_mode = state.get("retrieval_mode", "balanced_hybrid")

    # Request mode takes precedence unless it's the default
    if request_mode != "balanced_hybrid":
        mode = request_mode
    elif query_type == "keyword":
        mode = "lexical_first"
    elif query_type == "multi_hop":
        mode = "semantic_first"
    else:
        mode = "balanced_hybrid"

    return {**state, "retrieval_mode": mode}
