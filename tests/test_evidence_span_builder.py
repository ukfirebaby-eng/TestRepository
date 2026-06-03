from core.accuracy.evidence_span_builder import (
    build_evidence_spans,
    compute_source_hash,
)


def test_compute_source_hash_is_stable():
    assert compute_source_hash("alpha") == compute_source_hash("alpha")
    assert compute_source_hash("alpha") != compute_source_hash("beta")


def test_builds_sentence_spans_from_text_chunk():
    chunks = [
        {
            "chunk_id": "chunk_1",
            "text": "Cloud migration starts on 8 August. Security certification completes on 10 August.",
            "page": 2,
            "bbox": (1.0, 2.0, 3.0, 4.0),
        }
    ]

    spans = build_evidence_spans(
        document_id="doc_1",
        chunks=chunks,
        source_hash="sha256:abc",
    )

    assert [span.text for span in spans] == [
        "Cloud migration starts on 8 August.",
        "Security certification completes on 10 August.",
    ]
    assert spans[0].span_id == "span_doc_1_chunk_1_000"
    assert spans[0].span_type == "sentence"
    assert spans[0].bbox.x0 == 1.0


def test_keeps_short_table_rows_as_table_row_spans():
    chunks = [
        {
            "chunk_id": "chunk_table",
            "text": "Task | Owner | Date\nMigration | Platform Team | 2026-08-08",
            "page": 0,
            "bbox": None,
        }
    ]

    spans = build_evidence_spans(
        document_id="doc_1",
        chunks=chunks,
        source_hash="sha256:abc",
    )

    assert len(spans) == 2
    assert all(span.span_type == "table_row" for span in spans)
    assert spans[1].text == "Migration | Platform Team | 2026-08-08"
