"""
Reciprocal Rank Fusion (RRF) implementation.

Phase C-3: Merge lexical and semantic result lists into a single ranked
candidate set using the formula defined in spec §9.4.

  RRF(d) = Σ 1 / (k + rank_i(d))    where k = 60 by default

Duplicate chunk IDs are merged and their scores summed.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from eryc.models.domain import CandidateChunk, RetrievalDiagnostics, RetrievalMode


def reciprocal_rank_fusion(
    lexical_results: List[CandidateChunk],
    semantic_results: List[CandidateChunk],
    *,
    k: int = 60,
    max_candidates: int = 100,
) -> tuple[List[CandidateChunk], RetrievalDiagnostics]:
    """
    Merge two ranked lists using Reciprocal Rank Fusion.

    Args:
        lexical_results:   Candidates from FTS5, ordered by BM25 rank.
        semantic_results:  Candidates from sqlite-vec, ordered by distance.
        k:                 RRF constant (spec default: 60).
        max_candidates:    Maximum number of candidates to return.

    Returns:
        A tuple of (merged_candidates, diagnostics).  Candidates are sorted
        by descending RRF score.  ``rrf_score`` is set on each candidate.
    """
    # Build a combined registry keyed by chunk_id.
    registry: Dict[str, CandidateChunk] = {}

    for idx, chunk in enumerate(lexical_results):
        rank = idx + 1
        rrf = 1.0 / (k + rank)
        if chunk.chunk_id in registry:
            registry[chunk.chunk_id].rrf_score += rrf
            registry[chunk.chunk_id].lexical_rank = rank
        else:
            chunk.rrf_score = rrf
            chunk.lexical_rank = rank
            registry[chunk.chunk_id] = chunk

    for idx, chunk in enumerate(semantic_results):
        rank = idx + 1
        rrf = 1.0 / (k + rank)
        if chunk.chunk_id in registry:
            registry[chunk.chunk_id].rrf_score += rrf
            if registry[chunk.chunk_id].semantic_rank is None:
                registry[chunk.chunk_id].semantic_rank = rank
        else:
            chunk.rrf_score = rrf
            chunk.semantic_rank = rank
            registry[chunk.chunk_id] = chunk

    merged = sorted(registry.values(), key=lambda c: c.rrf_score, reverse=True)
    merged = merged[:max_candidates]

    mode: RetrievalMode
    if lexical_results and semantic_results:
        mode = RetrievalMode.HYBRID
    elif lexical_results:
        mode = RetrievalMode.LEXICAL
    else:
        mode = RetrievalMode.SEMANTIC

    diagnostics = RetrievalDiagnostics(
        mode=mode,
        query="",  # Set by the caller.
        lexical_hits=len(lexical_results),
        semantic_hits=len(semantic_results),
        fused_count=len(merged),
        final_count=len(merged),
        rrf_k=k,
    )

    return merged, diagnostics
