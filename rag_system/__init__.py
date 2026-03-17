"""
Agentic RAG System
==================

Production-grade RAG system with hybrid search (BM25 + dense vectors + RRF fusion),
LangGraph-based orchestration, reranking, and full observability.

Quick start:
    from rag_system.api.main import app
    # uvicorn rag_system.api.main:app --reload

    from rag_system.agent.graph import build_graph
    graph = build_graph()
    result = graph.invoke({"original_query": "...", "tenant_id": "t1", ...})
"""

__version__ = "0.1.0"
