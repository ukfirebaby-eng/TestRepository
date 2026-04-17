"""
lat CLI entry point.

Usage:
    python -m lat <command> [args]

Commands:
    init [--force]       Create lat.md/ knowledge graph and AGENTS.md
    check                Validate all cross-references; exit 1 on errors
    search <query>       Search the knowledge graph
    section <id>         Display a specific section
"""

import sys
from pathlib import Path


def _print_help() -> None:
    print(__doc__.strip())


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        _print_help()
        return

    cmd = args[0]
    root = Path.cwd()

    if cmd == "init":
        force = "--force" in args
        from lat.commands.init import init
        init(root, force=force)

    elif cmd == "check":
        from lat.commands.check import check
        errors, warnings = check(root)
        for w in warnings:
            print(f"WARNING {w}", file=sys.stderr)
        for e in errors:
            print(f"ERROR   {e}", file=sys.stderr)
        if errors:
            sys.exit(1)
        if not warnings:
            print("lat check passed — no issues found.")

    elif cmd == "search":
        if len(args) < 2:
            print("Usage: lat search <query>", file=sys.stderr)
            sys.exit(1)
        query = " ".join(args[1:])
        from lat.commands.search import search, print_results
        hits = search(root, query)
        print_results(hits)

    elif cmd == "section":
        if len(args) < 2:
            print("Usage: lat section <id>", file=sys.stderr)
            sys.exit(1)
        from lat.commands.section import show_section
        show_section(root, args[1])

    else:
        print(f"Unknown command: {cmd!r}. Run 'python -m lat --help' for usage.",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
