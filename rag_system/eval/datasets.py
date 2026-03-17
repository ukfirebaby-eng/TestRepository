"""Labeled evaluation datasets for the RAG system."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalQuery:
    query: str
    tenant_id: str
    expected_doc_ids: list[str] = field(default_factory=list)
    query_type: str = "semantic"
    expected_answer_contains: list[str] = field(default_factory=list)


# Default built-in eval dataset (used when no external dataset is configured)
DEFAULT_EVAL_QUERIES: list[EvalQuery] = [
    EvalQuery(
        query="What is Reciprocal Rank Fusion?",
        tenant_id="eval",
        query_type="semantic",
        expected_answer_contains=["rank", "fusion", "retrieval"],
    ),
    EvalQuery(
        query="How does BM25 scoring work?",
        tenant_id="eval",
        query_type="semantic",
        expected_answer_contains=["term frequency", "BM25"],
    ),
    EvalQuery(
        query="What are the advantages of hybrid search?",
        tenant_id="eval",
        query_type="semantic",
        expected_answer_contains=["hybrid"],
    ),
    EvalQuery(
        query="latest update",
        tenant_id="eval",
        query_type="temporal",
        expected_answer_contains=[],
    ),
    EvalQuery(
        query="compare BM25 versus dense retrieval",
        tenant_id="eval",
        query_type="multi_hop",
        expected_answer_contains=[],
    ),
]


def load_dataset(name: str = "default") -> list[EvalQuery]:
    if name == "default":
        return DEFAULT_EVAL_QUERIES
    raise ValueError(f"Unknown eval dataset: {name}")
