"""
Query endpoints for ERYC Document Intelligence Console.

Phase E-1: Synchronous and streaming query paths (spec §7.2).

POST /v1/query        — synchronous evidence-grounded query
POST /v1/query/stream — streaming query (SSE)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from eryc.api.auth import AuthenticatedUser, require_workspace_access, resolve_user
from eryc.config import get_settings
from eryc.database.connection import open_connection
from eryc.governance.audit import AuditLogger
from eryc.models.api import QueryRequest, QueryResponse
from eryc.models.domain import Citation, GroundingReport, RunDiagnostics, RunStatus
from eryc.workflow.graph import run_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/query", tags=["query"])


def _get_conn() -> sqlite3.Connection:
    return open_connection(get_settings().db_path)


@router.post("", response_model=QueryResponse)
def query(
    request: QueryRequest,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> QueryResponse:
    """
    Run a synchronous evidence-grounded query and return the grounded answer,
    citations and diagnostics (spec §7.2 — POST /v1/query).
    """
    workspace_id = request.filters.workspace_id
    require_workspace_access(workspace_id, user)

    run_id = "run_" + uuid.uuid4().hex
    thread_id = request.thread_id or ("thread_" + uuid.uuid4().hex)

    audit = AuditLogger(conn)
    audit.log(
        "query.run",
        user_id=user.user_id,
        workspace_id=workspace_id,
        resource_type="run",
        resource_id=run_id,
        details={"query": request.query[:200]},
    )

    # Ensure the thread exists.
    _ensure_thread(conn, thread_id=thread_id, workspace_id=workspace_id, user_id=user.user_id)

    # Persist initial run record.
    _create_run(conn, run_id=run_id, thread_id=thread_id, user_id=user.user_id, request=request)

    # Execute workflow.
    try:
        final_state = run_query(
            thread_id=thread_id,
            run_id=run_id,
            user_id=user.user_id,
            query=request.query,
            filters=request.filters.model_dump(),
            response_options=request.response_options.model_dump(),
        )
    except Exception as exc:
        logger.exception("Workflow error for run %s: %s", run_id, exc)
        _mark_run_failed(conn, run_id=run_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query workflow failed: {exc}",
        )

    # Persist final state.
    _persist_run_result(conn, run_id=run_id, state=final_state)

    return _build_response(run_id=run_id, thread_id=thread_id, state=final_state)


@router.post("/stream")
def query_stream(
    request: QueryRequest,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> StreamingResponse:
    """
    Run a streaming query over Server-Sent Events (spec §7.2).

    Emits ``data:`` lines containing JSON progress updates followed by the
    final answer.
    """
    workspace_id = request.filters.workspace_id
    require_workspace_access(workspace_id, user)

    run_id = "run_" + uuid.uuid4().hex
    thread_id = request.thread_id or ("thread_" + uuid.uuid4().hex)

    _ensure_thread(conn, thread_id=thread_id, workspace_id=workspace_id, user_id=user.user_id)
    _create_run(conn, run_id=run_id, thread_id=thread_id, user_id=user.user_id, request=request)

    def generate():
        yield _sse("status", {"run_id": run_id, "status": "running"})
        try:
            state = run_query(
                thread_id=thread_id,
                run_id=run_id,
                user_id=user.user_id,
                query=request.query,
                filters=request.filters.model_dump(),
                response_options=request.response_options.model_dump(),
            )
            _persist_run_result(conn, run_id=run_id, state=state)
            response = _build_response(run_id=run_id, thread_id=thread_id, state=state)
            yield _sse("complete", response.model_dump())
        except Exception as exc:
            _mark_run_failed(conn, run_id=run_id, error=str(exc))
            yield _sse("error", {"run_id": run_id, "error": str(exc)})

    return StreamingResponse(generate(), media_type="text/event-stream")


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _ensure_thread(
    conn: sqlite3.Connection,
    *,
    thread_id: str,
    workspace_id: str,
    user_id: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO query_threads(thread_id, workspace_id, user_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (thread_id, workspace_id, user_id, now, now),
    )
    conn.commit()


def _create_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    thread_id: str,
    user_id: str,
    request: QueryRequest,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO runs(run_id, thread_id, user_id, query, filters_json, status, started_at)
        VALUES (?, ?, ?, ?, ?, 'running', ?)
        """,
        (
            run_id,
            thread_id,
            user_id,
            request.query,
            json.dumps(request.filters.model_dump()),
            now,
        ),
    )
    conn.commit()


def _mark_run_failed(conn: sqlite3.Connection, *, run_id: str, error: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE runs SET status='failed', error_message=?, completed_at=? WHERE run_id=?",
        (error[:1000], now, run_id),
    )
    conn.commit()


def _persist_run_result(
    conn: sqlite3.Connection, *, run_id: str, state: Dict[str, Any]
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    grounding = state.get("grounding_report")
    diagnostics = state.get("diagnostics", {})
    conn.execute(
        """
        UPDATE runs
        SET status='completed',
            answer=?,
            query_class=?,
            retrieval_mode=?,
            retrieval_rounds=?,
            grounding_json=?,
            diagnostics_json=?,
            completed_at=?
        WHERE run_id=?
        """,
        (
            state.get("final_answer"),
            state.get("query_class"),
            state.get("retrieval_mode"),
            state.get("retrieval_round", 0),
            json.dumps(grounding) if grounding else None,
            json.dumps(diagnostics),
            state.get("completed_at") or now,
            run_id,
        ),
    )

    # Persist citations.
    for cit in state.get("citations", []):
        conn.execute(
            """
            INSERT OR IGNORE INTO run_citations(
                citation_id, run_id, chunk_id, document_id, version_id,
                title, locator, source_path, snippet, ordinal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cit.get("citation_id"),
                run_id,
                cit.get("chunk_id"),
                cit.get("document_id"),
                cit.get("version_id"),
                cit.get("title"),
                cit.get("locator"),
                cit.get("source_path"),
                cit.get("snippet"),
                cit.get("ordinal", 0),
            ),
        )

    conn.commit()


def _build_response(
    *, run_id: str, thread_id: str, state: Dict[str, Any]
) -> QueryResponse:
    citations = [Citation(**c) for c in state.get("citations", [])]
    grounding_data = state.get("grounding_report")
    grounding = GroundingReport(**grounding_data) if grounding_data else None
    diag_data = state.get("diagnostics", {})
    diagnostics = RunDiagnostics(
        query_class=state.get("query_class"),
        retrieval_rounds=state.get("retrieval_round", 0),
        retrieval_mode=state.get("retrieval_mode"),
        reranker_used=diag_data.get("reranker_used", False),
        reranker_timed_out=diag_data.get("reranker_timed_out", True),
    )
    errors = state.get("errors", [])

    return QueryResponse(
        run_id=run_id,
        thread_id=thread_id,
        status=RunStatus.COMPLETED if not errors else RunStatus.FAILED,
        answer=state.get("final_answer"),
        citations=citations,
        grounding=grounding,
        diagnostics=diagnostics,
        error="; ".join(errors) if errors else None,
    )
