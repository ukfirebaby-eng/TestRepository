"""Abstract reranker interface and mock implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from rag_system.models import Chunk


class BaseReranker(ABC):
    @abstractmethod
    def rerank(self, query: str, chunks: list[Chunk], top_n: int) -> list[Chunk]:
        """Rerank chunks by relevance to query. Returns top_n chunks sorted best-first."""


class MockReranker(BaseReranker):
    """Mock reranker that scores by simple keyword overlap.

    Used in development and tests when Cohere/cross-encoder is unavailable.
    """

    def rerank(self, query: str, chunks: list[Chunk], top_n: int) -> list[Chunk]:
        query_tokens = set(query.lower().split())
        scored: list[tuple[Chunk, float]] = []

        for chunk in chunks:
            text_tokens = set(chunk.semantic_text.lower().split())
            overlap = len(query_tokens & text_tokens)
            # Normalize by query length to get a 0-1 score
            score = overlap / max(len(query_tokens), 1)
            scored.append((chunk, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        result: list[Chunk] = []
        for rank, (chunk, score) in enumerate(scored[:top_n]):
            result.append(chunk.model_copy(update={"rerank_score": score, "rank": rank + 1}))
        return result


def get_reranker(
    reranker_type: str = "mock",
    api_key: str = "",
    model: str = "rerank-english-v3.0",
) -> BaseReranker:
    """Factory for reranker backends."""
    if reranker_type == "mock":
        return MockReranker()
    elif reranker_type == "cohere":
        from rag_system.reranking.cohere_reranker import CohereReranker
        return CohereReranker(api_key=api_key, model=model)
    else:
        raise ValueError(f"Unknown reranker type: {reranker_type}")
