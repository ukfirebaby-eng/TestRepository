# Claim-Centred Accuracy Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a validated evidence-and-claim layer so Diamond Miner builds graph facts from traceable source claims instead of promoting one-pass LLM graph extraction directly into the final topology.

**Architecture:** Keep the current FastAPI API, vault, reporting, exports, and `/app-v2` frontend stable while adding a backend accuracy layer alongside the existing ingestion path. The first implementation stores document manifests, evidence spans, extracted claims, validation results, and promotion candidates without replacing the existing graph until tests and evaluation metrics prove parity.

**Tech Stack:** Python 3, FastAPI, SQLite through `core/vault.py`, ChromaDB, Pydantic v2, PyMuPDF, OpenAI-compatible chat completions, pytest, deterministic evaluation tests.

---

## Brainstorming Summary

### Problem Frame

The current ingestion path parses a document into chunks, sends each chunk to `DeconstructorAgent.extract_topology`, and writes returned nodes and edges directly to SQLite through `HybridVault.insert_graph_topology`. That is fast and useful for prototypes, but it allows a weak extraction to become a graph fact before Diamond Miner has proved exactly which source sentence supports it.

The visible product symptom is confusing selected evidence such as a structural relationship from a programme to itself. The deeper cause is that the graph currently stores block-level provenance, not claim-level provenance. A chunk can contain several dates, owners, prerequisites, assumptions, and exceptions. Treating that whole block as one source of truth makes it hard to explain or validate a single edge.

### Options Considered

**Option A: Prompt-only accuracy pass.** Tighten the current deconstructor prompt and add more examples. This is low risk, but it does not solve provenance, validation, entity canonicalisation, or silent extraction failures.

**Option B: Replace ingestion in one large rewrite.** Move immediately to evidence spans, claims, validators, entities, and graph promotion. This is architecturally clean, but it risks destabilising ingestion, reporting, and the V2 app while the new pipeline is still unproven.

**Option C: Add a parallel claim layer first.** Keep the current graph path running, add document manifests, evidence spans, typed claims, and deterministic validation beside it, then introduce graph promotion behind a feature flag. This is the recommended path.

### Recommended Direction

Use Option C. The first phase should make accuracy measurable without changing user-facing behaviour by default. Once claim extraction precision, evidence linkage, and validation pass rates are visible in tests and ingestion telemetry, the graph promoter can replace direct LLM topology promotion for selected relationship types.

---

## Target Accuracy Rules

- LLMs may propose structured claims.
- Validators decide whether claims become accepted claims.
- Graph promotion decides whether accepted claims become graph nodes and edges.
- No accepted claim may exist without at least one evidence span.
- No promoted graph edge may exist without a claim id.
- No promoted graph edge may exist without evidence span ids.
- Explicit claims can be auto-promoted after validation.
- Implied and inferred claims remain stored for review unless a later task adds a human approval flow.
- Extraction failures must be stored and surfaced; they must not silently collapse into an empty graph.
- Existing reports, exports, document deletion, ingestion progress, and `/app-v2` must continue to work during the transition.

---

## Files and Responsibilities

### Create

- `core/accuracy/__init__.py`
  - Exports the accuracy-layer schemas and helpers.

- `core/accuracy/schemas.py`
  - Pydantic models for document manifests, evidence spans, extracted claims, validation results, canonical entities, promoted graph edges, and findings.

- `core/accuracy/evidence_span_builder.py`
  - Converts current parsed chunks into stable, smaller evidence spans.
  - Uses deterministic ids based on document id, source hash, chunk id, and local span index.
  - Handles sentence-like spans for text chunks and table-row/table-cell style spans for tabular chunks without adding new parser dependencies.

- `core/accuracy/claim_extractor.py`
  - Owns the claim-extraction prompt and response parsing.
  - Returns `ExtractedClaim` models plus structured failure records.
  - Does not write directly to graph tables.

- `core/accuracy/deterministic_validator.py`
  - Applies non-LLM validation gates for evidence linkage, schema completeness, modality, certainty, dates, confidence, and promotion eligibility.

- `core/accuracy/graph_promoter.py`
  - Converts accepted explicit claims into the existing node/edge shape.
  - Runs behind `DIAMOND_MINER_USE_CLAIM_PROMOTION=1` until parity is proven.

- `tests/test_accuracy_schemas.py`
  - Schema validation tests.

- `tests/test_evidence_span_builder.py`
  - Evidence span construction and stable id tests.

- `tests/test_claim_validator.py`
  - Deterministic validation tests.

- `tests/test_claim_graph_promoter.py`
  - Claim-to-graph mapping tests.

- `tests/test_vault_accuracy_layer.py`
  - SQLite persistence tests for manifests, spans, claims, validation results, and deletion cleanup.

- `tests/test_orchestrator_claim_layer.py`
  - Orchestrator wiring tests with mocked claim extraction.

### Modify

- `core/vault.py`
  - Add SQLite tables and methods for the accuracy layer.
  - Add cleanup for new tables in `delete_document()` and `clear_all()`.
  - Preserve existing `nodes`, `edges`, `documents`, report caches, and ChromaDB behaviour.

- `core/orchestrator.py`
  - Compute source hash and document manifest during ingestion.
  - Build and store evidence spans after parsing.
  - Optionally extract and validate claims alongside current graph extraction.
  - Keep current graph extraction as default until the promoter is explicitly enabled.

- `core/agents.py`
  - Keep `DeconstructorAgent` unchanged for compatibility.
  - Move new claim prompt logic into `core/accuracy/claim_extractor.py` rather than expanding this already-large file.

- `api.py`
  - Later phase only: expose ingestion accuracy telemetry in `JOB_STORE` after backend tests exist.
  - Do not change public API schemas in the first foundation task.

- `tests/test_vault_delete.py`
  - Extend deletion tests to assert new accuracy-layer rows are removed.

- `tests/test_evaluation_fixture_baselines.py`
  - Later phase only: add claim/evidence quality metrics after baseline fixtures exist.

---

## Data Model

### Document Manifest

```python
class DocumentManifest(BaseModel):
    document_id: str
    filename: str
    mime_type: str = "application/octet-stream"
    source_hash: str
    ingested_at: datetime
    parser_version: str = "legacy-parser-v1"
    schema_version: str = "claim-layer-v1"
    embedding_model: str = "chromadb-default"
    llm_model: str = ""
    document_anchor_date: date | None = None
    validation_status: Literal["pending", "partial", "passed", "failed"] = "pending"
```

### Evidence Span

```python
class EvidenceSpan(BaseModel):
    span_id: str
    document_id: str
    chunk_id: str
    page_number: int
    section_title: str = ""
    text: str
    span_type: Literal["sentence", "paragraph", "table_row", "table_cell", "caption", "heading"]
    bbox: BoundingBox | None = None
    source_hash: str
```

### Extracted Claim

```python
class ExtractedClaim(BaseModel):
    claim_id: str
    document_id: str
    claim_type: Literal[
        "dependency",
        "blocker",
        "objective",
        "success_criterion",
        "date_constraint",
        "resource_requirement",
        "owner_assignment",
        "risk",
        "assumption",
        "deliverable",
        "scope_inclusion",
        "scope_exclusion",
        "governance_rule",
        "quality_requirement",
    ]
    subject: str
    predicate: str
    object: str
    modality: Literal["must", "should", "may", "assumes", "prohibits"]
    certainty: Literal["explicit", "implied", "inferred"]
    status: Literal["active", "superseded", "rejected", "unknown"] = "active"
    date_start: date | None = None
    date_end: date | None = None
    owner: str = ""
    evidence_span_ids: list[str]
    source_quote: str
    confidence: float = Field(ge=0.0, le=1.0)
    validation_status: Literal["pending", "passed", "failed", "needs_review"] = "pending"
```

### Validation Result

```python
class ValidationResult(BaseModel):
    claim_id: str
    document_id: str
    status: Literal["passed", "failed", "needs_review"]
    reasons: list[str]
    can_promote: bool
```

### Promoted Graph Edge

```python
class PromotedGraphEdge(BaseModel):
    edge_id: str
    document_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    claim_id: str
    modality: str
    certainty: str
    status: str
    confidence: float
    evidence_span_ids: list[str]
    validation_status: Literal["passed"]
```

---

## Task 1: Add Accuracy Schemas

**Files:**
- Create: `core/accuracy/__init__.py`
- Create: `core/accuracy/schemas.py`
- Test: `tests/test_accuracy_schemas.py`

- [ ] **Step 1: Write the failing schema tests**

Create `tests/test_accuracy_schemas.py`:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from core.accuracy.schemas import (
    BoundingBox,
    DocumentManifest,
    EvidenceSpan,
    ExtractedClaim,
    ValidationResult,
)


def test_evidence_span_requires_text_and_source_hash():
    span = EvidenceSpan(
        span_id="span_doc_1",
        document_id="doc_1",
        chunk_id="chunk_1",
        page_number=1,
        text="Security certification must complete before migration starts.",
        span_type="sentence",
        bbox=BoundingBox(x0=1.0, y0=2.0, x1=3.0, y1=4.0),
        source_hash="abc123",
    )

    assert span.text.startswith("Security certification")
    assert span.bbox.x1 == 3.0


def test_claim_without_evidence_is_invalid():
    with pytest.raises(ValidationError):
        ExtractedClaim(
            claim_id="claim_1",
            document_id="doc_1",
            claim_type="dependency",
            subject="Cloud migration",
            predicate="requires",
            object="Security certification",
            modality="must",
            certainty="explicit",
            evidence_span_ids=[],
            source_quote="Cloud migration requires Security certification.",
            confidence=0.91,
        )


def test_document_manifest_tracks_source_hash_and_versions():
    manifest = DocumentManifest(
        document_id="doc_1",
        filename="strategy.md",
        source_hash="sha256:abc",
        ingested_at=datetime.now(timezone.utc),
        llm_model="gpt-4o-mini",
    )

    assert manifest.parser_version == "legacy-parser-v1"
    assert manifest.schema_version == "claim-layer-v1"
    assert manifest.validation_status == "pending"


def test_validation_result_controls_promotion():
    result = ValidationResult(
        claim_id="claim_1",
        document_id="doc_1",
        status="needs_review",
        reasons=["Inferred claims require human review before promotion."],
        can_promote=False,
    )

    assert result.can_promote is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest -q tests/test_accuracy_schemas.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'core.accuracy'`.

- [ ] **Step 3: Add the schema module**

Create `core/accuracy/__init__.py`:

```python
"""Claim-centred accuracy layer for Diamond Miner ingestion."""
```

Create `core/accuracy/schemas.py`:

```python
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class DocumentManifest(BaseModel):
    document_id: str
    filename: str
    mime_type: str = "application/octet-stream"
    source_hash: str
    ingested_at: datetime
    parser_version: str = "legacy-parser-v1"
    schema_version: str = "claim-layer-v1"
    embedding_model: str = "chromadb-default"
    llm_model: str = ""
    document_anchor_date: date | None = None
    validation_status: Literal["pending", "partial", "passed", "failed"] = "pending"


class EvidenceSpan(BaseModel):
    span_id: str
    document_id: str
    chunk_id: str
    page_number: int
    section_title: str = ""
    text: str
    span_type: Literal["sentence", "paragraph", "table_row", "table_cell", "caption", "heading"]
    bbox: BoundingBox | None = None
    source_hash: str

    @field_validator("text", "source_hash")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class ExtractedClaim(BaseModel):
    claim_id: str
    document_id: str
    claim_type: Literal[
        "dependency",
        "blocker",
        "objective",
        "success_criterion",
        "date_constraint",
        "resource_requirement",
        "owner_assignment",
        "risk",
        "assumption",
        "deliverable",
        "scope_inclusion",
        "scope_exclusion",
        "governance_rule",
        "quality_requirement",
    ]
    subject: str
    predicate: str
    object: str
    modality: Literal["must", "should", "may", "assumes", "prohibits"]
    certainty: Literal["explicit", "implied", "inferred"]
    status: Literal["active", "superseded", "rejected", "unknown"] = "active"
    date_start: date | None = None
    date_end: date | None = None
    owner: str = ""
    evidence_span_ids: list[str]
    source_quote: str
    confidence: float = Field(ge=0.0, le=1.0)
    validation_status: Literal["pending", "passed", "failed", "needs_review"] = "pending"

    @field_validator("subject", "predicate", "object", "source_quote")
    @classmethod
    def _require_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("evidence_span_ids")
    @classmethod
    def _require_evidence(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("at least one evidence span is required")
        return cleaned


class ValidationResult(BaseModel):
    claim_id: str
    document_id: str
    status: Literal["passed", "failed", "needs_review"]
    reasons: list[str]
    can_promote: bool


class CanonicalEntity(BaseModel):
    entity_id: str
    canonical_name: str
    entity_type: Literal["initiative", "team", "system", "deadline", "resource", "risk", "objective", "deliverable"]
    aliases: list[str] = Field(default_factory=list)
    source_span_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    human_locked: bool = False


class PromotedGraphEdge(BaseModel):
    edge_id: str
    document_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    claim_id: str
    modality: str
    certainty: str
    status: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_span_ids: list[str]
    validation_status: Literal["passed"]


class Finding(BaseModel):
    finding_id: str
    document_id: str
    finding_type: str
    severity: int = Field(ge=1, le=5)
    summary: str
    claims_involved: list[str]
    evidence_span_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str
    recommended_action: str
    human_review_status: Literal["pending", "accepted", "rejected"] = "pending"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest -q tests/test_accuracy_schemas.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/accuracy/__init__.py core/accuracy/schemas.py tests/test_accuracy_schemas.py
git commit -m "feat: add claim accuracy schemas"
```

---

## Task 2: Build Evidence Spans From Existing Chunks

**Files:**
- Create: `core/accuracy/evidence_span_builder.py`
- Test: `tests/test_evidence_span_builder.py`

- [ ] **Step 1: Write the failing evidence span tests**

Create `tests/test_evidence_span_builder.py`:

```python
from core.accuracy.evidence_span_builder import build_evidence_spans, compute_source_hash


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest -q tests/test_evidence_span_builder.py
```

Expected: FAIL with `ModuleNotFoundError` for `core.accuracy.evidence_span_builder`.

- [ ] **Step 3: Add evidence span builder**

Create `core/accuracy/evidence_span_builder.py`:

```python
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
    return BoundingBox(x0=float(raw_bbox[0]), y0=float(raw_bbox[1]), x1=float(raw_bbox[2]), y1=float(raw_bbox[3]))


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest -q tests/test_evidence_span_builder.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/accuracy/evidence_span_builder.py tests/test_evidence_span_builder.py
git commit -m "feat: build evidence spans from parsed chunks"
```

---

## Task 3: Persist Manifest, Spans, Claims, And Validation Results

**Files:**
- Modify: `core/vault.py`
- Modify: `tests/test_vault_delete.py`
- Test: `tests/test_vault_accuracy_layer.py`

- [ ] **Step 1: Write the failing vault persistence tests**

Create `tests/test_vault_accuracy_layer.py`:

```python
from datetime import datetime, timezone

import pytest

from core.accuracy.schemas import DocumentManifest, EvidenceSpan, ExtractedClaim, ValidationResult
from core.vault import HybridVault


@pytest.fixture
def vault(tmp_path):
    v = HybridVault(tenant_id="accuracy", base_dir=str(tmp_path))
    yield v
    v.conn.close()


def test_saves_and_reads_document_manifest(vault):
    manifest = DocumentManifest(
        document_id="doc_1",
        filename="strategy.md",
        source_hash="sha256:abc",
        ingested_at=datetime.now(timezone.utc),
        llm_model="gpt-4o-mini",
    )

    vault.save_document_manifest(manifest)

    loaded = vault.get_document_manifest("doc_1")
    assert loaded["document_id"] == "doc_1"
    assert loaded["source_hash"] == "sha256:abc"


def test_saves_evidence_spans_and_claims(vault):
    span = EvidenceSpan(
        span_id="span_1",
        document_id="doc_1",
        chunk_id="chunk_1",
        page_number=1,
        text="Cloud migration requires security certification.",
        span_type="sentence",
        source_hash="sha256:abc",
    )
    claim = ExtractedClaim(
        claim_id="claim_1",
        document_id="doc_1",
        claim_type="dependency",
        subject="Cloud migration",
        predicate="requires",
        object="security certification",
        modality="must",
        certainty="explicit",
        evidence_span_ids=["span_1"],
        source_quote="Cloud migration requires security certification.",
        confidence=0.92,
    )

    vault.insert_evidence_spans([span])
    vault.insert_extracted_claims([claim])

    assert vault.list_evidence_spans("doc_1")[0]["span_id"] == "span_1"
    assert vault.list_extracted_claims("doc_1")[0]["claim_id"] == "claim_1"


def test_saves_validation_results(vault):
    result = ValidationResult(
        claim_id="claim_1",
        document_id="doc_1",
        status="passed",
        reasons=[],
        can_promote=True,
    )

    vault.insert_validation_results([result])

    loaded = vault.list_validation_results("doc_1")
    assert loaded[0]["claim_id"] == "claim_1"
    assert loaded[0]["status"] == "passed"
    assert loaded[0]["can_promote"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest -q tests/test_vault_accuracy_layer.py
```

Expected: FAIL because `HybridVault` has no accuracy-layer persistence methods.

- [ ] **Step 3: Add SQLite tables in `initialize_schemas()`**

In `core/vault.py`, add these table definitions after the `documents` table:

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_manifests (
                document_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                parser_version TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                llm_model TEXT NOT NULL,
                document_anchor_date TEXT,
                validation_status TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evidence_spans (
                span_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                section_title TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL,
                span_type TEXT NOT NULL,
                bbox_json TEXT,
                source_hash TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_spans_document ON evidence_spans(document_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_spans_chunk ON evidence_spans(chunk_id)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_claims (
                claim_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                claim_type TEXT NOT NULL,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                modality TEXT NOT NULL,
                certainty TEXT NOT NULL,
                status TEXT NOT NULL,
                date_start TEXT,
                date_end TEXT,
                owner TEXT NOT NULL DEFAULT '',
                evidence_span_ids TEXT NOT NULL,
                source_quote TEXT NOT NULL,
                confidence REAL NOT NULL,
                validation_status TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_claims_document ON extracted_claims(document_id)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS claim_validation_results (
                claim_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                status TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                can_promote INTEGER NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_claim_validation_document ON claim_validation_results(document_id)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extraction_failures (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                span_id TEXT NOT NULL,
                agent TEXT NOT NULL,
                error TEXT NOT NULL,
                raw_payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_extraction_failures_document ON extraction_failures(document_id)")
```

- [ ] **Step 4: Add vault methods**

Add imports at the top of `core/vault.py`:

```python
from core.accuracy.schemas import DocumentManifest, EvidenceSpan, ExtractedClaim, ValidationResult
```

Add methods to `HybridVault`:

```python
    def save_document_manifest(self, manifest: DocumentManifest) -> None:
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO document_manifests
                (document_id, filename, mime_type, source_hash, ingested_at, parser_version,
                 schema_version, embedding_model, llm_model, document_anchor_date, validation_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                manifest.document_id,
                manifest.filename,
                manifest.mime_type,
                manifest.source_hash,
                manifest.ingested_at.isoformat(),
                manifest.parser_version,
                manifest.schema_version,
                manifest.embedding_model,
                manifest.llm_model,
                manifest.document_anchor_date.isoformat() if manifest.document_anchor_date else None,
                manifest.validation_status,
            ))
            self.conn.commit()

    def get_document_manifest(self, document_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM document_manifests WHERE document_id = ?", (document_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def insert_evidence_spans(self, spans: List[EvidenceSpan]) -> None:
        if not spans:
            return
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO evidence_spans
                (span_id, document_id, chunk_id, page_number, section_title, text, span_type, bbox_json, source_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    span.span_id,
                    span.document_id,
                    span.chunk_id,
                    span.page_number,
                    span.section_title,
                    span.text,
                    span.span_type,
                    span.bbox.model_dump_json() if span.bbox else None,
                    span.source_hash,
                )
                for span in spans
            ])
            self.conn.commit()

    def list_evidence_spans(self, document_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM evidence_spans WHERE document_id = ? ORDER BY span_id", (document_id,))
        return [dict(row) for row in cursor.fetchall()]

    def insert_extracted_claims(self, claims: List[ExtractedClaim]) -> None:
        if not claims:
            return
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO extracted_claims
                (claim_id, document_id, claim_type, subject, predicate, object, modality, certainty,
                 status, date_start, date_end, owner, evidence_span_ids, source_quote, confidence, validation_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    claim.claim_id,
                    claim.document_id,
                    claim.claim_type,
                    claim.subject,
                    claim.predicate,
                    claim.object,
                    claim.modality,
                    claim.certainty,
                    claim.status,
                    claim.date_start.isoformat() if claim.date_start else None,
                    claim.date_end.isoformat() if claim.date_end else None,
                    claim.owner,
                    json.dumps(claim.evidence_span_ids),
                    claim.source_quote,
                    claim.confidence,
                    claim.validation_status,
                )
                for claim in claims
            ])
            self.conn.commit()

    def list_extracted_claims(self, document_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM extracted_claims WHERE document_id = ? ORDER BY claim_id", (document_id,))
        rows = []
        for row in cursor.fetchall():
            item = dict(row)
            item["evidence_span_ids"] = json.loads(item["evidence_span_ids"])
            rows.append(item)
        return rows

    def insert_validation_results(self, results: List[ValidationResult]) -> None:
        if not results:
            return
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO claim_validation_results
                (claim_id, document_id, status, reasons_json, can_promote)
                VALUES (?, ?, ?, ?, ?)
            """, [
                (
                    result.claim_id,
                    result.document_id,
                    result.status,
                    json.dumps(result.reasons),
                    1 if result.can_promote else 0,
                )
                for result in results
            ])
            self.conn.commit()

    def list_validation_results(self, document_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM claim_validation_results WHERE document_id = ? ORDER BY claim_id", (document_id,))
        rows = []
        for row in cursor.fetchall():
            item = dict(row)
            item["reasons"] = json.loads(item.pop("reasons_json"))
            rows.append(item)
        return rows
```

- [ ] **Step 5: Extend deletion cleanup**

In `HybridVault.clear_all()`, add these tables to the deletion list before `documents`:

```python
            "extraction_failures",
            "claim_validation_results",
            "extracted_claims",
            "evidence_spans",
            "document_manifests",
```

In `HybridVault.delete_document()`, add:

```python
            cursor.execute("DELETE FROM extraction_failures WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM claim_validation_results WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM extracted_claims WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM evidence_spans WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM document_manifests WHERE document_id = ?", (document_id,))
```

- [ ] **Step 6: Extend deletion tests**

Add this test to `tests/test_vault_delete.py`:

```python
def test_deletes_accuracy_layer_rows(vault):
    from datetime import datetime, timezone

    from core.accuracy.schemas import DocumentManifest, EvidenceSpan

    _seed_document(vault)
    vault.save_document_manifest(DocumentManifest(
        document_id="doc_test",
        filename="test.pdf",
        source_hash="sha256:abc",
        ingested_at=datetime.now(timezone.utc),
        llm_model="gpt-4o-mini",
    ))
    vault.insert_evidence_spans([EvidenceSpan(
        span_id="span_1",
        document_id="doc_test",
        chunk_id="doc_test_chunk_1",
        page_number=1,
        text="Alpha requires Beta.",
        span_type="sentence",
        source_hash="sha256:abc",
    )])

    vault.delete_document("doc_test")

    assert vault.get_document_manifest("doc_test") is None
    assert vault.list_evidence_spans("doc_test") == []
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
python -m pytest -q tests/test_vault_accuracy_layer.py tests/test_vault_delete.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/vault.py tests/test_vault_accuracy_layer.py tests/test_vault_delete.py
git commit -m "feat: persist claim accuracy layer"
```

---

## Task 4: Add Deterministic Claim Validation

**Files:**
- Create: `core/accuracy/deterministic_validator.py`
- Test: `tests/test_claim_validator.py`

- [ ] **Step 1: Write the failing validator tests**

Create `tests/test_claim_validator.py`:

```python
from core.accuracy.deterministic_validator import validate_claim
from core.accuracy.schemas import ExtractedClaim


def _claim(**overrides):
    data = {
        "claim_id": "claim_1",
        "document_id": "doc_1",
        "claim_type": "dependency",
        "subject": "Cloud migration",
        "predicate": "requires",
        "object": "Security certification",
        "modality": "must",
        "certainty": "explicit",
        "evidence_span_ids": ["span_1"],
        "source_quote": "Cloud migration requires Security certification.",
        "confidence": 0.9,
    }
    data.update(overrides)
    return ExtractedClaim(**data)


def test_explicit_claim_with_evidence_can_promote():
    result = validate_claim(_claim(), known_span_ids={"span_1"})

    assert result.status == "passed"
    assert result.can_promote is True
    assert result.reasons == []


def test_unknown_evidence_span_fails():
    result = validate_claim(_claim(), known_span_ids=set())

    assert result.status == "failed"
    assert result.can_promote is False
    assert "Unknown evidence span: span_1" in result.reasons


def test_inferred_claim_needs_review():
    result = validate_claim(_claim(certainty="inferred"), known_span_ids={"span_1"})

    assert result.status == "needs_review"
    assert result.can_promote is False
    assert "Only explicit claims can be auto-promoted." in result.reasons


def test_low_confidence_claim_needs_review():
    result = validate_claim(_claim(confidence=0.41), known_span_ids={"span_1"})

    assert result.status == "needs_review"
    assert result.can_promote is False
    assert "Confidence below promotion threshold." in result.reasons
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest -q tests/test_claim_validator.py
```

Expected: FAIL because `core.accuracy.deterministic_validator` does not exist.

- [ ] **Step 3: Add deterministic validator**

Create `core/accuracy/deterministic_validator.py`:

```python
from collections.abc import Iterable

from core.accuracy.schemas import ExtractedClaim, ValidationResult


PROMOTION_CONFIDENCE_THRESHOLD = 0.65


def validate_claim(claim: ExtractedClaim, *, known_span_ids: Iterable[str]) -> ValidationResult:
    known = set(known_span_ids)
    reasons: list[str] = []

    for span_id in claim.evidence_span_ids:
        if span_id not in known:
            reasons.append(f"Unknown evidence span: {span_id}")

    if claim.certainty != "explicit":
        reasons.append("Only explicit claims can be auto-promoted.")

    if claim.confidence < PROMOTION_CONFIDENCE_THRESHOLD:
        reasons.append("Confidence below promotion threshold.")

    if claim.date_start and claim.date_end and claim.date_end < claim.date_start:
        reasons.append("Claim end date is before start date.")

    if any(reason.startswith("Unknown evidence span") for reason in reasons):
        status = "failed"
    elif reasons:
        status = "needs_review"
    else:
        status = "passed"

    return ValidationResult(
        claim_id=claim.claim_id,
        document_id=claim.document_id,
        status=status,
        reasons=reasons,
        can_promote=status == "passed",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest -q tests/test_claim_validator.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/accuracy/deterministic_validator.py tests/test_claim_validator.py
git commit -m "feat: validate extracted claims deterministically"
```

---

## Task 5: Add Claim Extractor Without Graph Writes

**Files:**
- Create: `core/accuracy/claim_extractor.py`
- Test: `tests/test_claim_extractor.py`

- [ ] **Step 1: Write tests for response parsing and failure handling**

Create `tests/test_claim_extractor.py`:

```python
import json

from core.accuracy.claim_extractor import parse_claim_response


def test_parse_claim_response_returns_claims():
    payload = json.dumps({
        "claims": [
            {
                "claim_id": "claim_doc_1_span_1_000",
                "document_id": "doc_1",
                "claim_type": "dependency",
                "subject": "Cloud migration",
                "predicate": "requires",
                "object": "Security certification",
                "modality": "must",
                "certainty": "explicit",
                "status": "active",
                "evidence_span_ids": ["span_1"],
                "source_quote": "Cloud migration requires Security certification.",
                "confidence": 0.88,
            }
        ]
    })

    claims = parse_claim_response(payload)

    assert len(claims) == 1
    assert claims[0].subject == "Cloud migration"


def test_parse_claim_response_rejects_malformed_claims():
    payload = json.dumps({
        "claims": [
            {
                "claim_id": "claim_bad",
                "document_id": "doc_1",
                "claim_type": "dependency",
                "subject": "Cloud migration",
                "predicate": "requires",
                "object": "Security certification",
                "modality": "must",
                "certainty": "explicit",
                "evidence_span_ids": [],
                "source_quote": "Cloud migration requires Security certification.",
                "confidence": 0.88,
            }
        ]
    })

    claims = parse_claim_response(payload)

    assert claims == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest -q tests/test_claim_extractor.py
```

Expected: FAIL because `core.accuracy.claim_extractor` does not exist.

- [ ] **Step 3: Add parser and extractor wrapper**

Create `core/accuracy/claim_extractor.py`:

```python
import json
from typing import Any

from core.accuracy.schemas import EvidenceSpan, ExtractedClaim
from core.agents import FAST_JSON_MAX_TOKENS, _get_client, _get_model


SYSTEM_PROMPT = """You are a claim extraction engine for operational risk analysis.

Extract only atomic claims that are directly supported by the provided evidence spans.
Do not create graph nodes or graph edges.
Every claim must cite at least one evidence_span_id.
Prefer explicit claims. Mark uncertain interpretations as implied or inferred.

Return only valid JSON:
{
  "claims": [
    {
      "claim_id": "claim_<document_id>_<span_id>_<index>",
      "document_id": "<document_id>",
      "claim_type": "dependency | blocker | objective | success_criterion | date_constraint | resource_requirement | owner_assignment | risk | assumption | deliverable | scope_inclusion | scope_exclusion | governance_rule | quality_requirement",
      "subject": "specific entity or work item",
      "predicate": "short verb phrase",
      "object": "specific entity, date, condition, or result",
      "modality": "must | should | may | assumes | prohibits",
      "certainty": "explicit | implied | inferred",
      "status": "active | superseded | rejected | unknown",
      "date_start": null,
      "date_end": null,
      "owner": "",
      "evidence_span_ids": ["span_id"],
      "source_quote": "exact quote from evidence span",
      "confidence": 0.0
    }
  ]
}
"""


def parse_claim_response(raw_json: str) -> list[ExtractedClaim]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return []

    claims: list[ExtractedClaim] = []
    for item in payload.get("claims", []):
        try:
            claims.append(ExtractedClaim(**item))
        except Exception:
            continue
    return claims


def extract_claims(spans: list[EvidenceSpan]) -> list[ExtractedClaim]:
    if not spans:
        return []

    span_payload: list[dict[str, Any]] = [
        {
            "span_id": span.span_id,
            "document_id": span.document_id,
            "text": span.text,
            "span_type": span.span_type,
        }
        for span in spans
    ]

    response = _get_client().chat.completions.create(
        model=_get_model("fast"),
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=FAST_JSON_MAX_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"evidence_spans": span_payload})},
        ],
    )
    return parse_claim_response(response.choices[0].message.content or "")
```

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest -q tests/test_claim_extractor.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/accuracy/claim_extractor.py tests/test_claim_extractor.py
git commit -m "feat: extract typed claims without graph writes"
```

---

## Task 6: Wire Claim Layer Into Ingestion Behind A Feature Flag

**Files:**
- Modify: `core/orchestrator.py`
- Test: `tests/test_orchestrator_claim_layer.py`

- [ ] **Step 1: Write orchestrator tests with mocked extractor**

Create `tests/test_orchestrator_claim_layer.py`:

```python
from pathlib import Path

from core.accuracy.schemas import ExtractedClaim
from core.orchestrator import DiamondOrchestrator
from core.vault import HybridVault


def test_claim_layer_stores_manifest_spans_claims_and_validation(monkeypatch, tmp_path):
    source = tmp_path / "strategy.md"
    source.write_text("Cloud migration requires Security certification.", encoding="utf-8")
    vault = HybridVault(tenant_id="claim_layer", base_dir=str(tmp_path / "vaults"))

    def fake_extract_claims(spans):
        return [
            ExtractedClaim(
                claim_id="claim_1",
                document_id="doc_1",
                claim_type="dependency",
                subject="Cloud migration",
                predicate="requires",
                object="Security certification",
                modality="must",
                certainty="explicit",
                evidence_span_ids=[spans[0].span_id],
                source_quote=spans[0].text,
                confidence=0.9,
            )
        ]

    monkeypatch.setenv("DIAMOND_MINER_CLAIM_LAYER", "1")
    monkeypatch.setattr("core.accuracy.claim_extractor.extract_claims", fake_extract_claims)
    monkeypatch.setattr("core.agents.DeconstructorAgent.extract_topology", lambda text: {"nodes": [], "edges": []})

    orchestrator = DiamondOrchestrator(
        tenant_id="claim_layer",
        document_id="doc_1",
        document_name="strategy.md",
        vault=vault,
    )
    orchestrator.run_ingestion_pipeline(str(source), max_workers=1)

    assert vault.get_document_manifest("doc_1")["filename"] == "strategy.md"
    assert len(vault.list_evidence_spans("doc_1")) == 1
    assert vault.list_extracted_claims("doc_1")[0]["subject"] == "Cloud migration"
    assert vault.list_validation_results("doc_1")[0]["status"] == "passed"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest -q tests/test_orchestrator_claim_layer.py
```

Expected: FAIL because the orchestrator does not build manifests, spans, claims, or validation results.

- [ ] **Step 3: Add feature flag helpers and imports**

In `core/orchestrator.py`, add imports:

```python
import os
from datetime import datetime, timezone
from core.accuracy.evidence_span_builder import build_evidence_spans, compute_source_hash
from core.accuracy.schemas import DocumentManifest
from core.accuracy.deterministic_validator import validate_claim
from core.accuracy import claim_extractor
from core.agents import _get_model
```

Add helper method to `DiamondOrchestrator`:

```python
    def _claim_layer_enabled(self) -> bool:
        return os.environ.get("DIAMOND_MINER_CLAIM_LAYER", "").strip() == "1"
```

- [ ] **Step 4: Build and store manifest/spans before chunk processing**

In `run_ingestion_pipeline()`, after `chunks = self._parse_document(file_path)`, add:

```python
        source_text = "\n\n".join(chunk["text"] for chunk in chunks)
        source_hash = compute_source_hash(source_text)
        if self._claim_layer_enabled():
            manifest = DocumentManifest(
                document_id=self.document_id,
                filename=self.document_name,
                source_hash=source_hash,
                ingested_at=datetime.now(timezone.utc),
                llm_model=_get_model("fast"),
            )
            self.vault.save_document_manifest(manifest)
            spans = build_evidence_spans(
                document_id=self.document_id,
                chunks=chunks,
                source_hash=source_hash,
            )
            self.vault.insert_evidence_spans(spans)
            claims = claim_extractor.extract_claims(spans)
            known_span_ids = {span.span_id for span in spans}
            validation_results = [validate_claim(claim, known_span_ids=known_span_ids) for claim in claims]
            self.vault.insert_extracted_claims([
                claim.model_copy(update={"validation_status": result.status})
                for claim, result in zip(claims, validation_results)
            ])
            self.vault.insert_validation_results(validation_results)
            self._emit(
                f"[*] Claim Layer: Stored {len(spans)} evidence span(s), "
                f"{len(claims)} claim(s), {sum(1 for r in validation_results if r.can_promote)} promotable."
            )
```

This intentionally runs before legacy parallel graph extraction, but only when `DIAMOND_MINER_CLAIM_LAYER=1`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
python -m pytest -q tests/test_orchestrator_claim_layer.py tests/test_vault_accuracy_layer.py
```

Expected: PASS.

- [ ] **Step 6: Run ingestion cleanup tests**

Run:

```bash
python -m pytest -q tests/test_ingestion_task_cleanup.py tests/test_api_ingest_types.py tests/test_vault_delete.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add core/orchestrator.py tests/test_orchestrator_claim_layer.py
git commit -m "feat: wire claim layer into ingestion behind flag"
```

---

## Task 7: Add Graph Promotion Behind A Separate Feature Flag

**Files:**
- Create: `core/accuracy/graph_promoter.py`
- Modify: `core/orchestrator.py`
- Test: `tests/test_claim_graph_promoter.py`

- [ ] **Step 1: Write graph promoter tests**

Create `tests/test_claim_graph_promoter.py`:

```python
from core.accuracy.graph_promoter import promote_claim_to_topology
from core.accuracy.schemas import ExtractedClaim


def test_dependency_claim_promotes_to_requires_edge():
    claim = ExtractedClaim(
        claim_id="claim_1",
        document_id="doc_1",
        claim_type="dependency",
        subject="Cloud migration",
        predicate="requires",
        object="Security certification",
        modality="must",
        certainty="explicit",
        evidence_span_ids=["span_1"],
        source_quote="Cloud migration requires Security certification.",
        confidence=0.9,
        validation_status="passed",
    )

    topology = promote_claim_to_topology(claim)

    assert topology["nodes"] == [
        {"id": "entity_cloud_migration", "label": "Concept", "name": "Cloud migration"},
        {"id": "entity_security_certification", "label": "Concept", "name": "Security certification"},
    ]
    assert topology["edges"] == [
        {
            "source_id": "entity_cloud_migration",
            "target_id": "entity_security_certification",
            "relationship": "REQUIRES",
            "claim_id": "claim_1",
            "evidence_span_ids": ["span_1"],
        }
    ]


def test_unpassed_claim_does_not_promote():
    claim = ExtractedClaim(
        claim_id="claim_1",
        document_id="doc_1",
        claim_type="dependency",
        subject="Cloud migration",
        predicate="requires",
        object="Security certification",
        modality="must",
        certainty="inferred",
        evidence_span_ids=["span_1"],
        source_quote="Cloud migration requires Security certification.",
        confidence=0.9,
        validation_status="needs_review",
    )

    assert promote_claim_to_topology(claim) == {"nodes": [], "edges": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest -q tests/test_claim_graph_promoter.py
```

Expected: FAIL because `core.accuracy.graph_promoter` does not exist.

- [ ] **Step 3: Add graph promoter**

Create `core/accuracy/graph_promoter.py`:

```python
import re

from core.accuracy.schemas import ExtractedClaim


RELATIONSHIP_BY_CLAIM_TYPE = {
    "dependency": "REQUIRES",
    "blocker": "BLOCKS",
    "deliverable": "PRODUCES",
    "scope_inclusion": "RELATES_TO",
    "scope_exclusion": "BLOCKS",
    "governance_rule": "REQUIRES",
    "quality_requirement": "REQUIRES",
}


def _entity_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"entity_{slug or 'unknown'}"


def promote_claim_to_topology(claim: ExtractedClaim) -> dict:
    if claim.validation_status != "passed":
        return {"nodes": [], "edges": []}
    relationship = RELATIONSHIP_BY_CLAIM_TYPE.get(claim.claim_type)
    if not relationship:
        return {"nodes": [], "edges": []}

    source_id = _entity_id(claim.subject)
    target_id = _entity_id(claim.object)
    return {
        "nodes": [
            {"id": source_id, "label": "Concept", "name": claim.subject},
            {"id": target_id, "label": "Concept", "name": claim.object},
        ],
        "edges": [
            {
                "source_id": source_id,
                "target_id": target_id,
                "relationship": relationship,
                "claim_id": claim.claim_id,
                "evidence_span_ids": claim.evidence_span_ids,
            }
        ],
    }
```

- [ ] **Step 4: Run promoter tests**

Run:

```bash
python -m pytest -q tests/test_claim_graph_promoter.py
```

Expected: PASS.

- [ ] **Step 5: Plan the vault edge schema extension before implementation**

Before wiring promotion into `insert_graph_topology()`, decide whether to extend the existing `edges` table or create a parallel `claim_promoted_edges` table. The safer first implementation is a parallel table because current frontend/API code assumes the existing edge schema.

Add this table in `core/vault.py`:

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS claim_promoted_edges (
                edge_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relationship TEXT NOT NULL,
                claim_id TEXT NOT NULL,
                evidence_span_ids TEXT NOT NULL,
                confidence REAL NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_claim_promoted_edges_document ON claim_promoted_edges(document_id)")
```

Add cleanup for `claim_promoted_edges` in `clear_all()` and `delete_document()`.

- [ ] **Step 6: Wire promotion only when explicitly enabled**

In `core/orchestrator.py`, add:

```python
    def _claim_promotion_enabled(self) -> bool:
        return os.environ.get("DIAMOND_MINER_USE_CLAIM_PROMOTION", "").strip() == "1"
```

After validation storage in Task 6, add:

```python
            if self._claim_promotion_enabled():
                from core.accuracy.graph_promoter import promote_claim_to_topology

                promoted_nodes = []
                promoted_edges = []
                for claim in [
                    claim.model_copy(update={"validation_status": result.status})
                    for claim, result in zip(claims, validation_results)
                ]:
                    topology = promote_claim_to_topology(claim)
                    promoted_nodes.extend(topology["nodes"])
                    promoted_edges.extend(topology["edges"])
                if promoted_nodes or promoted_edges:
                    self.vault.insert_graph_topology(
                        nodes=promoted_nodes,
                        edges=promoted_edges,
                        source_chunk_id="claim_layer",
                        document_id=self.document_id,
                    )
```

Do not enable `DIAMOND_MINER_USE_CLAIM_PROMOTION` by default.

- [ ] **Step 7: Run focused tests**

Run:

```bash
python -m pytest -q tests/test_claim_graph_promoter.py tests/test_orchestrator_claim_layer.py tests/test_frontend_v2_contract.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/accuracy/graph_promoter.py core/orchestrator.py core/vault.py tests/test_claim_graph_promoter.py
git commit -m "feat: add guarded claim graph promotion"
```

---

## Task 8: Surface Accuracy Telemetry Without Changing Public Schemas

**Files:**
- Modify: `api.py`
- Modify: `frontend/src/components/CommandCenterApp.tsx`
- Modify: `frontend/src/api/client.ts`
- Test: `tests/test_ingestion_task_cleanup.py`
- Test: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Backend telemetry rule**

When the claim layer is enabled, `JOB_STORE[job_id]` should include a nested `accuracy` object:

```python
{
    "accuracy": {
        "evidence_spans": 42,
        "claims": 18,
        "validated": 15,
        "needs_review": 3,
        "failed": 0
    }
}
```

This is additive. Existing status clients that ignore `accuracy` continue to work.

- [ ] **Step 2: Frontend display rule**

The V2 ingestion progress panel should show accuracy telemetry only when present:

```text
Evidence spans: 42
Claims extracted: 18
Validated: 15
Needs review: 3
Failed: 0
```

Do not add a new route or new report page in this task.

- [ ] **Step 3: Focused tests**

Add a backend test that constructs a fake `JOB_STORE` status with `accuracy` and confirms the status endpoint returns it unchanged. Add a frontend API/client test that confirms unknown fields on job status do not break parsing.

- [ ] **Step 4: Verification commands**

Run:

```bash
python -m pytest -q tests/test_ingestion_task_cleanup.py tests/test_api_ingest_types.py
cd frontend
npm.cmd run typecheck
npm.cmd run test
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api.py frontend/src/components/CommandCenterApp.tsx frontend/src/api/client.ts tests/test_ingestion_task_cleanup.py frontend/src/api/client.test.ts
git commit -m "feat: surface claim accuracy telemetry"
```

---

## Evaluation Gate Before Replacing Direct Graph Extraction

Do not make claim promotion the default until these checks exist and pass:

- 95 percent or better valid schema output on fixture documents.
- 90 percent or better evidence span linkage on fixture documents.
- 85 percent or better explicit dependency extraction recall on fixture documents.
- Less than 10 percent false positive contradiction rate on fixture documents.
- Zero graph-promoted claims without evidence span ids.
- Zero accepted claims without validation status.
- Zero promoted graph edges without a claim id.

Suggested fixture groups:

- 10 clean structured strategy documents.
- 10 messy PDFs.
- 10 documents with tables.
- 10 contradictory documents.
- 10 ambiguous documents.
- 10 false-positive traps.

Suggested deterministic command:

```bash
python -m pytest -m evaluation -q
```

Live model evaluation remains opt-in:

```bash
set DIAMOND_MINER_LIVE_EVALUATION=1
python -m pytest -m live_evaluation -q
```

---

## Verification Strategy

Run focused backend tests first:

```bash
python -m pytest -q tests/test_accuracy_schemas.py
python -m pytest -q tests/test_evidence_span_builder.py
python -m pytest -q tests/test_claim_validator.py
python -m pytest -q tests/test_claim_extractor.py
python -m pytest -q tests/test_vault_accuracy_layer.py
python -m pytest -q tests/test_orchestrator_claim_layer.py
```

Then run related existing ingestion and vault checks:

```bash
python -m pytest -q tests/test_api_ingest_types.py tests/test_ingestion_task_cleanup.py tests/test_vault_delete.py
```

Then run the existing analytical quality gate:

```bash
python -m pytest -m evaluation -q
```

Only after backend checks pass, run frontend checks if telemetry is surfaced:

```bash
cd frontend
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
```

---

## Risks And Guardrails

- **Risk: current ingestion slows down.** Guard with `DIAMOND_MINER_CLAIM_LAYER=1` until performance is measured.
- **Risk: new claim extraction increases LLM cost.** Batch spans per document and keep extraction disabled by default during foundation work.
- **Risk: graph output diverges from UI assumptions.** Do not replace existing `nodes` and `edges` until promoted edges pass evaluation gates.
- **Risk: table extraction is still too coarse.** The first span builder treats pipe-delimited/chunked tabular text as row spans. Add true cell-level extraction later after accuracy metrics show it is needed.
- **Risk: entity duplicates remain.** Entity canonicalisation is intentionally deferred until spans, claims, and validation storage are stable.
- **Risk: existing deletion misses new tables.** Every persistence task must update `delete_document()` and `clear_all()` tests.

---

## Questions Before Coding

- Should the first implementation enable `DIAMOND_MINER_CLAIM_LAYER=1` locally for development only, or should it remain disabled unless a developer opts in?
- Should failed claim extraction payloads be stored in SQLite only, or also exposed through ingestion status immediately?
- Should claim ids be deterministic from span ids and content hash, or generated by the extractor and normalised after parsing?
- Should the initial claim extractor process all spans in one request, or batch by 10-20 spans to reduce prompt size?
- Should explicit date constraints be promoted through the existing `temporal_metadata` table in this phase, or stored as claims only until the temporal pipeline is redesigned?

---

## Self-Review

### Spec Coverage

- Document manifests are covered by Task 1 and Task 3.
- Evidence spans are covered by Task 2 and Task 3.
- Typed claims are covered by Task 1 and Task 5.
- Structured output enforcement is covered by Task 1, Task 4, and Task 5.
- Deterministic validation is covered by Task 4.
- Parallel non-breaking ingestion is covered by Task 6.
- Guarded graph promotion is covered by Task 7.
- Accuracy telemetry is covered by Task 8.
- Evaluation gates are documented before default replacement.

### Placeholder Scan

The plan does not contain implementation placeholders. Deferred work is explicitly marked as a later phase with current-phase guardrails.

### Type Consistency

The same model names are used throughout: `DocumentManifest`, `EvidenceSpan`, `ExtractedClaim`, `ValidationResult`, `CanonicalEntity`, `PromotedGraphEdge`, and `Finding`.

