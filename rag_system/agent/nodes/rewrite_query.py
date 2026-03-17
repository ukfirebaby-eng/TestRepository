"""Query rewriting node: expand/rephrase the query for a retry retrieval pass."""

from __future__ import annotations

from rag_system.agent.state import RAGState


def rewrite_query_node(state: RAGState) -> RAGState:
    """Rewrite the query for better retrieval coverage on retry.

    In production this would call an LLM. Here we use lightweight heuristics:
    - Expand acronyms (placeholder)
    - Add synonyms for known terms
    - Simplify overly specific queries
    """
    original = state.get("original_query", "")
    rewritten = list(state.get("rewritten_queries", []))
    steps = state.get("max_steps_remaining", 0)

    attempt_num = len(rewritten) + 1

    # Heuristic rewrites (production: replace with LLM call)
    if attempt_num == 1:
        # First retry: generalize / expand
        new_query = _expand_query(original)
    else:
        # Second retry: try key phrases only
        new_query = _extract_key_phrases(original)

    rewritten.append(new_query)

    return {
        **state,
        "rewritten_queries": rewritten,
        "max_steps_remaining": max(0, steps - 1),
        "used_retry_loop": True,
        # Clear candidates so we start fresh
        "candidate_chunks": [],
    }


def _expand_query(query: str) -> str:
    """Simple expansion: add 'information about' prefix if query is short."""
    words = query.split()
    if len(words) <= 3:
        return f"information about {query}"
    return query


def _extract_key_phrases(query: str) -> str:
    """Strip stop words to extract core noun phrases."""
    stop_words = {
        "what", "is", "the", "a", "an", "how", "does", "do", "why",
        "when", "where", "who", "which", "are", "was", "were", "be",
        "been", "being", "have", "has", "had", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "to", "of",
        "in", "on", "at", "for", "with", "by", "from", "about",
    }
    words = [w for w in query.split() if w.lower() not in stop_words]
    return " ".join(words) if words else query
