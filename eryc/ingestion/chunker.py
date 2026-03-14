"""
Hierarchical chunking engine for the ERYC ingestion pipeline.

Phase B-4 of the implementation backlog.

The chunker splits a :class:`ParsedDocument` into retrievable segments
with deterministic IDs.  It respects section boundaries where possible
and only splits sections that exceed the configured token ceiling.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from eryc.ingestion.parsers.base import ParsedDocument, ParsedSection


@dataclass
class RawChunk:
    """
    An uncommitted chunk produced by the chunker.

    ``chunk_id`` is deterministic: SHA-256 of ``version_id + ordinal``.
    """

    chunk_id: str
    version_id: str
    document_id: str
    chunk_ordinal: int
    section_path: str
    token_count: int
    text: str
    text_preview: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def _estimate_tokens(text: str) -> int:
    """
    Estimate the token count of ``text`` without loading a tokeniser.

    Uses the rule-of-thumb that one token ≈ 4 characters of English text.
    """
    return max(1, len(text) // 4)


def _make_chunk_id(version_id: str, ordinal: int) -> str:
    """Return a deterministic chunk ID from the version ID and ordinal."""
    raw = f"{version_id}:{ordinal}"
    return "chunk_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _split_text_on_sentences(text: str, max_tokens: int) -> List[str]:
    """
    Split ``text`` into pieces each ≤ ``max_tokens`` on sentence boundaries.

    Falls back to hard character splitting if no sentence boundaries are found.
    """
    # Simple sentence splitter: split on '. ', '! ', '? ' or newlines.
    sentence_re = re.compile(r"(?<=[.!?])\s+|\n")
    sentences = sentence_re.split(text)

    chunks: List[str] = []
    current_parts: List[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        tok = _estimate_tokens(sentence)
        # If this single unit already exceeds the budget, split it further on words.
        if tok > max_tokens:
            if current_parts:
                chunks.append(" ".join(current_parts))
                current_parts = []
                current_tokens = 0
            words = sentence.split()
            word_buf: List[str] = []
            word_tokens = 0
            for word in words:
                wt = _estimate_tokens(word)
                if word_tokens + wt > max_tokens and word_buf:
                    chunks.append(" ".join(word_buf))
                    word_buf = [word]
                    word_tokens = wt
                else:
                    word_buf.append(word)
                    word_tokens += wt
            if word_buf:
                current_parts = word_buf
                current_tokens = word_tokens
        elif current_tokens + tok > max_tokens and current_parts:
            chunks.append(" ".join(current_parts))
            current_parts = [sentence]
            current_tokens = tok
        else:
            current_parts.append(sentence)
            current_tokens += tok

    if current_parts:
        chunks.append(" ".join(current_parts))

    return chunks or [text]


class Chunker:
    """
    Split a parsed document into retrievable chunks.

    Args:
        max_chunk_tokens:   Maximum token budget per chunk.
        overlap_sentences:  Number of sentences to repeat at the start of
                            each new chunk for retrieval context continuity.
    """

    def __init__(
        self,
        max_chunk_tokens: int = 400,
        overlap_sentences: int = 1,
    ) -> None:
        self._max_tokens = max_chunk_tokens
        self._overlap = overlap_sentences

    def chunk_document(
        self,
        parsed: ParsedDocument,
        *,
        version_id: str,
        document_id: str,
    ) -> List[RawChunk]:
        """
        Produce an ordered list of :class:`RawChunk` objects for ``parsed``.

        Each chunk carries:
        - a deterministic ``chunk_id``
        - the ``version_id`` and ``document_id`` it belongs to
        - a sequential ``chunk_ordinal`` (0-based)
        - a 200-character ``text_preview``
        """
        chunks: List[RawChunk] = []
        ordinal = 0

        for section in parsed.sections:
            section_chunks = self._chunk_section(section)
            for text in section_chunks:
                token_count = _estimate_tokens(text)
                preview = text[:200].rstrip()
                chunk_id = _make_chunk_id(version_id, ordinal)
                chunks.append(
                    RawChunk(
                        chunk_id=chunk_id,
                        version_id=version_id,
                        document_id=document_id,
                        chunk_ordinal=ordinal,
                        section_path=section.section_path,
                        token_count=token_count,
                        text=text,
                        text_preview=preview,
                        metadata={
                            "heading": section.heading,
                            "level": section.level,
                            **section.metadata,
                        },
                    )
                )
                ordinal += 1

        return chunks

    def _chunk_section(self, section: ParsedSection) -> List[str]:
        """Split a single section into ≤ max_chunk_tokens pieces."""
        text = section.text.strip()
        if not text:
            return []

        estimated = _estimate_tokens(text)
        if estimated <= self._max_tokens:
            return [text]

        return _split_text_on_sentences(text, self._max_tokens)
