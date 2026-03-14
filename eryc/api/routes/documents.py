"""
Document ingestion endpoints for ERYC Document Intelligence Console.

Phase E-3: Ingest job view — queued, running, failed and completed states.

POST /v1/documents/ingest      — queue a document for ingestion
GET  /v1/documents/ingest/{id} — retrieve ingest job status
GET  /v1/documents/ingest      — list ingest jobs
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from eryc.api.auth import AuthenticatedUser, require_workspace_access, resolve_user
from eryc.config import get_settings
from eryc.database.connection import open_connection
from eryc.governance.audit import AuditLogger
from eryc.ingestion.worker import IngestWorker
from eryc.models.api import IngestRequest, IngestResponse
from eryc.models.domain import IngestJob, IngestJobStatus, SensitivityLevel

router = APIRouter(prefix="/v1/documents", tags=["documents"])

# Shared worker singleton (started by the app lifespan).
_worker: Optional[IngestWorker] = None


def get_worker() -> IngestWorker:
    global _worker
    if _worker is None:
        _worker = IngestWorker(get_settings())
        _worker.start()
    return _worker


def _get_conn() -> sqlite3.Connection:
    return open_connection(get_settings().db_path)


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_document(
    request: IngestRequest,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> IngestResponse:
    """
    Queue a document for ingestion from a local or network source path.
    (spec §7.2 — POST /v1/documents/ingest)
    """
    require_workspace_access(request.workspace_id, user)

    worker = get_worker()
    job_id = worker.enqueue(
        conn,
        workspace_id=request.workspace_id,
        source_path=request.source_path,
        collection_id=request.collection_id,
        doc_type=request.doc_type,
        sensitivity_level=request.sensitivity_level.value,
    )

    audit = AuditLogger(conn)
    audit.log(
        "document.ingest.queued",
        user_id=user.user_id,
        workspace_id=request.workspace_id,
        resource_type="ingest_job",
        resource_id=job_id,
        details={"source_path": request.source_path},
    )

    return IngestResponse(
        job_id=job_id,
        status="queued",
        message="Document queued for ingestion",
    )


@router.get("/ingest/{job_id}")
def get_ingest_job(
    job_id: str,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> dict:
    """Retrieve the status of a single ingest job."""
    row = conn.execute(
        "SELECT * FROM ingest_jobs WHERE job_id = ?", (job_id,)
    ).fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    require_workspace_access(row["workspace_id"], user)
    return dict(row)


@router.get("/ingest")
def list_ingest_jobs(
    workspace_id: str = Query(...),
    job_status: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> List[dict]:
    """List ingest jobs for a workspace, optionally filtered by status."""
    require_workspace_access(workspace_id, user)

    if job_status:
        rows = conn.execute(
            "SELECT * FROM ingest_jobs WHERE workspace_id=? AND status=? ORDER BY queued_at DESC LIMIT ?",
            (workspace_id, job_status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ingest_jobs WHERE workspace_id=? ORDER BY queued_at DESC LIMIT ?",
            (workspace_id, limit),
        ).fetchall()

    return [dict(r) for r in rows]
