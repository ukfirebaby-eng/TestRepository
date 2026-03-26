"""
core/simulator.py — Blast radius and System Vulnerability Index (SVI) simulation.

No LLM calls. Pure Python BFS + arithmetic over the live SQLite graph.
"""

from collections import deque
from typing import Any, Dict, List


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
            src = row["source_id"] if hasattr(row, "__getitem__") else row[0]
            tgt = row["target_id"] if hasattr(row, "__getitem__") else row[1]
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

            # Node name lookup
            cur2 = self.vault.conn.cursor()
            cur2.execute("SELECT name FROM nodes WHERE id = ?", (hub,))
            name_row = cur2.fetchone()
            if name_row:
                try:
                    node_name = name_row["name"]
                except (KeyError, TypeError):
                    node_name = name_row[0]
            else:
                node_name = hub

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
        svi_sum = sum(r["svi_contribution"] for r in hub_results)
        n_hubs = len(hub_results)
        if n_hubs > 1:
            svi_total = min(svi_sum / n_hubs, 1.0)
        else:
            svi_total = min(svi_sum, 1.0)

        hub_results.sort(key=lambda x: x["svi_contribution"], reverse=True)

        return {"svi": svi_total, "nodes": hub_results}
