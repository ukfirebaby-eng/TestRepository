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
