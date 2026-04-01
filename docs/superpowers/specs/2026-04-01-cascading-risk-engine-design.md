# Design: Cascading Risk Simulation Engine

**Date:** 2026-04-01
**Status:** Approved
**Sub-project:** 1 of 3 (Autonomous Strategic Risk Simulator)

---

## Context

Diamond Miner's `BlastRadiusCalculator` in `core/simulator.py` performs a simple BFS traversal to compute a System Vulnerability Index (SVI) per node. While functional, it treats all edges equally, does not model probabilistic propagation, lacks centrality analysis, and the frontend Blast Radius tab has never actually displayed the SVI or node rankings. This sub-project shores up the cascading risk simulation foundation before the subsequent Black Swan and Probabilistic Forecasting sub-projects build on top of it.

---

## Decisions

| Question | Decision |
|---|---|
| Graph model | BFS with per-edge-type propagation probabilities (handles cycles naturally) |
| Vulnerability metrics source | Derived entirely from graph structure (no LLM calls) |
| Centrality metrics | Degree (in/out) + betweenness centrality (no clustering coefficient) |
| Return shape | Additive — new fields alongside existing `svi` and `nodes` |
| Frontend | Rewrite Blast Radius tab content (currently non-functional) |
| Dependencies | No new libraries — pure Python implementations |

---

## Architecture

### New Module: `core/centrality.py`

Pure calculation functions with no side effects — takes graph data as plain lists/dicts, returns metrics. No vault, no LLM, no I/O.

#### `compute_degree(nodes, edges) -> Dict[str, Dict]`

For each node, computes:
- `in_degree`: count of edges targeting this node, normalised by `(graph_size - 1)`
- `out_degree`: count of edges sourced from this node, normalised by `(graph_size - 1)`

Returns `{node_id: {"in_degree": float, "out_degree": float}}`.

Edge case: single-node graph returns `{"in_degree": 0.0, "out_degree": 0.0}`. Empty graph returns `{}`.

#### `compute_betweenness(nodes, edges) -> Dict[str, float]`

Betweenness centrality: fraction of all shortest paths (across all source-target pairs) that pass through each node. Uses BFS-based Brandes' algorithm (O(V*E)), which is efficient for the graph sizes Diamond Miner handles (<500 nodes).

Returns `{node_id: float}` where values are normalised to [0, 1] by dividing by `(V-1)(V-2)/2` for directed graphs.

Edge case: graph with ≤2 nodes returns `0.0` for all nodes.

#### `compute_ripa(li, re, criticality) -> float`

Composite RIPA Systemic Vulnerability Index for a single node:

```
SVI = LI × Criticality × (1 - RE)
```

Where:
- `LI` (Linkage Intensity) = normalised weighted degree: `sum(propagation_factor for each edge) / max_possible_weighted_degree`
- `RE` (Resilience) = `1 / (1 + dependency_concentration)` where `dependency_concentration = in_degree_count` for nodes with no alternative paths (i.e., all predecessors are single points of failure). Range: (0, 1] where 1 = fully resilient.
- `Criticality` = betweenness centrality value

Returns a float in [0, 1]. A node with high linkage, high criticality, and low resilience scores highest.

### Edge-Type Propagation Probabilities

Each of the six allowed edge types in the knowledge graph has a fixed propagation factor:

| Edge Type | Propagation Factor | Rationale |
|---|---|---|
| `REQUIRES` | 0.95 | Near-certain cascade — hard dependency |
| `BLOCKS` | 0.90 | Strong inhibition propagates failure |
| `PRODUCES` | 0.70 | Output disruption likely propagates |
| `MODIFIES` | 0.50 | Change impact is context-dependent |
| `CONTRADICTS` | 0.30 | Logical tension, not necessarily causal |
| `RELATES_TO` | 0.15 | Weak association, rarely cascades |

These are module-level constants in `core/centrality.py`:

```python
PROPAGATION_FACTORS: Dict[str, float] = {
    "REQUIRES": 0.95,
    "BLOCKS": 0.90,
    "PRODUCES": 0.70,
    "MODIFIES": 0.50,
    "CONTRADICTS": 0.30,
    "RELATES_TO": 0.15,
}
```

### Enhanced `BlastRadiusCalculator` in `core/simulator.py`

The existing class is modified (not replaced). The `.run()` method orchestration becomes:

1. Load graph topology from vault (existing)
2. Compute degree centrality via `compute_degree()`
3. Compute betweenness centrality via `compute_betweenness()`
4. For each node, run **probabilistic BFS**:
   - Seed Python's `random` with a fixed seed (for determinism in tests; production uses `random.seed(document_id)` for per-document reproducibility)
   - At each hop, generate `random.random()` and compare against the edge's propagation factor — only traverse if `rand < factor`
   - Track the activation path: ordered list of `(node_id, edge_type, propagation_probability)` tuples
   - Track cumulative probability: product of all hop probabilities along the path
   - Prune paths with cumulative probability below `0.05`
   - Do not revisit already-visited nodes (cycle handling)
5. Compute RIPA scores per node using centrality results
6. Assemble and return the enhanced result

#### Enhanced Return Shape

```python
{
    "svi": 0.73,                           # Total Systemic Risk (max RIPA SVI across all nodes)
    "nodes": [                             # Existing field, enriched
        {
            "id": "node_42",
            "name": "Vendor Onboarding",
            "svi_contribution": 0.39,      # This node's RIPA SVI
            "dependency_count": 5,          # Existing
            "in_degree": 0.12,             # NEW
            "out_degree": 0.35,            # NEW
            "betweenness": 0.58,           # NEW
            "ripa": {                      # NEW
                "li": 0.8,
                "re": 0.15,
                "criticality": 0.58,
                "svi": 0.39
            }
        }
    ],
    "cascade_paths": [                     # NEW
        {
            "trigger_node": "node_42",
            "affected_node": "node_17",
            "path": ["node_42", "node_8", "node_17"],
            "hops": [
                {"from": "node_42", "to": "node_8", "edge_type": "REQUIRES", "probability": 0.95},
                {"from": "node_8", "to": "node_17", "edge_type": "MODIFIES", "probability": 0.50}
            ],
            "depth": 2,
            "cumulative_probability": 0.475
        }
    ],
    "centrality_scores": {                 # NEW
        "node_42": {"in_degree": 0.12, "out_degree": 0.35, "betweenness": 0.58}
    },
    "ripa_summary": {                      # NEW
        "total_systemic_risk": 0.73,
        "top_vulnerabilities": [
            {"node_id": "node_42", "name": "Vendor Onboarding", "li": 0.8, "re": 0.15, "criticality": 0.58, "svi": 0.39}
        ]
    }
}
```

The existing `svi` field now reflects the RIPA-based maximum rather than simple BFS depth. The existing `nodes` array retains its shape with additional fields — any frontend code reading `nodes[].name` or `nodes[].dependency_count` continues to work.

---

## API

**No endpoint changes required.** The existing `POST /api/v1/simulate` with `simulator: "blast_radius"` calls `BlastRadiusCalculator.run()` and streams the result via SSE. The enhanced return shape flows through the same pipeline. The existing `GET /api/v1/reports/risk-simulation` returns cached results, which will include the new fields after re-running.

Cached results from before the upgrade will lack the new fields. The frontend handles this gracefully (see below).

---

## Frontend: Blast Radius Tab Rewrite

The existing Blast Radius tab in `static/index.html` has never displayed results despite the backend providing them. The `loadBlastRadius()` JS function is rewritten and the tab content HTML is replaced.

### Tab Content Structure

Four panels rendered vertically within the existing Blast Radius tab area:

**1. SVI Headline**
- Large number showing `ripa_summary.total_systemic_risk` formatted as a percentage (e.g. "73%")
- Colour-coded: red (>0.7), amber (0.4–0.7), green (<0.4)
- Label: "Total Systemic Risk"

**2. Centrality Rankings Table**
- Top 10 nodes sorted by betweenness centrality (descending)
- Columns: Node Name | In-Degree | Out-Degree | Betweenness | RIPA SVI
- Rows colour-coded by SVI severity (same red/amber/green thresholds)
- Values formatted to 2 decimal places

**3. RIPA Breakdown Panel**
- Shown for each node in `ripa_summary.top_vulnerabilities` (up to 10)
- Each entry: node name on the left, horizontal CSS bar on the right
- Bar is divided into three colour-coded segments proportional to LI, (1-RE), and Criticality
- Legend below the first entry: blue = Linkage Intensity, red = Vulnerability (1-RE), amber = Criticality
- No charting library — pure CSS `display: flex` with percentage widths

**4. Cascade Paths Panel**
- Header: "Highest-Probability Cascade Chains"
- List of top 20 cascade paths sorted by cumulative probability (descending)
- Each entry (collapsed): `Trigger Node → ... → Affected Node` with probability badge (e.g. "47.5%")
- Each entry (expanded, on click): shows each hop with edge type label and individual probability
- Collapsible via simple JS `classList.toggle` on a details class

### Graceful Degradation

If the API response lacks `centrality_scores`, `ripa_summary`, or `cascade_paths` (old cached data), the tab shows the SVI headline with whatever `svi` value exists, plus a message: "Re-run simulation to see enhanced analysis" with a button that triggers the POST endpoint.

### JS Changes

`loadBlastRadius()` is rewritten to:
1. Fetch from the existing endpoint
2. Parse the response for both old and new fields
3. Render the four panels using DOM manipulation (consistent with existing vanilla JS patterns in the file)
4. Attach click handlers for cascade path expand/collapse

---

## Testing

### `tests/test_centrality.py` — Centrality Calculations

- `test_degree_simple_graph`: 3-node chain A→B→C. A: out=0.5, in=0.0. B: out=0.5, in=0.5. C: out=0.0, in=0.5.
- `test_degree_empty_graph`: returns `{}`
- `test_degree_single_node`: returns `{"in_degree": 0.0, "out_degree": 0.0}`
- `test_betweenness_star_graph`: centre node of a 5-node star has betweenness ~1.0, leaf nodes have 0.0
- `test_betweenness_chain`: middle node in A→B→C has highest betweenness
- `test_betweenness_two_nodes`: returns 0.0 for both (no intermediate paths)
- `test_propagation_factors_complete`: all six edge types have defined factors

### `tests/test_ripa.py` — RIPA Scoring

- `test_high_risk_node`: high LI, high criticality, low RE → SVI near 1.0
- `test_low_risk_node`: low LI, low criticality, high RE → SVI near 0.0
- `test_zero_edges_node`: LI=0 → SVI=0 regardless of other factors
- `test_fully_resilient_node`: RE=1.0 → SVI=0 regardless of other factors
- `test_ripa_formula`: known inputs produce exact expected output

### `tests/test_cascade.py` — Probabilistic BFS

- `test_deterministic_with_seed`: same seed produces identical cascade paths across runs
- `test_pruning_below_threshold`: paths with cumulative probability <0.05 not included
- `test_cumulative_probability`: product of hop probabilities matches reported value
- `test_cycle_handling`: graph with cycle A→B→A doesn't infinite-loop, B visited only once
- `test_cascade_depth`: depth equals number of hops in the path
- `test_requires_edge_high_propagation`: REQUIRES edges propagate almost always (seeded test)
- `test_relates_to_edge_low_propagation`: RELATES_TO edges rarely propagate (seeded test)

### `tests/test_blast_radius_enhanced.py` — Integration

- `test_run_returns_all_fields`: `.run()` output contains `svi`, `nodes`, `cascade_paths`, `centrality_scores`, `ripa_summary`
- `test_nodes_enriched_with_centrality`: each node in `nodes` has `in_degree`, `out_degree`, `betweenness`, `ripa` sub-object
- `test_result_json_serialisable`: `json.dumps()` succeeds on `.run()` output
- `test_empty_graph`: returns `svi=0`, empty lists/dicts for all new fields
- `test_ripa_summary_top_vulnerabilities_sorted`: `top_vulnerabilities` list is sorted by SVI descending

### `tests/test_api_blast_radius.py` — API Endpoint

- `test_blast_radius_returns_enhanced_shape`: POST simulate with `"blast_radius"` returns response containing `centrality_scores` and `ripa_summary`
- `test_cached_result_includes_new_fields`: GET after POST returns the new fields from cache

All tests use `tmp_path` fixtures for isolated SQLite databases and `unittest.mock.patch` to stub vault data. Probabilistic BFS tests use `random.seed()` for determinism. No live API key needed.

---

## Files to Create / Modify

| File | Change |
|---|---|
| `core/centrality.py` | New — `PROPAGATION_FACTORS`, `compute_degree()`, `compute_betweenness()`, `compute_ripa()` |
| `core/simulator.py` | Modify — enhance `BlastRadiusCalculator` with probabilistic BFS, centrality integration, RIPA scoring, cascade path tracking |
| `static/index.html` | Modify — rewrite Blast Radius tab HTML + `loadBlastRadius()` JS to render SVI headline, centrality table, RIPA bars, cascade paths |
| `tests/test_centrality.py` | New |
| `tests/test_ripa.py` | New |
| `tests/test_cascade.py` | New |
| `tests/test_blast_radius_enhanced.py` | New |
| `tests/test_api_blast_radius.py` | New |

---

## Out of Scope

- LLM-annotated resilience scores (future: Black Swan sub-project)
- User-configurable propagation weights via UI sliders (future enhancement)
- GNN-based probabilistic inference (future: Probabilistic Forecasting sub-project)
- Clustering coefficient centrality metric
- Changes to Black Swan or Monte Carlo simulators
