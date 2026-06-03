"""
core/simulator.py — Blast radius and System Vulnerability Index (SVI) simulation,
plus Black Swan scenario generation via LLM.
"""

import datetime
import json
import random
import re
from collections import deque
from typing import Any, Dict, List

import numpy as np

from core.agents import _get_client, _get_model
from core.centrality import (
    PROPAGATION_FACTORS,
    compute_degree,
    compute_betweenness,
    compute_ripa,
    compute_linkage_intensity,
    compute_resilience,
    probabilistic_bfs,
)


class BlastRadiusCalculator:
    """Computes the SVI and per-hub blast radius for a given document's REQUIRES graph."""

    def __init__(self, document_id: str, vault):
        self.document_id = document_id
        self.vault = vault

    def run(self) -> Dict[str, Any]:
        cursor = self.vault.conn.cursor()

        # ── Load graph topology ─────────────────────────────────────
        cursor.execute(
            "SELECT source_id, target_id, relationship FROM edges WHERE document_id = ?",
            (self.document_id,),
        )
        edge_rows = cursor.fetchall()
        if not edge_rows:
            return {
                "svi": 0.0,
                "nodes": [],
                "cascade_paths": [],
                "centrality_scores": {},
                "ripa_summary": {"total_systemic_risk": 0.0, "top_vulnerabilities": []},
            }

        edges = []
        for row in edge_rows:
            relationship = row["relationship"] if "relationship" in row.keys() else ""
            edges.append({
                "source_id": row["source_id"],
                "target_id": row["target_id"],
                "relationship": relationship,
            })

        # Collect unique node IDs and batch-fetch names
        all_node_ids = set()
        for e in edges:
            all_node_ids.add(e["source_id"])
            all_node_ids.add(e["target_id"])

        placeholders = ",".join("?" for _ in all_node_ids)
        cursor.execute(
            f"SELECT id, name FROM nodes WHERE id IN ({placeholders})",
            list(all_node_ids),
        )
        name_map = {row["id"]: row["name"] for row in cursor.fetchall()}
        nodes = [{"id": nid, "name": name_map.get(nid, nid)} for nid in all_node_ids]

        # ── Centrality metrics ──────────────────────────────────────
        degree_scores = compute_degree(nodes, edges)
        betweenness_scores = compute_betweenness(nodes, edges)
        centrality_scores = {}
        for nid in all_node_ids:
            deg = degree_scores.get(nid, {"in_degree": 0.0, "out_degree": 0.0})
            centrality_scores[nid] = {
                "in_degree": round(deg["in_degree"], 4),
                "out_degree": round(deg["out_degree"], 4),
                "betweenness": round(betweenness_scores.get(nid, 0.0), 4),
            }

        # ── RIPA scoring ────────────────────────────────────────────
        max_weighted_degree = sum(
            PROPAGATION_FACTORS.get(e["relationship"], 0.15) for e in edges
        )
        ripa_scores = {}
        for nid in all_node_ids:
            deg = degree_scores.get(nid, {"in_degree": 0.0, "out_degree": 0.0})
            n_nodes = len(nodes)
            in_count = int(round(deg["in_degree"] * max(n_nodes - 1, 1)))
            li = compute_linkage_intensity(nid, edges, max_weighted_degree)
            re = compute_resilience(in_count)
            crit = betweenness_scores.get(nid, 0.0)
            svi = compute_ripa(li, re, crit)
            ripa_scores[nid] = {"li": round(li, 4), "re": round(re, 4), "criticality": round(crit, 4), "svi": round(svi, 4)}

        # ── Probabilistic BFS cascade paths ─────────────────────────
        random.seed(self.document_id)
        all_cascade_paths = []
        for nid in all_node_ids:
            paths = probabilistic_bfs(nid, nodes, edges)
            all_cascade_paths.extend(paths)
        all_cascade_paths.sort(key=lambda p: p["cumulative_probability"], reverse=True)
        all_cascade_paths = all_cascade_paths[:100]

        # ── Assemble result ─────────────────────────────────────────
        enriched_nodes = []
        for nid in all_node_ids:
            deg = centrality_scores.get(nid, {})
            ripa = ripa_scores.get(nid, {})
            node_cascade = [p for p in all_cascade_paths if p["trigger_node"] == nid]
            enriched_nodes.append({
                "id": nid,
                "name": name_map.get(nid, nid),
                "svi_contribution": ripa.get("svi", 0.0),
                "dependency_count": int(round(deg.get("in_degree", 0.0) * max(len(nodes) - 1, 1))),
                "cascade_depth": max((p["depth"] for p in node_cascade), default=0),
                "blast_radius_count": len(node_cascade),
                "in_degree": deg.get("in_degree", 0.0),
                "out_degree": deg.get("out_degree", 0.0),
                "betweenness": deg.get("betweenness", 0.0),
                "ripa": ripa,
            })

        enriched_nodes.sort(key=lambda n: n["ripa"].get("svi", 0.0), reverse=True)

        top_svi = max((n["ripa"]["svi"] for n in enriched_nodes), default=0.0)

        top_vulns = [
            {
                "node_id": n["id"],
                "name": n["name"],
                "li": n["ripa"]["li"],
                "re": n["ripa"]["re"],
                "criticality": n["ripa"]["criticality"],
                "svi": n["ripa"]["svi"],
            }
            for n in enriched_nodes[:10]
        ]

        return {
            "svi": round(top_svi, 4),
            "nodes": enriched_nodes,
            "cascade_paths": all_cascade_paths,
            "centrality_scores": centrality_scores,
            "ripa_summary": {
                "total_systemic_risk": round(top_svi, 4),
                "top_vulnerabilities": top_vulns,
            },
        }


class BlackSwanAgent:
    """
    Generates Black Swan risk scenarios grounded in the document's hub nodes.
    Uses the smart LLM tier at temperature 0.7 for creative-but-grounded output.
    """

    REQUIRED_KEYS = {"title", "trigger_node", "cascade_path", "impact_radius", "mitigation"}

    def __init__(self, document_id: str, vault):
        self.document_id = document_id
        self.vault = vault

    def run(self) -> Dict[str, Any]:
        # ── 1. Fetch hub vulnerabilities ────────────────────────────────────
        hub_vulns = self.vault.get_hub_vulnerabilities(self.document_id, limit=10)

        # ── 2. Fetch fragility lines ─────────────────────────────────────────
        fragility = self.vault.get_fragility_lines(self.document_id)

        # ── 3. Early exit if nothing to work with ────────────────────────────
        if not hub_vulns and not fragility:
            return {"scenarios": []}

        # ── 4. Build grounding context from hub node names ───────────────────
        hub_lines = []
        for hub in hub_vulns:
            name = hub.get("name", hub.get("id", "Unknown"))
            dep_count = hub.get("dependency_count", 0)
            hub_lines.append(f'- "{name}" (in-degree: {dep_count})')

        grounding_context = (
            "Hub nodes (nodes other project elements depend on):\n"
            + "\n".join(hub_lines)
        )

        # ── 5. Call LLM ───────────────────────────────────────────────────────
        system_prompt = (
            "You are a strategic risk analyst. Generate exactly 3 Black Swan scenarios "
            "for the project. Each scenario must reference only the specific node names "
            "provided in the context. Return valid JSON only."
        )

        user_prompt = (
            f"{grounding_context}\n\n"
            "Generate 3 Black Swan scenarios as a JSON array. Each scenario object must "
            "have these exact keys: 'title' (string), 'trigger_node' (string — must be "
            "one of the hub node names above), 'cascade_path' (array of strings — node "
            "names from the list above), 'impact_radius' (string, e.g. '7 of 12 nodes "
            "affected'), 'mitigation' (string). Return only the JSON array, no other text."
        )

        try:
            client = _get_client()
            response = client.chat.completions.create(
                model=_get_model("smart"),
                temperature=0.7,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
        except Exception:
            return {"scenarios": []}

        # ── 6. Parse and validate response ────────────────────────────────────
        try:
            stripped = re.sub(
                r"^```[^\n]*\n?|```$", "", content, flags=re.MULTILINE
            ).strip()
            parsed = json.loads(stripped)

            if not isinstance(parsed, list):
                return {"scenarios": []}

            validated = []
            for item in parsed:
                if not isinstance(item, dict):
                    return {"scenarios": []}
                if not self.REQUIRED_KEYS.issubset(item.keys()):
                    return {"scenarios": []}
                validated.append({
                    "title": item["title"],
                    "trigger_node": item["trigger_node"],
                    "cascade_path": item["cascade_path"],
                    "impact_radius": item["impact_radius"],
                    "mitigation": item["mitigation"],
                })
        except Exception:
            return {"scenarios": []}

        # ── 7. Return ─────────────────────────────────────────────────────────
        return {"scenarios": validated}


class MonteCarloForecaster:
    """
    Runs Monte Carlo schedule-delay simulations over a document's temporal data.
    Pure numpy + Python — no LLM calls.
    """

    def __init__(self, document_id: str, vault, n_trials: int = 5000):
        self.document_id = document_id
        self.vault = vault
        self.n_trials = n_trials

    def run(self) -> Dict[str, Any]:
        # ── 1. Early exit — check temporal data ─────────────────────────────
        if not self.vault.has_temporal_data(self.document_id):
            return {"available": False, "reason": "No schedule data found in this document"}

        # ── 2. Load schedule data ────────────────────────────────────────────
        cursor = self.vault.conn.cursor()
        cursor.execute(
            """
            SELECT tm.node_id, tm.start_date, tm.end_date
            FROM temporal_metadata tm
            WHERE tm.node_id IN (
                SELECT source_id FROM edges WHERE document_id = ?
                UNION
                SELECT target_id FROM edges WHERE document_id = ?
            )
            """,
            (self.document_id, self.document_id),
        )
        temporal_rows = cursor.fetchall()

        # Parse durations
        duration_days: Dict[str, int] = {}
        for row in temporal_rows:
            try:
                node_id = row[0]
                start_raw = row[1]
                end_raw = row[2]
            except (IndexError, KeyError):
                try:
                    node_id = row["node_id"]
                    start_raw = row["start_date"]
                    end_raw = row["end_date"]
                except (KeyError, TypeError):
                    continue

            if not start_raw or not end_raw:
                continue

            try:
                # Support both date and datetime ISO strings
                try:
                    start_dt = datetime.date.fromisoformat(str(start_raw)[:10])
                    end_dt = datetime.date.fromisoformat(str(end_raw)[:10])
                except ValueError:
                    start_dt = datetime.datetime.fromisoformat(str(start_raw)).date()
                    end_dt = datetime.datetime.fromisoformat(str(end_raw)).date()

                days = (end_dt - start_dt).days
                duration_days[node_id] = max(1, days)
            except Exception:
                continue

        # Load STARTS_AFTER edges
        cursor2 = self.vault.conn.cursor()
        cursor2.execute(
            "SELECT source_id, target_id FROM edges "
            "WHERE document_id = ? AND relationship = 'STARTS_AFTER'",
            (self.document_id,),
        )
        starts_after_rows = cursor2.fetchall()

        # Build dependency graph: target starts after source
        # predecessors[node] = list of nodes that must complete before node starts
        predecessors: Dict[str, List[str]] = {}
        for row in starts_after_rows:
            try:
                src = row[0]
                tgt = row[1]
            except (IndexError, KeyError):
                try:
                    src = row["source_id"]
                    tgt = row["target_id"]
                except (KeyError, TypeError):
                    continue
            predecessors.setdefault(tgt, []).append(src)

        # Load chronological friction lines
        friction_lines = self.vault.get_chronological_friction_lines(self.document_id)

        # Build per-node friction delay map
        friction_delay: Dict[str, int] = {}
        for fl in friction_lines:
            days_at_risk = int(fl.get("days_at_risk", 0))
            if days_at_risk <= 0:
                continue
            for key in ("source_id", "target_id", "node_id"):
                node_ref = fl.get(key)
                if node_ref:
                    friction_delay[node_ref] = friction_delay.get(node_ref, 0) + days_at_risk

        # ── 3. Monte Carlo simulation ────────────────────────────────────────
        all_nodes = list(duration_days.keys())
        if not all_nodes:
            return {"available": False, "reason": "No schedule data found in this document"}

        n = len(all_nodes)
        node_index = {node_id: i for i, node_id in enumerate(all_nodes)}

        # Pre-compute base durations array
        base_durations = np.array([duration_days[nid] for nid in all_nodes], dtype=float)

        # Topological BFS order for delay propagation
        # Build in-degree for nodes that have predecessors among known nodes
        topo_in_degree: Dict[str, int] = {nid: 0 for nid in all_nodes}
        adj: Dict[str, List[str]] = {nid: [] for nid in all_nodes}
        for tgt, preds in predecessors.items():
            if tgt not in node_index:
                continue
            for src in preds:
                if src not in node_index:
                    continue
                topo_in_degree[tgt] = topo_in_degree.get(tgt, 0) + 1
                adj[src].append(tgt)

        # Kahn's algorithm for topological order
        topo_queue: deque = deque(
            nid for nid in all_nodes if topo_in_degree.get(nid, 0) == 0
        )
        topo_order: List[str] = []
        in_deg_copy = dict(topo_in_degree)
        while topo_queue:
            node = topo_queue.popleft()
            topo_order.append(node)
            for child in adj.get(node, []):
                in_deg_copy[child] -= 1
                if in_deg_copy[child] == 0:
                    topo_queue.append(child)
        # Any remaining nodes (cycles) appended at end
        remaining = [nid for nid in all_nodes if nid not in set(topo_order)]
        topo_order.extend(remaining)

        # Per-node accumulated delay across all trials (for at-risk calculation)
        node_delay_sum = np.zeros(n, dtype=float)

        trial_max_delays = np.zeros(self.n_trials, dtype=float)

        for t in range(self.n_trials):
            # Sample variance for each node
            variances = np.random.normal(0, 0.2 * base_durations)
            trial_durations = np.maximum(1.0, base_durations + variances)

            # Delay propagation through dependency graph
            delay = np.zeros(n, dtype=float)

            for nid in topo_order:
                if nid not in node_index:
                    continue
                idx = node_index[nid]
                # Add excess duration variance as delay contribution
                excess = trial_durations[idx] - base_durations[idx]
                if excess > 0:
                    delay[idx] += excess

                # Add friction delay
                if nid in friction_delay:
                    delay[idx] += friction_delay[nid]

                # Propagate to successors
                for child in adj.get(nid, []):
                    if child not in node_index:
                        continue
                    cidx = node_index[child]
                    delay[cidx] = max(delay[cidx], delay[idx])

            trial_max_delays[t] = delay.max() if delay.max() > 0 else 0.0
            node_delay_sum += delay

        # ── 4. Percentiles ───────────────────────────────────────────────────
        p50 = int(np.percentile(trial_max_delays, 50))
        p80 = int(np.percentile(trial_max_delays, 80))
        p95 = int(np.percentile(trial_max_delays, 95))

        # ── 5. At-risk nodes ─────────────────────────────────────────────────
        mean_delays = node_delay_sum / self.n_trials
        sorted_indices = np.argsort(mean_delays)[::-1][:10]
        top_node_ids = [all_nodes[i] for i in sorted_indices if mean_delays[i] > 0]

        at_risk_nodes = []
        if top_node_ids:
            placeholders = ",".join("?" * len(top_node_ids))
            cursor3 = self.vault.conn.cursor()
            cursor3.execute(
                f"SELECT id, name FROM nodes WHERE id IN ({placeholders})",
                top_node_ids,
            )
            name_rows = cursor3.fetchall()
            name_map = {}
            for row in name_rows:
                try:
                    name_map[row[0]] = row[1]
                except (IndexError, KeyError):
                    try:
                        name_map[row["id"]] = row["name"]
                    except (KeyError, TypeError):
                        pass

            for nid in top_node_ids:
                idx = node_index[nid]
                displayed_mean_delay = int(mean_delays[idx])
                if displayed_mean_delay <= 0:
                    continue
                at_risk_nodes.append({
                    "id": nid,
                    "name": name_map.get(nid, nid),
                    "mean_delay_days": displayed_mean_delay,
                })

        # ── 6. Return ─────────────────────────────────────────────────────────
        return {
            "available": True,
            "p50_delay_days": p50,
            "p80_delay_days": p80,
            "p95_delay_days": p95,
            "at_risk_nodes": at_risk_nodes,
        }
