"""Prometheus metrics for the RAG system."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NoOpMetrics:
    """No-op metrics when prometheus_client is not available."""

    def observe_latency(self, stage: str, latency_ms: float) -> None:
        pass

    def increment_counter(self, name: str, labels: dict | None = None) -> None:
        pass

    def record_gauge(self, name: str, value: float, labels: dict | None = None) -> None:
        pass


class PrometheusMetrics:
    """Prometheus metrics collector."""

    def __init__(self) -> None:
        try:
            from prometheus_client import Counter, Gauge, Histogram
            self._latency = Histogram(
                "rag_stage_latency_ms",
                "Latency per RAG pipeline stage in milliseconds",
                ["stage"],
                buckets=[10, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
            )
            self._queries = Counter(
                "rag_queries_total",
                "Total RAG queries",
                ["tenant_id", "query_type"],
            )
            self._retrieval_loops = Counter(
                "rag_retry_loops_total",
                "Number of retrieval retry loops",
            )
            self._citations = Histogram(
                "rag_citation_count",
                "Number of citations per answer",
                buckets=[0, 1, 2, 3, 5, 8, 12],
            )
            self._available = True
        except ImportError:
            logger.debug("prometheus_client not available; metrics disabled")
            self._available = False

    def observe_latency(self, stage: str, latency_ms: float) -> None:
        if self._available:
            self._latency.labels(stage=stage).observe(latency_ms)

    def increment_counter(self, name: str, labels: dict | None = None) -> None:
        pass  # simplified

    def record_gauge(self, name: str, value: float, labels: dict | None = None) -> None:
        pass  # simplified


def get_metrics() -> Any:
    """Get metrics collector."""
    try:
        import prometheus_client  # noqa: F401
        return PrometheusMetrics()
    except ImportError:
        return NoOpMetrics()
