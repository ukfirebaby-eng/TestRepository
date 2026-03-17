"""Evaluation metrics: nDCG, citation precision, faithfulness."""

from __future__ import annotations

import math


def ndcg_at_k(
    retrieved_ids: list[str],
    relevant_ids: list[str],
    k: int = 10,
) -> float:
    """Compute Normalized Discounted Cumulative Gain at k.

    Args:
        retrieved_ids: Retrieved doc IDs in rank order (best first).
        relevant_ids: Ground-truth relevant doc IDs.
        k: Cutoff rank.

    Returns:
        nDCG@k score in [0, 1].
    """
    if not relevant_ids:
        return 0.0

    relevant_set = set(relevant_ids)
    dcg = 0.0
    for rank, doc_id in enumerate(retrieved_ids[:k], start=1):
        if doc_id in relevant_set:
            dcg += 1.0 / math.log2(rank + 1)

    # Ideal DCG: all relevant docs at top positions
    ideal_count = min(len(relevant_set), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))

    return dcg / idcg if idcg > 0 else 0.0


def citation_precision(
    cited_chunk_ids: list[str],
    relevant_chunk_ids: list[str],
) -> float:
    """Fraction of cited chunks that are relevant.

    Returns 0 if no citations, 1 if all citations are relevant.
    """
    if not cited_chunk_ids:
        return 0.0

    relevant_set = set(relevant_chunk_ids)
    correct = sum(1 for cid in cited_chunk_ids if cid in relevant_set)
    return correct / len(cited_chunk_ids)


def faithfulness_score(answer: str, evidence_chunks: list[str]) -> float:
    """Estimate answer faithfulness via simple text overlap heuristic.

    Returns fraction of answer words that appear in evidence.
    In production, use an LLM-based faithfulness checker.
    """
    if not answer or not evidence_chunks:
        return 0.0

    answer_words = set(answer.lower().split())
    evidence_text = " ".join(evidence_chunks).lower()
    evidence_words = set(evidence_text.split())

    overlap = answer_words & evidence_words
    return len(overlap) / len(answer_words) if answer_words else 0.0
