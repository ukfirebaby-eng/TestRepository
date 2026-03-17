"""Index store: maps tenant+doc to indexed chunk IDs for reindex tracking."""

from __future__ import annotations


class InMemoryIndexStore:
    """Tracks which documents have been indexed and their chunk IDs."""

    def __init__(self) -> None:
        # (tenant_id, doc_id) -> set of chunk_ids
        self._index: dict[tuple[str, str], set[str]] = {}

    def record_indexed(self, tenant_id: str, doc_id: str, chunk_ids: list[str]) -> None:
        self._index[(tenant_id, doc_id)] = set(chunk_ids)

    def get_chunk_ids(self, tenant_id: str, doc_id: str) -> set[str]:
        return self._index.get((tenant_id, doc_id), set())

    def remove(self, tenant_id: str, doc_id: str) -> None:
        self._index.pop((tenant_id, doc_id), None)

    def list_docs(self, tenant_id: str) -> list[str]:
        return [doc_id for (tid, doc_id) in self._index if tid == tenant_id]

    def total_chunks(self, tenant_id: str) -> int:
        return sum(
            len(ids) for (tid, _), ids in self._index.items() if tid == tenant_id
        )
