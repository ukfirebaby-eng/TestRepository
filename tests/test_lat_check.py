"""Tests for lat/commands/check.py"""

import sys
import os
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lat.commands.check import check


def _make_repo(files: dict) -> Path:
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


class TestCheck(unittest.TestCase):

    def test_clean_graph(self):
        root = _make_repo({
            "lat.md/a.md": (
                "## Engine\n<!-- id: engine -->\n<!-- require-code-mention: true -->\n\nBody.\n"
            ),
            "scheduler/foo.py": "class Foo:  # @lat: [[engine]]\n    pass\n",
        })
        errors, warnings = check(root)
        self.assertEqual(errors, [])

    def test_broken_section_link(self):
        root = _make_repo({
            "lat.md/a.md": "## Engine\n<!-- id: engine -->\n\nLinks [[missing-section]].\n",
        })
        errors, warnings = check(root)
        self.assertTrue(any("BROKEN LINK" in e and "missing-section" in e for e in errors))

    def test_broken_file_link_is_warning(self):
        root = _make_repo({
            "lat.md/a.md": "## Engine\n<!-- id: engine -->\n\nSee [[scheduler/nonexistent.py#Foo]].\n",
        })
        errors, warnings = check(root)
        self.assertTrue(any("BROKEN FILE LINK" in w for w in warnings))
        self.assertEqual(errors, [])

    def test_broken_source_annotation(self):
        root = _make_repo({
            "lat.md/a.md": "## Engine\n<!-- id: engine -->\n\nBody.\n",
            "scheduler/foo.py": "class Foo:  # @lat: [[missing-id]]\n    pass\n",
        })
        errors, warnings = check(root)
        self.assertTrue(any("BROKEN BACKLINK" in e and "missing-id" in e for e in errors))

    def test_missing_require_code_mention(self):
        root = _make_repo({
            "lat.md/a.md": (
                "## Engine\n<!-- id: engine -->\n<!-- require-code-mention: true -->\n\nBody.\n"
            ),
        })
        errors, warnings = check(root)
        self.assertTrue(any("MISSING BACKLINK" in e and "engine" in e for e in errors))

    def test_require_code_mention_satisfied(self):
        root = _make_repo({
            "lat.md/a.md": (
                "## Engine\n<!-- id: engine -->\n<!-- require-code-mention: true -->\n\nBody.\n"
            ),
            "scheduler/foo.py": "class Foo:  # @lat: [[engine]]\n    pass\n",
        })
        errors, warnings = check(root)
        missing = [e for e in errors if "MISSING BACKLINK" in e]
        self.assertEqual(missing, [])

    def test_duplicate_id_is_error(self):
        root = _make_repo({
            "lat.md/a.md": (
                "## A\n<!-- id: dup -->\n\nBody.\n\n"
                "## B\n<!-- id: dup -->\n\nBody.\n"
            ),
        })
        errors, warnings = check(root)
        self.assertTrue(any("DUPLICATE ID" in e for e in errors))

    def test_valid_self_link_within_graph(self):
        root = _make_repo({
            "lat.md/a.md": (
                "## A\n<!-- id: section-a -->\n\nLinks [[section-b]].\n\n"
                "## B\n<!-- id: section-b -->\n\nLinks [[section-a]].\n"
            ),
        })
        errors, warnings = check(root)
        link_errors = [e for e in errors if "BROKEN LINK" in e]
        self.assertEqual(link_errors, [])


if __name__ == "__main__":
    unittest.main()
