"""FastAPI application factory for the RAG system."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rag_system.api.middleware.rate_limit import rate_limit_middleware
from rag_system.api.routes import documents, evals, graph, health, ingest, query, traces
from rag_system.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _build_components(settings: Settings):
    """Instantiate all backend components based on settings."""
    from rag_system.ingestion.embedder import get_embedder
    from rag_system.ingestion.pipeline import IngestionPipeline
    from rag_system.reranking.base import get_reranker
    from rag_system.retrieval.hybrid import HybridRetriever
    from rag_system.storage.document_store import InMemoryDocumentStore
    from rag_system.storage.index_store import InMemoryIndexStore

    retriever = HybridRetriever(rrf_k=settings.rrf_k)
    embedder = get_embedder(settings.embedder, api_key=settings.openai_api_key)
    reranker = get_reranker(
        settings.reranker,
        api_key=settings.cohere_api_key,
    )
    document_store = InMemoryDocumentStore()
    index_store = InMemoryIndexStore()

    pipeline = IngestionPipeline(
        retriever=retriever,
        document_store=document_store,
        index_store=index_store,
        embedder=embedder,
        chunk_size=settings.chunk_size_tokens,
        chunk_overlap=settings.chunk_overlap_tokens,
    )

    # Build LLM client if API key is available
    llm_client = None
    if settings.anthropic_api_key:
        try:
            import anthropic
            llm_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        except ImportError:
            logger.warning("anthropic package not installed; using extractive mode")

    from rag_system.agent.graph import build_graph
    graph = build_graph(
        retriever=retriever,
        reranker=reranker,
        embedder=embedder,
        llm_client=llm_client,
        document_store=document_store,
        bm25_k=settings.bm25_k,
        dense_k=settings.dense_k,
        rerank_top_n=settings.rerank_top_n,
        final_chunks=settings.final_context_chunks,
    )

    return {
        "retriever": retriever,
        "embedder": embedder,
        "reranker": reranker,
        "document_store": document_store,
        "index_store": index_store,
        "pipeline": pipeline,
        "graph": graph,
        "settings": settings,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and tear down backend components."""
    settings = get_settings()
    logger.info("Starting RAG system (backend=%s)", settings.backend)

    components = _build_components(settings)
    for name, component in components.items():
        setattr(app.state, name, component)

    logger.info("RAG system ready")
    yield

    logger.info("RAG system shutting down")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Agentic RAG System",
        description="Production-grade RAG with hybrid search, LangGraph orchestration, and reranking",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting
    app.middleware("http")(rate_limit_middleware)

    # Routes
    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(ingest.router)
    app.include_router(documents.router)
    app.include_router(traces.router)
    app.include_router(evals.router)
    app.include_router(graph.router)

    return app


# Default application instance (used by uvicorn)
app = create_app()
