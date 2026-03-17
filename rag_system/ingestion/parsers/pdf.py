"""PDF parser using pypdf."""

from __future__ import annotations

from .base import BaseParser, ParsedDocument, ParsedSection


class PDFParser(BaseParser):
    """Parse PDF content, extracting text page by page."""

    def parse(self, content: bytes, source_uri: str = "") -> ParsedDocument:
        try:
            import io
            from pypdf import PdfReader
        except ImportError as e:
            raise ImportError("pypdf is required: pip install pypdf") from e

        reader = PdfReader(io.BytesIO(content))
        sections: list[ParsedSection] = []
        all_text_parts: list[str] = []

        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                all_text_parts.append(text)
                sections.append(ParsedSection(
                    title=f"Page {page_num}",
                    text=text,
                    breadcrumbs=[f"Page {page_num}"],
                    level=1,
                ))

        raw_text = "\n\n".join(all_text_parts)

        # Try to get title from metadata
        metadata = reader.metadata or {}
        title = getattr(metadata, "title", None) or source_uri or "PDF Document"

        return ParsedDocument(
            title=str(title),
            sections=sections,
            raw_text=raw_text,
            metadata={"source_uri": source_uri, "page_count": len(reader.pages)},
        )
