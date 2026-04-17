"""
lat init — create lat.md/ and AGENTS.md, set up the knowledge graph.
"""

import sys
from pathlib import Path

from ..templates.content import (
    AGENTS_MD,
    API_MD,
    ARCHITECTURE_MD,
    CONCEPTS_MD,
    DECISIONS_MD,
)

_LAT_FILES = {
    "architecture.md": ARCHITECTURE_MD,
    "concepts.md":     CONCEPTS_MD,
    "api.md":          API_MD,
    "decisions.md":    DECISIONS_MD,
}


def init(root: Path, *, force: bool = False) -> None:
    lat_dir = root / "lat.md"

    if lat_dir.exists() and not force:
        print(
            f"Error: {lat_dir} already exists. "
            "Use --force to overwrite.",
            file=sys.stderr,
        )
        sys.exit(1)

    lat_dir.mkdir(exist_ok=True)

    for filename, content in _LAT_FILES.items():
        path = lat_dir / filename
        path.write_text(content, encoding="utf-8")
        print(f"  wrote {path.relative_to(root)}")

    agents_md = root / "AGENTS.md"
    agents_md.write_text(AGENTS_MD, encoding="utf-8")
    print(f"  wrote AGENTS.md")

    print()
    print("Knowledge graph initialised. Next steps:")
    print("  python -m lat check           # verify consistency")
    print("  python -m lat search <term>   # explore the graph")
    print()
    print("To enforce consistency on every commit, add to .git/hooks/pre-commit:")
    print("  #!/bin/sh")
    print("  python -m lat check")
