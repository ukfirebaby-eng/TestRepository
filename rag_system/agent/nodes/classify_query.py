"""Query classification node: determine query type to guide retrieval strategy."""

from __future__ import annotations

import re

from rag_system.agent.state import RAGState


def classify_query_node(state: RAGState) -> RAGState:
    """Classify query type without requiring an LLM call.

    Heuristic classification:
    - keyword: short query with IDs, codes, or exact terms
    - temporal: contains time words (latest, recent, current, 2024...)
    - multi_hop: contains "and then", "after", "compare", "difference between"
    - ambiguous: very short (< 4 words) with no clear topic
    - semantic: everything else (natural language question)
    """
    query = state.get("original_query", "")
    words = query.split()
    lower = query.lower()

    is_temporal = bool(re.search(
        r"\b(latest|recent|current|last|new|today|this year|\d{4})\b", lower
    ))
    is_multi_hop = bool(re.search(
        r"\b(and then|after|compare|difference between|versus|vs\.?|both)\b", lower
    ))
    is_exact = bool(re.search(r"\b[A-Z0-9]{2,}-\d+\b", query))  # ticket/ID pattern
    is_ambiguous = len(words) <= 2 and not is_exact

    if is_exact:
        query_type = "keyword"
    elif is_temporal:
        query_type = "temporal"
    elif is_multi_hop:
        query_type = "multi_hop"
    elif is_ambiguous:
        query_type = "ambiguous"
    else:
        query_type = "semantic"

    classification = {
        "type": query_type,
        "requires_exact_match": is_exact,
        "is_temporal": is_temporal,
        "is_multi_hop": is_multi_hop,
        "is_ambiguous": is_ambiguous,
        "word_count": len(words),
    }

    return {**state, "query_classification": classification}
