"""Tests for Reciprocal Rank Fusion."""

import pytest

from rag_system.retrieval.rrf import reciprocal_rank_fusion


class TestRRF:
    def test_single_list_preserves_order(self):
        ranking = [["a", "b", "c"]]
        result = reciprocal_rank_fusion(ranking)
        ids = [r[0] for r in result]
        assert ids == ["a", "b", "c"]

    def test_two_lists_boosts_common_items(self):
        # "b" appears in both lists at rank 1 → should score highest
        ranking = [["b", "a", "c"], ["b", "c", "d"]]
        result = reciprocal_rank_fusion(ranking)
        assert result[0][0] == "b"

    def test_scores_sum_correctly(self):
        # With k=60: rank 1 in one list = 1/61 ≈ 0.01639
        ranking = [["a"]]
        result = reciprocal_rank_fusion(ranking, k=60)
        assert len(result) == 1
        assert abs(result[0][1] - 1 / 61) < 1e-9

    def test_two_lists_score_addition(self):
        # "a" at rank 1 in both lists → score = 2/61
        ranking = [["a", "b"], ["a", "c"]]
        result = reciprocal_rank_fusion(ranking, k=60)
        a_score = dict(result)["a"]
        assert abs(a_score - 2 / 61) < 1e-9

    def test_empty_lists(self):
        result = reciprocal_rank_fusion([])
        assert result == []

    def test_empty_inner_list(self):
        result = reciprocal_rank_fusion([[]])
        assert result == []

    def test_disjoint_lists_union(self):
        # Items only in one list should still appear
        ranking = [["a", "b"], ["c", "d"]]
        result = reciprocal_rank_fusion(ranking)
        ids = {r[0] for r in result}
        assert ids == {"a", "b", "c", "d"}

    def test_rank_ordering(self):
        # "a" at rank 1, "z" at rank 100 → a should rank higher
        ranking = [["a"] + [f"x{i}" for i in range(99)] + ["z"]]
        result = reciprocal_rank_fusion(ranking)
        result_ids = [r[0] for r in result]
        assert result_ids.index("a") < result_ids.index("z")

    def test_custom_k(self):
        # Smaller k amplifies rank difference
        ranking = [["a", "b"]]
        result_k1 = dict(reciprocal_rank_fusion(ranking, k=1))
        result_k100 = dict(reciprocal_rank_fusion(ranking, k=100))
        # With k=1: score_a=0.5, score_b=0.333; ratio ≈ 1.5
        # With k=100: score_a=1/101, score_b=1/102; ratio ≈ 1.01
        ratio_k1 = result_k1["a"] / result_k1["b"]
        ratio_k100 = result_k100["a"] / result_k100["b"]
        assert ratio_k1 > ratio_k100

    def test_descending_order(self):
        ranking = [["a", "b", "c", "d"]]
        result = reciprocal_rank_fusion(ranking)
        scores = [s for _, s in result]
        assert scores == sorted(scores, reverse=True)
