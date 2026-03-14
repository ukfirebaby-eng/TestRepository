"""
Run history endpoints for ERYC Document Intelligence Console.

Phase E-2: Stored runs, diagnostics and citation browser.

GET /v1/runs/{run_id}  — retrieve a completed run
GET /v1/runs           — list runs for the authenticated user
"""

from __future__ import annotations

import json
import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from eryc.api.auth import AuthenticatedUser, resolve_user
from eryc.config import get_settings
from eryc.database.connection import open_connection
from eryc.models.api import RunResponse
from eryc.models.domain import Citation, GroundingReport, RunDiagnostics, RunStatus

router = APIRouter(prefix="/v1/runs", tags=["runs"])


def _get_conn() -> sqlite3.Connection:
    return open_connection(get_settings().db_path)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    run_id: str,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> RunResponse:
    """
    Return the stored run record, answer, citations and diagnostics.
    (spec §7.2 — GET /v1/runs/{run_id})
    """
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    # Only the owning user or a manager can read a run.
    if row["user_id"] != user.user_id and not user.is_manager:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    citations = _load_citations(conn, run_id)
    grounding_data = json.loads(row["grounding_json"] or "null")
    grounding = GroundingReport(**grounding_data) if grounding_data else None
    diag_data = json.loads(row["diagnostics_json"] or "{}")
    diagnostics = RunDiagnostics(
        query_class=row["query_class"],
        retrieval_rounds=row["retrieval_rounds"],
        retrieval_mode=row["retrieval_mode"],
    )

    return RunResponse(
        run_id=run_id,
        thread_id=row["thread_id"],
        user_id=row["user_id"],
        query=row["query"],
        status=RunStatus(row["status"]),
        answer=row["answer"],
        citations=citations,
        grounding=grounding,
        diagnostics=diagnostics,
        error_message=row["error_message"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


@router.get("", response_model=List[RunResponse])
def list_runs(
    workspace_id: Optional[str] = Query(default=None),
    thread_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> List[RunResponse]:
    """List recent runs for the authenticated user."""
    params: list = [user.user_id, limit]
    where_extra = ""

    if thread_id:
        where_extra += " AND r.thread_id = ?"
        params.insert(1, thread_id)
    if workspace_id:
        where_extra += " AND t.workspace_id = ?"
        params.insert(-1, workspace_id)

    sql = f"""
        SELECT r.*
        FROM runs r
        JOIN query_threads t ON t.thread_id = r.thread_id
        WHERE r.user_id = ?
          {where_extra}
        ORDER BY r.started_at DESC
        LIMIT ?
    """

    rows = conn.execute(sql, params).fetchall()
    results = []
    for row in rows:
        citations = _load_citations(conn, row["run_id"])
        grounding_data = json.loads(row["grounding_json"] or "null")
        grounding = GroundingReport(**grounding_data) if grounding_data else None
        results.append(
            RunResponse(
                run_id=row["run_id"],
                thread_id=row["thread_id"],
                user_id=row["user_id"],
                query=row["query"],
                status=RunStatus(row["status"]),
                answer=row["answer"],
                citations=citations,
                grounding=grounding,
                diagnostics=RunDiagnostics(
                    query_class=row["query_class"],
                    retrieval_rounds=row["retrieval_rounds"],
                    retrieval_mode=row["retrieval_mode"],
                ),
                error_message=row["error_message"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
            )
        )
    return results


def _load_citations(conn: sqlite3.Connection, run_id: str) -> List[Citation]:
    rows = conn.execute(
        "SELECT * FROM run_citations WHERE run_id=? ORDER BY ordinal",
        (run_id,),
    ).fetchall()
    return [
        Citation(
            citation_id=r["citation_id"],
            run_id=r["run_id"],
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            version_id=r["version_id"],
            title=r["title"],
            locator=r["locator"],
            source_path=r["source_path"],
            snippet=r["snippet"],
            ordinal=r["ordinal"],
        )
        for r in rows
    ]
