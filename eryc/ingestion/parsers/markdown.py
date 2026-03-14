"""
Markdown document parser.

Uses ``markdown-it-py`` to walk the token stream and extract sections
keyed by heading hierarchy.  Falls back to a simple heading-split
heuristic if the library is not available.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List, Optional

from eryc.ingestion.parsers.base import ParsedDocument, ParsedSection, ParserBase


class MarkdownParser(ParserBase):
    """Parse Markdown files into hierarchical sections."""

    supported_extensions = [".md", ".markdown"]

    def parse(self, path: Path, *, doc_type: Optional[str] = None) -> ParsedDocument:
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        sections = self._extract_sections(raw_text)

        # Derive title from the first H1 or the file stem.
        title = path.stem
        for section in sections:
            if section.level == 1:
                title = section.heading
                break

        content_hash = hashlib.sha256(raw_text.encode()).hexdigest()

        return ParsedDocument(
            source_path=str(path),
            canonical_title=title,
            sections=sections,
            raw_text=raw_text,
            doc_type=doc_type or "markdown",
            content_hash=content_hash,
            metadata={"file_size": path.stat().st_size},
        )

    def _extract_sections(self, text: str) -> List[ParsedSection]:
        """
        Split the document into sections on heading boundaries.

        Returns a flat list of :class:`ParsedSection` objects.  If no
        headings are found the entire text is treated as a single section.
        """
        try:
            return self._extract_with_markdown_it(text)
        except Exception:
            return self._extract_with_regex(text)

    def _extract_with_markdown_it(self, text: str) -> List[ParsedSection]:
        from markdown_it import MarkdownIt  # type: ignore

        md = MarkdownIt()
        tokens = md.parse(text)

        sections: List[ParsedSection] = []
        heading_stack: List[tuple[int, str]] = []  # (level, heading_text)
        current_body_lines: List[str] = []
        current_heading = ""
        current_level = 0

        def _flush() -> None:
            if not current_heading and not current_body_lines:
                return
            path = "/".join(h for _, h in heading_stack)
            sections.append(
                ParsedSection(
                    section_path=path or "Root",
                    heading=current_heading,
                    text="\n".join(current_body_lines).strip(),
                    level=current_level,
                )
            )

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.type == "heading_open":
                _flush()
                level = int(tok.tag[1])  # h1 → 1, h2 → 2, …
                heading_text = ""
                if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                    heading_text = tokens[i + 1].content
                # Maintain heading stack at this level.
                heading_stack = [(l, h) for l, h in heading_stack if l < level]
                heading_stack.append((level, heading_text))
                current_heading = heading_text
                current_level = level
                current_body_lines = []
            elif tok.type == "inline":
                parent = tokens[i - 1].type if i > 0 else ""
                if parent != "heading_open":
                    current_body_lines.append(tok.content)
            i += 1

        _flush()
        return sections or [
            ParsedSection(section_path="Root", heading="", text=text, level=0)
        ]

    def _extract_with_regex(self, text: str) -> List[ParsedSection]:
        """Simple regex-based fallback when markdown-it-py is unavailable."""
        heading_re = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(heading_re.finditer(text))

        if not matches:
            return [ParsedSection(section_path="Root", heading="", text=text, level=0)]

        sections: List[ParsedSection] = []
        prev_end = 0
        path_stack: List[tuple[int, str]] = []

        for i, match in enumerate(matches):
            level = len(match.group(1))
            heading = match.group(2).strip()
            body_start = match.end()
            body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[body_start:body_end].strip()

            path_stack = [(l, h) for l, h in path_stack if l < level]
            path_stack.append((level, heading))
            section_path = "/".join(h for _, h in path_stack)

            sections.append(
                ParsedSection(
                    section_path=section_path,
                    heading=heading,
                    text=body,
                    level=level,
                )
            )
            prev_end = body_end

        return sections
