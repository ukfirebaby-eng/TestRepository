"""Document and chunk persistence (in-memory for dev, SQLite/Postgres for prod)."""

from __future__ import annotations

from typing import Any

from rag_system.models import Chunk, Document


class InMemoryDocumentStore:
    """In-memory document store for development and testing."""

    def __init__(self) -> None:
        self._documents: dict[str, Document] = {}  # doc_id -> Document
        self._traces: dict[str, dict[str, Any]] = {}  # trace_id -> trace data

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def save_document(self, doc: Document) -> None:
        self._documents[doc.doc_id] = doc

    def get_document(self, doc_id: str, tenant_id: str) -> Document | None:
        doc = self._documents.get(doc_id)
        if doc and doc.tenant_id == tenant_id and not doc.is_deleted:
            return doc
        return None

    def delete_document(self, doc_id: str, tenant_id: str) -> bool:
        doc = self._documents.get(doc_id)
        if doc and doc.tenant_id == tenant_id:
            doc.is_deleted = True
            return True
        return False

    def list_documents(
        self,
        tenant_id: str,
        include_deleted: bool = False,
    ) -> list[Document]:
        return [
            d for d in self._documents.values()
            if d.tenant_id == tenant_id and (include_deleted or not d.is_deleted)
        ]

    # ------------------------------------------------------------------
    # Chunks
    # ------------------------------------------------------------------

    def get_chunks(self, doc_id: str, tenant_id: str) -> list[Chunk]:
        doc = self.get_document(doc_id, tenant_id)
        return doc.chunks if doc else []

    def get_chunk(self, chunk_id: str, tenant_id: str) -> Chunk | None:
        for doc in self._documents.values():
            if doc.tenant_id == tenant_id and not doc.is_deleted:
                for chunk in doc.chunks:
                    if chunk.chunk_id == chunk_id:
                        return chunk
        return None

    # ------------------------------------------------------------------
    # Traces / audit
    # ------------------------------------------------------------------

    def save_trace(self, trace_id: str, data: dict[str, Any]) -> None:
        self._traces[trace_id] = data

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        return self._traces.get(trace_id)
