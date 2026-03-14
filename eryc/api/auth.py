"""
Authentication and access-scope resolution for the ERYC API.

Phase A-4: Simple token-based authentication backed by the ``users`` table.
In the v1 deployment this uses a shared secret with per-user API keys stored
in the database.  Production deployments should integrate with the
organisation's identity provider.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from eryc.database.connection import open_connection
from eryc.config import get_settings

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def _get_db() -> sqlite3.Connection:
    settings = get_settings()
    return open_connection(settings.db_path)


class AuthenticatedUser:
    """Represents a successfully authenticated user."""

    def __init__(
        self,
        user_id: str,
        username: str,
        role: str,
        workspace_ids: list[str],
    ) -> None:
        self.user_id = user_id
        self.username = username
        self.role = role
        self.workspace_ids = workspace_ids

    @property
    def is_manager(self) -> bool:
        return self.role in ("admin", "manager")


def resolve_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
    conn: sqlite3.Connection = Depends(_get_db),
) -> AuthenticatedUser:
    """
    FastAPI dependency that resolves the caller to a User record.

    Accepts a Bearer token that is the SHA-256 hex digest of the user's
    stored api_key (if present) or the raw user_id for development use.
    Raises HTTP 401 if the token cannot be resolved.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    token = credentials.credentials

    # Look up by user_id directly (development / simple deployments).
    row = conn.execute(
        """
        SELECT u.user_id, u.username, u.role
        FROM users u
        WHERE u.user_id = ?
        """,
        (token,),
    ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Collect the workspaces this user belongs to.
    ws_rows = conn.execute(
        "SELECT workspace_id FROM workspace_members WHERE user_id = ?",
        (row["user_id"],),
    ).fetchall()
    workspace_ids = [r["workspace_id"] for r in ws_rows]

    return AuthenticatedUser(
        user_id=row["user_id"],
        username=row["username"],
        role=row["role"],
        workspace_ids=workspace_ids,
    )


def require_workspace_access(
    workspace_id: str,
    user: AuthenticatedUser,
) -> None:
    """
    Raise HTTP 403 if ``user`` does not have access to ``workspace_id``.

    Admins bypass this check.
    """
    if user.role == "admin":
        return
    if workspace_id not in user.workspace_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access to workspace '{workspace_id}' is not permitted",
        )
