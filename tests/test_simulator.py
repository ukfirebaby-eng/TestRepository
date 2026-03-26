"""
tests/test_simulator.py — Unit tests for BlastRadiusCalculator and BlackSwanAgent.
"""

import json
import numpy
import pytest
from unittest.mock import MagicMock, patch, call
from core.simulator import BlastRadiusCalculator, BlackSwanAgent, MonteCarloForecaster


def _make_vault(edges, node_names=None, fragility_lines=None):
    """
    Build a mock vault whose conn.cursor() returns canned results.

    edges        — list of dicts with 'source_id' and 'target_id'
    node_names   — dict {node_id: name}; defaults to id == name
    fragility_lines — list of dicts with 'cascade_nodes' list
    """
    node_names = node_names or {}
    fragility_lines = fragility_lines or []

    vault = MagicMock()

    # Each call to vault.conn.cursor() returns a fresh mock cursor.
    # We use side_effect on fetchall/fetchone to serve the right data.

    # cursor 1 — edges query (fetchall)
    edge_cursor = MagicMock()
    edge_cursor.fetchall.return_value = edges

    # cursor 2+ — per-hub name lookups (fetchone)
    # We'll use a factory so each cursor gets its own fetchone behaviour.
    def make_name_cursor(node_id):
        nc = MagicMock()
        name = node_names.get(node_id, node_id)
        nc.fetchone.return_value = {"name": name}
        return nc

    # conn.cursor() is called once for edges, then once per hub node.
    # We track call count to distinguish.
    call_count = [0]
    hub_queue = []  # will be populated as BFS runs; we pre-build cursors lazily

    def cursor_factory():
        call_count[0] += 1
        if call_count[0] == 1:
            return edge_cursor
        # For subsequent calls the execute() arg contains the node id.
        # Return a generic cursor whose fetchone returns the right name.
        nc = MagicMock()
        def fetchone_side_effect():
            # Retrieve the node id from the last execute call args
            node_id = nc.execute.call_args[0][1][0]
            name = node_names.get(node_id, node_id)
            return {"name": name}
        nc.fetchone.side_effect = fetchone_side_effect
        return nc

    vault.conn.cursor.side_effect = cursor_factory
    vault.get_fragility_lines.return_value = fragility_lines
    return vault


class TestBlastRadiusCalculator:

    def test_svi_computed_correctly(self):
        """
        Topology: A, B, C, D all REQUIRE hub H (in-degree 4).
        E REQUIRES D (so E is also a node).
        Only one hub (H), max_in_degree = 4.
        blast_radius = reverse BFS from H = {A, B, C, D, E} = 5 nodes reachable.
        total_nodes = 6 (A B C D E H).
        svi_contribution = (5/6) * (4/4) = 0.8333...
        svi_total = min(0.8333, 1.0) = 0.8333 (single hub, no division).
        """
        edges = [
            {"source_id": "A", "target_id": "H"},
            {"source_id": "B", "target_id": "H"},
            {"source_id": "C", "target_id": "H"},
            {"source_id": "D", "target_id": "H"},
            {"source_id": "E", "target_id": "D"},
        ]
        vault = _make_vault(edges)
        result = BlastRadiusCalculator("doc1", vault).run()

        assert result["svi"] == pytest.approx(5 / 6, rel=1e-4)
        assert len(result["nodes"]) == 1
        hub = result["nodes"][0]
        assert hub["id"] == "H"
        assert hub["blast_radius_count"] == 5
        assert hub["svi_contribution"] == pytest.approx(5 / 6, rel=1e-4)

    def test_cascade_depth_via_bfs(self):
        """
        Chain: X -> Y -> Z -> HUB, plus W1, W2, W3 also -> HUB (hub in-degree=4).
        Reverse BFS from HUB: depth 1 = {X's chain base, W1, W2, W3},
        following Z <- Y <- X gives depth 3 from HUB.
        cascade_depth should be 3.
        """
        edges = [
            {"source_id": "Z",  "target_id": "HUB"},
            {"source_id": "W1", "target_id": "HUB"},
            {"source_id": "W2", "target_id": "HUB"},
            {"source_id": "W3", "target_id": "HUB"},
            {"source_id": "Y",  "target_id": "Z"},
            {"source_id": "X",  "target_id": "Y"},
        ]
        vault = _make_vault(edges)
        result = BlastRadiusCalculator("doc2", vault).run()

        assert len(result["nodes"]) == 1
        hub = result["nodes"][0]
        assert hub["id"] == "HUB"
        assert hub["cascade_depth"] == 3

    def test_empty_graph_returns_zero_svi(self):
        """No REQUIRES edges → svi=0.0, nodes=[]."""
        vault = _make_vault(edges=[])
        result = BlastRadiusCalculator("doc3", vault).run()
        assert result == {"svi": 0.0, "nodes": []}

    def test_newly_detected_flag(self):
        """
        BFS finds nodes not listed in fragility_lines cascade_nodes → newly_detected=True.
        Here the pre-computed set only contains {A}, but BFS also reaches B, C, D, E.
        """
        edges = [
            {"source_id": "A", "target_id": "H"},
            {"source_id": "B", "target_id": "H"},
            {"source_id": "C", "target_id": "H"},
            {"source_id": "D", "target_id": "H"},
            {"source_id": "E", "target_id": "D"},
        ]
        fragility_lines = [{"cascade_nodes": ["A"]}]  # only A pre-computed
        vault = _make_vault(edges, fragility_lines=fragility_lines)
        result = BlastRadiusCalculator("doc4", vault).run()

        assert len(result["nodes"]) == 1
        hub = result["nodes"][0]
        # B, C, D, E are reachable but not in precomputed → newly_detected=True
        assert hub["newly_detected"] is True

    def test_multi_hub_svi_is_sum_capped(self):
        """
        Two hub nodes H1 and H2, each with in-degree 3.
        max_in_degree = 3 for both.

        Topology:
          A, B, C -> H1  (H1 in-degree 3)
          D, E, F -> H2  (H2 in-degree 3)

        total_nodes = 8 (A B C H1 D E F H2)
        max_in_degree = 3

        H1: blast_radius = {A, B, C} = 3
            svi_contribution = (3/8) * (3/3) = 0.375

        H2: blast_radius = {D, E, F} = 3
            svi_contribution = (3/8) * (3/3) = 0.375

        svi_total = min(0.375 + 0.375, 1.0) = 0.75
        (NOT the average 0.375 that the old branching code produced)
        """
        edges = [
            {"source_id": "A", "target_id": "H1"},
            {"source_id": "B", "target_id": "H1"},
            {"source_id": "C", "target_id": "H1"},
            {"source_id": "D", "target_id": "H2"},
            {"source_id": "E", "target_id": "H2"},
            {"source_id": "F", "target_id": "H2"},
        ]
        vault = _make_vault(edges)
        result = BlastRadiusCalculator("doc5", vault).run()

        assert result["svi"] == pytest.approx(0.75, rel=1e-4)
        assert len(result["nodes"]) == 2


# ── Helpers for BlackSwanAgent tests ─────────────────────────────────────────

_SAMPLE_HUBS = [
    {"id": "node_1", "name": "Budget Approval", "label": "Process", "dependency_count": 5},
    {"id": "node_2", "name": "Core Platform", "label": "System",  "dependency_count": 3},
]

_VALID_SCENARIOS = [
    {
        "title": "Scenario A",
        "trigger_node": "Budget Approval",
        "cascade_path": ["Budget Approval", "Core Platform"],
        "impact_radius": "7 of 12 nodes affected",
        "mitigation": "Establish a backup approval process.",
    },
    {
        "title": "Scenario B",
        "trigger_node": "Core Platform",
        "cascade_path": ["Core Platform"],
        "impact_radius": "3 of 12 nodes affected",
        "mitigation": "Introduce redundancy.",
    },
    {
        "title": "Scenario C",
        "trigger_node": "Budget Approval",
        "cascade_path": ["Budget Approval"],
        "impact_radius": "5 of 12 nodes affected",
        "mitigation": "Pre-authorise contingency funds.",
    },
]


def _make_mock_client(content: str) -> MagicMock:
    """Build a mock OpenAI client that returns `content` from chat.completions.create."""
    mock_message = MagicMock()
    mock_message.content = content

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


class TestBlackSwanAgent:

    def test_returns_three_scenarios(self):
        """Mock LLM returns valid JSON with 3 scenarios; verify all required keys present."""
        content = json.dumps(_VALID_SCENARIOS)
        mock_client = _make_mock_client(content)

        vault = MagicMock()
        vault.get_hub_vulnerabilities.return_value = _SAMPLE_HUBS
        vault.get_fragility_lines.return_value = []

        with patch("core.simulator._get_client", return_value=mock_client):
            result = BlackSwanAgent("doc_bs_1", vault).run()

        assert "scenarios" in result
        assert len(result["scenarios"]) == 3
        for scenario in result["scenarios"]:
            assert "title" in scenario
            assert "trigger_node" in scenario
            assert "cascade_path" in scenario
            assert "impact_radius" in scenario
            assert "mitigation" in scenario

    def test_node_names_grounded_in_prompt(self):
        """Hub node names from vault must appear in the LLM call's user message."""
        content = json.dumps(_VALID_SCENARIOS)
        mock_client = _make_mock_client(content)

        vault = MagicMock()
        vault.get_hub_vulnerabilities.return_value = _SAMPLE_HUBS
        vault.get_fragility_lines.return_value = []

        with patch("core.simulator._get_client", return_value=mock_client):
            BlackSwanAgent("doc_bs_2", vault).run()

        call_kwargs = mock_client.chat.completions.create.call_args
        # call_args.kwargs is the reliable way to get keyword arguments
        messages = call_kwargs.kwargs.get("messages", call_kwargs[0][0] if call_kwargs[0] else [])
        # Flatten all message content into one string for easy assertion
        all_content = " ".join(m["content"] for m in messages)

        assert "Budget Approval" in all_content
        assert "Core Platform" in all_content

    def test_handles_malformed_llm_response(self):
        """Non-JSON / partial JSON from LLM → returns {'scenarios': []} without exception."""
        for bad_content in ["not json at all", '{"broken": true', "```json\n[{bad}]\n```"]:
            mock_client = _make_mock_client(bad_content)

            vault = MagicMock()
            vault.get_hub_vulnerabilities.return_value = _SAMPLE_HUBS
            vault.get_fragility_lines.return_value = []

            with patch("core.simulator._get_client", return_value=mock_client):
                result = BlackSwanAgent("doc_bs_3", vault).run()

            assert result == {"scenarios": []}, f"Failed for input: {bad_content!r}"


# ── Helpers for MonteCarloForecaster tests ────────────────────────────────────

def _make_mc_vault(
    has_temporal=True,
    temporal_rows=None,
    starts_after_rows=None,
    node_name_rows=None,
    friction_lines=None,
):
    """
    Build a mock vault for MonteCarloForecaster.

    conn.cursor() is called up to 3 times:
      1st  → temporal_metadata query  (fetchall → temporal_rows)
      2nd  → STARTS_AFTER edges query (fetchall → starts_after_rows)
      3rd  → nodes name lookup        (fetchall → node_name_rows)
    """
    temporal_rows = temporal_rows or []
    starts_after_rows = starts_after_rows or []
    node_name_rows = node_name_rows or []
    friction_lines = friction_lines or []

    vault = MagicMock()
    vault.has_temporal_data.return_value = has_temporal
    vault.get_chronological_friction_lines.return_value = friction_lines

    cursors = []
    for rows in [temporal_rows, starts_after_rows, node_name_rows]:
        c = MagicMock()
        c.fetchall.return_value = rows
        cursors.append(c)

    # Provide extra cursors beyond the expected 3 in case code asks for more
    extra = MagicMock()
    extra.fetchall.return_value = []

    call_count = [0]

    def cursor_factory():
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(cursors):
            return cursors[idx]
        return extra

    vault.conn.cursor.side_effect = cursor_factory
    return vault


class TestMonteCarloForecaster:

    def test_returns_unavailable_when_no_temporal_data(self):
        """vault.has_temporal_data returns False → {"available": False, ...}"""
        vault = _make_mc_vault(has_temporal=False)
        result = MonteCarloForecaster("doc_mc_1", vault).run()

        assert result["available"] is False
        assert "reason" in result

    def test_p50_le_p80_le_p95(self):
        """With real temporal data mocked, p50 <= p80 <= p95 always holds."""
        numpy.random.seed(42)

        temporal_rows = [
            ("node_A", "2025-01-01", "2025-03-01"),   # 59 days
            ("node_B", "2025-01-15", "2025-04-15"),   # 89 days
            ("node_C", "2025-02-01", "2025-05-01"),   # 89 days
        ]
        node_name_rows = [
            ("node_A", "Task A"),
            ("node_B", "Task B"),
            ("node_C", "Task C"),
        ]

        vault = _make_mc_vault(
            has_temporal=True,
            temporal_rows=temporal_rows,
            starts_after_rows=[],
            node_name_rows=node_name_rows,
            friction_lines=[],
        )

        result = MonteCarloForecaster("doc_mc_2", vault, n_trials=1000).run()

        assert result["available"] is True
        assert result["p50_delay_days"] <= result["p80_delay_days"] <= result["p95_delay_days"]

    def test_at_risk_nodes_non_empty_when_delays_exist(self):
        """Nodes with positive durations and friction → at_risk_nodes not empty."""
        numpy.random.seed(42)

        temporal_rows = [
            ("node_X", "2025-01-01", "2025-06-01"),   # 151 days — long task
            ("node_Y", "2025-01-01", "2025-04-01"),   # 89 days
        ]
        # node_X starts after node_Y (dependency chain)
        starts_after_rows = [
            ("node_Y", "node_X"),
        ]
        node_name_rows = [
            ("node_X", "Long Task"),
            ("node_Y", "Prerequisite"),
        ]
        friction_lines = [
            {"source_id": "node_Y", "days_at_risk": 20},
        ]

        vault = _make_mc_vault(
            has_temporal=True,
            temporal_rows=temporal_rows,
            starts_after_rows=starts_after_rows,
            node_name_rows=node_name_rows,
            friction_lines=friction_lines,
        )

        result = MonteCarloForecaster("doc_mc_3", vault, n_trials=500).run()

        assert result["available"] is True
        assert len(result["at_risk_nodes"]) > 0
        # Each at-risk node has the required keys
        for node in result["at_risk_nodes"]:
            assert "id" in node
            assert "name" in node
            assert "mean_delay_days" in node

    def test_zero_delay_with_no_friction_lines(self):
        """No friction and tight durations (symmetric variance) → p50 near 0."""
        numpy.random.seed(42)

        # Very short tasks with no dependencies or friction
        temporal_rows = [
            ("node_P", "2025-01-01", "2025-01-02"),   # 1 day
            ("node_Q", "2025-01-01", "2025-01-02"),   # 1 day
        ]
        node_name_rows = [
            ("node_P", "Tiny Task P"),
            ("node_Q", "Tiny Task Q"),
        ]

        vault = _make_mc_vault(
            has_temporal=True,
            temporal_rows=temporal_rows,
            starts_after_rows=[],
            node_name_rows=node_name_rows,
            friction_lines=[],
        )

        result = MonteCarloForecaster("doc_mc_4", vault, n_trials=2000).run()

        assert result["available"] is True
        # With 1-day tasks and no friction, most delay samples round to 0
        # p95 should be very small (variance of ±20% of 1 day is tiny)
        assert result["p95_delay_days"] <= 5
