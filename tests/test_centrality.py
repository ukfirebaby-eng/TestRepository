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
