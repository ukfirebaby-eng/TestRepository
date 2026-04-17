"""Tests for lat/commands/init.py and lat/commands/section.py"""

import sys
import os
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lat.commands.init import init
from lat.commands.section import show_section


def _tmp_root() -> Path:
    return Path(tempfile.mkdtemp())


class TestInit(unittest.TestCase):

    def test_creates_lat_dir(self):
        root = _tmp_root()
        init(root)
        self.assertTrue((root / "lat.md").is_dir())

    def test_creates_all_files(self):
        root = _tmp_root()
        init(root)
        for name in ("architecture.md", "concepts.md", "api.md", "decisions.md"):
            self.assertTrue((root / "lat.md" / name).exists(), f"Missing {name}")

    def test_creates_agents_md(self):
        root = _tmp_root()
        init(root)
        self.assertTrue((root / "AGENTS.md").exists())

    def test_agents_md_content(self):
        root = _tmp_root()
        init(root)
        content = (root / "AGENTS.md").read_text()
        self.assertIn("lat check", content)
        self.assertIn("lat search", content)

    def test_idempotent_with_force(self):
        root = _tmp_root()
        init(root)
        # Second call with force should overwrite without error
        init(root, force=True)
        self.assertTrue((root / "lat.md" / "architecture.md").exists())

    def test_fails_without_force_if_exists(self):
        root = _tmp_root()
        init(root)
        with self.assertRaises(SystemExit) as ctx:
            init(root, force=False)
        self.assertEqual(ctx.exception.code, 1)

    def test_files_contain_section_ids(self):
        root = _tmp_root()
        init(root)
        arch = (root / "lat.md" / "architecture.md").read_text()
        self.assertIn("<!-- id: scheduler-engine -->", arch)
        self.assertIn("<!-- id: scheduler-loop -->", arch)


class TestShowSection(unittest.TestCase):

    def _make_repo_with_section(self, section_id="test-sec"):
        root = _tmp_root()
        (root / "lat.md").mkdir()
        (root / "lat.md" / "test.md").write_text(
            f"## Test Section\n<!-- id: {section_id} -->\n\nSection body text.\n",
            encoding="utf-8",
        )
        return root

    def test_prints_section(self):
        root = self._make_repo_with_section("test-sec")
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            show_section(root, "test-sec")
        output = buf.getvalue()
        self.assertIn("Test Section", output)
        self.assertIn("Section body text", output)

    def test_exits_on_missing_section(self):
        root = self._make_repo_with_section("test-sec")
        with self.assertRaises(SystemExit) as ctx:
            show_section(root, "nonexistent")
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
