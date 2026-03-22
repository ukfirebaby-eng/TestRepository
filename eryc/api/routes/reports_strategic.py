"""
Strategic reporting endpoints (C-Suite / Executive persona).

GET /v1/reports/strategic/vulnerability   — systemic vulnerability & SPOF analysis
GET /v1/reports/strategic/risk-cascade    — risk cascade index per node
GET /v1/reports/strategic/gqm-alignment  — Goal-Question-Metric alignment
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple

from fastapi import APIRouter, Depends, Query

from eryc.api.auth import AuthenticatedUser, require_workspace_access, resolve_user
from eryc.config import get_settings
from eryc.database.connection import open_connection
from eryc.models.api import (
    GQMAlignmentReport,
    RiskCascadeNode,
    RiskCascadeReport,
    UnmappedNode,
    VulnerabilityNode,
    VulnerabilityReport,
)

router = APIRouter(prefix="/v1/reports/strategic", tags=["reports-strategic"])


def _get_conn() -> sqlite3.Connection:
    return open_connection(get_settings().db_path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------


def _load_graph(conn: sqlite3.Connection, workspace_id: str) -> Tuple[
    List[dict], Dict[str, List[str]], Dict[str, List[str]]
]:
    """
    Returns (nodes_list, adjacency_out, adjacency_in).
    adjacency_out[node_id] = list of target node_ids (successors)
    adjacency_in[node_id]  = list of source node_ids (predecessors)
    """
    nodes = [dict(r) for r in conn.execute(
        "SELECT * FROM graph_nodes WHERE workspace_id = ?", (workspace_id,)
    ).fetchall()]

    edges = conn.execute(
        "SELECT source_node_id, target_node_id FROM graph_edges WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchall()

    adj_out: Dict[str, List[str]] = defaultdict(list)
    adj_in: Dict[str, List[str]] = defaultdict(list)
    for e in edges:
        adj_out[e["source_node_id"]].append(e["target_node_id"])
        adj_in[e["target_node_id"]].append(e["source_node_id"])

    return nodes, adj_out, adj_in


def _downstream_bfs(start: str, adj_out: Dict[str, List[str]]) -> Tuple[int, int]:
    """Returns (cascade_size, cascade_depth) for a node failing."""
    visited: Set[str] = set()
    queue = deque([(start, 0)])
    max_depth = 0
    while queue:
        node, depth = queue.popleft()
        for neighbour in adj_out.get(node, []):
            if neighbour not in visited:
                visited.add(neighbour)
                max_depth = max(max_depth, depth + 1)
                queue.append((neighbour, depth + 1))
    return len(visited), max_depth


def _eigenvector_centrality(
    node_ids: List[str],
    adj_in: Dict[str, List[str]],
    iterations: int = 50,
) -> Dict[str, float]:
    """Power-iteration approximation of eigenvector centrality."""
    scores: Dict[str, float] = {n: 1.0 for n in node_ids}
    for _ in range(iterations):
        new_scores: Dict[str, float] = {}
        for n in node_ids:
            new_scores[n] = sum(scores.get(p, 0.0) for p in adj_in.get(n, []))
        norm = max(new_scores.values()) if new_scores and max(new_scores.values()) > 0 else 1.0
        scores = {n: v / norm for n, v in new_scores.items()}
    return scores


def _risk_level(cascade_size: int, centrality: float) -> str:
    score = cascade_size * 0.6 + centrality * 100 * 0.4
    if score >= 20:
        return "critical"
    if score >= 10:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Vulnerability & SPOF analysis
# ---------------------------------------------------------------------------


@router.get("/vulnerability", response_model=VulnerabilityReport)
def vulnerability_report(
    workspace_id: str = Query(...),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> VulnerabilityReport:
    """
    Systemic Vulnerability & Single-Point-of-Failure analysis.

    Uses eigenvector centrality and downstream cascade metrics to surface
    the highest-risk hub nodes in the knowledge graph.
    """
    require_workspace_access(workspace_id, user)

    nodes, adj_out, adj_in = _load_graph(conn, workspace_id)
    node_ids = [n["node_id"] for n in nodes]
    node_map = {n["node_id"]: n for n in nodes}

    edge_count = conn.execute(
        "SELECT COUNT(*) FROM graph_edges WHERE workspace_id = ?", (workspace_id,)
    ).fetchone()[0]

    centrality = _eigenvector_centrality(node_ids, adj_in)

    result: List[VulnerabilityNode] = []
    for n in nodes:
        nid = n["node_id"]
        in_deg = len(adj_in.get(nid, []))
        cascade_size, cascade_depth = _downstream_bfs(nid, adj_out)
        c_score = centrality.get(nid, 0.0)
        result.append(
            VulnerabilityNode(
                node_id=nid,
                name=n["name"],
                node_type=n["node_type"],
                phase=n["phase"],
                in_degree=in_deg,
                centrality_score=round(c_score, 4),
                cascade_size=cascade_size,
                cascade_depth=cascade_depth,
                risk_level=_risk_level(cascade_size, c_score),
            )
        )

    result.sort(key=lambda x: (x.cascade_size, x.centrality_score), reverse=True)

    return VulnerabilityReport(
        workspace_id=workspace_id,
        generated_at=_now(),
        total_nodes=len(nodes),
        total_edges=edge_count,
        nodes=result,
    )


# ---------------------------------------------------------------------------
# Risk Cascade Index
# ---------------------------------------------------------------------------


@router.get("/risk-cascade", response_model=RiskCascadeReport)
def risk_cascade_report(
    workspace_id: str = Query(...),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> RiskCascadeReport:
    """
    Risk Cascade Index — for each node, quantifies the total blast radius
    (cascade_size) and propagation depth (cascade_depth) if that node fails.

    The Systemic Vulnerability Index is a composite:
        SVI = (cascade_size / total_nodes) * 0.7 + (cascade_depth / max_depth) * 0.3
    """
    require_workspace_access(workspace_id, user)

    nodes, adj_out, _ = _load_graph(conn, workspace_id)
    total_nodes = len(nodes)
    if total_nodes == 0:
        return RiskCascadeReport(workspace_id=workspace_id, generated_at=_now(), nodes=[])

    results: List[RiskCascadeNode] = []
    all_depths: List[int] = []

    for n in nodes:
        cascade_size, cascade_depth = _downstream_bfs(n["node_id"], adj_out)
        all_depths.append(cascade_depth)
        results.append(
            RiskCascadeNode(
                node_id=n["node_id"],
                name=n["name"],
                node_type=n["node_type"],
                phase=n["phase"],
                cascade_size=cascade_size,
                cascade_depth=cascade_depth,
                systemic_vulnerability_index=0.0,  # filled below
            )
        )

    max_depth = max(all_depths) if all_depths else 1

    for r in results:
        size_ratio = r.cascade_size / total_nodes if total_nodes > 0 else 0.0
        depth_ratio = r.cascade_depth / max_depth if max_depth > 0 else 0.0
        r.systemic_vulnerability_index = round(size_ratio * 0.7 + depth_ratio * 0.3, 4)

    results.sort(key=lambda x: x.systemic_vulnerability_index, reverse=True)

    return RiskCascadeReport(workspace_id=workspace_id, generated_at=_now(), nodes=results)


# ---------------------------------------------------------------------------
# GQM Alignment
# ---------------------------------------------------------------------------


def _has_path_to_goal(
    start: str,
    adj_out: Dict[str, List[str]],
    goal_ids: Set[str],
) -> bool:
    """BFS to check whether a node can reach any goal node via contributes_to edges."""
    visited: Set[str] = set()
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node in goal_ids:
            return True
        for neighbour in adj_out.get(node, []):
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append(neighbour)
    return False


@router.get("/gqm-alignment", response_model=GQMAlignmentReport)
def gqm_alignment_report(
    workspace_id: str = Query(...),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> GQMAlignmentReport:
    """
    Goal-Question-Metric (GQM) alignment report.

    Traces the graph upward from operational nodes (tasks/resources) through
    'contributes_to' edges to detect whether they ultimately connect to a
    strategic goal node. Unmapped nodes represent potential wasted capital.
    """
    require_workspace_access(workspace_id, user)

    nodes, _, _ = _load_graph(conn, workspace_id)

    # Build contributes_to adjacency only
    contributes_edges = conn.execute(
        """
        SELECT source_node_id, target_node_id
        FROM graph_edges
        WHERE workspace_id = ? AND edge_type = 'contributes_to'
        """,
        (workspace_id,),
    ).fetchall()

    adj_contributes: Dict[str, List[str]] = defaultdict(list)
    for e in contributes_edges:
        adj_contributes[e["source_node_id"]].append(e["target_node_id"])

    goal_ids: Set[str] = {n["node_id"] for n in nodes if n["node_type"] == "goal"}
    operational_nodes = [n for n in nodes if n["node_type"] in ("task", "resource")]

    unmapped: List[UnmappedNode] = []
    mapped_count = 0

    for n in operational_nodes:
        if _has_path_to_goal(n["node_id"], adj_contributes, goal_ids):
            mapped_count += 1
        else:
            reason = (
                "No 'contributes_to' edges defined"
                if not adj_contributes.get(n["node_id"])
                else "Contributes_to path does not reach any goal node"
            )
            unmapped.append(
                UnmappedNode(
                    node_id=n["node_id"],
                    name=n["name"],
                    node_type=n["node_type"],
                    phase=n["phase"],
                    reason=reason,
                )
            )

    total = len(operational_nodes)
    alignment_ratio = round(mapped_count / total, 4) if total > 0 else 1.0

    return GQMAlignmentReport(
        workspace_id=workspace_id,
        generated_at=_now(),
        total_operational_nodes=total,
        mapped_count=mapped_count,
        unmapped_count=len(unmapped),
        alignment_ratio=alignment_ratio,
        unmapped_nodes=unmapped,
    )
