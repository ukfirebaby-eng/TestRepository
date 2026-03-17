"""Test configuration and shared fixtures for the RAG system tests."""

import pytest


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset rate limit buckets before each test to prevent cross-test interference."""
    from rag_system.api.middleware.rate_limit import reset_buckets
    reset_buckets()
    yield
    reset_buckets()
