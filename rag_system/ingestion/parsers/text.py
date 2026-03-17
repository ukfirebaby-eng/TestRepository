"""Plain text parser."""

from __future__ import annotations

import re

from .base import BaseParser, ParsedDocument, ParsedSection


class TextParser(BaseParser):
    """Parse plain text, splitting on blank lines as paragraph boundaries."""

    def parse(self, content: bytes, source_uri: str = "") -> ParsedDocument:
        text = content.decode("utf-8", errors="replace")
        # Split on double newlines to get paragraphs
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

        sections: list[ParsedSection] = []
        for i, para in enumerate(paragraphs):
            # Use first line as a rough title if it's short
            lines = para.splitlines()
            title = lines[0][:80] if lines else f"Paragraph {i+1}"
            sections.append(ParsedSection(title=title, text=para, level=1))

        return ParsedDocument(
            title=sections[0].title if sections else "Untitled",
            sections=sections,
            raw_text=text,
            metadata={"source_uri": source_uri},
        )
