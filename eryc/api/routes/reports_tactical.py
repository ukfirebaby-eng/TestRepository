"""
Tactical reporting endpoints (Middle Management / Project Leader persona).

GET /v1/reports/tactical/schedule-collapse — negative slack & schedule collision forecast
GET /v1/reports/tactical/bottleneck-triage — dynamic bottleneck prioritisation
GET /v1/reports/tactical/itdo             — ITDO automated trigger dashboard
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from eryc.api.auth import AuthenticatedUser, require_workspace_access, resolve_user
from eryc.config import get_settings
from eryc.database.connection import open_connection
from eryc.models.api import (
    BottleneckNode,
    BottleneckTriageReport,
    ITDOPhase,
    ITDOReport,
    ScheduleCollisionEntry,
    ScheduleCollapseReport,
)

router = APIRouter(prefix="/v1/reports/tactical", tags=["reports-tactical"])

_ITDO_DEFAULT_THRESHOLD = 5


def _get_conn() -> sqlite3.Connection:
    return open_connection(get_settings().db_path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Schedule Collapse Forecasting (Negative Slack)
# ---------------------------------------------------------------------------


@router.get("/schedule-collapse", response_model=ScheduleCollapseReport)
def schedule_collapse_report(
    workspace_id: str = Query(...),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> ScheduleCollapseReport:
    """
    Negative Slack / Schedule Collapse Forecast.

    For every depends_on edge (predecessor → successor), checks whether the
    predecessor's planned_end is later than the successor's planned_start.
    Each such overlap is a "chronological friction" instance indicating an
    impossible deadline that requires rescheduling or resource reallocation.
    """
    require_workspace_access(workspace_id, user)

    edges = conn.execute(
        """
        SELECT e.source_node_id, e.target_node_id,
               src.name AS src_name, src.phase AS src_phase,
               tgt.name AS tgt_name, tgt.phase AS tgt_phase,
               tm_src.planned_end  AS pred_end,
               tm_tgt.planned_start AS succ_start
        FROM graph_edges e
        JOIN graph_nodes src ON src.node_id = e.source_node_id
        JOIN graph_nodes tgt ON tgt.node_id = e.target_node_id
        LEFT JOIN temporal_metadata tm_src ON tm_src.node_id = e.source_node_id
        LEFT JOIN temporal_metadata tm_tgt ON tm_tgt.node_id = e.target_node_id
        WHERE e.workspace_id = ? AND e.edge_type = 'depends_on'
        """,
        (workspace_id,),
    ).fetchall()

    collisions: List[ScheduleCollisionEntry] = []
    for row in edges:
        pred_end = _parse_dt(row["pred_end"])
        succ_start = _parse_dt(row["succ_start"])
        if pred_end is None or succ_start is None:
            continue
        if pred_end > succ_start:
            overlap = (pred_end - succ_start).total_seconds() / 86400.0
            collisions.append(
                ScheduleCollisionEntry(
                    successor_node_id=row["target_node_id"],
                    successor_name=row["tgt_name"],
                    predecessor_node_id=row["source_node_id"],
                    predecessor_name=row["src_name"],
                    predecessor_planned_end=row["pred_end"],
                    successor_planned_start=row["succ_start"],
                    overlap_days=round(overlap, 2),
                    phase=row["tgt_phase"] or row["src_phase"],
                )
            )

    collisions.sort(key=lambda x: x.overlap_days, reverse=True)

    return ScheduleCollapseReport(
        workspace_id=workspace_id,
        generated_at=_now(),
        total_collisions=len(collisions),
        collisions=collisions,
    )


# ---------------------------------------------------------------------------
# Dynamic Bottleneck Triage
# ---------------------------------------------------------------------------


@router.get("/bottleneck-triage", response_model=BottleneckTriageReport)
def bottleneck_triage_report(
    workspace_id: str = Query(...),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> BottleneckTriageReport:
    """
    Dynamic Bottleneck Triage.

    Aggregates structural (red) and temporal (yellow) friction items by node,
    then computes a priority score and triage rank.  Critical items are
    weighted 4×, high 3×, medium 2×, low 1×.

    Priority score = structural_count * 1.5 + temporal_count + critical_weight
    """
    require_workspace_access(workspace_id, user)

    friction_rows = conn.execute(
        """
        SELECT fi.source_node_id AS node_id, fi.friction_type, fi.severity
        FROM friction_items fi
        WHERE fi.workspace_id = ? AND fi.resolved = 0 AND fi.source_node_id IS NOT NULL
        UNION ALL
        SELECT fi.target_node_id AS node_id, fi.friction_type, fi.severity
        FROM friction_items fi
        WHERE fi.workspace_id = ? AND fi.resolved = 0 AND fi.target_node_id IS NOT NULL
        """,
        (workspace_id, workspace_id),
    ).fetchall()

    severity_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1}

    node_stats: Dict[str, Dict] = defaultdict(
        lambda: {"structural": 0, "temporal": 0, "critical": 0, "priority": 0.0}
    )

    for r in friction_rows:
        nid = r["node_id"]
        ft = r["friction_type"]
        sev = r["severity"]
        node_stats[nid][ft] = node_stats[nid].get(ft, 0) + 1
        if sev == "critical":
            node_stats[nid]["critical"] += 1
        w = severity_weight.get(sev, 1)
        node_stats[nid]["priority"] += (1.5 if ft == "structural" else 1.0) * w

    node_ids = list(node_stats.keys())
    if not node_ids:
        return BottleneckTriageReport(
            workspace_id=workspace_id, generated_at=_now(), bottlenecks=[]
        )

    placeholders = ",".join("?" * len(node_ids))
    node_rows = {
        r["node_id"]: r
        for r in conn.execute(
            f"SELECT node_id, name, phase FROM graph_nodes WHERE node_id IN ({placeholders})",
            node_ids,
        ).fetchall()
    }

    bottlenecks: List[BottleneckNode] = []
    for nid, stats in node_stats.items():
        nr = node_rows.get(nid)
        bottlenecks.append(
            BottleneckNode(
                node_id=nid,
                name=nr["name"] if nr else nid,
                phase=nr["phase"] if nr else None,
                structural_friction_count=stats.get("structural", 0),
                temporal_friction_count=stats.get("temporal", 0),
                total_friction=stats.get("structural", 0) + stats.get("temporal", 0),
                critical_count=stats.get("critical", 0),
                priority_score=round(stats["priority"], 2),
                triage_rank=0,  # filled below
            )
        )

    bottlenecks.sort(key=lambda x: x.priority_score, reverse=True)
    for rank, b in enumerate(bottlenecks, start=1):
        b.triage_rank = rank

    return BottleneckTriageReport(
        workspace_id=workspace_id, generated_at=_now(), bottlenecks=bottlenecks
    )


# ---------------------------------------------------------------------------
# ITDO Dashboard
# ---------------------------------------------------------------------------


@router.get("/itdo", response_model=ITDOReport)
def itdo_report(
    workspace_id: str = Query(...),
    threshold: int = Query(default=_ITDO_DEFAULT_THRESHOLD, ge=1, le=50),
    user: AuthenticatedUser = Depends(resolve_user),
    conn: sqlite3.Connection = Depends(_get_conn),
) -> ITDOReport:
    """
    ITDO (If Trigger, Diagnose and Optimise) Dashboard.

    Groups unresolved friction items by the phase of their associated node.
    If a phase has more than `threshold` critical paradoxes (structural,
    critical severity) the trigger fires, generating an automated
    recommended action.
    """
    require_workspace_access(workspace_id, user)

    rows = conn.execute(
        """
        SELECT
            COALESCE(n_src.phase, n_tgt.phase, 'unassigned') AS phase,
            fi.friction_type,
            fi.severity
        FROM friction_items fi
        LEFT JOIN graph_nodes n_src ON n_src.node_id = fi.source_node_id
        LEFT JOIN graph_nodes n_tgt ON n_tgt.node_id = fi.target_node_id
        WHERE fi.workspace_id = ? AND fi.resolved = 0
        """,
        (workspace_id,),
    ).fetchall()

    phase_data: Dict[str, Dict] = defaultdict(
        lambda: {"critical_paradoxes": 0, "total": 0}
    )
    for r in rows:
        phase = r["phase"] or "unassigned"
        phase_data[phase]["total"] += 1
        if r["friction_type"] == "structural" and r["severity"] == "critical":
            phase_data[phase]["critical_paradoxes"] += 1

    phases: List[ITDOPhase] = []
    for phase, data in sorted(phase_data.items()):
        trigger = data["critical_paradoxes"] >= threshold
        if trigger:
            action = (
                f"DIAGNOSTIC REVIEW REQUIRED: Phase '{phase}' has "
                f"{data['critical_paradoxes']} critical structural paradoxes "
                f"(threshold: {threshold}). Halt further work in this phase, "
                "convene a cross-functional review, and resolve all critical "
                "friction items before proceeding."
            )
        else:
            action = (
                f"Monitor: {data['critical_paradoxes']} critical paradox(es) "
                f"in phase '{phase}' — below trigger threshold of {threshold}."
            )
        phases.append(
            ITDOPhase(
                phase=phase,
                critical_paradox_count=data["critical_paradoxes"],
                total_friction_count=data["total"],
                trigger_fired=trigger,
                recommended_action=action,
            )
        )

    phases.sort(key=lambda x: x.critical_paradox_count, reverse=True)

    return ITDOReport(
        workspace_id=workspace_id,
        generated_at=_now(),
        itdo_threshold=threshold,
        phases=phases,
    )
