"""
KnowledgeGraph: loads and indexes the lat.md/ knowledge graph and source annotations.
"""

from dataclasses import dataclass, field
from pathlib import Path

from .parser import (
    Section,
    SourceAnnotation,
    parse_sections,
    parse_source_annotations,
)

# Directories to scan for # @lat: source annotations (relative to repo root)
_SOURCE_GLOBS = [
    "scheduler/**/*.py",
    "examples/**/*.py",
]


@dataclass
class KnowledgeGraph:
    sections: dict                  # id -> Section
    backlinks: dict                 # section_id -> list[section_id]  (who links here)
    source_annotations: list        # list[SourceAnnotation]
    load_errors: list               # list[str] — duplicate ids, parse errors

    @classmethod
    def load(cls, root: Path) -> "KnowledgeGraph":
        sections: dict = {}
        backlinks: dict = {}
        source_annotations: list = []
        load_errors: list = []

        # --- Parse lat.md/ files ---
        lat_dir = root / "lat.md"
        if lat_dir.exists():
            for md_file in sorted(lat_dir.rglob("*.md")):
                rel = str(md_file.relative_to(root))
                text = md_file.read_text(encoding="utf-8")
                file_sections, errors = parse_sections(text, rel)
                load_errors.extend(errors)
                for s in file_sections:
                    sections[s.id] = s

        # --- Build backlink index ---
        for sec in sections.values():
            for link in sec.wiki_links:
                # Only section links go into backlinks (not file links)
                from .parser import is_file_link
                if not is_file_link(link):
                    backlinks.setdefault(link, [])
                    backlinks[link].append(sec.id)

        # --- Parse source annotations ---
        for glob_pattern in _SOURCE_GLOBS:
            for src_file in sorted(root.glob(glob_pattern)):
                rel = str(src_file.relative_to(root))
                text = src_file.read_text(encoding="utf-8")
                annotations = parse_source_annotations(text, rel)
                source_annotations.extend(annotations)

        return cls(
            sections=sections,
            backlinks=backlinks,
            source_annotations=source_annotations,
            load_errors=load_errors,
        )
