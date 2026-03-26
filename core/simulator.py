"""
core/simulator.py — Blast radius and System Vulnerability Index (SVI) simulation,
plus Black Swan scenario generation via LLM.
"""

import json
import re
from collections import deque
from typing import Any, Dict, List

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
