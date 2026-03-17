"""Trace retrieval endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from rag_system.api.middleware.auth import verify_api_key

router = APIRouter(tags=["traces"])


@router.get("/v1/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
) -> dict:
    """Retrieve a query trace by ID."""
    doc_store = getattr(request.app.state, "document_store", None)
    if doc_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document store not initialized",
        )

    trace = doc_store.get_trace(trace_id)
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace {trace_id} not found",
        )

    return trace
