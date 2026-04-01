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
