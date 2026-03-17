"""Ingress node: validates input and initializes session state."""

from __future__ import annotations

import time
import uuid

from rag_system.agent.state import RAGState


def ingress_node(state: RAGState) -> RAGState:
    """Validate the incoming query and initialize session metadata."""
    query = state.get("original_query", "").strip()

    if not query:
        return {**state, "error": "Empty query"}

    if len(query) > 4096:
        return {**state, "error": "Query exceeds maximum length of 4096 characters"}

    session_id = state.get("session_id") or str(uuid.uuid4())

    return {
        **state,
        "original_query": query,
        "session_id": session_id,
        "cost_counters": {
            "llm_tokens": 0,
            "embedding_calls": 0,
            "rerank_calls": 0,
        },
        "latency_counters": {"ingress_ms": 0.0},
        "error": None,
    }
