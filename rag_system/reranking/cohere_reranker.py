"""Cohere Rerank API client."""

from __future__ import annotations

from rag_system.models import Chunk
from rag_system.reranking.base import BaseReranker


class CohereReranker(BaseReranker):
    """Reranker using the Cohere Rerank API.

    Requires: pip install cohere
    And: COHERE_API_KEY environment variable.

    Note: Cohere's rerank score is query-dependent; trust the rank ordering
    more than the absolute score value.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "rerank-english-v3.0",
        max_chunks_per_call: int = 100,
    ) -> None:
        try:
            import cohere
        except ImportError as e:
            raise ImportError("cohere is required: pip install cohere") from e

        self._client = cohere.Client(api_key)
        self._model = model
        self._max_chunks = max_chunks_per_call

    def rerank(self, query: str, chunks: list[Chunk], top_n: int) -> list[Chunk]:
        if not chunks:
            return []

        # Cohere has a max doc limit per call
        candidates = chunks[: self._max_chunks]
        documents = [c.semantic_text for c in candidates]

        response = self._client.rerank(
            query=query,
            documents=documents,
            model=self._model,
            top_n=min(top_n, len(candidates)),
        )

        result: list[Chunk] = []
        for rank, item in enumerate(response.results):
            chunk = candidates[item.index]
            result.append(chunk.model_copy(update={
                "rerank_score": float(item.relevance_score),
                "rank": rank + 1,
            }))
        return result
