"""Tests for lat/commands/search.py"""

import sys
import os
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lat.commands.search import search, _score, _snippet
from lat.parser import Section


def _make_repo(files: dict) -> Path:
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _section(id, title, body="", links=None):
    return Section(
        id=id, title=title, file="test.md", lineno=1,
        require_code_mention=False,
        body=body, wiki_links=links or [],
    )


class TestScore(unittest.TestCase):

    def test_id_match(self):
        s = _section("scheduler-engine", "Scheduler Engine", body="")
        score = _score(s, ["scheduler"])
        self.assertGreaterEqual(score, 10)

    def test_title_match(self):
        s = _section("some-id", "Retry Logic", body="")
        score = _score(s, ["retry"])
        self.assertGreaterEqual(score, 8)

    def test_body_match_capped(self):
        s = _section("some-id", "Title", body="retry " * 10)
        score = _score(s, ["retry"])
        # body contributes at most 6
        self.assertLessEqual(score, 6)

    def test_link_match(self):
        s = _section("some-id", "Title", body="", links=["retry-logic"])
        score = _score(s, ["retry"])
        self.assertGreaterEqual(score, 4)

    def test_no_match_zero(self):
        s = _section("engine", "Engine", body="nothing relevant")
        score = _score(s, ["banana"])
        self.assertEqual(score, 0)

    def test_case_insensitive(self):
        s = _section("Retry", "RETRY", body="")
        score = _score(s, ["retry"])
        self.assertGreater(score, 0)


class TestSnippet(unittest.TestCase):

    def test_returns_200_chars(self):
        body = "a" * 300
        snippet = _snippet(body, ["a"])
        self.assertLessEqual(len(snippet.replace("...", "")), 205)

    def test_contains_term(self):
        body = "hello world, this is the scheduler engine loop."
        snippet = _snippet(body, ["scheduler"])
        self.assertIn("scheduler", snippet)

    def test_fallback_no_match(self):
        body = "hello world"
        snippet = _snippet(body, ["banana"])
        self.assertEqual(snippet, "hello world")


class TestSearch(unittest.TestCase):

    def test_returns_hits(self):
        root = _make_repo({
            "lat.md/a.md": "## Scheduler Engine\n<!-- id: scheduler-engine -->\n\nCentral orchestrator.\n",
            "lat.md/b.md": "## Job Model\n<!-- id: job-model -->\n\nThe job class.\n",
        })
        hits = search(root, "scheduler")
        ids = [h.section_id for h in hits]
        self.assertIn("scheduler-engine", ids)

    def test_sorted_by_score(self):
        root = _make_repo({
            "lat.md/a.md": (
                "## Scheduler Engine\n<!-- id: scheduler-engine -->\n\nscheduler scheduler scheduler.\n"
                "\n## Cron Expression\n<!-- id: cron-expression -->\n\nscheduler.\n"
            ),
        })
        hits = search(root, "scheduler")
        self.assertGreater(hits[0].score, hits[-1].score)

    def test_no_results(self):
        root = _make_repo({
            "lat.md/a.md": "## Engine\n<!-- id: engine -->\n\nBody.\n",
        })
        hits = search(root, "banana")
        self.assertEqual(hits, [])

    def test_empty_query(self):
        root = _make_repo({
            "lat.md/a.md": "## Engine\n<!-- id: engine -->\n\nBody.\n",
        })
        hits = search(root, "")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
