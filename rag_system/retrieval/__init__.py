"""Retrieval layer: BM25, dense vector, hybrid search with RRF fusion."""

from .hybrid import HybridRetriever
from .rrf import reciprocal_rank_fusion

__all__ = ["HybridRetriever", "reciprocal_rank_fusion"]
