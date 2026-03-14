"""
PDF document parser (requires pypdf).

Extracts text page-by-page.  Each page becomes a section since PDF
metadata provides no reliable heading structure without additional
layout analysis.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Optional

from eryc.ingestion.parsers.base import ParsedDocument, ParsedSection, ParserBase


class PdfParser(ParserBase):
    """Parse PDF files using pypdf."""

    supported_extensions = [".pdf"]

    def parse(self, path: Path, *, doc_type: Optional[str] = None) -> ParsedDocument:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        sections: List[ParsedSection] = []
        raw_parts: List[str] = []

        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                sections.append(
                    ParsedSection(
                        section_path=f"Page/{i + 1}",
                        heading=f"Page {i + 1}",
                        text=text,
                        level=1,
                        metadata={"page_number": i + 1},
                    )
                )
                raw_parts.append(text)

        raw_text = "\n\n".join(raw_parts)
        content_hash = hashlib.sha256(raw_text.encode()).hexdigest()

        # Use document info title if available.
        title = path.stem
        if reader.metadata and reader.metadata.title:
            title = reader.metadata.title

        return ParsedDocument(
            source_path=str(path),
            canonical_title=title,
            sections=sections or [
                ParsedSection(section_path="Root", heading="", text=raw_text, level=0)
            ],
            raw_text=raw_text,
            doc_type=doc_type or "pdf",
            content_hash=content_hash,
            metadata={
                "file_size": path.stat().st_size,
                "page_count": len(reader.pages),
            },
        )
