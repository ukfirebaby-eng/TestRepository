"""Evaluation harness: runs queries against the RAG system and computes metrics."""

from __future__ import annotations

import time
from typing import Any

from rag_system.agent.state import initial_state
from rag_system.eval.datasets import EvalQuery, load_dataset
from rag_system.eval.metrics import citation_precision, faithfulness_score, ndcg_at_k
from rag_system.models import EvalRequest, EvalResult


class EvalHarness:
    """Runs a labeled eval dataset against the compiled RAG graph."""

    def __init__(self, graph) -> None:
        self.graph = graph

    def run(self, req: EvalRequest) -> EvalResult:
        queries = load_dataset(req.dataset_name)

        if req.max_queries is not None:
            queries = queries[: req.max_queries]

        results: list[dict[str, Any]] = []

        for eq in queries:
            t0 = time.time()
            state = initial_state(
                query=eq.query,
                tenant_id=req.tenant_id,
                max_steps=2,
            )
            result = self.graph.invoke(state)
            latency_ms = (time.time() - t0) * 1000

            answer = result.get("validated_answer", "")
            citations = result.get("citations", [])
            cited_ids = [c.chunk_id for c in citations]
            retrieved_doc_ids = [c.doc_id for c in result.get("reranked_chunks", [])]

            # Compute per-query metrics
            ndcg = ndcg_at_k(
                retrieved_doc_ids,
                eq.expected_doc_ids,
                k=10,
            ) if eq.expected_doc_ids else 0.0

            cp = citation_precision(
                cited_ids,
                eq.expected_doc_ids,  # using doc_ids as proxy for chunk relevance
            )

            faith = faithfulness_score(
                answer,
                [c.semantic_text for c in result.get("reranked_chunks", [])],
            )

            results.append({
                "query": eq.query,
                "ndcg": ndcg,
                "citation_precision": cp,
                "faithfulness": faith,
                "latency_ms": latency_ms,
                "used_retry_loop": result.get("used_retry_loop", False),
            })

        n = len(results)
        if n == 0:
            return EvalResult(
                dataset_name=req.dataset_name,
                num_queries=0,
                ndcg_at_10=0.0,
                citation_precision=0.0,
                faithfulness=0.0,
                avg_latency_ms=0.0,
                loop_rate=0.0,
            )

        return EvalResult(
            dataset_name=req.dataset_name,
            num_queries=n,
            ndcg_at_10=sum(r["ndcg"] for r in results) / n,
            citation_precision=sum(r["citation_precision"] for r in results) / n,
            faithfulness=sum(r["faithfulness"] for r in results) / n,
            avg_latency_ms=sum(r["latency_ms"] for r in results) / n,
            loop_rate=sum(1 for r in results if r["used_retry_loop"]) / n,
        )
