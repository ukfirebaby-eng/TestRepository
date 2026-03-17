"""Finalize node: assemble the final response."""

from __future__ import annotations

import time

from rag_system.agent.state import RAGState


def finalize_node(state: RAGState) -> RAGState:
    """Assemble the final response state.

    Computes total latency and ensures all required fields are present.
    """
    latency = dict(state.get("latency_counters", {}))
    total_ms = sum(latency.values())
    latency["total_ms"] = total_ms

    answer = state.get("validated_answer") or state.get("draft_answer") or \
             "I was unable to generate an answer."

    return {
        **state,
        "validated_answer": answer,
        "latency_counters": latency,
    }
