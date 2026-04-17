"""
Markdown section and source annotation parsing primitives.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

WIKI_LINK_RE = re.compile(r'\[\[([^\]]+)\]\]')
HEADING_RE   = re.compile(r'^(#{2,3})\s+(.+)$')
ID_RE        = re.compile(r'<!--\s*id:\s*([a-z0-9_-]+)\s*-->')
REQUIRE_RE   = re.compile(r'<!--\s*require-code-mention:\s*true\s*-->')
ANNOT_RE     = re.compile(r'#\s*@lat:\s*(.+)$')


@dataclass
class Section:
    id: str
    title: str
    file: str
    lineno: int
    require_code_mention: bool
    body: str
    wiki_links: list


@dataclass
class SourceAnnotation:
    source_file: str
    lineno: int
    section_ids: list


def parse_sections(text: str, filepath: str) -> tuple:
    """
    Parse markdown text and return (sections, errors).

    sections: list[Section]
    errors: list[str] — duplicate-id or malformed-section messages
    """
    lines = text.splitlines()
    sections = []
    errors = []
    seen_ids = {}

    i = 0
    while i < len(lines):
        m = HEADING_RE.match(lines[i])
        if not m:
            i += 1
            continue

        heading_lineno = i + 1  # 1-based
        title = m.group(2).strip()

        # Peek up to 3 lines ahead for <!-- id: ... -->
        section_id = None
        require_code_mention = False
        peek_end = min(i + 4, len(lines))
        id_line_offset = None

        for j in range(i + 1, peek_end):
            id_m = ID_RE.search(lines[j])
            if id_m:
                section_id = id_m.group(1)
                id_line_offset = j
                if j + 1 < len(lines) and REQUIRE_RE.search(lines[j + 1]):
                    require_code_mention = True
                break

        if section_id is None:
            i += 1
            continue

        # Collect body: from the heading line to the next same-or-higher heading
        body_start = i
        body_lines = []
        i = id_line_offset + 1
        if require_code_mention:
            i += 1  # skip require-code-mention line too

        while i < len(lines):
            if HEADING_RE.match(lines[i]):
                break
            body_lines.append(lines[i])
            i += 1

        body = "\n".join(body_lines)
        wiki_links = WIKI_LINK_RE.findall(body)
        # Also include links in the heading line itself
        wiki_links += WIKI_LINK_RE.findall(title)

        if section_id in seen_ids:
            errors.append(
                f"[DUPLICATE ID] {filepath}:{heading_lineno}: id '{section_id}' "
                f"already defined at {seen_ids[section_id]}"
            )
        else:
            seen_ids[section_id] = f"{filepath}:{heading_lineno}"
            sections.append(Section(
                id=section_id,
                title=title,
                file=filepath,
                lineno=heading_lineno,
                require_code_mention=require_code_mention,
                body=body,
                wiki_links=wiki_links,
            ))

    return sections, errors


def parse_source_annotations(text: str, filepath: str) -> list:
    """Parse # @lat: [[...]] comments from source code, return list[SourceAnnotation]."""
    annotations = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = ANNOT_RE.search(line)
        if m:
            ids = WIKI_LINK_RE.findall(m.group(1))
            if ids:
                annotations.append(SourceAnnotation(
                    source_file=filepath,
                    lineno=lineno,
                    section_ids=ids,
                ))
    return annotations


def is_file_link(target: str) -> bool:
    """Return True if a wiki-link target refers to a source file (not a section id)."""
    return "/" in target or target.endswith(".py")


def parse_file_link(target: str) -> tuple:
    """Split a file link into (path, anchor_or_None)."""
    if "#" in target:
        path, anchor = target.split("#", 1)
        return path, anchor
    return target, None
