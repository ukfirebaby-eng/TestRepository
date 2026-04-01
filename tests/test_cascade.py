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
