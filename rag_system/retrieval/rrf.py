"""Reciprocal Rank Fusion (RRF) for combining ranked lists.

RRF score formula: score(d) = sum_i( 1 / (k + rank_i(d)) )

where rank_i(d) is the 1-based position of document d in ranking list i,
and k is a smoothing constant (typically 60).

RRF is robust because it ignores raw score incompatibility between lexical
and semantic retrieval systems, which operate on different score scales.
"""

from __future__ import annotations


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Fuse multiple ranked lists using Reciprocal Rank Fusion.

    Args:
        rankings: Each inner list is a ranked list of chunk IDs (best first).
        k: Smoothing constant. Higher k reduces the impact of top-rank advantage.
           Elastic and OpenSearch default to 60.

    Returns:
        List of (chunk_id, rrf_score) sorted by score descending.
    """
    scores: dict[str, float] = {}

    for ranking in rankings:
        for rank_0based, chunk_id in enumerate(ranking):
            rank_1based = rank_0based + 1
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank_1based)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
