"""Document retrieval endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from rag_system.api.middleware.auth import verify_api_key

router = APIRouter(tags=["documents"])


@router.get("/v1/documents/{doc_id}")
async def get_document(
    doc_id: str,
    tenant_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
) -> dict:
    """Retrieve a document by ID."""
    doc_store = getattr(request.app.state, "document_store", None)
    if doc_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document store not initialized",
        )

    doc = doc_store.get_document(doc_id, tenant_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {doc_id} not found",
        )

    return {
        "doc_id": doc.doc_id,
        "tenant_id": doc.tenant_id,
        "title": doc.title,
        "source_uri": doc.source_uri,
        "document_type": doc.document_type,
        "version": doc.version,
        "acl_tags": doc.acl_tags,
        "chunk_count": len(doc.chunks),
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
        "metadata": doc.metadata,
    }
