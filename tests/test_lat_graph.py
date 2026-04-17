"""Tests for lat/graph.py"""

import sys
import os
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lat.graph import KnowledgeGraph


def _make_repo(files: dict) -> Path:
    """Create a temporary directory tree from a {rel_path: content} dict."""
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


class TestKnowledgeGraphLoad(unittest.TestCase):

    def test_loads_sections(self):
        root = _make_repo({
            "lat.md/arch.md": "## Engine\n<!-- id: engine -->\n\nBody.\n",
        })
        g = KnowledgeGraph.load(root)
        self.assertIn("engine", g.sections)
        self.assertEqual(g.sections["engine"].title, "Engine")

    def test_multiple_files(self):
        root = _make_repo({
            "lat.md/a.md": "## A\n<!-- id: section-a -->\n\nLinks [[section-b]].\n",
            "lat.md/b.md": "## B\n<!-- id: section-b -->\n\nBody.\n",
        })
        g = KnowledgeGraph.load(root)
        self.assertIn("section-a", g.sections)
        self.assertIn("section-b", g.sections)

    def test_backlinks_built(self):
        root = _make_repo({
            "lat.md/a.md": "## A\n<!-- id: section-a -->\n\nLinks [[section-b]].\n",
            "lat.md/b.md": "## B\n<!-- id: section-b -->\n\nBody.\n",
        })
        g = KnowledgeGraph.load(root)
        self.assertIn("section-a", g.backlinks.get("section-b", []))

    def test_source_annotations_loaded(self):
        root = _make_repo({
            "lat.md/a.md": "## A\n<!-- id: section-a -->\n\nBody.\n",
            "scheduler/foo.py": "class Foo:  # @lat: [[section-a]]\n    pass\n",
        })
        g = KnowledgeGraph.load(root)
        self.assertEqual(len(g.source_annotations), 1)
        self.assertEqual(g.source_annotations[0].section_ids, ["section-a"])

    def test_duplicate_ids_reported(self):
        root = _make_repo({
            "lat.md/a.md": (
                "## A\n<!-- id: dup -->\n\nBody.\n\n"
                "## B\n<!-- id: dup -->\n\nBody.\n"
            ),
        })
        g = KnowledgeGraph.load(root)
        self.assertEqual(len(g.load_errors), 1)
        self.assertIn("DUPLICATE ID", g.load_errors[0])

    def test_empty_lat_dir(self):
        root = _make_repo({})
        g = KnowledgeGraph.load(root)
        self.assertEqual(g.sections, {})
        self.assertEqual(g.source_annotations, [])

    def test_no_lat_dir(self):
        root = _make_repo({})
        g = KnowledgeGraph.load(root)
        self.assertEqual(g.sections, {})


if __name__ == "__main__":
    unittest.main()
