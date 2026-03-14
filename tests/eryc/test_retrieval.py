"""
Tests for the retrieval layer: fusion, context expansion, lexical search.
"""

import sqlite3
import json
from pathlib import Path
from typing import List

import pytest

from eryc.database.connection import open_connection
from eryc.database.migrations import apply_migrations
from eryc.models.domain import CandidateChunk
from eryc.retrieval.fusion import reciprocal_rank_fusion
from eryc.retrieval.lexical import LexicalRetriever
from eryc.retrieval.context import ContextExpander


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = open_connection(tmp_path / "retrieval_test.db")
    apply_migrations(c)
    _seed_test_data(c)
    yield c
    c.close()


def _seed_test_data(conn: sqlite3.Connection) -> None:
    """Insert minimal fixture data for retrieval tests."""
    now = "2026-03-14T10:00:00+00:00"

    conn.execute(
        "INSERT OR IGNORE INTO workspaces(workspace_id, name, domain_pack, created_at, updated_at) "
        "VALUES ('ws1', 'Test Workspace', 'generic', ?, ?)",
        (now, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO documents(document_id, workspace_id, doc_type, canonical_title, "
        "sensitivity_level, access_scope, created_at, updated_at) "
        "VALUES ('doc1', 'ws1', 'case_note', 'Case Note 001', 'standard', 'workspace', ?, ?)",
        (now, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO document_versions(version_id, document_id, version_number, "
        "content_hash, index_status, created_at) "
        "VALUES ('ver1', 'doc1', 1, 'abc123', 'indexed', ?)",
        (now,),
    )

    chunks = [
        ("chunk_01", "ver1", "doc1", 0, "Root", 50,
         "The initial assessment identified three concerns about missed visits.",
         "The initial assessment identified three concerns"),
        ("chunk_02", "ver1", "doc1", 1, "Root/Actions", 30,
         "Action: complete follow-up visit within 7 days.",
         "Action: complete follow-up visit within 7 days"),
        ("chunk_03", "ver1", "doc1", 2, "Root/Summary", 40,
         "A review meeting was scheduled to discuss progress.",
         "A review meeting was scheduled to discuss progress"),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO chunks(chunk_id, version_id, document_id, chunk_ordinal, "
        "section_path, token_count, text, text_preview, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}')",
        chunks,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# RRF fusion tests
# ---------------------------------------------------------------------------


def _make_candidate(chunk_id: str) -> CandidateChunk:
    return CandidateChunk(
        chunk_id=chunk_id,
        document_id="doc1",
        version_id="ver1",
        canonical_title="Test",
        section_path="Root",
        text="some text",
        text_preview="some text",
    )


class TestRRFFusion:
    def test_fuses_two_lists(self) -> None:
        lex = [_make_candidate(f"c{i}") for i in range(5)]
        sem = [_make_candidate(f"c{i}") for i in range(3, 8)]
        fused, diag = reciprocal_rank_fusion(lex, sem)

        assert len(fused) <= 10
        # c3 and c4 appear in both lists — they should have higher scores.
        top_ids = {c.chunk_id for c in fused[:4]}
        assert "c3" in top_ids or "c4" in top_ids

    def test_deduplicates_results(self) -> None:
        shared = [_make_candidate("shared")]
        fused, _ = reciprocal_rank_fusion(shared, shared)
        ids = [c.chunk_id for c in fused]
        assert ids.count("shared") == 1

    def test_empty_semantic_returns_lexical(self) -> None:
        lex = [_make_candidate("a"), _make_candidate("b")]
        fused, diag = reciprocal_rank_fusion(lex, [])
        assert len(fused) == 2
        assert diag.semantic_hits == 0

    def test_rrf_scores_are_positive(self) -> None:
        lex = [_make_candidate(f"x{i}") for i in range(3)]
        sem = [_make_candidate(f"y{i}") for i in range(3)]
        fused, _ = reciprocal_rank_fusion(lex, sem)
        assert all(c.rrf_score > 0 for c in fused)

    def test_respects_max_candidates(self) -> None:
        lex = [_make_candidate(f"l{i}") for i in range(50)]
        sem = [_make_candidate(f"s{i}") for i in range(50)]
        fused, _ = reciprocal_rank_fusion(lex, sem, max_candidates=10)
        assert len(fused) <= 10


# ---------------------------------------------------------------------------
# Lexical retrieval tests
# ---------------------------------------------------------------------------


class TestLexicalRetriever:
    def test_returns_relevant_chunks(self, conn: sqlite3.Connection) -> None:
        retriever = LexicalRetriever(conn)
        results = retriever.search("assessment concerns", workspace_id="ws1")
        # Expect at least one result mentioning "assessment".
        assert any("assessment" in c.text.lower() for c in results)

    def test_empty_index_returns_empty_list(self, tmp_path: Path) -> None:
        c = open_connection(tmp_path / "empty.db")
        apply_migrations(c)
        # No data seeded.
        retriever = LexicalRetriever(c)
        results = retriever.search("anything", workspace_id="ws_none")
        assert results == []
        c.close()

    def test_limit_is_respected(self, conn: sqlite3.Connection) -> None:
        retriever = LexicalRetriever(conn)
        results = retriever.search("visit", workspace_id="ws1", limit=1)
        assert len(results) <= 1


# ---------------------------------------------------------------------------
# Context expansion tests
# ---------------------------------------------------------------------------


class TestContextExpander:
    def test_expands_to_adjacent_chunks(self, conn: sqlite3.Connection) -> None:
        candidate = CandidateChunk(
            chunk_id="chunk_02",
            document_id="doc1",
            version_id="ver1",
            canonical_title="Case Note 001",
            section_path="Root/Actions",
            text="Action: complete follow-up visit within 7 days.",
            text_preview="Action: complete follow-up visit within 7 days",
        )
        expander = ContextExpander(conn, window=1)
        context = expander.expand([candidate], max_context_chunks=10)

        chunk_ids = {c.chunk_id for c in context}
        # chunk_01 and chunk_03 are adjacent to chunk_02.
        assert "chunk_02" in chunk_ids
        assert len(context) > 1

    def test_no_duplicates_in_result(self, conn: sqlite3.Connection) -> None:
        candidates = [
            CandidateChunk(
                chunk_id="chunk_01",
                document_id="doc1",
                version_id="ver1",
                canonical_title="Case Note 001",
                section_path="Root",
                text="The initial assessment.",
                text_preview="The initial assessment",
            )
        ]
        expander = ContextExpander(conn, window=1)
        context = expander.expand(candidates, max_context_chunks=10)
        ids = [c.chunk_id for c in context]
        assert len(ids) == len(set(ids))
