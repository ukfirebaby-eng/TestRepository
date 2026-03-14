"""
Audit logging for the ERYC Document Intelligence Console.

Phase F-2: Records important operational events to the ``audit_events``
table (spec §10).  The audit trail supports governance review, access
history and continuous improvement (spec §14.2.5).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Write structured audit events to the ``audit_events`` table.

    Events are written synchronously within the caller's transaction or in
    a short independent commit.  Failures are logged but never re-raised so
    that audit errors do not disrupt the primary request path.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def log(
        self,
        event_type: str,
        *,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Persist a single audit event.

        Args:
            event_type:    Descriptive event type, e.g. ``"query.run"``,
                           ``"document.ingest"``, ``"source.opened"``.
            user_id:       The acting user (if known).
            workspace_id:  The affected workspace (if applicable).
            resource_type: Type of the affected resource (e.g. ``"run"``).
            resource_id:   Identifier of the affected resource.
            details:       Arbitrary extra data serialised as JSON.
        """
        try:
            event_id = "evt_" + uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute(
                """
                INSERT INTO audit_events(
                    event_id, event_type, user_id, workspace_id,
                    resource_type, resource_id, details_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event_type,
                    user_id,
                    workspace_id,
                    resource_type,
                    resource_id,
                    json.dumps(details or {}),
                    now,
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("Audit log write failed: %s", exc)


# ---------------------------------------------------------------------------
# Convenience event types
# ---------------------------------------------------------------------------

QUERY_RUN = "query.run"
QUERY_STREAM = "query.stream"
SOURCE_OPENED = "source.opened"
DOCUMENT_INGEST_QUEUED = "document.ingest.queued"
DOCUMENT_INGEST_COMPLETED = "document.ingest.completed"
DOCUMENT_INGEST_FAILED = "document.ingest.failed"
FEEDBACK_SUBMITTED = "feedback.submitted"
INDEX_REBUILT = "index.rebuilt"
EXPORT_CREATED = "export.created"
ACCESS_DENIED = "access.denied"
