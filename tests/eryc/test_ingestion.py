"""
Tests for the ingestion pipeline: parsers, chunker, metadata extraction.
"""

import textwrap
from pathlib import Path

import pytest

from eryc.ingestion.chunker import Chunker, _estimate_tokens
from eryc.ingestion.metadata import extract_metadata
from eryc.ingestion.parsers.markdown import MarkdownParser
from eryc.ingestion.parsers.text_parser import PlainTextParser


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestMarkdownParser:
    def test_parses_headings_into_sections(self, tmp_path: Path) -> None:
        md = textwrap.dedent("""\
            # My Document

            Introduction paragraph.

            ## Section One

            Content of section one.

            ## Section Two

            Content of section two.
        """)
        p = tmp_path / "test.md"
        p.write_text(md)

        doc = MarkdownParser().parse(p)

        assert doc.canonical_title == "My Document"
        assert len(doc.sections) >= 2
        section_texts = [s.text for s in doc.sections]
        assert any("Content of section one" in t for t in section_texts)

    def test_content_hash_is_deterministic(self, tmp_path: Path) -> None:
        text = "# Title\n\nBody text."
        p = tmp_path / "a.md"
        p.write_text(text)

        doc1 = MarkdownParser().parse(p)
        doc2 = MarkdownParser().parse(p)
        assert doc1.content_hash == doc2.content_hash

    def test_falls_back_to_filename_when_no_h1(self, tmp_path: Path) -> None:
        p = tmp_path / "my_document.md"
        p.write_text("## Section\n\nContent.")
        doc = MarkdownParser().parse(p)
        assert doc.canonical_title == "my_document"


class TestPlainTextParser:
    def test_splits_on_paragraph_breaks(self, tmp_path: Path) -> None:
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        p = tmp_path / "test.txt"
        p.write_text(text)

        doc = PlainTextParser().parse(p)
        assert len(doc.sections) == 3

    def test_single_section_for_no_breaks(self, tmp_path: Path) -> None:
        p = tmp_path / "single.txt"
        p.write_text("One continuous block of text without blank lines.")
        doc = PlainTextParser().parse(p)
        assert len(doc.sections) == 1

    def test_doc_type_defaults_to_text(self, tmp_path: Path) -> None:
        p = tmp_path / "x.txt"
        p.write_text("Hello")
        doc = PlainTextParser().parse(p)
        assert doc.doc_type == "text"


# ---------------------------------------------------------------------------
# Chunker tests
# ---------------------------------------------------------------------------


class TestChunker:
    def test_produces_chunks_with_deterministic_ids(self, tmp_path: Path) -> None:
        p = tmp_path / "doc.md"
        p.write_text("# Title\n\nSome body text here.")
        doc = MarkdownParser().parse(p)
        chunker = Chunker(max_chunk_tokens=500)

        chunks1 = chunker.chunk_document(doc, version_id="v1", document_id="d1")
        chunks2 = chunker.chunk_document(doc, version_id="v1", document_id="d1")

        assert len(chunks1) == len(chunks2)
        for c1, c2 in zip(chunks1, chunks2):
            assert c1.chunk_id == c2.chunk_id

    def test_ordinals_are_sequential(self, tmp_path: Path) -> None:
        p = tmp_path / "doc.md"
        p.write_text(
            "# Title\n\nParagraph one.\n\n## Section\n\nParagraph two."
        )
        doc = MarkdownParser().parse(p)
        chunks = Chunker().chunk_document(doc, version_id="v1", document_id="d1")

        ordinals = [c.chunk_ordinal for c in chunks]
        assert ordinals == list(range(len(chunks)))

    def test_large_section_is_split(self) -> None:
        """A section exceeding max_tokens should produce multiple chunks."""
        from eryc.ingestion.parsers.base import ParsedDocument, ParsedSection

        long_text = " ".join(["word"] * 600)
        section = ParsedSection(section_path="Root", heading="", text=long_text, level=0)
        doc = ParsedDocument(
            source_path="/tmp/x.txt",
            canonical_title="X",
            sections=[section],
            raw_text=long_text,
        )
        chunks = Chunker(max_chunk_tokens=200).chunk_document(
            doc, version_id="v1", document_id="d1"
        )
        assert len(chunks) > 1

    def test_token_estimate(self) -> None:
        # 100 characters ≈ 25 tokens
        text = "a" * 100
        assert _estimate_tokens(text) == 25


# ---------------------------------------------------------------------------
# Metadata extraction tests
# ---------------------------------------------------------------------------


class TestMetadataExtraction:
    def _make_doc(self, text: str, title: str = "Test") -> object:
        from eryc.ingestion.parsers.base import ParsedDocument, ParsedSection

        return ParsedDocument(
            source_path="/tmp/test.txt",
            canonical_title=title,
            sections=[
                ParsedSection(section_path="Root", heading="", text=text, level=0)
            ],
            raw_text=text,
        )

    def test_classifies_case_note(self) -> None:
        doc = self._make_doc("This is a case note recording a home visit.")
        meta = extract_metadata(doc)
        assert meta["doc_type"] == "case_note"

    def test_classifies_policy(self) -> None:
        doc = self._make_doc("This policy sets out the procedure for emergency referrals.")
        meta = extract_metadata(doc)
        assert meta["doc_type"] == "policy"

    def test_detects_confidential_sensitivity(self) -> None:
        doc = self._make_doc("CONFIDENTIAL: This document contains sensitive information.")
        meta = extract_metadata(doc)
        assert meta["sensitivity_level"] == "confidential"

    def test_defaults_to_standard_sensitivity(self) -> None:
        doc = self._make_doc("A routine operational document.")
        meta = extract_metadata(doc)
        assert meta["sensitivity_level"] == "standard"

    def test_hint_overrides_classification(self) -> None:
        doc = self._make_doc("Some text.")
        meta = extract_metadata(doc, doc_type_hint="referral")
        assert meta["doc_type"] == "referral"
