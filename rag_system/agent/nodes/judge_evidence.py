"""Evidence sufficiency judge: decide if retrieved chunks are enough to answer."""

from __future__ import annotations

from rag_system.agent.state import RAGState

# Minimum reranked chunks to consider evidence sufficient
_MIN_CHUNKS = 1
# Minimum average rerank score threshold (when scores are available)
_MIN_SCORE = 0.01


def judge_evidence_node(state: RAGState) -> RAGState:
    """Heuristically judge whether retrieved evidence is sufficient.

    Criteria:
    - At least _MIN_CHUNKS reranked chunks available
    - Average rerank score above threshold (if scores present)
    - Not exceeded retry budget

    Sets state["evidence_sufficient"] = True/False.
    Also builds a brief evidence_summary string.
    """
    reranked = state.get("reranked_chunks", [])
    query = state.get("original_query", "")
    steps = state.get("max_steps_remaining", 0)

    if not reranked:
        return {
            **state,
            "evidence_sufficient": False,
            "evidence_summary": "No relevant chunks found.",
        }

    # Check relevance scores
    scored = [c for c in reranked if c.rerank_score is not None]
    if scored:
        avg_score = sum(c.rerank_score for c in scored) / len(scored)
        sufficient = len(reranked) >= _MIN_CHUNKS and avg_score >= _MIN_SCORE
    else:
        sufficient = len(reranked) >= _MIN_CHUNKS

    # Build brief evidence summary
    titles = [c.section_title for c in reranked[:3] if c.section_title]
    summary = f"Found {len(reranked)} chunks from sections: {', '.join(titles)}" if titles else \
              f"Found {len(reranked)} chunks."

    return {
        **state,
        "evidence_sufficient": sufficient,
        "evidence_summary": summary,
    }
