"""Evaluation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from rag_system.api.middleware.auth import verify_api_key
from rag_system.models import EvalRequest, EvalResult

router = APIRouter(tags=["evals"])


@router.post("/v1/evals/run", response_model=EvalResult)
async def run_eval(
    req: EvalRequest,
    request: Request,
    _: str = Depends(verify_api_key),
) -> EvalResult:
    """Run an evaluation benchmark against the RAG system."""
    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG graph not initialized",
        )

    try:
        from rag_system.eval.harness import EvalHarness
        harness = EvalHarness(graph=graph)
        return harness.run(req)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Eval error: {e}",
        )
