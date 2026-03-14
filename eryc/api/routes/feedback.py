"""
Feedback capture endpoint for ERYC Document Intelligence Console.

Phase E-4: Capture ratings and reason codes linked to completed runs.

POST /v1/feedback  — submit feedback for a run
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from eryc.api.auth import AuthenticatedUser, resolve_user
from eryc.config import get_settings
from eryc.database.connection import open_connection
from eryc.governance.audit import AuditLogger
from eryc.models.api import FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/v1/feedback", tags=["feedback"])


def _get_conn() -> sqlite3.Connection:
    return open_connection(get_settings().db_path)


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    request: FeedbackRequest,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> FeedbackResponse:
    """
    Capture user feedback for a completed run.
    (spec §7.2 — POST /v1/feedback)
    """
    # Verify the run exists and belongs to this user.
    run_row = conn.execute(
        "SELECT user_id FROM runs WHERE run_id = ?", (request.run_id,)
    ).fetchone()

    if run_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    feedback_id = "fbk_" + uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """
        INSERT INTO feedback_events(
            feedback_id, run_id, user_id, rating, reason_code, comment, submitted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            feedback_id,
            request.run_id,
            user.user_id,
            request.rating,
            request.reason_code,
            request.comment,
            now,
        ),
    )
    conn.commit()

    audit = AuditLogger(conn)
    audit.log(
        "feedback.submitted",
        user_id=user.user_id,
        resource_type="run",
        resource_id=request.run_id,
        details={"rating": request.rating, "reason_code": request.reason_code},
    )

    return FeedbackResponse(
        feedback_id=feedback_id,
        message="Feedback recorded",
    )
