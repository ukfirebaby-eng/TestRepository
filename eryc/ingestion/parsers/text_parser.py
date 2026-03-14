"""
Plain text document parser.

Treats the file as a single section, or optionally splits on blank-line
paragraph boundaries.  Acts as the fallback parser for unsupported formats.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List, Optional

from eryc.ingestion.parsers.base import ParsedDocument, ParsedSection, ParserBase


class PlainTextParser(ParserBase):
    """Parse plain text files into paragraphs or a single section."""

    supported_extensions = [".txt", ".text", ".log", ".csv", ".tsv"]

    def parse(self, path: Path, *, doc_type: Optional[str] = None) -> ParsedDocument:
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        sections = self._split_paragraphs(raw_text)
        content_hash = hashlib.sha256(raw_text.encode()).hexdigest()

        return ParsedDocument(
            source_path=str(path),
            canonical_title=path.stem.replace("_", " ").replace("-", " ").title(),
            sections=sections,
            raw_text=raw_text,
            doc_type=doc_type or "text",
            content_hash=content_hash,
            metadata={"file_size": path.stat().st_size},
        )

    def _split_paragraphs(self, text: str) -> List[ParsedSection]:
        """
        Split on double-newline paragraph boundaries.

        If the text has fewer than two paragraphs, the entire content is
        returned as a single section.
        """
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        if len(paragraphs) <= 1:
            return [
                ParsedSection(
                    section_path="Root",
                    heading="",
                    text=text.strip(),
                    level=0,
                )
            ]

        return [
            ParsedSection(
                section_path=f"Paragraph/{i + 1}",
                heading="",
                text=para,
                level=0,
            )
            for i, para in enumerate(paragraphs)
        ]
