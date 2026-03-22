"""
Temporal Knowledge Graph management endpoints.

POST   /v1/graph/nodes                        — create a graph node
GET    /v1/graph/nodes                        — list nodes in a workspace
GET    /v1/graph/nodes/{node_id}              — get a node

POST   /v1/graph/edges                        — create a directed edge
GET    /v1/graph/edges                        — list edges in a workspace

PUT    /v1/graph/nodes/{node_id}/temporal     — set temporal metadata
GET    /v1/graph/nodes/{node_id}/temporal     — get temporal metadata

POST   /v1/graph/friction                     — record a friction item
GET    /v1/graph/friction                     — list friction items
PATCH  /v1/graph/friction/{friction_id}/resolve — mark resolved
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from eryc.api.auth import AuthenticatedUser, require_workspace_access, resolve_user
from eryc.config import get_settings
from eryc.database.connection import open_connection
from eryc.models.api import (
    CreateEdgeRequest,
    CreateFrictionRequest,
    CreateNodeRequest,
    EdgeResponse,
    FrictionItemResponse,
    NodeResponse,
    SetTemporalMetadataRequest,
    TemporalMetadataResponse,
)
from eryc.models.domain import FrictionSeverity, FrictionType

router = APIRouter(prefix="/v1/graph", tags=["graph"])


def _get_conn() -> sqlite3.Connection:
    return open_connection(get_settings().db_path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


@router.post("/nodes", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
def create_node(
    request: CreateNodeRequest,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> NodeResponse:
    """Create a graph node (task, goal, phase, or resource)."""
    require_workspace_access(request.workspace_id, user)

    node_id = str(uuid.uuid4())
    created_at = _now()

    conn.execute(
        """
        INSERT INTO graph_nodes
            (node_id, workspace_id, node_type, name, description, phase,
             document_id, chunk_id, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            node_id,
            request.workspace_id,
            request.node_type.value,
            request.name,
            request.description,
            request.phase,
            request.document_id,
            request.chunk_id,
            json.dumps(request.metadata),
            created_at,
        ),
    )
    conn.commit()

    return NodeResponse(
        node_id=node_id,
        workspace_id=request.workspace_id,
        node_type=request.node_type,
        name=request.name,
        description=request.description,
        phase=request.phase,
        document_id=request.document_id,
        chunk_id=request.chunk_id,
        metadata=request.metadata,
        created_at=created_at,
    )


@router.get("/nodes", response_model=List[NodeResponse])
def list_nodes(
    workspace_id: str = Query(...),
    node_type: Optional[str] = Query(default=None),
    phase: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> List[NodeResponse]:
    """List graph nodes, optionally filtered by type or phase."""
    require_workspace_access(workspace_id, user)

    clauses = ["workspace_id = ?"]
    params: list = [workspace_id]
    if node_type:
        clauses.append("node_type = ?")
        params.append(node_type)
    if phase:
        clauses.append("phase = ?")
        params.append(phase)
    params.append(limit)

    rows = conn.execute(
        f"SELECT * FROM graph_nodes WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?",
        params,
    ).fetchall()

    return [
        NodeResponse(
            node_id=r["node_id"],
            workspace_id=r["workspace_id"],
            node_type=r["node_type"],
            name=r["name"],
            description=r["description"],
            phase=r["phase"],
            document_id=r["document_id"],
            chunk_id=r["chunk_id"],
            metadata=json.loads(r["metadata_json"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/nodes/{node_id}", response_model=NodeResponse)
def get_node(
    node_id: str,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> NodeResponse:
    row = conn.execute("SELECT * FROM graph_nodes WHERE node_id = ?", (node_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    require_workspace_access(row["workspace_id"], user)
    return NodeResponse(
        node_id=row["node_id"],
        workspace_id=row["workspace_id"],
        node_type=row["node_type"],
        name=row["name"],
        description=row["description"],
        phase=row["phase"],
        document_id=row["document_id"],
        chunk_id=row["chunk_id"],
        metadata=json.loads(row["metadata_json"]),
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


@router.post("/edges", response_model=EdgeResponse, status_code=status.HTTP_201_CREATED)
def create_edge(
    request: CreateEdgeRequest,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> EdgeResponse:
    """Create a directed edge between two nodes."""
    require_workspace_access(request.workspace_id, user)

    for nid in (request.source_node_id, request.target_node_id):
        row = conn.execute("SELECT node_id FROM graph_nodes WHERE node_id = ?", (nid,)).fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node {nid} not found",
            )

    edge_id = str(uuid.uuid4())
    created_at = _now()

    conn.execute(
        """
        INSERT INTO graph_edges
            (edge_id, workspace_id, source_node_id, target_node_id,
             edge_type, weight, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            edge_id,
            request.workspace_id,
            request.source_node_id,
            request.target_node_id,
            request.edge_type.value,
            request.weight,
            json.dumps(request.metadata),
            created_at,
        ),
    )
    conn.commit()

    return EdgeResponse(
        edge_id=edge_id,
        workspace_id=request.workspace_id,
        source_node_id=request.source_node_id,
        target_node_id=request.target_node_id,
        edge_type=request.edge_type,
        weight=request.weight,
        metadata=request.metadata,
        created_at=created_at,
    )


@router.get("/edges", response_model=List[EdgeResponse])
def list_edges(
    workspace_id: str = Query(...),
    edge_type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> List[EdgeResponse]:
    require_workspace_access(workspace_id, user)

    if edge_type:
        rows = conn.execute(
            "SELECT * FROM graph_edges WHERE workspace_id=? AND edge_type=? LIMIT ?",
            (workspace_id, edge_type, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM graph_edges WHERE workspace_id=? LIMIT ?",
            (workspace_id, limit),
        ).fetchall()

    return [
        EdgeResponse(
            edge_id=r["edge_id"],
            workspace_id=r["workspace_id"],
            source_node_id=r["source_node_id"],
            target_node_id=r["target_node_id"],
            edge_type=r["edge_type"],
            weight=r["weight"],
            metadata=json.loads(r["metadata_json"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Temporal metadata
# ---------------------------------------------------------------------------


@router.put("/nodes/{node_id}/temporal", response_model=TemporalMetadataResponse)
def set_temporal_metadata(
    node_id: str,
    request: SetTemporalMetadataRequest,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> TemporalMetadataResponse:
    """Set or update scheduling metadata for a node."""
    row = conn.execute("SELECT workspace_id FROM graph_nodes WHERE node_id = ?", (node_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    require_workspace_access(row["workspace_id"], user)

    updated_at = _now()
    conn.execute(
        """
        INSERT INTO temporal_metadata
            (node_id, planned_start, planned_end, actual_start, actual_end,
             duration_days, slack_days, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(node_id) DO UPDATE SET
            planned_start  = excluded.planned_start,
            planned_end    = excluded.planned_end,
            actual_start   = excluded.actual_start,
            actual_end     = excluded.actual_end,
            duration_days  = excluded.duration_days,
            slack_days     = excluded.slack_days,
            updated_at     = excluded.updated_at
        """,
        (
            node_id,
            request.planned_start,
            request.planned_end,
            request.actual_start,
            request.actual_end,
            request.duration_days,
            request.slack_days,
            updated_at,
        ),
    )
    conn.commit()

    return TemporalMetadataResponse(
        node_id=node_id,
        planned_start=request.planned_start,
        planned_end=request.planned_end,
        actual_start=request.actual_start,
        actual_end=request.actual_end,
        duration_days=request.duration_days,
        slack_days=request.slack_days,
        updated_at=updated_at,
    )


@router.get("/nodes/{node_id}/temporal", response_model=TemporalMetadataResponse)
def get_temporal_metadata(
    node_id: str,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> TemporalMetadataResponse:
    node = conn.execute("SELECT workspace_id FROM graph_nodes WHERE node_id = ?", (node_id,)).fetchone()
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    require_workspace_access(node["workspace_id"], user)

    row = conn.execute("SELECT * FROM temporal_metadata WHERE node_id = ?", (node_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No temporal metadata for this node")

    return TemporalMetadataResponse(
        node_id=row["node_id"],
        planned_start=row["planned_start"],
        planned_end=row["planned_end"],
        actual_start=row["actual_start"],
        actual_end=row["actual_end"],
        duration_days=row["duration_days"],
        slack_days=row["slack_days"],
        updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# Friction items
# ---------------------------------------------------------------------------


@router.post("/friction", response_model=FrictionItemResponse, status_code=status.HTTP_201_CREATED)
def create_friction_item(
    request: CreateFrictionRequest,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> FrictionItemResponse:
    """Record a structural (red) or temporal (yellow) friction item."""
    require_workspace_access(request.workspace_id, user)

    friction_id = str(uuid.uuid4())
    created_at = _now()

    conn.execute(
        """
        INSERT INTO friction_items
            (friction_id, workspace_id, friction_type, severity,
             source_node_id, target_node_id, description, chunk_id,
             resolved, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (
            friction_id,
            request.workspace_id,
            request.friction_type.value,
            request.severity.value,
            request.source_node_id,
            request.target_node_id,
            request.description,
            request.chunk_id,
            created_at,
        ),
    )
    conn.commit()

    return FrictionItemResponse(
        friction_id=friction_id,
        workspace_id=request.workspace_id,
        friction_type=request.friction_type,
        severity=request.severity,
        source_node_id=request.source_node_id,
        target_node_id=request.target_node_id,
        description=request.description,
        chunk_id=request.chunk_id,
        provenance_text=None,
        resolved=False,
        resolved_at=None,
        created_at=created_at,
    )


@router.get("/friction", response_model=List[FrictionItemResponse])
def list_friction_items(
    workspace_id: str = Query(...),
    friction_type: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    resolved: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> List[FrictionItemResponse]:
    require_workspace_access(workspace_id, user)

    clauses = ["fi.workspace_id = ?"]
    params: list = [workspace_id]
    if friction_type:
        clauses.append("fi.friction_type = ?")
        params.append(friction_type)
    if severity:
        clauses.append("fi.severity = ?")
        params.append(severity)
    if resolved is not None:
        clauses.append("fi.resolved = ?")
        params.append(1 if resolved else 0)
    params.append(limit)

    rows = conn.execute(
        f"""
        SELECT fi.*, c.text_preview AS provenance_text
        FROM friction_items fi
        LEFT JOIN chunks c ON c.chunk_id = fi.chunk_id
        WHERE {' AND '.join(clauses)}
        ORDER BY
            CASE fi.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                             WHEN 'medium' THEN 2 ELSE 3 END,
            fi.created_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()

    return [
        FrictionItemResponse(
            friction_id=r["friction_id"],
            workspace_id=r["workspace_id"],
            friction_type=FrictionType(r["friction_type"]),
            severity=FrictionSeverity(r["severity"]),
            source_node_id=r["source_node_id"],
            target_node_id=r["target_node_id"],
            description=r["description"],
            chunk_id=r["chunk_id"],
            provenance_text=r["provenance_text"],
            resolved=bool(r["resolved"]),
            resolved_at=r["resolved_at"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.patch("/friction/{friction_id}/resolve", response_model=FrictionItemResponse)
def resolve_friction_item(
    friction_id: str,
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> FrictionItemResponse:
    """Mark a friction item as resolved."""
    row = conn.execute("SELECT * FROM friction_items WHERE friction_id = ?", (friction_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friction item not found")
    require_workspace_access(row["workspace_id"], user)

    resolved_at = _now()
    conn.execute(
        "UPDATE friction_items SET resolved=1, resolved_at=? WHERE friction_id=?",
        (resolved_at, friction_id),
    )
    conn.commit()

    chunk_row = conn.execute(
        "SELECT text_preview FROM chunks WHERE chunk_id = ?", (row["chunk_id"],)
    ).fetchone() if row["chunk_id"] else None

    return FrictionItemResponse(
        friction_id=row["friction_id"],
        workspace_id=row["workspace_id"],
        friction_type=FrictionType(row["friction_type"]),
        severity=FrictionSeverity(row["severity"]),
        source_node_id=row["source_node_id"],
        target_node_id=row["target_node_id"],
        description=row["description"],
        chunk_id=row["chunk_id"],
        provenance_text=chunk_row["text_preview"] if chunk_row else None,
        resolved=True,
        resolved_at=resolved_at,
        created_at=row["created_at"],
    )
