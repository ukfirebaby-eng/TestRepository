"""Trace and feedback node: emit observability data."""

from __future__ import annotations

import logging

from rag_system.agent.state import RAGState

logger = logging.getLogger(__name__)


def trace_and_feedback_node(
    state: RAGState,
    document_store=None,
    tracer=None,
) -> RAGState:
    """Emit trace data and persist the query/answer for evaluation.

    In production: calls LangSmith/OpenTelemetry APIs.
    In dev mode: logs to standard logger.
    """
    session_id = state.get("session_id", "unknown")
    query = state.get("original_query", "")
    answer = state.get("validated_answer", "")
    citations = state.get("citations", [])
    latency = state.get("latency_counters", {})
    cost = state.get("cost_counters", {})
    classification = state.get("query_classification", {})
    attempts = state.get("retrieval_attempts", [])
    used_retry = state.get("used_retry_loop", False)

    trace_data = {
        "session_id": session_id,
        "tenant_id": state.get("tenant_id"),
        "query": query,
        "answer_length": len(answer),
        "citation_count": len(citations),
        "retrieval_attempts": len(attempts),
        "used_retry_loop": used_retry,
        "query_type": classification.get("type"),
        "evidence_sufficient": state.get("evidence_sufficient"),
        "confidence": state.get("confidence"),
        "latency_ms": latency,
        "cost": cost,
    }

    logger.info("RAG trace: %s", trace_data)

    # Persist to document store for later retrieval
    if document_store and session_id:
        try:
            document_store.save_trace(session_id, trace_data)
        except Exception:
            pass

    # Emit to tracer if configured
    if tracer:
        try:
            tracer.record(trace_data)
        except Exception:
            pass

    return state
