"""Abstract base classes for retrieval backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from rag_system.models import Chunk


class RetrievalBackend(ABC):
    """Abstract retrieval backend. Implementations: in-memory, Elasticsearch."""

    @abstractmethod
    def index(self, chunks: list[Chunk]) -> None:
        """Index a list of chunks."""

    @abstractmethod
    def delete(self, doc_id: str, tenant_id: str) -> int:
        """Delete all chunks for a document. Returns number deleted."""

    @abstractmethod
    def bm25_search(
        self,
        query: str,
        tenant_id: str,
        filters: dict[str, Any],
        k: int,
    ) -> list[tuple[str, float]]:
        """BM25 lexical search. Returns [(chunk_id, score)] sorted descending."""

    @abstractmethod
    def dense_search(
        self,
        embedding: list[float],
        tenant_id: str,
        filters: dict[str, Any],
        k: int,
    ) -> list[tuple[str, float]]:
        """Dense vector search. Returns [(chunk_id, score)] sorted descending."""

    @abstractmethod
    def get_chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        """Fetch chunks by ID."""

    @abstractmethod
    def get_all_chunks(self, tenant_id: str) -> list[Chunk]:
        """Return all chunks for a tenant (used for full reindex)."""
