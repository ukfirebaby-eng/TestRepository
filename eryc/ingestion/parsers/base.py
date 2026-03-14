"""
Abstract base parser and shared data structures for the ingestion pipeline.

Phase B-2 of the implementation backlog.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ParsedSection:
    """
    A logical section within a parsed document.

    ``section_path`` is a '/' delimited breadcrumb, e.g. ``"Introduction/Background"``.
    ``text`` contains the full body text for this section.
    """

    section_path: str
    heading: str
    text: str
    level: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """
    The canonical parsed representation of a source file.

    Produced by a :class:`ParserBase` subclass; consumed by the chunking
    engine and metadata extractor.
    """

    source_path: str
    canonical_title: str
    sections: List[ParsedSection]
    raw_text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    doc_type: Optional[str] = None
    content_hash: str = ""

    @property
    def full_text(self) -> str:
        """Concatenate all section texts into a single string."""
        return "\n\n".join(s.text for s in self.sections) or self.raw_text


class ParserBase(ABC):
    """Base class for all document parsers."""

    #: File extensions this parser handles (lowercase, with leading dot).
    supported_extensions: List[str] = []

    @abstractmethod
    def parse(self, path: Path, *, doc_type: Optional[str] = None) -> ParsedDocument:
        """
        Parse the file at ``path`` and return a :class:`ParsedDocument`.

        Args:
            path:      Absolute path to the source file.
            doc_type:  Optional caller-supplied document type hint.
        """
        ...

    @classmethod
    def can_handle(cls, path: Path) -> bool:
        """Return True if this parser can handle the given file extension."""
        return path.suffix.lower() in cls.supported_extensions


def get_parser(path: Path) -> ParserBase:
    """
    Return the most appropriate parser for the given file path.

    Raises:
        ValueError: If no parser supports the file extension.
    """
    from eryc.ingestion.parsers.markdown import MarkdownParser
    from eryc.ingestion.parsers.text_parser import PlainTextParser

    parsers: List[ParserBase] = [
        MarkdownParser(),
        PlainTextParser(),
    ]

    # Attempt optional heavy-dependency parsers without hard import failures.
    try:
        from eryc.ingestion.parsers.docx_parser import DocxParser  # type: ignore

        parsers.append(DocxParser())
    except ImportError:
        pass

    try:
        from eryc.ingestion.parsers.pdf_parser import PdfParser  # type: ignore

        parsers.append(PdfParser())
    except ImportError:
        pass

    for parser in parsers:
        if parser.can_handle(path):
            return parser

    # Fall back to plain text for unknown extensions.
    return PlainTextParser()
