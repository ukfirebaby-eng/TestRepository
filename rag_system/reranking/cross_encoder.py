"""Local cross-encoder reranker using sentence-transformers."""

from __future__ import annotations

from rag_system.models import Chunk
from rag_system.reranking.base import BaseReranker


class CrossEncoderReranker(BaseReranker):
    """Local cross-encoder reranker.

    Requires: pip install sentence-transformers

    Default model: cross-encoder/ms-marco-MiniLM-L-6-v2
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required: pip install sentence-transformers"
            ) from e

        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, chunks: list[Chunk], top_n: int) -> list[Chunk]:
        if not chunks:
            return []

        pairs = [(query, c.semantic_text) for c in chunks]
        scores = self._model.predict(pairs)

        scored = sorted(
            zip(chunks, scores),
            key=lambda x: float(x[1]),
            reverse=True,
        )

        result: list[Chunk] = []
        for rank, (chunk, score) in enumerate(scored[:top_n]):
            result.append(chunk.model_copy(update={
                "rerank_score": float(score),
                "rank": rank + 1,
            }))
        return result
