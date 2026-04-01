import pytest
from core.centrality import PROPAGATION_FACTORS, compute_degree, compute_betweenness


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
