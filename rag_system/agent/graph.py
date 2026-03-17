"""LangGraph workflow definition for the RAG agent.

Graph topology:
    ingress
      → policy_check
      → classify_query
      → plan_retrieval
      → retrieve_candidates
      → rerank_candidates
      → judge_evidence
          ├─ [sufficient or no budget] → compose_answer
          └─ [insufficient + budget]  → rewrite_query → retrieve_candidates (loop)
      → compose_answer
      → validate_grounding
      → finalize
      → trace_and_feedback
      → END
"""

from __future__ import annotations

from functools import partial
from typing import Any

from rag_system.agent.state import RAGState
from rag_system.agent.nodes.ingress import ingress_node
from rag_system.agent.nodes.policy_check import policy_check_node
from rag_system.agent.nodes.classify_query import classify_query_node
from rag_system.agent.nodes.plan_retrieval import plan_retrieval_node
from rag_system.agent.nodes.retrieve_candidates import retrieve_candidates_node
from rag_system.agent.nodes.rerank_candidates import rerank_candidates_node
from rag_system.agent.nodes.judge_evidence import judge_evidence_node
from rag_system.agent.nodes.rewrite_query import rewrite_query_node
from rag_system.agent.nodes.compose_answer import compose_answer_node
from rag_system.agent.nodes.validate_grounding import validate_grounding_node
from rag_system.agent.nodes.finalize import finalize_node
from rag_system.agent.nodes.trace_and_feedback import trace_and_feedback_node


def _should_retry(state: RAGState) -> str:
    """Conditional edge: retry or proceed to answer generation."""
    sufficient = state.get("evidence_sufficient", False)
    steps = state.get("max_steps_remaining", 0)
    error = state.get("error")

    if error:
        return "compose_answer"
    if sufficient or steps <= 0:
        return "compose_answer"
    return "rewrite_query"


def _abort_on_error(state: RAGState) -> str:
    """Conditional edge after policy check: abort or continue."""
    error = state.get("error")
    # Policy violations don't abort but are flagged; only hard errors abort
    if error:
        return "finalize"
    return "classify_query"


def build_graph(
    retriever=None,
    reranker=None,
    embedder=None,
    llm_client=None,
    document_store=None,
    tracer=None,
    bm25_k: int = 50,
    dense_k: int = 50,
    rerank_top_n: int = 20,
    final_chunks: int = 8,
):
    """Build and compile the LangGraph RAG workflow.

    Args:
        retriever: HybridRetriever instance
        reranker: BaseReranker instance
        embedder: BaseEmbedder instance
        llm_client: Anthropic client (optional; uses extractive mode if None)
        document_store: InMemoryDocumentStore for trace persistence
        tracer: Optional observability tracer
        bm25_k: BM25 candidate count
        dense_k: Dense candidate count
        rerank_top_n: Candidates sent to reranker
        final_chunks: Final context chunks for LLM

    Returns:
        Compiled LangGraph graph ready for .invoke() / .stream()
    """
    try:
        from langgraph.graph import StateGraph, END
    except ImportError as e:
        raise ImportError("langgraph is required: pip install langgraph") from e

    # Bind dependencies into node functions
    retrieve_fn = partial(
        retrieve_candidates_node,
        retriever=retriever,
        embedder=embedder,
        bm25_k=bm25_k,
        dense_k=dense_k,
    )
    rerank_fn = partial(
        rerank_candidates_node,
        reranker=reranker,
        rerank_top_n=rerank_top_n,
        final_chunks=final_chunks,
    )
    compose_fn = partial(compose_answer_node, llm_client=llm_client)
    trace_fn = partial(
        trace_and_feedback_node,
        document_store=document_store,
        tracer=tracer,
    )

    graph = StateGraph(RAGState)

    # Register nodes
    graph.add_node("ingress", ingress_node)
    graph.add_node("policy_check", policy_check_node)
    graph.add_node("classify_query", classify_query_node)
    graph.add_node("plan_retrieval", plan_retrieval_node)
    graph.add_node("retrieve_candidates", retrieve_fn)
    graph.add_node("rerank_candidates", rerank_fn)
    graph.add_node("judge_evidence", judge_evidence_node)
    graph.add_node("rewrite_query", rewrite_query_node)
    graph.add_node("compose_answer", compose_fn)
    graph.add_node("validate_grounding", validate_grounding_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("trace_and_feedback", trace_fn)

    # Entry point
    graph.set_entry_point("ingress")

    # Linear edges
    graph.add_edge("ingress", "policy_check")
    graph.add_conditional_edges(
        "policy_check",
        _abort_on_error,
        {"classify_query": "classify_query", "finalize": "finalize"},
    )
    graph.add_edge("classify_query", "plan_retrieval")
    graph.add_edge("plan_retrieval", "retrieve_candidates")
    graph.add_edge("retrieve_candidates", "rerank_candidates")
    graph.add_edge("rerank_candidates", "judge_evidence")

    # Conditional: retry loop or proceed
    graph.add_conditional_edges(
        "judge_evidence",
        _should_retry,
        {"compose_answer": "compose_answer", "rewrite_query": "rewrite_query"},
    )

    # Retry loop: rewrite → retrieve → rerank → judge (loop)
    graph.add_edge("rewrite_query", "retrieve_candidates")

    # Answer path
    graph.add_edge("compose_answer", "validate_grounding")
    graph.add_edge("validate_grounding", "finalize")
    graph.add_edge("finalize", "trace_and_feedback")
    graph.add_edge("trace_and_feedback", END)

    return graph.compile()
