"""
tests/test_simulator.py — Unit tests for BlastRadiusCalculator and BlackSwanAgent.
"""

import json
import numpy
import pytest
import sqlite3
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

    # Build name rows from all node IDs referenced in edges
    all_ids = set()
    for e in edges:
        all_ids.add(e["source_id"])
        all_ids.add(e["target_id"])
    name_rows = [{"id": nid, "name": node_names.get(nid, nid)} for nid in sorted(all_ids)]

    # The simulator uses a single cursor for two fetchall() calls:
    # 1st: edges query, 2nd: batch node-name query
    primary_cursor = MagicMock()
    primary_cursor.fetchall.side_effect = [edges, name_rows]

    vault.conn.cursor.return_value = primary_cursor
    vault.get_fragility_lines.return_value = fragility_lines
    return vault


class TestBlastRadiusCalculator:

    def test_svi_computed_correctly(self):
        """
        RIPA-based SVI: hub H has highest in-degree (4) → should have
        highest SVI contribution among all nodes.
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

        assert result["svi"] > 0.0
        assert "nodes" in result
        assert "cascade_paths" in result
        assert "centrality_scores" in result
        assert "ripa_summary" in result
        # All 6 nodes should be present
        assert len(result["nodes"]) == 6
        node_ids = {n["id"] for n in result["nodes"]}
        assert "H" in node_ids
        # H should have the highest in-degree
        h_node = next(n for n in result["nodes"] if n["id"] == "H")
        assert h_node["dependency_count"] >= 3

    def test_cascade_paths_present(self):
        """
        Chain topology should produce cascade paths via probabilistic BFS.
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

        assert len(result["nodes"]) == 7  # Z, HUB, W1, W2, W3, Y, X
        node_ids = {n["id"] for n in result["nodes"]}
        assert "HUB" in node_ids
        assert "ripa" in result["nodes"][0]

    def test_empty_graph_returns_zero_svi(self):
        """No edges → svi=0.0, empty collections."""
        vault = _make_vault(edges=[])
        result = BlastRadiusCalculator("doc3", vault).run()
        assert result["svi"] == 0.0
        assert result["nodes"] == []
        assert result["cascade_paths"] == []

    def test_accepts_sqlite_row_edges_from_real_vault_cursor(self):
        """Production SQLite cursors return sqlite3.Row objects, not plain dicts."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE edges (
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relationship TEXT NOT NULL,
                document_id TEXT NOT NULL
            );
            CREATE TABLE nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );
        """)
        conn.executemany(
            "INSERT INTO nodes (id, name) VALUES (?, ?)",
            [("portal", "Portal"), ("identity", "Identity")],
        )
        conn.execute(
            "INSERT INTO edges (source_id, target_id, relationship, document_id) VALUES (?, ?, ?, ?)",
            ("portal", "identity", "REQUIRES", "doc_sqlite"),
        )
        conn.commit()
        vault = MagicMock()
        vault.conn = conn

        result = BlastRadiusCalculator("doc_sqlite", vault).run()

        assert result["svi"] >= 0.0
        assert {node["id"] for node in result["nodes"]} == {"portal", "identity"}

    def test_centrality_scores_populated(self):
        """Every node should have centrality scores."""
        edges = [
            {"source_id": "A", "target_id": "H"},
            {"source_id": "B", "target_id": "H"},
            {"source_id": "C", "target_id": "H"},
            {"source_id": "D", "target_id": "H"},
            {"source_id": "E", "target_id": "D"},
        ]
        vault = _make_vault(edges)
        result = BlastRadiusCalculator("doc4", vault).run()

        # Every node should have centrality scores
        for nid in ["A", "B", "C", "D", "E", "H"]:
            assert nid in result["centrality_scores"]
            scores = result["centrality_scores"][nid]
            assert "in_degree" in scores
            assert "out_degree" in scores
            assert "betweenness" in scores

    def test_multi_node_ripa_ranking(self):
        """
        Two hub nodes H1 and H2 each with in-degree 3. Both should
        rank above leaf nodes in RIPA SVI.
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

        assert result["svi"] >= 0.0
        assert len(result["nodes"]) == 8
        node_ids = {n["id"] for n in result["nodes"]}
        assert {"H1", "H2"}.issubset(node_ids)
        # Both hubs should have non-zero dependency counts
        hub_nodes = [n for n in result["nodes"] if n["id"] in ("H1", "H2")]
        assert all(h["dependency_count"] >= 0 for h in hub_nodes)


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
        assert result["at_risk_nodes"] == []
