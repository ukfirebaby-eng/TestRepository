# Cascading Risk Simulation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the BlastRadiusCalculator with probabilistic BFS propagation, centrality metrics (degree + betweenness), RIPA vulnerability scoring, cascade path tracking, and rewrite the sim-page Blast Radius tab to display all new metrics.

**Architecture:** A new `core/centrality.py` module owns pure graph-metric calculations (no I/O, no LLM). The existing `BlastRadiusCalculator` in `core/simulator.py` is enhanced to use these calculations and return an enriched result shape. The frontend Blast Radius tab is rewritten to render SVI headline, centrality table, RIPA bars, and cascade paths.

**Tech Stack:** Python (stdlib only — `collections`, `random`), FastAPI, vanilla JS, CSS

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `core/centrality.py` | Create | `PROPAGATION_FACTORS`, `compute_degree()`, `compute_betweenness()`, `compute_ripa()` |
| `core/simulator.py` | Modify | Enhance `BlastRadiusCalculator` with probabilistic BFS, centrality integration, RIPA scoring, cascade path tracking |
| `static/index.html` | Modify | Rewrite Blast Radius tab HTML and `renderSimPage()` blast radius section |
| `tests/test_centrality.py` | Create | Unit tests for degree and betweenness centrality |
| `tests/test_ripa.py` | Create | Unit tests for RIPA scoring |
| `tests/test_cascade.py` | Create | Unit tests for probabilistic BFS and path tracking |
| `tests/test_blast_radius_enhanced.py` | Create | Integration tests for enhanced `.run()` |
| `tests/test_api_blast_radius.py` | Create | API endpoint tests for enhanced response shape |

---

## Task 1: Create `core/centrality.py` with propagation factors and degree centrality

**Files:**
- Create: `core/centrality.py`
- Create: `tests/test_centrality.py`

- [ ] **Step 1: Write the failing tests for degree centrality**

Create `tests/test_centrality.py`:

```python
import pytest
from core.centrality import PROPAGATION_FACTORS, compute_degree


class TestPropagationFactors:
    def test_all_edge_types_defined(self):
        expected = {"REQUIRES", "BLOCKS", "PRODUCES", "MODIFIES", "CONTRADICTS", "RELATES_TO"}
        assert set(PROPAGATION_FACTORS.keys()) == expected

    def test_requires_highest(self):
        assert PROPAGATION_FACTORS["REQUIRES"] == 0.95

    def test_relates_to_lowest(self):
        assert PROPAGATION_FACTORS["RELATES_TO"] == 0.15

    def test_all_values_between_0_and_1(self):
        for val in PROPAGATION_FACTORS.values():
            assert 0.0 < val <= 1.0


class TestComputeDegree:
    def test_simple_chain(self):
        nodes = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        edges = [
            {"source_id": "A", "target_id": "B"},
            {"source_id": "B", "target_id": "C"},
        ]
        result = compute_degree(nodes, edges)
        assert result["A"]["in_degree"] == 0.0
        assert result["A"]["out_degree"] == 0.5
        assert result["B"]["in_degree"] == 0.5
        assert result["B"]["out_degree"] == 0.5
        assert result["C"]["in_degree"] == 0.5
        assert result["C"]["out_degree"] == 0.0

    def test_empty_graph(self):
        result = compute_degree([], [])
        assert result == {}

    def test_single_node(self):
        nodes = [{"id": "A"}]
        result = compute_degree(nodes, [])
        assert result["A"]["in_degree"] == 0.0
        assert result["A"]["out_degree"] == 0.0

    def test_star_graph(self):
        nodes = [{"id": "H"}, {"id": "A"}, {"id": "B"}, {"id": "C"}, {"id": "D"}]
        edges = [
            {"source_id": "H", "target_id": "A"},
            {"source_id": "H", "target_id": "B"},
            {"source_id": "H", "target_id": "C"},
            {"source_id": "H", "target_id": "D"},
        ]
        result = compute_degree(nodes, edges)
        assert result["H"]["out_degree"] == 1.0
        assert result["H"]["in_degree"] == 0.0
        assert result["A"]["in_degree"] == 0.25
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_centrality.py -v`
Expected: `ERROR` — `ModuleNotFoundError: No module named 'core.centrality'`

- [ ] **Step 3: Create `core/centrality.py` with propagation factors and degree centrality**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_centrality.py -v`
Expected: all 8 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add core/centrality.py tests/test_centrality.py
git commit -m "feat: add core/centrality.py with propagation factors and degree centrality"
```

---

## Task 2: Add betweenness centrality to `core/centrality.py`

**Files:**
- Modify: `core/centrality.py`
- Modify: `tests/test_centrality.py`

- [ ] **Step 1: Write the failing tests for betweenness centrality**

Append to `tests/test_centrality.py`:

```python
from core.centrality import compute_betweenness


class TestComputeBetweenness:
    def test_chain_middle_highest(self):
        """A->B->C: B is on all shortest paths between A and C."""
        nodes = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        edges = [
            {"source_id": "A", "target_id": "B"},
            {"source_id": "B", "target_id": "C"},
        ]
        result = compute_betweenness(nodes, edges)
        assert result["B"] > result["A"]
        assert result["B"] > result["C"]
        assert result["A"] == 0.0
        assert result["C"] == 0.0

    def test_star_centre_highest(self):
        """H->A, H->B, H->C, H->D: H bridges all paths."""
        nodes = [{"id": "H"}, {"id": "A"}, {"id": "B"}, {"id": "C"}, {"id": "D"}]
        edges = [
            {"source_id": "H", "target_id": "A"},
            {"source_id": "H", "target_id": "B"},
            {"source_id": "H", "target_id": "C"},
            {"source_id": "H", "target_id": "D"},
        ]
        result = compute_betweenness(nodes, edges)
        assert result["H"] >= result["A"]

    def test_two_nodes(self):
        nodes = [{"id": "A"}, {"id": "B"}]
        edges = [{"source_id": "A", "target_id": "B"}]
        result = compute_betweenness(nodes, edges)
        assert result["A"] == 0.0
        assert result["B"] == 0.0

    def test_empty_graph(self):
        result = compute_betweenness([], [])
        assert result == {}

    def test_single_node(self):
        nodes = [{"id": "A"}]
        result = compute_betweenness(nodes, [])
        assert result["A"] == 0.0

    def test_diamond_graph(self):
        """A->B, A->C, B->D, C->D: B and C share betweenness equally."""
        nodes = [{"id": "A"}, {"id": "B"}, {"id": "C"}, {"id": "D"}]
        edges = [
            {"source_id": "A", "target_id": "B"},
            {"source_id": "A", "target_id": "C"},
            {"source_id": "B", "target_id": "D"},
            {"source_id": "C", "target_id": "D"},
        ]
        result = compute_betweenness(nodes, edges)
        assert abs(result["B"] - result["C"]) < 0.001
        assert result["B"] > 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_centrality.py::TestComputeBetweenness -v`
Expected: `FAILED` — `ImportError: cannot import name 'compute_betweenness'`

- [ ] **Step 3: Add `compute_betweenness()` to `core/centrality.py`**

Add these imports at the top of `core/centrality.py`:

```python
from collections import deque
```

Then append this function after `compute_degree()`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_centrality.py -v`
Expected: all 14 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add core/centrality.py tests/test_centrality.py
git commit -m "feat: add betweenness centrality (Brandes' algorithm)"
```

---

## Task 3: Add RIPA scoring to `core/centrality.py`

**Files:**
- Modify: `core/centrality.py`
- Create: `tests/test_ripa.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ripa.py`:

```python
import pytest
from core.centrality import compute_ripa, compute_resilience, compute_linkage_intensity, PROPAGATION_FACTORS


class TestComputeLinkageIntensity:
    def test_single_requires_edge(self):
        edges = [{"source_id": "A", "target_id": "B", "relationship": "REQUIRES"}]
        li = compute_linkage_intensity("A", edges, max_weighted_degree=0.95)
        assert abs(li - 1.0) < 0.001

    def test_mixed_edges(self):
        edges = [
            {"source_id": "A", "target_id": "B", "relationship": "REQUIRES"},
            {"source_id": "A", "target_id": "C", "relationship": "RELATES_TO"},
        ]
        expected = (0.95 + 0.15) / (0.95 * 2)
        li = compute_linkage_intensity("A", edges, max_weighted_degree=0.95 * 2)
        assert abs(li - expected) < 0.001

    def test_no_edges(self):
        li = compute_linkage_intensity("A", [], max_weighted_degree=1.0)
        assert li == 0.0


class TestComputeResilience:
    def test_no_dependencies(self):
        re = compute_resilience(in_degree_count=0)
        assert re == 1.0

    def test_some_dependencies(self):
        re = compute_resilience(in_degree_count=4)
        assert abs(re - 0.2) < 0.001

    def test_one_dependency(self):
        re = compute_resilience(in_degree_count=1)
        assert abs(re - 0.5) < 0.001


class TestComputeRipa:
    def test_high_risk_node(self):
        svi = compute_ripa(li=0.9, re=0.1, criticality=0.8)
        assert svi > 0.6

    def test_low_risk_node(self):
        svi = compute_ripa(li=0.1, re=0.9, criticality=0.1)
        assert svi < 0.01

    def test_zero_linkage(self):
        svi = compute_ripa(li=0.0, re=0.1, criticality=0.8)
        assert svi == 0.0

    def test_fully_resilient(self):
        svi = compute_ripa(li=0.9, re=1.0, criticality=0.8)
        assert svi == 0.0

    def test_exact_formula(self):
        svi = compute_ripa(li=0.5, re=0.25, criticality=0.4)
        expected = 0.5 * 0.4 * (1 - 0.25)
        assert abs(svi - expected) < 0.0001
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ripa.py -v`
Expected: `FAILED` — `ImportError: cannot import name 'compute_ripa'`

- [ ] **Step 3: Add RIPA functions to `core/centrality.py`**

Append to `core/centrality.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ripa.py -v`
Expected: all 11 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add core/centrality.py tests/test_ripa.py
git commit -m "feat: add RIPA scoring (linkage intensity, resilience, composite SVI)"
```

---

## Task 4: Add probabilistic BFS with cascade path tracking

**Files:**
- Modify: `core/centrality.py`
- Create: `tests/test_cascade.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cascade.py`:

```python
import pytest
import random
from core.centrality import probabilistic_bfs, PROPAGATION_FACTORS


def _chain_graph():
    """A -REQUIRES-> B -REQUIRES-> C -REQUIRES-> D"""
    nodes = [{"id": "A"}, {"id": "B"}, {"id": "C"}, {"id": "D"}]
    edges = [
        {"source_id": "A", "target_id": "B", "relationship": "REQUIRES"},
        {"source_id": "B", "target_id": "C", "relationship": "REQUIRES"},
        {"source_id": "C", "target_id": "D", "relationship": "REQUIRES"},
    ]
    return nodes, edges


def _cycle_graph():
    """A -REQUIRES-> B -REQUIRES-> C -REQUIRES-> A (cycle)"""
    nodes = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
    edges = [
        {"source_id": "A", "target_id": "B", "relationship": "REQUIRES"},
        {"source_id": "B", "target_id": "C", "relationship": "REQUIRES"},
        {"source_id": "C", "target_id": "A", "relationship": "REQUIRES"},
    ]
    return nodes, edges


class TestProbabilisticBFS:
    def test_deterministic_with_seed(self):
        nodes, edges = _chain_graph()
        random.seed(42)
        result1 = probabilistic_bfs("A", nodes, edges)
        random.seed(42)
        result2 = probabilistic_bfs("A", nodes, edges)
        assert result1 == result2

    def test_cascade_depth(self):
        nodes, edges = _chain_graph()
        random.seed(0)
        result = probabilistic_bfs("A", nodes, edges)
        for path in result:
            assert path["depth"] == len(path["path"]) - 1

    def test_cumulative_probability(self):
        nodes, edges = _chain_graph()
        random.seed(0)
        result = probabilistic_bfs("A", nodes, edges)
        for path in result:
            expected_prob = 1.0
            for hop in path["hops"]:
                expected_prob *= hop["probability"]
            assert abs(path["cumulative_probability"] - expected_prob) < 0.0001

    def test_cycle_handling(self):
        nodes, edges = _cycle_graph()
        random.seed(0)
        result = probabilistic_bfs("A", nodes, edges)
        all_affected = [p["affected_node"] for p in result]
        assert all_affected.count("A") == 0  # trigger node never appears as affected

    def test_pruning_below_threshold(self):
        """RELATES_TO (0.15) chain of 3 hops: 0.15^3 = 0.003 < 0.05 threshold."""
        nodes = [{"id": "A"}, {"id": "B"}, {"id": "C"}, {"id": "D"}]
        edges = [
            {"source_id": "A", "target_id": "B", "relationship": "RELATES_TO"},
            {"source_id": "B", "target_id": "C", "relationship": "RELATES_TO"},
            {"source_id": "C", "target_id": "D", "relationship": "RELATES_TO"},
        ]
        random.seed(1)
        result = probabilistic_bfs("A", nodes, edges, prune_threshold=0.05)
        deep_paths = [p for p in result if p["depth"] >= 3]
        assert len(deep_paths) == 0

    def test_requires_propagates(self):
        """With seed 0, REQUIRES (0.95) should propagate in most cases."""
        nodes = [{"id": "A"}, {"id": "B"}]
        edges = [{"source_id": "A", "target_id": "B", "relationship": "REQUIRES"}]
        random.seed(0)
        result = probabilistic_bfs("A", nodes, edges)
        assert len(result) == 1
        assert result[0]["affected_node"] == "B"

    def test_empty_graph(self):
        result = probabilistic_bfs("A", [], [])
        assert result == []

    def test_path_includes_trigger(self):
        nodes, edges = _chain_graph()
        random.seed(0)
        result = probabilistic_bfs("A", nodes, edges)
        for path in result:
            assert path["path"][0] == "A"
            assert path["trigger_node"] == "A"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cascade.py -v`
Expected: `FAILED` — `ImportError: cannot import name 'probabilistic_bfs'`

- [ ] **Step 3: Add `probabilistic_bfs()` to `core/centrality.py`**

Add `import random` at the top of `core/centrality.py` alongside the existing `from collections import deque`.

Then append:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cascade.py -v`
Expected: all 8 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add core/centrality.py tests/test_cascade.py
git commit -m "feat: add probabilistic BFS with cascade path tracking"
```

---

## Task 5: Enhance BlastRadiusCalculator with centrality, RIPA, and cascade paths

**Files:**
- Modify: `core/simulator.py`
- Create: `tests/test_blast_radius_enhanced.py`

- [ ] **Step 1: Write the failing integration tests**

Create `tests/test_blast_radius_enhanced.py`:

```python
import json
import random
import pytest
from unittest.mock import MagicMock
from core.simulator import BlastRadiusCalculator


def _make_mock_vault(nodes_data, edges_data, fragility_lines=None):
    """Create a mock vault with graph topology data."""
    vault = MagicMock()
    cursor = MagicMock()
    vault.conn.cursor.return_value = cursor

    # Simulate edges query: SELECT source_id, target_id, relationship FROM edges WHERE document_id = ?
    cursor.fetchall.side_effect = [
        # First call: edges query
        [(e["source_id"], e["target_id"], e.get("relationship", "REQUIRES")) for e in edges_data],
        # Second call: node names batch query
        [(n["id"], n["name"]) for n in nodes_data],
    ]

    vault.get_fragility_lines.return_value = fragility_lines or []
    return vault


class TestEnhancedBlastRadius:
    def test_run_returns_all_fields(self):
        nodes = [
            {"id": "n1", "name": "Task Alpha"},
            {"id": "n2", "name": "Task Beta"},
            {"id": "n3", "name": "Task Gamma"},
        ]
        edges = [
            {"source_id": "n1", "target_id": "n2", "relationship": "REQUIRES"},
            {"source_id": "n2", "target_id": "n3", "relationship": "REQUIRES"},
        ]
        vault = _make_mock_vault(nodes, edges)
        calc = BlastRadiusCalculator("doc1", vault)
        result = calc.run()

        assert "svi" in result
        assert "nodes" in result
        assert "cascade_paths" in result
        assert "centrality_scores" in result
        assert "ripa_summary" in result

    def test_nodes_enriched_with_centrality(self):
        nodes = [
            {"id": "n1", "name": "Alpha"},
            {"id": "n2", "name": "Beta"},
            {"id": "n3", "name": "Gamma"},
        ]
        edges = [
            {"source_id": "n1", "target_id": "n2", "relationship": "REQUIRES"},
            {"source_id": "n2", "target_id": "n3", "relationship": "REQUIRES"},
        ]
        vault = _make_mock_vault(nodes, edges)
        calc = BlastRadiusCalculator("doc1", vault)
        result = calc.run()

        for node in result["nodes"]:
            assert "in_degree" in node
            assert "out_degree" in node
            assert "betweenness" in node
            assert "ripa" in node
            assert "li" in node["ripa"]
            assert "re" in node["ripa"]
            assert "criticality" in node["ripa"]
            assert "svi" in node["ripa"]

    def test_result_json_serialisable(self):
        nodes = [{"id": "n1", "name": "Alpha"}, {"id": "n2", "name": "Beta"}]
        edges = [{"source_id": "n1", "target_id": "n2", "relationship": "REQUIRES"}]
        vault = _make_mock_vault(nodes, edges)
        calc = BlastRadiusCalculator("doc1", vault)
        result = calc.run()
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_empty_graph(self):
        vault = _make_mock_vault([], [])
        calc = BlastRadiusCalculator("doc1", vault)
        result = calc.run()
        assert result["svi"] == 0.0
        assert result["nodes"] == []
        assert result["cascade_paths"] == []
        assert result["centrality_scores"] == {}
        assert result["ripa_summary"]["total_systemic_risk"] == 0.0
        assert result["ripa_summary"]["top_vulnerabilities"] == []

    def test_ripa_summary_sorted_by_svi(self):
        nodes = [
            {"id": "n1", "name": "Hub"},
            {"id": "n2", "name": "Leaf A"},
            {"id": "n3", "name": "Leaf B"},
            {"id": "n4", "name": "Leaf C"},
        ]
        edges = [
            {"source_id": "n1", "target_id": "n2", "relationship": "REQUIRES"},
            {"source_id": "n1", "target_id": "n3", "relationship": "REQUIRES"},
            {"source_id": "n1", "target_id": "n4", "relationship": "REQUIRES"},
            {"source_id": "n2", "target_id": "n3", "relationship": "MODIFIES"},
        ]
        vault = _make_mock_vault(nodes, edges)
        calc = BlastRadiusCalculator("doc1", vault)
        result = calc.run()
        vulns = result["ripa_summary"]["top_vulnerabilities"]
        for i in range(len(vulns) - 1):
            assert vulns[i]["svi"] >= vulns[i + 1]["svi"]

    def test_cascade_paths_present(self):
        nodes = [
            {"id": "n1", "name": "A"},
            {"id": "n2", "name": "B"},
            {"id": "n3", "name": "C"},
        ]
        edges = [
            {"source_id": "n1", "target_id": "n2", "relationship": "REQUIRES"},
            {"source_id": "n2", "target_id": "n3", "relationship": "REQUIRES"},
        ]
        vault = _make_mock_vault(nodes, edges)
        calc = BlastRadiusCalculator("doc1", vault)
        result = calc.run()
        # REQUIRES (0.95) should cascade with high probability
        assert len(result["cascade_paths"]) > 0

    def test_svi_equals_max_ripa(self):
        nodes = [
            {"id": "n1", "name": "A"},
            {"id": "n2", "name": "B"},
        ]
        edges = [{"source_id": "n1", "target_id": "n2", "relationship": "REQUIRES"}]
        vault = _make_mock_vault(nodes, edges)
        calc = BlastRadiusCalculator("doc1", vault)
        result = calc.run()
        max_ripa = max((n["ripa"]["svi"] for n in result["nodes"]), default=0.0)
        assert abs(result["svi"] - max_ripa) < 0.0001
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_blast_radius_enhanced.py -v`
Expected: `FAILED` — current `BlastRadiusCalculator.run()` does not return `cascade_paths`, `centrality_scores`, or `ripa_summary`

- [ ] **Step 3: Rewrite `BlastRadiusCalculator.run()` in `core/simulator.py`**

At the top of `core/simulator.py`, add this import alongside the existing ones:

```python
import random
from core.centrality import (
    PROPAGATION_FACTORS,
    compute_degree,
    compute_betweenness,
    compute_ripa,
    compute_linkage_intensity,
    compute_resilience,
    probabilistic_bfs,
)
```

Then replace the entire `run()` method of `BlastRadiusCalculator` with:

```python
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

        edges = [
            {"source_id": r[0], "target_id": r[1], "relationship": r[2]}
            for r in edge_rows
        ]

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
        name_map = {row[0]: row[1] for row in cursor.fetchall()}
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
        all_cascade_paths = all_cascade_paths[:100]  # cap at top 100

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_blast_radius_enhanced.py -v`
Expected: all 7 tests `PASSED`

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/ -q --tb=no`
Expected: same pass count as before. Pre-existing `test_vault_delete.py` failures are unrelated.

- [ ] **Step 6: Commit**

```bash
git add core/simulator.py tests/test_blast_radius_enhanced.py
git commit -m "feat: enhance BlastRadiusCalculator with centrality, RIPA, cascade paths"
```

---

## Task 6: Add API endpoint tests for enhanced response shape

**Files:**
- Create: `tests/test_api_blast_radius.py`

- [ ] **Step 1: Write the tests**

Create `tests/test_api_blast_radius.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from api import app


def _make_mock_vault_with_graph():
    """Mock vault that returns a simple 3-node graph."""
    vault = MagicMock()
    vault.list_documents.return_value = []
    cursor = MagicMock()
    vault.conn.cursor.return_value = cursor

    # Document exists check
    cursor.fetchone.side_effect = [
        {"id": "doc1"},  # document exists
    ]

    # Return a mock simulation result (as if BlastRadiusCalculator already ran)
    vault.get_risk_simulation.return_value = None  # no cache
    return vault


def _fake_blast_result():
    return {
        "svi": 0.42,
        "nodes": [
            {
                "id": "n1", "name": "Alpha", "svi_contribution": 0.42,
                "dependency_count": 2, "cascade_depth": 2, "blast_radius_count": 2,
                "in_degree": 0.0, "out_degree": 0.5, "betweenness": 0.5,
                "ripa": {"li": 0.8, "re": 0.33, "criticality": 0.5, "svi": 0.42},
            },
        ],
        "cascade_paths": [
            {
                "trigger_node": "n1", "affected_node": "n2",
                "path": ["n1", "n2"], "hops": [{"from": "n1", "to": "n2", "edge_type": "REQUIRES", "probability": 0.95}],
                "depth": 1, "cumulative_probability": 0.95,
            },
        ],
        "centrality_scores": {
            "n1": {"in_degree": 0.0, "out_degree": 0.5, "betweenness": 0.5},
        },
        "ripa_summary": {
            "total_systemic_risk": 0.42,
            "top_vulnerabilities": [
                {"node_id": "n1", "name": "Alpha", "li": 0.8, "re": 0.33, "criticality": 0.5, "svi": 0.42},
            ],
        },
    }


class TestApiBlastRadius:
    def test_cached_result_includes_new_fields(self):
        mock_vault = MagicMock()
        mock_vault.list_documents.return_value = []
        mock_vault.get_risk_simulation.return_value = {
            "blast_radius": _fake_blast_result(),
            "black_swan": {"scenarios": []},
            "monte_carlo": {"available": False},
        }
        cursor = MagicMock()
        mock_vault.conn.cursor.return_value = cursor
        cursor.fetchone.return_value = {"id": "doc1"}

        with patch("api.vault", mock_vault):
            client = TestClient(app)
            response = client.get("/api/v1/reports/risk-simulation/doc1")
        assert response.status_code == 200
        body = response.json()
        assert body["cached"] is True
        blast = body["result"]["blast_radius"]
        assert "centrality_scores" in blast
        assert "ripa_summary" in blast
        assert "cascade_paths" in blast

    def test_blast_radius_node_has_ripa(self):
        mock_vault = MagicMock()
        mock_vault.list_documents.return_value = []
        mock_vault.get_risk_simulation.return_value = {
            "blast_radius": _fake_blast_result(),
            "black_swan": {"scenarios": []},
            "monte_carlo": {"available": False},
        }
        cursor = MagicMock()
        mock_vault.conn.cursor.return_value = cursor
        cursor.fetchone.return_value = {"id": "doc1"}

        with patch("api.vault", mock_vault):
            client = TestClient(app)
            response = client.get("/api/v1/reports/risk-simulation/doc1")
        blast = response.json()["result"]["blast_radius"]
        node = blast["nodes"][0]
        assert "ripa" in node
        assert "li" in node["ripa"]
        assert "re" in node["ripa"]
        assert "criticality" in node["ripa"]
        assert "svi" in node["ripa"]
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_api_blast_radius.py -v`
Expected: all 2 tests `PASSED` (these test cached result shape, which is just JSON — the shape is controlled by BlastRadiusCalculator.run() which we already enhanced)

- [ ] **Step 3: Commit**

```bash
git add tests/test_api_blast_radius.py
git commit -m "test: add API tests for enhanced blast radius response shape"
```

---

## Task 7: Rewrite Blast Radius tab in `static/index.html`

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Replace the Blast Radius HTML section**

In `static/index.html`, find the existing blast radius section. It looks like:

```html
<div id="sim-blast">
    <h2>&#128165; Blast Radius Analysis</h2>
    <div id="sim-svi"></div>
    <table id="sim-blast-table">
        <thead><tr><th>Node</th><th>Cascade Depth</th><th>Blast Radius</th><th>SVI Contribution</th></tr></thead>
        <tbody id="sim-blast-body"></tbody>
    </table>
</div>
```

Replace it with:

```html
            <div id="sim-blast">
                <h2>&#128165; Blast Radius Analysis</h2>

                <!-- SVI Headline -->
                <div id="sim-svi-headline" style="text-align:center;margin:16px 0;">
                    <div id="sim-svi-value" style="font-size:3rem;font-weight:700;font-family:'JetBrains Mono',monospace;"></div>
                    <div style="color:var(--text-secondary);font-size:0.85rem;">Total Systemic Risk</div>
                </div>

                <!-- Centrality Rankings Table -->
                <div class="cfg-section-label" style="margin-top:16px;">CENTRALITY RANKINGS</div>
                <table id="sim-centrality-table" style="width:100%;border-collapse:collapse;margin-top:8px;font-size:0.82rem;">
                    <thead>
                        <tr style="border-bottom:1px solid var(--border-dim);color:var(--text-secondary);">
                            <th style="text-align:left;padding:6px 8px;">Node</th>
                            <th style="text-align:right;padding:6px 8px;">In-Deg</th>
                            <th style="text-align:right;padding:6px 8px;">Out-Deg</th>
                            <th style="text-align:right;padding:6px 8px;">Betweenness</th>
                            <th style="text-align:right;padding:6px 8px;">RIPA SVI</th>
                        </tr>
                    </thead>
                    <tbody id="sim-centrality-body"></tbody>
                </table>

                <!-- RIPA Breakdown -->
                <div class="cfg-section-label" style="margin-top:20px;">VULNERABILITY BREAKDOWN</div>
                <div id="sim-ripa-bars" style="margin-top:8px;"></div>
                <div id="sim-ripa-legend" style="display:none;margin-top:6px;font-size:0.72rem;color:var(--text-secondary);">
                    <span style="display:inline-block;width:10px;height:10px;background:#4f9fff;margin-right:3px;vertical-align:middle;"></span> Linkage
                    <span style="display:inline-block;width:10px;height:10px;background:#ff3333;margin:0 3px 0 12px;vertical-align:middle;"></span> Vulnerability
                    <span style="display:inline-block;width:10px;height:10px;background:#f0b429;margin:0 3px 0 12px;vertical-align:middle;"></span> Criticality
                </div>

                <!-- Cascade Paths -->
                <div class="cfg-section-label" style="margin-top:20px;">CASCADE CHAINS</div>
                <div id="sim-cascade-paths" style="margin-top:8px;"></div>

                <!-- Fallback for old cached data -->
                <div id="sim-blast-upgrade" style="display:none;text-align:center;margin:24px 0;color:var(--text-secondary);">
                    <p>Re-run simulation to see enhanced analysis</p>
                    <button class="toolbar-btn" onclick="regenerateSim()">&#8634; Re-run</button>
                </div>
            </div>
```

- [ ] **Step 2: Add CSS for the RIPA bars and cascade paths**

Find the config drawer CSS section (the line `/* ── Config drawer ──`) in the `<style>` block. Insert the following CSS **before** that line:

```css
        /* ── Blast radius enhancements ──────────────────────────────── */
        .ripa-bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .ripa-bar-label { width: 140px; font-size: 0.78rem; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .ripa-bar-track { flex: 1; height: 14px; display: flex; border-radius: 3px; overflow: hidden; background: var(--bg-surface); }
        .ripa-bar-seg { height: 100%; }
        .ripa-bar-value { width: 48px; text-align: right; font-size: 0.75rem; font-family: 'JetBrains Mono', monospace; color: var(--text-secondary); }
        .cascade-item { border: 1px solid var(--border-dim); border-radius: 4px; margin-bottom: 6px; }
        .cascade-summary {
            padding: 8px 10px; cursor: pointer; display: flex; justify-content: space-between;
            align-items: center; font-size: 0.8rem; color: var(--text-primary);
        }
        .cascade-summary:hover { background: var(--bg-hover); }
        .cascade-prob { background: rgba(79,159,255,0.15); color: var(--accent-cyan); padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-family: 'JetBrains Mono', monospace; }
        .cascade-detail { display: none; padding: 6px 10px 10px; border-top: 1px solid var(--border-dim); font-size: 0.75rem; color: var(--text-secondary); }
        .cascade-detail.open { display: block; }
        .cascade-hop { padding: 2px 0; }
        .cascade-hop-type { color: var(--accent-cyan); font-family: 'JetBrains Mono', monospace; }
```

- [ ] **Step 3: Replace the blast radius rendering JS**

Find the existing `renderSimPage` function in `static/index.html`. Within it, locate the section that handles `blastSection` (the part that populates `sim-svi` and `sim-blast-body`). Replace the entire blast radius rendering block — from the line `const sviEl = document.getElementById('sim-svi');` through the end of the `nodes.forEach` block — with:

```javascript
        // ── Blast Radius rendering ─────────────────────────────────
        const blastSection = result?.blast_radius;
        if (blastSection && blastSection.ripa_summary) {
            // SVI Headline
            const sviVal = blastSection.ripa_summary.total_systemic_risk || 0;
            const sviPct = Math.round(sviVal * 100);
            const sviEl = document.getElementById('sim-svi-value');
            sviEl.textContent = sviPct + '%';
            sviEl.style.color = sviVal > 0.7 ? '#ff3333' : sviVal > 0.4 ? '#f0b429' : '#4caf50';

            // Centrality Rankings Table
            const cBody = document.getElementById('sim-centrality-body');
            cBody.innerHTML = '';
            const topNodes = (blastSection.nodes || []).slice(0, 10);
            topNodes.forEach(node => {
                const svi = node.ripa?.svi || 0;
                const rowColor = svi > 0.7 ? 'rgba(255,51,51,0.1)' : svi > 0.4 ? 'rgba(240,180,41,0.1)' : 'transparent';
                const row = document.createElement('tr');
                row.style.background = rowColor;
                row.style.borderBottom = '1px solid var(--border-dim)';
                row.innerHTML = `
                    <td style="padding:6px 8px;">${node.name || node.id}</td>
                    <td style="text-align:right;padding:6px 8px;font-family:'JetBrains Mono',monospace;">${(node.in_degree || 0).toFixed(2)}</td>
                    <td style="text-align:right;padding:6px 8px;font-family:'JetBrains Mono',monospace;">${(node.out_degree || 0).toFixed(2)}</td>
                    <td style="text-align:right;padding:6px 8px;font-family:'JetBrains Mono',monospace;">${(node.betweenness || 0).toFixed(2)}</td>
                    <td style="text-align:right;padding:6px 8px;font-family:'JetBrains Mono',monospace;color:${svi > 0.7 ? '#ff3333' : svi > 0.4 ? '#f0b429' : '#4caf50'};">${svi.toFixed(2)}</td>
                `;
                cBody.appendChild(row);
            });

            // RIPA Breakdown Bars
            const ripaBars = document.getElementById('sim-ripa-bars');
            ripaBars.innerHTML = '';
            const vulns = blastSection.ripa_summary.top_vulnerabilities || [];
            if (vulns.length > 0) {
                document.getElementById('sim-ripa-legend').style.display = 'block';
            }
            vulns.slice(0, 10).forEach(v => {
                const total = v.li + (1 - v.re) + v.criticality;
                const liPct = total > 0 ? (v.li / total * 100) : 0;
                const rePct = total > 0 ? ((1 - v.re) / total * 100) : 0;
                const crPct = total > 0 ? (v.criticality / total * 100) : 0;
                const row = document.createElement('div');
                row.className = 'ripa-bar-row';
                row.innerHTML = `
                    <div class="ripa-bar-label" title="${v.name}">${v.name}</div>
                    <div class="ripa-bar-track">
                        <div class="ripa-bar-seg" style="width:${liPct}%;background:#4f9fff;"></div>
                        <div class="ripa-bar-seg" style="width:${rePct}%;background:#ff3333;"></div>
                        <div class="ripa-bar-seg" style="width:${crPct}%;background:#f0b429;"></div>
                    </div>
                    <div class="ripa-bar-value">${v.svi.toFixed(2)}</div>
                `;
                ripaBars.appendChild(row);
            });

            // Cascade Paths
            const cascadeEl = document.getElementById('sim-cascade-paths');
            cascadeEl.innerHTML = '';
            const paths = (blastSection.cascade_paths || []).slice(0, 20);
            paths.forEach((p, idx) => {
                const item = document.createElement('div');
                item.className = 'cascade-item';
                const pathStr = p.path.join(' → ');
                const probPct = (p.cumulative_probability * 100).toFixed(1);
                item.innerHTML = `
                    <div class="cascade-summary" onclick="this.nextElementSibling.classList.toggle('open')">
                        <span>${pathStr}</span>
                        <span class="cascade-prob">${probPct}%</span>
                    </div>
                    <div class="cascade-detail">
                        ${p.hops.map(h => `<div class="cascade-hop">${h.from} <span class="cascade-hop-type">${h.edge_type}</span> → ${h.to} (${(h.probability * 100).toFixed(0)}%)</div>`).join('')}
                    </div>
                `;
                cascadeEl.appendChild(item);
            });

            document.getElementById('sim-blast-upgrade').style.display = 'none';
        } else if (blastSection) {
            // Old cached data without enhanced fields
            const sviEl = document.getElementById('sim-svi-value');
            sviEl.textContent = blastSection.svi !== undefined ? Math.round(blastSection.svi * 100) + '%' : 'N/A';
            sviEl.style.color = 'var(--text-secondary)';
            document.getElementById('sim-centrality-body').innerHTML = '';
            document.getElementById('sim-ripa-bars').innerHTML = '';
            document.getElementById('sim-cascade-paths').innerHTML = '';
            document.getElementById('sim-blast-upgrade').style.display = 'block';
        }
```

- [ ] **Step 4: Smoke test**

Start the server (`python run.py`) and open `http://localhost:8000`.

1. Upload a document and wait for ingestion to complete
2. Click the Risk Simulator button
3. Click Regenerate to trigger a fresh simulation
4. Verify:
   - SVI headline shows a percentage, colour-coded
   - Centrality table shows top nodes with In-Deg, Out-Deg, Betweenness, RIPA SVI columns
   - RIPA bars show coloured segments with legend
   - Cascade paths are listed with probability badges
   - Clicking a cascade path expands to show per-hop details
   - Clicking again collapses it

- [ ] **Step 5: Commit**

```bash
git add static/index.html
git commit -m "feat: rewrite Blast Radius tab with SVI headline, centrality table, RIPA bars, cascade paths"
```

---

## Verification

Run the full test suite:

```
pytest tests/ -q
```

Expected: all new tests pass; pre-existing `test_vault_delete.py` failures are unrelated.

Full end-to-end smoke test:
1. `python run.py` → open `http://localhost:8000`
2. Upload a PDF document
3. After ingestion, click Risk Simulator → Regenerate
4. SVI headline displays with colour coding
5. Centrality table ranks nodes by betweenness
6. RIPA bars visualise vulnerability breakdown per node
7. Cascade paths expand/collapse with per-hop detail
8. Old cached results show "Re-run simulation" prompt
