"""Metadata extraction and ACL tagging for ingested documents."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


def extract_metadata(
    content: bytes,
    source_uri: str = "",
    document_type: str = "text",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract metadata from raw content and source URI."""
    meta: dict[str, Any] = {}

    if source_uri:
        meta["source_uri"] = source_uri
        parsed = urlparse(source_uri)
        if parsed.scheme in ("http", "https"):
            meta["domain"] = parsed.netloc
        if parsed.path:
            meta["path"] = parsed.path
            ext = parsed.path.rsplit(".", 1)[-1].lower()
            if ext in ("pdf", "html", "htm", "txt", "md"):
                meta["file_extension"] = ext

    meta["document_type"] = document_type
    meta["content_length_bytes"] = len(content)

    if extra:
        meta.update(extra)

    return meta


def classify_document_type(source_uri: str, content: bytes) -> str:
    """Infer document type from URI and content sniffing."""
    if source_uri:
        lower = source_uri.lower()
        if lower.endswith(".pdf"):
            return "pdf"
        if lower.endswith((".html", ".htm")):
            return "html"
        if lower.endswith((".md", ".markdown")):
            return "markdown"
        if lower.endswith(".txt"):
            return "text"

    # Content sniffing
    if content.startswith(b"%PDF"):
        return "pdf"
    if b"<html" in content[:1024].lower() or b"<!doctype" in content[:256].lower():
        return "html"

    return "text"


def compute_acl_tags(
    tenant_id: str,
    metadata: dict[str, Any],
    explicit_tags: list[str] | None = None,
) -> list[str]:
    """Compute ACL tags for a document.

    By default, all documents are tagged with 'public' within their tenant.
    Explicit tags override this behavior.
    """
    tags = [f"tenant:{tenant_id}"]

    if explicit_tags:
        tags.extend(explicit_tags)
    else:
        tags.append("public")

    # Tag based on document type if available
    dt = metadata.get("document_type", "")
    if dt:
        tags.append(f"type:{dt}")

    return list(set(tags))
