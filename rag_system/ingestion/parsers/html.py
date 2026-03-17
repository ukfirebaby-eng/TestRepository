"""HTML parser using BeautifulSoup."""

from __future__ import annotations

from .base import BaseParser, ParsedDocument, ParsedSection


class HTMLParser(BaseParser):
    """Parse HTML content, extracting sections from heading structure."""

    def parse(self, content: bytes, source_uri: str = "") -> ParsedDocument:
        try:
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise ImportError("beautifulsoup4 is required: pip install beautifulsoup4") from e

        soup = BeautifulSoup(content, "html.parser")

        # Remove script and style tags
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else "Untitled"

        sections: list[ParsedSection] = []
        heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}
        breadcrumbs: list[str] = []
        current_heading = ""
        current_level = 1
        current_text_parts: list[str] = []

        def flush_section() -> None:
            if current_text_parts and current_heading:
                text = " ".join(current_text_parts).strip()
                if text:
                    sections.append(ParsedSection(
                        title=current_heading,
                        text=text,
                        breadcrumbs=list(breadcrumbs),
                        level=current_level,
                    ))
            current_text_parts.clear()

        for element in soup.body.descendants if soup.body else []:
            if hasattr(element, "name"):
                if element.name in heading_tags:
                    flush_section()
                    level = int(element.name[1])
                    heading_text = element.get_text(strip=True)
                    current_heading = heading_text
                    current_level = level
                    # Update breadcrumbs
                    breadcrumbs = breadcrumbs[: level - 1] + [heading_text]
                elif element.name in {"p", "li", "td", "th", "blockquote"}:
                    text = element.get_text(" ", strip=True)
                    if text:
                        current_text_parts.append(text)

        flush_section()

        # Fallback: no structured content found
        if not sections:
            raw = soup.get_text(" ", strip=True)
            sections = [ParsedSection(title=title, text=raw, level=1)]

        raw_text = soup.get_text(" ", strip=True)
        return ParsedDocument(
            title=title,
            sections=sections,
            raw_text=raw_text,
            metadata={"source_uri": source_uri},
        )
