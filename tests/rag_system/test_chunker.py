"""Tests for the hierarchical chunker."""

import pytest

from rag_system.ingestion.chunker import Chunker
from rag_system.ingestion.parsers.base import ParsedDocument, ParsedSection


def _make_parsed_doc(sections: list[tuple[str, str]]) -> ParsedDocument:
    return ParsedDocument(
        title="Test Document",
        sections=[
            ParsedSection(title=title, text=text, level=1)
            for title, text in sections
        ],
        raw_text=" ".join(text for _, text in sections),
    )


class TestChunker:
    def test_short_section_becomes_single_chunk(self):
        chunker = Chunker(chunk_size=512, overlap=64)
        doc = _make_parsed_doc([("Intro", "This is a short introduction.")])
        chunks = chunker.chunk_document(doc, "doc1", "t1")
        assert len(chunks) == 1
        assert chunks[0].semantic_text == "This is a short introduction."

    def test_chunk_has_required_fields(self):
        chunker = Chunker(chunk_size=512)
        doc = _make_parsed_doc([("Section", "Some content here.")])
        chunks = chunker.chunk_document(doc, "doc1", "t1")
        c = chunks[0]
        assert c.chunk_id
        assert c.doc_id == "doc1"
        assert c.tenant_id == "t1"
        assert c.section_title == "Section"
        assert c.semantic_text == "Some content here."
        assert c.raw_text == "Some content here."

    def test_long_section_split_into_multiple_chunks(self):
        chunker = Chunker(chunk_size=10, overlap=2)
        # Generate a long text with many short sentences
        sentences = [f"Sentence number {i} has some words in it." for i in range(30)]
        text = " ".join(sentences)
        doc = _make_parsed_doc([("Long Section", text)])
        chunks = chunker.chunk_document(doc, "doc1", "t1")
        assert len(chunks) > 1

    def test_empty_section_skipped(self):
        chunker = Chunker(chunk_size=512)
        doc = _make_parsed_doc([("Empty", ""), ("Real", "This has content.")])
        chunks = chunker.chunk_document(doc, "doc1", "t1")
        assert len(chunks) == 1
        assert chunks[0].semantic_text == "This has content."

    def test_multiple_sections_become_separate_chunks(self):
        chunker = Chunker(chunk_size=512)
        doc = _make_parsed_doc([
            ("Section A", "Content A."),
            ("Section B", "Content B."),
        ])
        chunks = chunker.chunk_document(doc, "doc1", "t1")
        assert len(chunks) == 2
        titles = {c.section_title for c in chunks}
        assert titles == {"Section A", "Section B"}

    def test_acl_tags_propagated(self):
        chunker = Chunker(chunk_size=512)
        doc = _make_parsed_doc([("S", "Text.")])
        chunks = chunker.chunk_document(doc, "doc1", "t1", acl_tags=["internal"])
        assert "internal" in chunks[0].acl_tags

    def test_source_uri_propagated(self):
        chunker = Chunker(chunk_size=512)
        doc = _make_parsed_doc([("S", "Text.")])
        chunks = chunker.chunk_document(doc, "doc1", "t1", source_uri="https://example.com")
        assert chunks[0].source_uri == "https://example.com"

    def test_version_propagated(self):
        chunker = Chunker(chunk_size=512)
        doc = _make_parsed_doc([("S", "Text.")])
        chunks = chunker.chunk_document(doc, "doc1", "t1", version="2")
        assert chunks[0].version == "2"

    def test_unique_chunk_ids(self):
        chunker = Chunker(chunk_size=10, overlap=2)
        sentences = [f"Sentence {i}." for i in range(20)]
        doc = _make_parsed_doc([("S", " ".join(sentences))])
        chunks = chunker.chunk_document(doc, "doc1", "t1")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))
