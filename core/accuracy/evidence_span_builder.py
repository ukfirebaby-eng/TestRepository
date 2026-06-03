import hashlib
import re
from typing import Any

from core.accuracy.schemas import BoundingBox, EvidenceSpan


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def compute_source_hash(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    return f"sha256:{digest}"


def _bbox_from_chunk(raw_bbox: Any) -> BoundingBox | None:
    if not raw_bbox:
        return None
    if len(raw_bbox) != 4:
        return None
    return BoundingBox(
        x0=float(raw_bbox[0]),
        y0=float(raw_bbox[1]),
        x1=float(raw_bbox[2]),
        y1=float(raw_bbox[3]),
    )


def _split_text(text: str) -> list[tuple[str, str]]:
    stripped = text.strip()
    if not stripped:
        return []
    if "|" in stripped and "\n" in stripped:
        return [("table_row", row.strip()) for row in stripped.splitlines() if row.strip()]
    sentences = [part.strip() for part in _SENTENCE_RE.split(stripped) if part.strip()]
    if len(sentences) > 1:
        return [("sentence", sentence) for sentence in sentences]
    return [("paragraph", stripped)]


def build_evidence_spans(
    *,
    document_id: str,
    chunks: list[dict[str, Any]],
    source_hash: str,
) -> list[EvidenceSpan]:
    spans: list[EvidenceSpan] = []
    for chunk in chunks:
        chunk_id = str(chunk["chunk_id"])
        page_number = int(chunk.get("page") or 0)
        bbox = _bbox_from_chunk(chunk.get("bbox"))
        for local_index, (span_type, text) in enumerate(_split_text(str(chunk.get("text", "")))):
            spans.append(
                EvidenceSpan(
                    span_id=f"span_{document_id}_{chunk_id}_{local_index:03d}",
                    document_id=document_id,
                    chunk_id=chunk_id,
                    page_number=page_number,
                    text=text,
                    span_type=span_type,
                    bbox=bbox,
                    source_hash=source_hash,
                )
            )
    return spans
