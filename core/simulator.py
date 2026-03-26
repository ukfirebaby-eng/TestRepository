"""
core/simulator.py — Blast radius and System Vulnerability Index (SVI) simulation,
plus Black Swan scenario generation via LLM.
"""

import datetime
import json
import re
from collections import deque
from typing import Any, Dict, List

import numpy as np

from core.agents import _get_client, _get_model


class BlastRadiusCalculator:
    """Computes the SVI and per-hub blast radius for a given document's REQUIRES graph."""

    def __init__(self, document_id: str, vault):
        self.document_id = document_id
        self.vault = vault

    def run(self) -> Dict[str, Any]:
        # ── 1. Load REQUIRES edges ──────────────────────────────────────────
        cursor = self.vault.conn.cursor()
        cursor.execute(
            "SELECT source_id, target_id FROM edges "
            "WHERE document_id = ? AND relationship = 'REQUIRES'",
            (self.document_id,),
        )
        edges = cursor.fetchall()

        # ── 2. Count all nodes ──────────────────────────────────────────────
        all_node_ids: set = set()
        # forward_graph[source] = [targets]  (source depends on target)
        forward_graph: Dict[str, List[str]] = {}
        # reverse_graph[target] = [sources]  (who depends on target)
        reverse_graph: Dict[str, List[str]] = {}
        # in-degree: how many nodes depend on this node (i.e. it is a target)
        in_degree: Dict[str, int] = {}

        for row in edges:
            # Try dict-style first (sqlite3.Row / mock dict), fall back to index
            try:
                src = row["source_id"]
                tgt = row["target_id"]
            except (KeyError, TypeError):
                src = row[0]
                tgt = row[1]

            all_node_ids.add(src)
            all_node_ids.add(tgt)

            forward_graph.setdefault(src, []).append(tgt)
            reverse_graph.setdefault(tgt, []).append(src)
            in_degree[tgt] = in_degree.get(tgt, 0) + 1

        total_nodes = len(all_node_ids)
        if total_nodes == 0:
            return {"svi": 0.0, "nodes": []}

        # ── 3. Find hub nodes (in-degree >= 3) ─────────────────────────────
        hub_nodes = [node for node, deg in in_degree.items() if deg >= 3]
        if not hub_nodes:
            return {"svi": 0.0, "nodes": []}

        max_in_degree = max(in_degree[n] for n in hub_nodes)

        # ── 7. Pre-computed cascade_nodes from fragility_lines ──────────────
        fragility_lines = self.vault.get_fragility_lines(self.document_id)
        precomputed_cascade: set = set()
        for fl in fragility_lines:
            cascade = fl.get("cascade_nodes", [])
            if isinstance(cascade, list):
                precomputed_cascade.update(cascade)

        # ── 4 & 5. BFS + SVI per hub node ───────────────────────────────────
        hub_results = []

        # Batch-fetch all hub node names in a single query (avoids N+1 round-trips)
        if hub_nodes:
            placeholders = ",".join("?" * len(hub_nodes))
            cursor = self.vault.conn.cursor()
            cursor.execute(
                f"SELECT id, name FROM nodes WHERE id IN ({placeholders})",
                list(hub_nodes)
            )
            node_name_map = {row[0]: row[1] for row in cursor.fetchall()}
        else:
            node_name_map = {}

        for hub in hub_nodes:
            # BFS on reverse_graph from hub: who would be affected if hub fails?
            visited: set = set()
            queue: deque = deque()
            queue.append((hub, 0))
            visited.add(hub)
            max_depth = 0

            while queue:
                node, depth = queue.popleft()
                for dependent in reverse_graph.get(node, []):
                    if dependent not in visited:
                        visited.add(dependent)
                        new_depth = depth + 1
                        if new_depth > max_depth:
                            max_depth = new_depth
                        queue.append((dependent, new_depth))

            reachable = visited - {hub}
            blast_radius_count = len(reachable)
            cascade_depth = max_depth

            if max_in_degree == 0:
                svi_contribution = 0.0
            else:
                svi_contribution = (blast_radius_count / total_nodes) * (
                    in_degree[hub] / max_in_degree
                )

            # Node name lookup (resolved from pre-fetched batch map)
            node_name = node_name_map.get(hub, hub)

            # newly_detected: any reachable node NOT in pre-computed cascade set
            newly_detected = any(n not in precomputed_cascade for n in reachable)

            hub_results.append(
                {
                    "id": hub,
                    "name": node_name,
                    "cascade_depth": cascade_depth,
                    "blast_radius_count": blast_radius_count,
                    "svi_contribution": svi_contribution,
                    "newly_detected": newly_detected,
                }
            )

        # ── 6. SVI total ─────────────────────────────────────────────────────
        svi_total = min(sum(n["svi_contribution"] for n in hub_results), 1.0)

        hub_results.sort(key=lambda x: x["svi_contribution"], reverse=True)

        return {"svi": svi_total, "nodes": hub_results}


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
                at_risk_nodes.append({
                    "id": nid,
                    "name": name_map.get(nid, nid),
                    "mean_delay_days": int(mean_delays[idx]),
                })

        # ── 6. Return ─────────────────────────────────────────────────────────
        return {
            "available": True,
            "p50_delay_days": p50,
            "p80_delay_days": p80,
            "p95_delay_days": p95,
            "at_risk_nodes": at_risk_nodes,
        }
