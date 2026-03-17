"""Hierarchical text chunker.

Splits document sections into chunks of approximately `chunk_size` tokens
with `overlap` token overlap between consecutive chunks.

Token counting: uses tiktoken if available, otherwise falls back to
simple word-based estimation (1 token ≈ 0.75 words).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from rag_system.ingestion.parsers.base import ParsedDocument, ParsedSection
from rag_system.models import Chunk


def _count_tokens_approx(text: str) -> int:
    """Estimate token count without requiring tiktoken."""
    return max(1, int(len(text.split()) / 0.75))


def _get_tokenizer():
    try:
        import tiktoken
        return tiktoken.get_encoding("cl100k_base")
    except (ImportError, Exception):
        return None


def _count_tokens(text: str, enc) -> int:
    if enc is None:
        return _count_tokens_approx(text)
    return len(enc.encode(text))


def _split_sentences(text: str) -> list[str]:
    """Split text into sentence-like units."""
    # Split on sentence boundaries, keeping the delimiter
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


class Chunker:
    """Hierarchical chunker: respects section boundaries, then splits on tokens."""

    def __init__(
        self,
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._enc = _get_tokenizer()

    def chunk_document(
        self,
        doc: ParsedDocument,
        doc_id: str,
        tenant_id: str,
        acl_tags: list[str] | None = None,
        document_type: str = "text",
        source_uri: str = "",
        version: str = "1",
        extra_metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        """Chunk a parsed document into Chunk objects."""
        chunks: list[Chunk] = []
        now = datetime.utcnow()

        for section in doc.sections:
            section_chunks = self._chunk_section(
                section=section,
                doc_id=doc_id,
                tenant_id=tenant_id,
                acl_tags=acl_tags or [],
                document_type=document_type,
                source_uri=source_uri,
                version=version,
                now=now,
                extra_metadata=extra_metadata or {},
            )
            chunks.extend(section_chunks)

        return chunks

    def _chunk_section(
        self,
        section: ParsedSection,
        doc_id: str,
        tenant_id: str,
        acl_tags: list[str],
        document_type: str,
        source_uri: str,
        version: str,
        now: datetime,
        extra_metadata: dict[str, Any],
    ) -> list[Chunk]:
        text = section.text.strip()
        if not text:
            return []

        token_count = _count_tokens(text, self._enc)
        if token_count <= self.chunk_size:
            # Section fits in one chunk
            return [self._make_chunk(
                text=text,
                section=section,
                doc_id=doc_id,
                tenant_id=tenant_id,
                acl_tags=acl_tags,
                document_type=document_type,
                source_uri=source_uri,
                version=version,
                now=now,
                extra_metadata=extra_metadata,
            )]

        # Split the section into overlapping windows
        sentences = _split_sentences(text)
        chunks: list[Chunk] = []
        current_sents: list[str] = []
        current_tokens = 0

        def flush(sents: list[str]) -> Chunk:
            chunk_text = " ".join(sents)
            return self._make_chunk(
                text=chunk_text,
                section=section,
                doc_id=doc_id,
                tenant_id=tenant_id,
                acl_tags=acl_tags,
                document_type=document_type,
                source_uri=source_uri,
                version=version,
                now=now,
                extra_metadata=extra_metadata,
            )

        for sent in sentences:
            sent_tokens = _count_tokens(sent, self._enc)
            if current_tokens + sent_tokens > self.chunk_size and current_sents:
                chunks.append(flush(current_sents))
                # Keep overlap: backtrack sentences until within overlap budget
                overlap_sents: list[str] = []
                overlap_tokens = 0
                for s in reversed(current_sents):
                    st = _count_tokens(s, self._enc)
                    if overlap_tokens + st > self.overlap:
                        break
                    overlap_sents.insert(0, s)
                    overlap_tokens += st
                current_sents = overlap_sents
                current_tokens = overlap_tokens

            current_sents.append(sent)
            current_tokens += sent_tokens

        if current_sents:
            chunks.append(flush(current_sents))

        return chunks

    def _make_chunk(
        self,
        text: str,
        section: ParsedSection,
        doc_id: str,
        tenant_id: str,
        acl_tags: list[str],
        document_type: str,
        source_uri: str,
        version: str,
        now: datetime,
        extra_metadata: dict[str, Any],
    ) -> Chunk:
        return Chunk(
            chunk_id=str(uuid.uuid4()),
            doc_id=doc_id,
            tenant_id=tenant_id,
            section_title=section.title,
            breadcrumbs=list(section.breadcrumbs),
            source_uri=source_uri,
            version=version,
            created_at=now,
            updated_at=now,
            acl_tags=list(acl_tags),
            document_type=document_type,
            semantic_text=text,
            raw_text=text,
            keyword_fields={
                "section_title": section.title,
                "document_type": document_type,
                **extra_metadata,
            },
        )
