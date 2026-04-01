import random
from collections import deque
from typing import Any, Dict, List

PROPAGATION_FACTORS: Dict[str, float] = {
    "REQUIRES": 0.95,
    "BLOCKS": 0.90,
    "PRODUCES": 0.70,
    "MODIFIES": 0.50,
    "CONTRADICTS": 0.30,
    "RELATES_TO": 0.15,
}


def compute_degree(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Compute normalised in-degree and out-degree for each node."""
    if not nodes:
        return {}
    n = len(nodes)
    divisor = max(n - 1, 1)
    in_count: Dict[str, int] = {}
    out_count: Dict[str, int] = {}
    for node in nodes:
        nid = node["id"]
        in_count[nid] = 0
        out_count[nid] = 0
    for edge in edges:
        src = edge["source_id"]
        tgt = edge["target_id"]
        if src in out_count:
            out_count[src] += 1
        if tgt in in_count:
            in_count[tgt] += 1
    result: Dict[str, Dict[str, float]] = {}
    for node in nodes:
        nid = node["id"]
        result[nid] = {
            "in_degree": in_count[nid] / divisor,
            "out_degree": out_count[nid] / divisor,
        }
    return result


def compute_betweenness(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, float]:
    """Compute betweenness centrality using Brandes' algorithm for directed graphs.

    Returns normalised values in [0, 1].
    """
    if not nodes:
        return {}
    node_ids = [n["id"] for n in nodes]
    if len(node_ids) <= 2:
        return {nid: 0.0 for nid in node_ids}

    # Build adjacency list
    adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
    for edge in edges:
        src = edge["source_id"]
        tgt = edge["target_id"]
        if src in adj:
            adj[src].append(tgt)

    cb: Dict[str, float] = {nid: 0.0 for nid in node_ids}

    for s in node_ids:
        # BFS from s
        stack: List[str] = []
        pred: Dict[str, List[str]] = {nid: [] for nid in node_ids}
        sigma: Dict[str, int] = {nid: 0 for nid in node_ids}
        sigma[s] = 1
        dist: Dict[str, int] = {nid: -1 for nid in node_ids}
        dist[s] = 0
        queue: deque = deque([s])

        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in adj.get(v, []):
                if dist[w] < 0:
                    queue.append(w)
                    dist[w] = dist[v] + 1
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)

        delta: Dict[str, float] = {nid: 0.0 for nid in node_ids}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                cb[w] += delta[w]

    # Normalise: directed graph factor is (V-1)(V-2)
    n = len(node_ids)
    norm = (n - 1) * (n - 2)
    if norm > 0:
        for nid in cb:
            cb[nid] /= norm

    return cb


def compute_linkage_intensity(node_id: str, edges: List[Dict[str, Any]], max_weighted_degree: float) -> float:
    """Normalised weighted degree for a node: sum of propagation factors for its edges."""
    if max_weighted_degree <= 0:
        return 0.0
    total = 0.0
    for edge in edges:
        if edge["source_id"] == node_id or edge["target_id"] == node_id:
            rel = edge.get("relationship", "RELATES_TO")
            total += PROPAGATION_FACTORS.get(rel, 0.15)
    return total / max_weighted_degree


def compute_resilience(in_degree_count: int) -> float:
    """Resilience: 1 / (1 + dependency_concentration).

    Higher in-degree = more things depend on this node = lower resilience if it fails.
    """
    return 1.0 / (1.0 + in_degree_count)


def compute_ripa(li: float, re: float, criticality: float) -> float:
    """RIPA Systemic Vulnerability Index: LI * Criticality * (1 - RE)."""
    return li * criticality * (1.0 - re)


def probabilistic_bfs(
    trigger_node_id: str,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    prune_threshold: float = 0.05,
) -> List[Dict[str, Any]]:
    """Run probabilistic BFS from a trigger node, tracking cascade paths.

    Each edge is activated based on its relationship's propagation factor.
    Uses the current random state (call random.seed() before for determinism).
    Returns list of cascade path dicts sorted by cumulative_probability descending.
    """
    if not nodes or not edges:
        return []

    node_ids = {n["id"] for n in nodes}
    if trigger_node_id not in node_ids:
        return []

    # Build adjacency: source -> [(target, relationship)]
    adj: Dict[str, List[tuple]] = {nid: [] for nid in node_ids}
    for edge in edges:
        src = edge["source_id"]
        tgt = edge["target_id"]
        rel = edge.get("relationship", "RELATES_TO")
        if src in adj:
            adj[src].append((tgt, rel))

    # BFS with probability tracking
    cascade_paths: List[Dict[str, Any]] = []
    # Queue entries: (current_node, path_so_far, hops_so_far, cumulative_prob)
    queue: deque = deque()
    visited = {trigger_node_id}

    for neighbour, rel in adj.get(trigger_node_id, []):
        prob = PROPAGATION_FACTORS.get(rel, 0.15)
        if random.random() < prob:
            queue.append((
                neighbour,
                [trigger_node_id, neighbour],
                [{"from": trigger_node_id, "to": neighbour, "edge_type": rel, "probability": prob}],
                prob,
            ))

    while queue:
        current, path, hops, cum_prob = queue.popleft()

        if current in visited:
            continue
        visited.add(current)

        if cum_prob >= prune_threshold:
            cascade_paths.append({
                "trigger_node": trigger_node_id,
                "affected_node": current,
                "path": list(path),
                "hops": list(hops),
                "depth": len(path) - 1,
                "cumulative_probability": round(cum_prob, 6),
            })

        for neighbour, rel in adj.get(current, []):
            if neighbour not in visited:
                prob = PROPAGATION_FACTORS.get(rel, 0.15)
                next_cum = cum_prob * prob
                if next_cum >= prune_threshold and random.random() < prob:
                    queue.append((
                        neighbour,
                        path + [neighbour],
                        hops + [{"from": current, "to": neighbour, "edge_type": rel, "probability": prob}],
                        next_cum,
                    ))

    cascade_paths.sort(key=lambda p: p["cumulative_probability"], reverse=True)
    return cascade_paths
