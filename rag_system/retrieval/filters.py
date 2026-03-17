"""Metadata filter construction for retrieval queries."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def build_filters(
    tenant_id: str,
    acl_tags: list[str] | None = None,
    document_types: list[str] | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a unified filter dict for retrieval backends.

    The filter dict is backend-agnostic; each backend translates it
    into its own query syntax (Elasticsearch DSL, in-memory predicates, etc.).
    """
    filters: dict[str, Any] = {"tenant_id": tenant_id}

    if acl_tags:
        filters["acl_tags"] = acl_tags
    if document_types:
        filters["document_type"] = {"$in": document_types}
    if after:
        filters["created_at"] = {**filters.get("created_at", {}), "$gte": after.isoformat()}
    if before:
        filters["created_at"] = {**filters.get("created_at", {}), "$lte": before.isoformat()}
    if extra:
        filters.update(extra)

    return filters


def apply_filters_to_chunk(chunk: Any, filters: dict[str, Any]) -> bool:
    """Return True if a chunk satisfies all filter conditions.

    Used by in-memory backends.
    """
    from rag_system.models import Chunk

    c: Chunk = chunk

    if "tenant_id" in filters and c.tenant_id != filters["tenant_id"]:
        return False

    if "acl_tags" in filters:
        allowed = set(filters["acl_tags"])
        if c.acl_tags and not set(c.acl_tags).intersection(allowed | {"public"}):
            return False

    if "document_type" in filters:
        dt_filter = filters["document_type"]
        if isinstance(dt_filter, dict) and "$in" in dt_filter:
            if c.document_type not in dt_filter["$in"]:
                return False
        elif c.document_type != dt_filter:
            return False

    if "created_at" in filters:
        ct_filter = filters["created_at"]
        created = c.created_at.isoformat()
        if "$gte" in ct_filter and created < ct_filter["$gte"]:
            return False
        if "$lte" in ct_filter and created > ct_filter["$lte"]:
            return False

    return True
