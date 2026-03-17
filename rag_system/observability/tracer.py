"""OpenTelemetry tracer setup for the RAG system."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NoOpTracer:
    """No-op tracer for environments without OpenTelemetry configured."""

    def record(self, data: dict[str, Any]) -> None:
        pass

    def start_span(self, name: str) -> "NoOpSpan":
        return NoOpSpan(name)


class NoOpSpan:
    def __init__(self, name: str) -> None:
        self.name = name

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def record_exception(self, exc: Exception) -> None:
        pass


def get_tracer(service_name: str = "rag-system") -> Any:
    """Get an OpenTelemetry tracer, or a no-op tracer if OTEL is not configured."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider()
        trace.set_tracer_provider(provider)
        return trace.get_tracer(service_name)
    except (ImportError, Exception) as e:
        logger.debug("OpenTelemetry not available, using no-op tracer: %s", e)
        return NoOpTracer()
