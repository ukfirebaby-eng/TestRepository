"""
lat section — display a specific section from the knowledge graph.
"""

import sys
from pathlib import Path

from ..graph import KnowledgeGraph


def show_section(root: Path, section_id: str) -> None:
    graph = KnowledgeGraph.load(root)
    if section_id not in graph.sections:
        print(f"Error: section [[{section_id}]] not found in lat.md/", file=sys.stderr)
        sys.exit(1)

    sec = graph.sections[section_id]
    print(f"## {sec.title}")
    print(f"<!-- id: {sec.id} -->")
    if sec.require_code_mention:
        print("<!-- require-code-mention: true -->")
    print()
    print(sec.body)

    # Show backlinks if any
    backlinks = graph.backlinks.get(section_id, [])
    if backlinks:
        print()
        print(f"Linked from: {', '.join(f'[[{b}]]' for b in backlinks)}")
