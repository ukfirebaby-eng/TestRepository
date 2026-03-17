"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from rag_system.config import get_settings
from rag_system.models import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/v1/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Basic liveness check. Returns 200 if the service is running."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        backend=settings.backend,
        components={
            "api": "ok",
            "retriever": "ok" if _get_retriever(request) else "unavailable",
        },
    )


@router.get("/v1/ready", response_model=ReadyResponse)
async def ready(request: Request) -> ReadyResponse:
    """Readiness check: returns 200 only when all dependencies are available."""
    retriever = _get_retriever(request)
    checks = {
        "retriever": retriever is not None,
        "embedder": _get_embedder(request) is not None,
    }
    all_ready = all(checks.values())
    return ReadyResponse(ready=all_ready, checks=checks)


def _get_retriever(request: Request):
    return getattr(request.app.state, "retriever", None)


def _get_embedder(request: Request):
    return getattr(request.app.state, "embedder", None)
