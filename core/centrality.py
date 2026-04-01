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
