"""Retrieval node: execute hybrid search and collect candidates."""

from __future__ import annotations

import time
from typing import Any

from rag_system.agent.state import RAGState
from rag_system.models import RetrievalAttempt


def retrieve_candidates_node(
    state: RAGState,
    retriever=None,
    embedder=None,
    bm25_k: int = 50,
    dense_k: int = 50,
) -> RAGState:
    """Execute hybrid retrieval for the current query.

    Uses the latest rewritten query if available, otherwise the original query.
    """
    if retriever is None or embedder is None:
        return {**state, "error": "Retriever or embedder not configured"}

    rewritten = state.get("rewritten_queries", [])
    query = rewritten[-1] if rewritten else state.get("original_query", "")
    mode = state.get("retrieval_mode", "balanced_hybrid")
    tenant_id = state.get("tenant_id", "")
    filters = state.get("request_filters", {})

    t0 = time.time()

    # Embed the query
    embedding = embedder.embed(query)
    embed_ms = (time.time() - t0) * 1000

    t1 = time.time()
    chunks = retriever.retrieve(
        query=query,
        embedding=embedding,
        tenant_id=tenant_id,
        filters=filters,
        bm25_k=bm25_k,
        dense_k=dense_k,
        mode=mode,
    )
    retrieve_ms = (time.time() - t1) * 1000

    attempt_num = len(state.get("retrieval_attempts", [])) + 1
    attempt = RetrievalAttempt(
        attempt_number=attempt_num,
        query=query,
        mode=mode,
        filters=filters,
        fused_candidates=len(chunks),
        latency_ms=embed_ms + retrieve_ms,
    )

    attempts = list(state.get("retrieval_attempts", []))
    attempts.append(attempt.model_dump())

    # Merge new candidates with existing (dedup by chunk_id)
    existing = {c.chunk_id: c for c in state.get("candidate_chunks", [])}
    for chunk in chunks:
        existing[chunk.chunk_id] = chunk

    cost = dict(state.get("cost_counters", {}))
    cost["embedding_calls"] = cost.get("embedding_calls", 0) + 1

    latency = dict(state.get("latency_counters", {}))
    latency[f"retrieve_{attempt_num}_ms"] = embed_ms + retrieve_ms

    return {
        **state,
        "candidate_chunks": list(existing.values()),
        "retrieval_attempts": attempts,
        "cost_counters": cost,
        "latency_counters": latency,
    }
