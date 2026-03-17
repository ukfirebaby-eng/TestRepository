"""In-memory token bucket rate limiter (per tenant)."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status

from rag_system.config import get_settings


class _Bucket:
    """Token bucket for a single tenant."""

    def __init__(self, rate: float, capacity: float) -> None:
        self.rate = rate        # tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self._lock = Lock()

    def consume(self, n: float = 1.0) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_refill = now
            if self.tokens >= n:
                self.tokens -= n
                return True
            return False


_buckets: dict[str, _Bucket] = defaultdict(lambda: _Bucket(
    rate=get_settings().rate_limit_rpm / 60,  # convert RPM to RPS
    capacity=get_settings().rate_limit_rpm / 60 * 10,  # 10-second burst
))
_buckets_lock = Lock()


def reset_buckets() -> None:
    """Clear all rate limit buckets. Intended for use in tests."""
    with _buckets_lock:
        _buckets.clear()


async def rate_limit_middleware(request: Request, call_next):
    """Rate limit requests per tenant (identified via X-Tenant-Id header or query param)."""
    tenant_id = (
        request.headers.get("X-Tenant-Id")
        or request.query_params.get("tenant_id")
        or "anonymous"
    )

    with _buckets_lock:
        bucket = _buckets[tenant_id]

    if not bucket.consume():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for tenant {tenant_id}",
        )

    return await call_next(request)
