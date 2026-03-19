"""
Entity management endpoints for ERYC Document Intelligence Console.

POST /v1/entities             — create a new entity (e.g. a location)
GET  /v1/entities             — list entities for a workspace
GET  /v1/entities/{entity_id} — retrieve a single entity
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from eryc.api.auth import AuthenticatedUser, require_workspace_access, resolve_user
from eryc.config import get_settings
from eryc.database.connection import open_connection
from eryc.models.api import CreateEntityRequest, EntityResponse

router = APIRouter(prefix="/v1/entities", tags=["entities"])


def _get_conn() -> sqlite3.Connection:
    return open_connection(get_settings().db_path)


@router.post("", response_model=EntityResponse, status_code=status.HTTP_201_CREATED)
def create_entity(
    request: CreateEntityRequest,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> EntityResponse:
    """Create a new entity (e.g. a location) within a workspace."""
    require_workspace_access(request.workspace_id, user)

    entity_id = str(uuid.uuid4())
    canonical_name = request.canonical_name or request.name.lower()
    created_at = datetime.now(timezone.utc).isoformat()

    import json

    conn.execute(
        """
        INSERT INTO entities (entity_id, workspace_id, entity_type, name, canonical_name, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity_id,
            request.workspace_id,
            request.entity_type,
            request.name,
            canonical_name,
            json.dumps(request.metadata),
            created_at,
        ),
    )
    conn.commit()

    return EntityResponse(
        entity_id=entity_id,
        workspace_id=request.workspace_id,
        entity_type=request.entity_type,
        name=request.name,
        canonical_name=canonical_name,
        metadata=request.metadata,
        created_at=created_at,
    )


@router.get("", response_model=List[EntityResponse])
def list_entities(
    workspace_id: str = Query(...),
    entity_type: str = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> List[EntityResponse]:
    """List entities for a workspace, optionally filtered by type."""
    require_workspace_access(workspace_id, user)

    import json

    if entity_type:
        rows = conn.execute(
            "SELECT * FROM entities WHERE workspace_id=? AND entity_type=? ORDER BY created_at DESC LIMIT ?",
            (workspace_id, entity_type, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM entities WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?",
            (workspace_id, limit),
        ).fetchall()

    return [
        EntityResponse(
            entity_id=r["entity_id"],
            workspace_id=r["workspace_id"],
            entity_type=r["entity_type"],
            name=r["name"],
            canonical_name=r["canonical_name"],
            metadata=json.loads(r["metadata_json"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/{entity_id}", response_model=EntityResponse)
def get_entity(
    entity_id: str,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> EntityResponse:
    """Retrieve a single entity by ID."""
    import json

    row = conn.execute(
        "SELECT * FROM entities WHERE entity_id = ?", (entity_id,)
    ).fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

    require_workspace_access(row["workspace_id"], user)

    return EntityResponse(
        entity_id=row["entity_id"],
        workspace_id=row["workspace_id"],
        entity_type=row["entity_type"],
        name=row["name"],
        canonical_name=row["canonical_name"],
        metadata=json.loads(row["metadata_json"]),
        created_at=row["created_at"],
    )
