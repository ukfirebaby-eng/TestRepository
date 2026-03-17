"""Grounding validation node: verify citations resolve to retrieved chunks."""

from __future__ import annotations

import re

from rag_system.agent.state import RAGState
from rag_system.models import Citation


def validate_grounding_node(state: RAGState) -> RAGState:
    """Validate that the draft answer is grounded in retrieved evidence.

    Checks:
    1. Every citation resolves to a reranked chunk
    2. Answer actually addresses the question (length heuristic)
    3. No citation points to a chunk not in the evidence set
    4. Strips citations to non-existent chunks from the answer
    """
    answer = state.get("draft_answer", "")
    citations = state.get("citations", [])
    reranked = state.get("reranked_chunks", [])

    valid_chunk_ids = {c.chunk_id for c in reranked}
    cited_ids = set(re.findall(r"\[([a-f0-9\-]{36})\]", answer))

    # Filter out any citations to chunks not in evidence
    valid_citations = [c for c in citations if c.chunk_id in valid_chunk_ids]

    # Remove dangling citation markers from answer text
    validated_answer = answer
    for cid in cited_ids - valid_chunk_ids:
        validated_answer = validated_answer.replace(f"[{cid}]", "")

    # Sanity check: answer should be non-empty and somewhat address the query
    if len(validated_answer.strip()) < 20:
        validated_answer = "I was unable to find a satisfactory answer from the available evidence."
        valid_citations = []

    return {
        **state,
        "validated_answer": validated_answer.strip(),
        "citations": valid_citations,
    }
