"""Ingestion endpoints: POST /v1/ingest and POST /v1/reindex."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from rag_system.api.middleware.auth import verify_api_key
from rag_system.models import IngestRequest, IngestResponse, ReindexRequest, ReindexResponse

router = APIRouter(tags=["ingest"])


@router.post("/v1/ingest", response_model=IngestResponse)
async def ingest(
    req: IngestRequest,
    request: Request,
    _: str = Depends(verify_api_key),
) -> IngestResponse:
    """Ingest a document into the RAG index."""
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion pipeline not initialized",
        )

    try:
        return pipeline.ingest(req)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion error: {e}",
        )


@router.post("/v1/reindex", response_model=ReindexResponse)
async def reindex(
    req: ReindexRequest,
    request: Request,
    _: str = Depends(verify_api_key),
) -> ReindexResponse:
    """Reindex documents for a tenant."""
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion pipeline not initialized",
        )

    try:
        count = pipeline.reindex(req.tenant_id, req.doc_ids)
        return ReindexResponse(queued_docs=count, status="completed")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reindex error: {e}",
        )
