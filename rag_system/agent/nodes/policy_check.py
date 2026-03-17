"""Policy check node: enforce content policy before any retrieval."""

from __future__ import annotations

from rag_system.agent.state import RAGState

# Simple blocklist for demonstration. In production, use a classifier.
_BLOCKED_PATTERNS = [
    "ignore previous instructions",
    "disregard system prompt",
    "act as",
]


def policy_check_node(state: RAGState) -> RAGState:
    """Check query against content policy. Sets policy_flags on violations."""
    query = (state.get("original_query") or "").lower()
    flags: list[str] = list(state.get("policy_flags") or [])

    for pattern in _BLOCKED_PATTERNS:
        if pattern in query:
            flags.append(f"prompt_injection_attempt:{pattern}")

    return {**state, "policy_flags": flags}
