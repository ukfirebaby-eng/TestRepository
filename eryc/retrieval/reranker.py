"""
Optional reranking step for the ERYC retrieval pipeline.

Phase C-5: Improve the final ordering of the top candidate set.
Times out gracefully and falls back to the fused ranking if the reranker
exceeds the configured deadline (spec §11.1 — reranker timeout).
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

from eryc.models.domain import CandidateChunk

logger = logging.getLogger(__name__)

# Default timeout in seconds.  Spec §11.1 treats reranker timeout as a
# known failure mode that should degrade gracefully.
_DEFAULT_TIMEOUT_SECONDS = 3.0


class Reranker:
    """
    Cross-encoder reranker that improves ordering of candidate chunks.

    Uses ``cross-encoder/ms-marco-MiniLM-L-6-v2`` when available; falls
    back to the fused RRF ordering otherwise.
    """

    def __init__(self, *, timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout_seconds
        self._model = None
        try:
            from sentence_transformers import CrossEncoder  # type: ignore

            self._model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("Loaded reranker model")
        except ImportError:
            logger.debug("Cross-encoder not available; reranking disabled")

    @property
    def available(self) -> bool:
        return self._model is not None

    def rerank(
        self,
        query: str,
        candidates: List[CandidateChunk],
        *,
        top_n: int = 30,
    ) -> Tuple[List[CandidateChunk], bool]:
        """
        Rerank the top ``top_n`` candidates by cross-encoder score.

        Returns:
            A tuple of (reranked_candidates, timed_out).  If the reranker
            is unavailable or times out, the original order is returned and
            ``timed_out`` is True.
        """
        if not self.available or not candidates:
            return candidates[:top_n], True

        top = candidates[:top_n]
        pairs = [(query, c.text) for c in top]

        start = time.monotonic()
        try:
            scores = self._model.predict(pairs)  # type: ignore
            elapsed = time.monotonic() - start

            if elapsed > self._timeout:
                logger.warning(
                    "Reranker exceeded timeout (%.2fs > %.2fs); using fused order",
                    elapsed,
                    self._timeout,
                )
                return top, True

            ranked = sorted(
                zip(scores, top),
                key=lambda x: x[0],
                reverse=True,
            )
            for score, chunk in ranked:
                chunk.rerank_score = float(score)

            return [c for _, c in ranked], False

        except Exception as exc:
            logger.warning("Reranker failed: %s; using fused order", exc)
            return top, True
