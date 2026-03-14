"""
LangGraph workflow graph for the ERYC evidence-grounded query workflow.

Implements the bounded evidence-grounded query workflow described in spec §6
and illustrated in Figure 2.

Workflow stages (spec §6.1):
  ingress_check → classify_query → plan_retrieval →
  hybrid_retrieval → evidence_judge →
    (enough)        → answer_compose → grounding_validate → END
    (needs_more)    → hybrid_retrieval  (loop, max 3 rounds)
    (insufficient)  → grounding_validate → END
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from langgraph.graph import END, StateGraph

from eryc.config import Settings, get_settings
from eryc.workflow.nodes import (
    answer_compose,
    classify_query,
    evidence_judge,
    grounding_validate,
    hybrid_retrieval,
    ingress_check,
    plan_retrieval,
)
from eryc.workflow.state import EDICState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------


def _route_after_evidence_judge(
    state: EDICState,
) -> Literal["answer_compose", "hybrid_retrieval", "grounding_validate"]:
    """
    Route based on the evidence judge's verdict and loop-control limits.

    spec §6.3: maximum retrieval rounds = 3.
    """
    verdict = state.get("evidence_verdict", "enough")
    round_number = state.get("retrieval_round", 0)
    settings = get_settings()

    if verdict == "enough":
        return "answer_compose"
    elif verdict == "needs_more" and round_number < settings.max_retrieval_rounds:
        return "hybrid_retrieval"
    else:
        # insufficient or rounds exhausted
        return "grounding_validate"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_graph(
    checkpointer=None,
) -> StateGraph:
    """
    Construct and compile the ERYC query workflow graph.

    Args:
        checkpointer:  A LangGraph checkpointer instance for thread persistence.
                       When None the graph runs statelessly.

    Returns:
        A compiled LangGraph application ready for ``invoke`` or ``astream``.
    """
    graph = StateGraph(EDICState)

    # --- Register nodes ---
    graph.add_node("ingress_check", ingress_check)
    graph.add_node("classify_query", classify_query)
    graph.add_node("plan_retrieval", plan_retrieval)
    graph.add_node("hybrid_retrieval", hybrid_retrieval)
    graph.add_node("evidence_judge", evidence_judge)
    graph.add_node("answer_compose", answer_compose)
    graph.add_node("grounding_validate", grounding_validate)

    # --- Entry point ---
    graph.set_entry_point("ingress_check")

    # --- Linear edges ---
    graph.add_edge("ingress_check", "classify_query")
    graph.add_edge("classify_query", "plan_retrieval")
    graph.add_edge("plan_retrieval", "hybrid_retrieval")
    graph.add_edge("hybrid_retrieval", "evidence_judge")
    graph.add_edge("answer_compose", "grounding_validate")
    graph.add_edge("grounding_validate", END)

    # --- Conditional edge after evidence judgement ---
    graph.add_conditional_edges(
        "evidence_judge",
        _route_after_evidence_judge,
        {
            "answer_compose": "answer_compose",
            "hybrid_retrieval": "hybrid_retrieval",
            "grounding_validate": "grounding_validate",
        },
    )

    return graph.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Checkpoint factory
# ---------------------------------------------------------------------------


def make_checkpointer(checkpoint_db_path: Path) -> Any:
    """
    Create a SQLite-backed LangGraph checkpointer.

    Falls back to an in-memory checkpointer if the SQLite checkpointer
    is not available in the installed langgraph version.
    """
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        conn = sqlite3.connect(str(checkpoint_db_path), check_same_thread=False)
        return SqliteSaver(conn)
    except ImportError:
        logger.warning(
            "langgraph.checkpoint.sqlite not available; "
            "using in-memory checkpointing"
        )
        try:
            from langgraph.checkpoint.memory import MemorySaver

            return MemorySaver()
        except ImportError:
            return None


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------


def run_query(
    *,
    thread_id: str,
    run_id: str,
    user_id: str,
    query: str,
    filters: Dict[str, Any],
    response_options: Optional[Dict[str, Any]] = None,
    settings: Optional[Settings] = None,
) -> EDICState:
    """
    Execute a complete query through the ERYC workflow and return the final state.

    This is the primary entry point used by the API query handler.
    """
    from eryc.workflow.state import initial_state

    cfg = settings or get_settings()
    checkpointer = make_checkpointer(cfg.checkpoint_db_path)
    app = build_graph(checkpointer=checkpointer)

    initial = initial_state(
        thread_id=thread_id,
        run_id=run_id,
        user_id=user_id,
        query=query,
        filters=filters,
        response_options=response_options,
    )

    config = {"configurable": {"thread_id": thread_id}}
    result: EDICState = app.invoke(initial, config=config)
    return result
