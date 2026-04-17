"""Tests for lat/parser.py"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from lat.parser import (
    parse_sections,
    parse_source_annotations,
    is_file_link,
    parse_file_link,
)


SIMPLE_MD = """\
## My Section
<!-- id: my-section -->

This section links to [[other-section]] and [[src/foo.py#Bar]].
"""

REQUIRE_MD = """\
## Required Section
<!-- id: required-section -->
<!-- require-code-mention: true -->

Must be mentioned in source code.
"""

MULTI_MD = """\
# Header (ignored - single #)

## First
<!-- id: first-section -->

Body of first. Links [[second-section]].

## Second
<!-- id: second-section -->

Body of second.

### Sub-section
<!-- id: sub-section -->

Nested section body.
"""

DUPLICATE_MD = """\
## Section A
<!-- id: dup-id -->

First.

## Section B
<!-- id: dup-id -->

Second with same id.
"""

NO_ID_MD = """\
## Section Without ID

This heading has no id comment so it should be skipped.

## Another Section
<!-- id: has-id -->

This one has an id.
"""

SOURCE_PY = """\
class Foo:  # @lat: [[my-section]]
    pass

def bar():  # @lat: [[first-section]], [[second-section]]
    pass

# not an annotation
x = 1
"""


class TestParseSections(unittest.TestCase):

    def test_simple_section(self):
        sections, errors = parse_sections(SIMPLE_MD, "lat.md/test.md")
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(sections), 1)
        s = sections[0]
        self.assertEqual(s.id, "my-section")
        self.assertEqual(s.title, "My Section")
        self.assertFalse(s.require_code_mention)
        self.assertIn("other-section", s.wiki_links)
        self.assertIn("src/foo.py#Bar", s.wiki_links)

    def test_require_code_mention(self):
        sections, errors = parse_sections(REQUIRE_MD, "lat.md/test.md")
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(sections), 1)
        self.assertTrue(sections[0].require_code_mention)

    def test_multiple_sections(self):
        sections, errors = parse_sections(MULTI_MD, "lat.md/test.md")
        self.assertEqual(len(errors), 0)
        ids = [s.id for s in sections]
        self.assertIn("first-section", ids)
        self.assertIn("second-section", ids)
        self.assertIn("sub-section", ids)

    def test_duplicate_id(self):
        sections, errors = parse_sections(DUPLICATE_MD, "lat.md/test.md")
        self.assertEqual(len(sections), 1)  # only first registered
        self.assertEqual(len(errors), 1)
        self.assertIn("DUPLICATE ID", errors[0])
        self.assertIn("dup-id", errors[0])

    def test_section_without_id_skipped(self):
        sections, errors = parse_sections(NO_ID_MD, "lat.md/test.md")
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].id, "has-id")

    def test_lineno_is_one_based(self):
        sections, _ = parse_sections(SIMPLE_MD, "lat.md/test.md")
        self.assertEqual(sections[0].lineno, 1)

    def test_file_recorded(self):
        sections, _ = parse_sections(SIMPLE_MD, "lat.md/foo.md")
        self.assertEqual(sections[0].file, "lat.md/foo.md")


class TestParseSourceAnnotations(unittest.TestCase):

    def test_single_annotation(self):
        annotations = parse_source_annotations(SOURCE_PY, "scheduler/foo.py")
        self.assertGreaterEqual(len(annotations), 2)
        first = annotations[0]
        self.assertEqual(first.source_file, "scheduler/foo.py")
        self.assertEqual(first.section_ids, ["my-section"])

    def test_multi_annotation(self):
        annotations = parse_source_annotations(SOURCE_PY, "scheduler/foo.py")
        multi = [a for a in annotations if len(a.section_ids) > 1]
        self.assertEqual(len(multi), 1)
        self.assertIn("first-section", multi[0].section_ids)
        self.assertIn("second-section", multi[0].section_ids)

    def test_no_annotations(self):
        annotations = parse_source_annotations("x = 1\ny = 2\n", "foo.py")
        self.assertEqual(annotations, [])


class TestIsFileLink(unittest.TestCase):

    def test_section_link(self):
        self.assertFalse(is_file_link("scheduler-engine"))
        self.assertFalse(is_file_link("job-model"))

    def test_file_link_with_slash(self):
        self.assertTrue(is_file_link("scheduler/scheduler.py#Scheduler"))
        self.assertTrue(is_file_link("src/foo.py"))

    def test_py_extension(self):
        self.assertTrue(is_file_link("scheduler.py"))


class TestParseFileLink(unittest.TestCase):

    def test_no_anchor(self):
        path, anchor = parse_file_link("scheduler/scheduler.py")
        self.assertEqual(path, "scheduler/scheduler.py")
        self.assertIsNone(anchor)

    def test_with_anchor(self):
        path, anchor = parse_file_link("scheduler/scheduler.py#Scheduler")
        self.assertEqual(path, "scheduler/scheduler.py")
        self.assertEqual(anchor, "Scheduler")


if __name__ == "__main__":
    unittest.main()
