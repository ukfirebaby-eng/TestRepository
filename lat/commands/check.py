"""
lat check — enforce referential consistency of the knowledge graph.
"""

from pathlib import Path

from ..graph import KnowledgeGraph
from ..parser import is_file_link, parse_file_link


def check(root: Path) -> tuple:
    """
    Validate the knowledge graph against itself and the source tree.

    Returns (errors, warnings) where each is a list[str].
    Exit code should be 1 if errors is non-empty.
    """
    errors: list = []
    warnings: list = []

    graph = KnowledgeGraph.load(root)

    # Step 1: propagate load errors (duplicate ids, etc.)
    for err in graph.load_errors:
        errors.append(err)

    # Step 2: check wiki links inside lat.md/ sections
    for sec in graph.sections.values():
        for link in sec.wiki_links:
            if is_file_link(link):
                filepath, _anchor = parse_file_link(link)
                target = root / filepath
                if not target.exists():
                    warnings.append(
                        f"[BROKEN FILE LINK] {sec.file}:{sec.lineno}: "
                        f"[[{link}]] — {filepath} does not exist"
                    )
            else:
                if link not in graph.sections:
                    errors.append(
                        f"[BROKEN LINK] {sec.file}:{sec.lineno}: "
                        f"[[{link}]] not found in lat.md/"
                    )

    # Step 3: validate source annotations point to known sections
    for ann in graph.source_annotations:
        for sid in ann.section_ids:
            if sid not in graph.sections:
                errors.append(
                    f"[BROKEN BACKLINK] {ann.source_file}:{ann.lineno}: "
                    f"[[{sid}]] not found in lat.md/"
                )

    # Step 4: require-code-mention enforcement
    # Build a set of section ids mentioned by any source annotation
    mentioned: set = set()
    for ann in graph.source_annotations:
        for sid in ann.section_ids:
            mentioned.add(sid)

    for sec in graph.sections.values():
        if sec.require_code_mention and sec.id not in mentioned:
            errors.append(
                f"[MISSING BACKLINK] {sec.file}:{sec.lineno}: "
                f"section [[{sec.id}]] requires a source mention (require-code-mention: true) "
                f"but no '# @lat: [[{sec.id}]]' found in source files"
            )

    return errors, warnings
