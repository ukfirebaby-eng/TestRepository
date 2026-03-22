"""
Operational reporting endpoints (Individual Contributor / Analyst persona).

GET /v1/reports/operational/friction-queue  — prioritised friction resolution queue
GET /v1/reports/operational/trust-scores    — document ambiguity & trust scores
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, Query

from eryc.api.auth import AuthenticatedUser, require_workspace_access, resolve_user
from eryc.config import get_settings
from eryc.database.connection import open_connection
from eryc.models.api import (
    DocumentTrustScore,
    FrictionItemResponse,
    FrictionQueueReport,
    TrustScoreReport,
)
from eryc.models.domain import FrictionSeverity, FrictionType

router = APIRouter(prefix="/v1/reports/operational", tags=["reports-operational"])


def _get_conn() -> sqlite3.Connection:
    return open_connection(get_settings().db_path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Friction Resolution Queue (Kanban-style)
# ---------------------------------------------------------------------------


@router.get("/friction-queue", response_model=FrictionQueueReport)
def friction_queue_report(
    workspace_id: str = Query(...),
    friction_type: str = Query(default=None),
    severity: str = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> FrictionQueueReport:
    """
    Friction Resolution Queue.

    Returns all unresolved friction items as a prioritised, Kanban-style queue.
    Each item includes the originating chunk's text for context-rich resolution.
    Items are sorted: critical → high → medium → low, then by creation date.
    """
    require_workspace_access(workspace_id, user)

    clauses = ["fi.workspace_id = ?", "fi.resolved = 0"]
    params: list = [workspace_id]
    if friction_type:
        clauses.append("fi.friction_type = ?")
        params.append(friction_type)
    if severity:
        clauses.append("fi.severity = ?")
        params.append(severity)
    params.append(limit)

    rows = conn.execute(
        f"""
        SELECT
            fi.*,
            c.text_preview AS provenance_text
        FROM friction_items fi
        LEFT JOIN chunks c ON c.chunk_id = fi.chunk_id
        WHERE {' AND '.join(clauses)}
        ORDER BY
            CASE fi.severity
                WHEN 'critical' THEN 0
                WHEN 'high'     THEN 1
                WHEN 'medium'   THEN 2
                ELSE                 3
            END,
            fi.created_at ASC
        LIMIT ?
        """,
        params,
    ).fetchall()

    items = [
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
            resolved=False,
            resolved_at=None,
            created_at=r["created_at"],
        )
        for r in rows
    ]

    total = conn.execute(
        "SELECT COUNT(*) FROM friction_items WHERE workspace_id = ? AND resolved = 0",
        (workspace_id,),
    ).fetchone()[0]

    return FrictionQueueReport(
        workspace_id=workspace_id,
        generated_at=_now(),
        total_unresolved=total,
        items=items,
    )


# ---------------------------------------------------------------------------
# Document Trust Scores
# ---------------------------------------------------------------------------


def _risk_band(trust_score: float) -> str:
    if trust_score >= 0.85:
        return "low"
    if trust_score >= 0.65:
        return "medium"
    if trust_score >= 0.40:
        return "high"
    return "critical"


@router.get("/trust-scores", response_model=TrustScoreReport)
def trust_score_report(
    workspace_id: str = Query(...),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> TrustScoreReport:
    """
    Document Ambiguity & Trust Score Report.

    For each document in the workspace, computes a Trust Score in [0, 1]:

        trust_score = 1 - (friction_generating_nodes / total_nodes)

    A low score indicates high "Trust Debt" — the document contains
    contradictory or ambiguous logic that requires human rewriting before
    safe execution can begin.
    """
    require_workspace_access(workspace_id, user)

    # Total nodes per document
    node_rows = conn.execute(
        """
        SELECT document_id, COUNT(*) AS node_count
        FROM graph_nodes
        WHERE workspace_id = ? AND document_id IS NOT NULL
        GROUP BY document_id
        """,
        (workspace_id,),
    ).fetchall()

    if not node_rows:
        return TrustScoreReport(
            workspace_id=workspace_id, generated_at=_now(), documents=[]
        )

    doc_node_counts: Dict[str, int] = {r["document_id"]: r["node_count"] for r in node_rows}

    # Nodes that are referenced by at least one unresolved friction item
    friction_node_rows = conn.execute(
        """
        SELECT DISTINCT gn.document_id
        FROM friction_items fi
        JOIN graph_nodes gn ON (
            gn.node_id = fi.source_node_id OR gn.node_id = fi.target_node_id
        )
        WHERE fi.workspace_id = ? AND fi.resolved = 0 AND gn.document_id IS NOT NULL
        """,
        (workspace_id,),
    ).fetchall()

    # Count friction-generating nodes per document
    friction_node_counts_rows = conn.execute(
        """
        SELECT gn.document_id, COUNT(DISTINCT gn.node_id) AS friction_node_count
        FROM friction_items fi
        JOIN graph_nodes gn ON (
            gn.node_id = fi.source_node_id OR gn.node_id = fi.target_node_id
        )
        WHERE fi.workspace_id = ? AND fi.resolved = 0 AND gn.document_id IS NOT NULL
        GROUP BY gn.document_id
        """,
        (workspace_id,),
    ).fetchall()

    friction_counts: Dict[str, int] = {
        r["document_id"]: r["friction_node_count"] for r in friction_node_counts_rows
    }

    doc_ids = list(doc_node_counts.keys())
    placeholders = ",".join("?" * len(doc_ids))
    doc_meta = {
        r["document_id"]: r
        for r in conn.execute(
            f"SELECT document_id, canonical_title FROM documents WHERE document_id IN ({placeholders})",
            doc_ids,
        ).fetchall()
    }

    results: List[DocumentTrustScore] = []
    for doc_id, total_nodes in doc_node_counts.items():
        friction_nodes = friction_counts.get(doc_id, 0)
        trust_score = round(1.0 - (friction_nodes / total_nodes if total_nodes > 0 else 0.0), 4)
        meta = doc_meta.get(doc_id)
        results.append(
            DocumentTrustScore(
                document_id=doc_id,
                canonical_title=meta["canonical_title"] if meta else doc_id,
                total_nodes=total_nodes,
                friction_generating_nodes=friction_nodes,
                trust_score=trust_score,
                trust_debt=round(1.0 - trust_score, 4),
                risk_band=_risk_band(trust_score),
            )
        )

    results.sort(key=lambda x: x.trust_score)

    return TrustScoreReport(
        workspace_id=workspace_id, generated_at=_now(), documents=results
    )
