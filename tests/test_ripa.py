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
