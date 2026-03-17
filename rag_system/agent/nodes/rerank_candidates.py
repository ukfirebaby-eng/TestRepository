"""Reranking node: rerank candidates and trim to final context window."""

from __future__ import annotations

import time

from rag_system.agent.state import RAGState


def rerank_candidates_node(
    state: RAGState,
    reranker=None,
    rerank_top_n: int = 20,
    final_chunks: int = 8,
) -> RAGState:
    """Rerank candidates and trim to the final context set.

    Pipeline:
    1. Take up to rerank_top_n candidates from the fused list
    2. Run reranker to get a relevance-ordered set
    3. Trim to final_chunks for LLM context
    """
    candidates = state.get("candidate_chunks", [])
    query = state.get("rewritten_queries", [])
    query = query[-1] if query else state.get("original_query", "")

    if not candidates:
        return {**state, "reranked_chunks": []}

    t0 = time.time()

    if reranker is not None:
        reranked = reranker.rerank(query, candidates[:rerank_top_n], top_n=final_chunks)
    else:
        # No reranker: just take top final_chunks by existing rank
        reranked = sorted(
            candidates[:rerank_top_n],
            key=lambda c: c.rank or 9999,
        )[:final_chunks]

    rerank_ms = (time.time() - t0) * 1000

    cost = dict(state.get("cost_counters", {}))
    cost["rerank_calls"] = cost.get("rerank_calls", 0) + 1

    latency = dict(state.get("latency_counters", {}))
    latency["rerank_ms"] = rerank_ms

    return {
        **state,
        "reranked_chunks": reranked,
        "cost_counters": cost,
        "latency_counters": latency,
    }
