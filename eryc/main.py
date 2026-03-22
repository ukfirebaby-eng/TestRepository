"""
FastAPI application entry point for ERYC Document Intelligence Console.

Phase A-1: Application skeleton, configuration, logging and health endpoints.

Run with:
    uvicorn eryc.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from eryc import __version__
from eryc.api.routes import (
    documents,
    entities,
    feedback,
    graph,
    query,
    reports_operational,
    reports_strategic,
    reports_tactical,
    runs,
)
from eryc.config import get_settings
from eryc.database.connection import open_connection
from eryc.database.migrations import apply_migrations
from eryc.models.api import ErrorDetail, HealthResponse

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application lifespan handler.

    Runs schema migrations on startup and stops the ingest worker on shutdown.
    """
    settings = get_settings()
    settings.ensure_dirs()

    # Apply database migrations.
    conn = open_connection(settings.db_path)
    apply_migrations(conn)
    conn.close()

    # Apply checkpoint database migrations (minimal schema).
    ckpt_conn = open_connection(settings.checkpoint_db_path)
    ckpt_conn.close()

    logger.info("ERYC Document Intelligence Console v%s starting", __version__)

    yield

    # Stop the ingest worker gracefully.
    from eryc.api.routes.documents import _worker

    if _worker is not None:
        _worker.stop(wait=False)
    logger.info("ERYC shutdown complete")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="ERYC Document Intelligence Console",
        description=(
            "A local-first, evidence-grounded document intelligence platform "
            "for small teams."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(query.router)
    app.include_router(documents.router)
    app.include_router(runs.router)
    app.include_router(feedback.router)
    app.include_router(entities.router)
    app.include_router(graph.router)
    app.include_router(reports_strategic.router)
    app.include_router(reports_tactical.router)
    app.include_router(reports_operational.router)

    # Health endpoint (unauthenticated)
    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Service health check."""
        db_ok = False
        vec_ok = False
        try:
            conn = open_connection(settings.db_path)
            conn.execute("SELECT 1")
            db_ok = True
            try:
                conn.execute("SELECT vec_version()")
                vec_ok = True
            except sqlite3.OperationalError:
                pass
            conn.close()
        except Exception:
            pass

        return HealthResponse(
            status="ok" if db_ok else "degraded",
            version=__version__,
            db_ok=db_ok,
            vector_search_available=vec_ok,
        )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content=ErrorDetail(
                code="internal_error",
                message="An unexpected error occurred",
            ).model_dump(),
        )

    return app


app = create_app()
