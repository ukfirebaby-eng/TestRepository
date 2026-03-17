"""Query endpoints: POST /v1/query and POST /v1/query/stream."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from rag_system.agent.state import initial_state
from rag_system.api.middleware.auth import verify_api_key
from rag_system.models import QueryRequest, QueryResponse

router = APIRouter(tags=["query"])


@router.post("/v1/query", response_model=QueryResponse)
async def query(
    req: QueryRequest,
    request: Request,
    _: str = Depends(verify_api_key),
) -> QueryResponse:
    """Execute a RAG query and return a cited answer."""
    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG graph not initialized",
        )

    settings_obj = getattr(request.app.state, "settings", None)
    max_steps = getattr(settings_obj, "max_retrieval_rounds", 3) if settings_obj else 3

    t0 = time.time()
    trace_id = str(uuid.uuid4())

    agent_state = initial_state(
        query=req.query,
        tenant_id=req.tenant_id,
        user_id=req.user_id,
        session_id=req.session_id or trace_id,
        retrieval_mode=req.retrieval_mode,
        filters=req.filters,
        max_steps=max_steps,
    )

    try:
        result = graph.invoke(agent_state)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent error: {e}",
        )

    latency_ms = (time.time() - t0) * 1000

    return QueryResponse(
        answer=result.get("validated_answer") or "No answer generated.",
        citations=result.get("citations", []),
        confidence=result.get("confidence", 1.0),
        retrieval_mode_used=result.get("retrieval_mode", req.retrieval_mode),
        trace_id=result.get("session_id", trace_id),
        latency_ms=latency_ms,
        used_retry_loop=result.get("used_retry_loop", False),
        evidence_sufficient=result.get("evidence_sufficient", False),
        query_classification=result.get("query_classification", {}),
    )


@router.post("/v1/query/stream")
async def query_stream(
    req: QueryRequest,
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Stream a RAG query response using Server-Sent Events."""
    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG graph not initialized",
        )

    settings_obj = getattr(request.app.state, "settings", None)
    max_steps = getattr(settings_obj, "max_retrieval_rounds", 3) if settings_obj else 3

    trace_id = str(uuid.uuid4())
    agent_state = initial_state(
        query=req.query,
        tenant_id=req.tenant_id,
        user_id=req.user_id,
        session_id=req.session_id or trace_id,
        retrieval_mode=req.retrieval_mode,
        filters=req.filters,
        max_steps=max_steps,
    )

    async def event_stream():
        import json

        # LangGraph stream yields (node_name, state_update) tuples
        for chunk in graph.stream(agent_state):
            for node_name, state_update in chunk.items():
                event = json.dumps({"node": node_name, "update": _safe_state(state_update)})
                yield f"data: {event}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _safe_state(state: dict) -> dict:
    """Strip non-serializable objects for streaming output."""
    safe = {}
    for k, v in state.items():
        if k in ("candidate_chunks", "reranked_chunks"):
            safe[k] = len(v) if isinstance(v, list) else v
        elif k == "citations":
            safe[k] = [c.model_dump() if hasattr(c, "model_dump") else c for c in (v or [])]
        elif isinstance(v, (str, int, float, bool, list, dict, type(None))):
            safe[k] = v
    return safe
