# Claim-Accuracy Staged Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make validated, evidence-backed claims the authoritative source of Diamond Miner graph topology after a measured shadow-mode rollout.

**Architecture:** Extend the existing `core/accuracy/` boundary instead of replacing it. Introduce one pipeline-mode setting, versioned persistence, layout-aware evidence, complete validation, selective critic review, managed canonical entities, deterministic findings, and a labelled evaluation gate; retain legacy topology only as a temporary shadow comparison and rollback path.

**Tech Stack:** Python 3.14, FastAPI 0.135.1, Pydantic 2.12.5, SQLite, ChromaDB 1.5.5, PyMuPDF 1.27.2.2, OpenAI-compatible clients, pytest, React 19, TypeScript 5.9, Vitest, Playwright.

**Approved design:** `docs/superpowers/specs/2026-06-20-claim-accuracy-staged-cutover-design.md`

---

## Delivery order

1. Integrity foundation: Tasks 1-4.
2. Source fidelity: Tasks 5-6.
3. Verification and entities: Tasks 7-9.
4. Findings and consumer safety: Tasks 10-11.
5. Evaluation and cutover: Tasks 12-14.

Do not skip directly to claim authority. `shadow` remains the required mode until Task 13 proves the holdout gate.

## File structure

### Create

- `core/accuracy/pipeline_mode.py` — resolves legacy settings into one pipeline authority mode.
- `core/storage/__init__.py` — storage package marker.
- `core/storage/migrations.py` — ordered, transactional SQLite schema migrations.
- `core/accuracy/layout_elements.py` — common parser output types for paragraphs, shapes, rows, and cells.
- `core/accuracy/critic_agent.py` — selective claim critic and revision parser.
- `core/accuracy/entity_registry.py` — canonical entity, mention, alias, merge, and human-lock operations.
- `core/accuracy/contradiction_rules.py` — deterministic contradiction candidate rules.
- `core/accuracy/finding_store.py` — converts rule candidates into persisted evidence-backed findings.
- `core/evals/corpus.py` — labelled corpus loader and schema checks.
- `core/evals/metrics.py` — precision, recall, linkage, and false-positive metrics.
- `tests/test_pipeline_mode.py`
- `tests/test_storage_migrations.py`
- `tests/test_manifest_freshness.py`
- `tests/test_layout_elements.py`
- `tests/test_claim_critic.py`
- `tests/test_entity_registry.py`
- `tests/test_contradiction_rules.py`
- `tests/test_finding_store.py`
- `tests/test_claim_cutover.py`
- `tests/fixtures/accuracy_corpus/manifest.json` — corpus index containing exactly 60 labelled fixtures.

### Modify

- `core/accuracy/schemas.py` — add analysis versions, richer validation, critic, entity, and finding models.
- `core/accuracy/evidence_span_builder.py` — consume layout elements and preserve exact provenance.
- `core/accuracy/claim_extractor.py` — application-owned IDs, quote normalisation, and redacted failures.
- `core/accuracy/deterministic_validator.py` — validate resolved evidence and entity context.
- `core/accuracy/graph_promoter.py` — return complete claim-origin edges only.
- `core/orchestrator.py` — execute one explicit pipeline mode and analysis version.
- `core/vault.py` — call migrations and expose storage APIs without route-level SQL.
- `core/evaluation.py` — delegate measured quality metrics to `core/evals/` and retain baseline compatibility.
- `core/risk_finding.py` — require validated provenance for elevated findings.
- `core/simulator.py` — exclude stale, rejected, and unverified claim inputs.
- `core/config.py`, `.env.example`, `api.py` — expose pipeline mode and migration compatibility.
- `frontend/src/api/types.ts`, `frontend/src/api/client.ts` — additive accuracy/freshness types.
- `frontend/src/components/AccuracyWorkspace.tsx` — critic/entity review and gate state.
- `frontend/src/components/GeneratedReportsPanel.tsx` — stale and evidence-authority messaging.
- `frontend/e2e/app-v2.spec.ts` — cutover, stale-state, and review acceptance.
- `.github/workflows/evaluation.yml` — deterministic corpus gate on every relevant change.

---

## Milestone 1: Integrity foundation

### Task 1: Replace Boolean accuracy flags with one pipeline mode

**Files:**
- Create: `core/accuracy/pipeline_mode.py`
- Modify: `core/config.py`
- Modify: `.env.example`
- Modify: `api.py:1350-1405`
- Modify: `core/orchestrator.py:35-45`
- Test: `tests/test_pipeline_mode.py`
- Test: `tests/test_api_config_get.py`
- Test: `tests/test_api_config_post.py`

- [ ] **Step 1: Write mode-resolution tests**

```python
from core.accuracy.pipeline_mode import PipelineMode, resolve_pipeline_mode


def test_explicit_mode_wins_over_legacy_flags(monkeypatch):
    monkeypatch.setenv("DIAMOND_MINER_PIPELINE_MODE", "shadow")
    monkeypatch.setenv("DIAMOND_MINER_CLAIM_LAYER", "0")
    monkeypatch.setenv("DIAMOND_MINER_USE_CLAIM_PROMOTION", "1")
    assert resolve_pipeline_mode() is PipelineMode.SHADOW


def test_legacy_flags_map_to_claims(monkeypatch):
    monkeypatch.delenv("DIAMOND_MINER_PIPELINE_MODE", raising=False)
    monkeypatch.setenv("DIAMOND_MINER_CLAIM_LAYER", "1")
    monkeypatch.setenv("DIAMOND_MINER_USE_CLAIM_PROMOTION", "1")
    assert resolve_pipeline_mode() is PipelineMode.CLAIMS


def test_no_flags_preserves_legacy_default(monkeypatch):
    for name in (
        "DIAMOND_MINER_PIPELINE_MODE",
        "DIAMOND_MINER_CLAIM_LAYER",
        "DIAMOND_MINER_USE_CLAIM_PROMOTION",
    ):
        monkeypatch.delenv(name, raising=False)
    assert resolve_pipeline_mode() is PipelineMode.LEGACY
```

- [ ] **Step 2: Run the focused tests and verify red**

Run: `python -m pytest tests/test_pipeline_mode.py -q`

Expected: collection fails because `core.accuracy.pipeline_mode` does not exist.

- [ ] **Step 3: Implement the resolver**

```python
from enum import StrEnum
import os


class PipelineMode(StrEnum):
    LEGACY = "legacy"
    SHADOW = "shadow"
    CLAIMS = "claims"


def resolve_pipeline_mode(env: dict[str, str] | None = None) -> PipelineMode:
    values = os.environ if env is None else env
    explicit = values.get("DIAMOND_MINER_PIPELINE_MODE", "").strip().lower()
    if explicit:
        return PipelineMode(explicit)
    claim_layer = values.get("DIAMOND_MINER_CLAIM_LAYER", "").strip() == "1"
    claim_promotion = values.get("DIAMOND_MINER_USE_CLAIM_PROMOTION", "").strip() == "1"
    if claim_layer and claim_promotion:
        return PipelineMode.CLAIMS
    if claim_layer:
        return PipelineMode.SHADOW
    return PipelineMode.LEGACY
```

Add `DIAMOND_MINER_PIPELINE_MODE` to managed configuration with allowed values `"" | "legacy" | "shadow" | "claims"`. Keep reading the two legacy fields but stop writing them from the UI after migration.

- [ ] **Step 4: Make orchestrator decisions use the enum**

```python
from core.accuracy.pipeline_mode import PipelineMode, resolve_pipeline_mode


def _pipeline_mode(self) -> PipelineMode:
    return resolve_pipeline_mode()
```

At ingestion start, resolve once into `pipeline_mode`. Run claim extraction in `SHADOW` and `CLAIMS`; run legacy topology in `LEGACY` and `SHADOW`. In `SHADOW`, store claim-promoted edges with non-authoritative origin. In `CLAIMS`, do not call `DeconstructorAgent.extract_topology` unless an explicit diagnostic argument is passed by a test harness.

- [ ] **Step 5: Verify configuration and compatibility**

Run: `python -m pytest tests/test_pipeline_mode.py tests/test_api_config_get.py tests/test_api_config_post.py tests/test_orchestrator_claim_layer.py -q`

Expected: all selected tests pass and legacy configurations resolve deterministically.

- [ ] **Step 6: Commit**

```bash
git add .env.example api.py core/config.py core/orchestrator.py core/accuracy/pipeline_mode.py tests/test_pipeline_mode.py tests/test_api_config_get.py tests/test_api_config_post.py tests/test_orchestrator_claim_layer.py
git commit -m "feat: unify accuracy pipeline modes"
```

### Task 2: Add transactional, versioned SQLite migrations

**Files:**
- Create: `core/storage/__init__.py`
- Create: `core/storage/migrations.py`
- Modify: `core/vault.py:20-210`
- Test: `tests/test_storage_migrations.py`

- [ ] **Step 1: Write migration idempotency and rollback tests**

```python
import sqlite3
import pytest

from core.storage.migrations import Migration, apply_migrations


def test_apply_migrations_records_each_version_once():
    conn = sqlite3.connect(":memory:")
    migrations = [Migration(1, "CREATE TABLE sample (id TEXT PRIMARY KEY)")]
    apply_migrations(conn, migrations)
    apply_migrations(conn, migrations)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    assert rows == [(1,)]


def test_failed_migration_rolls_back_schema_and_version():
    conn = sqlite3.connect(":memory:")
    migrations = [Migration(1, "CREATE TABLE broken (id TEXT)\n-- statement-break\nINVALID SQL")]
    with pytest.raises(sqlite3.Error):
        apply_migrations(conn, migrations)
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE name = 'broken'"
    ).fetchone() is None
```

- [ ] **Step 2: Run the migration tests and verify red**

Run: `python -m pytest tests/test_storage_migrations.py -q`

Expected: collection fails because the migration module does not exist.

- [ ] **Step 3: Implement the migration runner**

```python
from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3


@dataclass(frozen=True)
class Migration:
    version: int
    sql: str


def apply_migrations(conn: sqlite3.Connection, migrations: list[Migration]) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    for migration in sorted(migrations, key=lambda item: item.version):
        if migration.version in applied:
            continue
        with conn:
            for statement in migration.sql.split("-- statement-break"):
                if statement.strip():
                    conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (migration.version, datetime.now(timezone.utc).isoformat()),
            )
```

Move only new schema changes into `MIGRATIONS`; do not mechanically move the existing bootstrap schema in this task. Call `apply_migrations()` after existing table creation so old vaults upgrade safely.

- [ ] **Step 4: Add the first migration**

Migration 1 adds:

```sql
ALTER TABLE edges ADD COLUMN edge_origin TEXT NOT NULL DEFAULT 'legacy';
-- statement-break
ALTER TABLE edges ADD COLUMN promotion_version TEXT;
-- statement-break
ALTER TABLE edges ADD COLUMN promoted_at TEXT;
```

Use a `column_exists()` precondition in Python because some development vaults already contain manually added columns. Test both a new and an upgraded vault.

- [ ] **Step 5: Verify new and existing vault startup**

Run: `python -m pytest tests/test_storage_migrations.py tests/test_vault_accuracy_layer.py tests/test_run_startup.py -q`

Expected: all tests pass and applying migrations twice produces no duplicate-column error.

- [ ] **Step 6: Commit**

```bash
git add core/storage/__init__.py core/storage/migrations.py core/vault.py tests/test_storage_migrations.py
git commit -m "feat: add transactional vault migrations"
```

### Task 3: Version manifests and derived artefacts

**Files:**
- Modify: `core/accuracy/schemas.py:14-26`
- Modify: `core/accuracy/evidence_span_builder.py`
- Modify: `core/orchestrator.py:215-300`
- Modify: `core/vault.py`
- Modify: `core/storage/migrations.py`
- Modify: `api.py:150-180`
- Test: `tests/test_manifest_freshness.py`
- Test: `tests/test_ingestion_task_cleanup.py`

- [ ] **Step 1: Write byte-hash and freshness tests**

```python
from core.accuracy.evidence_span_builder import compute_source_hash_bytes


def test_source_hash_uses_original_bytes():
    assert compute_source_hash_bytes(b"a\r\nb") != compute_source_hash_bytes(b"a\nb")


def test_reanalysis_marks_prior_run_stale(tmp_path):
    vault = make_vault(tmp_path)
    first = vault.begin_analysis_run("doc_1", "sha256:first")
    second = vault.begin_analysis_run("doc_1", "sha256:second")
    assert vault.get_analysis_run(first)["freshness_status"] == "stale"
    assert vault.get_analysis_run(second)["freshness_status"] == "current"
```

Use the existing vault fixture pattern from `tests/test_vault_accuracy_layer.py`; do not instantiate a global vault.

- [ ] **Step 2: Run focused tests and verify red**

Run: `python -m pytest tests/test_manifest_freshness.py -q`

Expected: failures for missing byte hashing and analysis-run APIs.

- [ ] **Step 3: Add analysis version models**

```python
class AnalysisRun(BaseModel):
    analysis_run_id: str
    document_id: str
    source_hash: str
    started_at: datetime
    completed_at: datetime | None = None
    pipeline_mode: Literal["legacy", "shadow", "claims"]
    freshness_status: Literal["current", "stale"] = "current"
    validation_status: Literal["pending", "partial", "passed", "failed"] = "pending"
```

Add `analysis_run_id` to `EvidenceSpan`, `ExtractedClaim`, `ValidationResult`, canonical-entity persistence, claim-origin edges, and findings. Existing rows migrate to `analysis_run_id = 'legacy'`.

- [ ] **Step 4: Hash bytes before parsing and begin a run**

```python
def compute_source_hash_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


payload = Path(file_path).read_bytes()
source_hash = compute_source_hash_bytes(payload)
analysis_run = self.vault.begin_analysis_run(
    document_id=self.document_id,
    source_hash=source_hash,
    pipeline_mode=pipeline_mode.value,
)
```

Complete the run only after parsing, extraction, validation, and authoritative promotion finish. Persist `partial` when individual spans fail and `failed` when parsing or authoritative promotion fails.

- [ ] **Step 5: Add explicit reanalysis semantics**

Add `POST /api/v1/documents/{document_id}/reingest` accepting the replacement file. It verifies that the document exists, writes a generated temporary filename, starts a new analysis run, and leaves the prior run readable as stale audit history. Do not infer document identity from filename.

- [ ] **Step 6: Verify lifecycle behavior**

Run: `python -m pytest tests/test_manifest_freshness.py tests/test_ingestion_task_cleanup.py tests/test_api_status.py -q`

Expected: all tests pass; prior runs become stale only after a new run begins.

- [ ] **Step 7: Commit**

```bash
git add api.py core/accuracy/schemas.py core/accuracy/evidence_span_builder.py core/orchestrator.py core/storage/migrations.py core/vault.py tests/test_manifest_freshness.py tests/test_ingestion_task_cleanup.py tests/test_api_status.py
git commit -m "feat: version document analysis artefacts"
```

### Task 4: Complete deterministic claim validation

**Files:**
- Modify: `core/accuracy/schemas.py:55-121`
- Modify: `core/accuracy/claim_extractor.py`
- Modify: `core/accuracy/deterministic_validator.py`
- Modify: `core/vault.py`
- Modify: `core/storage/migrations.py`
- Test: `tests/test_claim_validator.py`
- Test: `tests/test_claim_extractor.py`

- [ ] **Step 1: Add failing provenance and predicate tests**

```python
def test_validator_rejects_quote_missing_from_evidence(claim, evidence_span):
    claim = claim.model_copy(update={"source_quote": "words not present"})
    result = validate_claim(claim, evidence_by_id={evidence_span.span_id: evidence_span})
    assert result.status == "failed"
    assert "source_quote_not_found" in result.errors


def test_validator_rejects_cross_document_evidence(claim, evidence_span):
    foreign = evidence_span.model_copy(update={"document_id": "other"})
    result = validate_claim(claim, evidence_by_id={foreign.span_id: foreign})
    assert result.status == "failed"
    assert "evidence_document_mismatch" in result.errors


def test_validator_rejects_predicate_not_allowed_for_type(claim, evidence_span):
    claim = claim.model_copy(update={"claim_type": "dependency", "predicate": "owns"})
    result = validate_claim(claim, evidence_by_id={evidence_span.span_id: evidence_span})
    assert result.status == "failed"
    assert "predicate_not_allowed" in result.errors
```

- [ ] **Step 2: Run tests and verify the current validator fails them**

Run: `python -m pytest tests/test_claim_validator.py -q`

Expected: failures because the validator accepts only a set of span IDs and stores undifferentiated reasons.

- [ ] **Step 3: Extend validation results**

```python
class ValidationResult(BaseModel):
    claim_id: str
    document_id: str
    analysis_run_id: str
    validator: str = "deterministic"
    validator_version: str = "2"
    status: Literal["passed", "failed", "needs_review"]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    can_promote: bool
    validated_at: datetime
```

Persist each result under `(claim_id, validator, validator_version)` rather than replacing audit history by claim ID.

- [ ] **Step 4: Implement contextual validation**

```python
PREDICATES_BY_TYPE = {
    "dependency": {"requires", "depends on", "cannot begin until"},
    "blocker": {"blocks", "prevents", "delays"},
    "owner_assignment": {"owns", "is accountable for", "is responsible for"},
    "scope_inclusion": {"includes", "is in scope"},
    "scope_exclusion": {"excludes", "is out of scope"},
}


def normalise_quote(value: str) -> str:
    return " ".join(value.split()).casefold()
```

Resolve every cited span. Missing or foreign evidence, absent quote text, invalid predicates, invalid date order, and missing promotion provenance are errors. Non-explicit certainty, low confidence, generic entities, and unresolved entities are warnings and route to review.

- [ ] **Step 5: Make IDs application-owned and redact failures**

Ignore model-provided claim IDs. Derive a UUIDv5 from document ID, analysis run, claim type, normalised subject/predicate/object, and sorted evidence IDs. Before storing `raw_payload`, replace values matching configured API-key patterns with `[REDACTED]`.

- [ ] **Step 6: Verify validator and persistence behavior**

Run: `python -m pytest tests/test_claim_validator.py tests/test_claim_extractor.py tests/test_vault_accuracy_layer.py -q`

Expected: all tests pass; no claim controls its own final validation status.

- [ ] **Step 7: Commit**

```bash
git add core/accuracy/schemas.py core/accuracy/claim_extractor.py core/accuracy/deterministic_validator.py core/storage/migrations.py core/vault.py tests/test_claim_validator.py tests/test_claim_extractor.py tests/test_vault_accuracy_layer.py
git commit -m "feat: enforce claim provenance validation"
```

---

## Milestone 2: Source fidelity

### Task 5: Introduce common layout elements and exact PDF evidence geometry

**Files:**
- Create: `core/accuracy/layout_elements.py`
- Modify: `core/orchestrator.py:46-173`
- Modify: `core/accuracy/evidence_span_builder.py`
- Modify: `core/accuracy/schemas.py`
- Test: `tests/test_layout_elements.py`
- Test: `tests/test_parsers.py`
- Test: `tests/test_evidence_span_builder.py`

- [ ] **Step 1: Write failing PDF geometry tests**

```python
def test_pdf_sentence_spans_have_distinct_geometry(tmp_path):
    pdf_path = make_two_sentence_pdf(tmp_path)
    elements = parse_pdf_layout(str(pdf_path))
    spans = build_evidence_spans(
        document_id="doc_1",
        analysis_run_id="run_1",
        elements=elements,
        source_hash="sha256:test",
    )
    assert [span.text for span in spans] == ["Alpha starts Monday.", "Beta starts Friday."]
    assert spans[0].bbox != spans[1].bbox
```

The fixture helper creates one page with the two sentences on separate lines using PyMuPDF; it does not mock geometry.

- [ ] **Step 2: Run tests and verify red**

Run: `python -m pytest tests/test_layout_elements.py tests/test_evidence_span_builder.py -q`

Expected: failures because the common element API does not exist and current sentence spans share one block box.

- [ ] **Step 3: Define the common element model**

```python
class LayoutElement(BaseModel):
    element_id: str
    document_id: str
    element_type: Literal["heading", "paragraph", "sentence", "table", "table_row", "table_cell", "caption", "shape"]
    text: str
    page_number: int = 0
    section_path: list[str] = Field(default_factory=list)
    bbox: BoundingBox | None = None
    table_id: str | None = None
    row_index: int | None = None
    column_index: int | None = None
    header_refs: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Parse PDF words into sentence boxes**

Use `page.get_text("words")` and `page.get_text("dict")`. Group words by block/line, split sentence boundaries from the rendered text, and union only the word boxes belonging to each sentence. Preserve page numbers as one-based values.

```python
def union_bbox(boxes: list[BoundingBox]) -> BoundingBox:
    return BoundingBox(
        x0=min(box.x0 for box in boxes),
        y0=min(box.y0 for box in boxes),
        x1=max(box.x1 for box in boxes),
        y1=max(box.y1 for box in boxes),
    )
```

- [ ] **Step 5: Make evidence construction consume elements**

Create one `EvidenceSpan` per sentence, heading, caption, shape, or table cell. Carry section path and table coordinates directly; do not infer a table from pipe characters inside arbitrary text.

- [ ] **Step 6: Verify all existing format parsers still route correctly**

Run: `python -m pytest tests/test_layout_elements.py tests/test_parsers.py tests/test_evidence_span_builder.py -q`

Expected: all tests pass and PDF sentence geometry differs where source geometry differs.

- [ ] **Step 7: Commit**

```bash
git add core/accuracy/layout_elements.py core/accuracy/schemas.py core/accuracy/evidence_span_builder.py core/orchestrator.py tests/test_layout_elements.py tests/test_parsers.py tests/test_evidence_span_builder.py
git commit -m "feat: preserve exact PDF evidence geometry"
```

### Task 6: Preserve native table and document structure

**Files:**
- Modify: `core/orchestrator.py:86-173`
- Modify: `core/accuracy/layout_elements.py`
- Modify: `core/accuracy/evidence_span_builder.py`
- Modify: `core/storage/migrations.py`
- Modify: `core/vault.py`
- Test: `tests/test_layout_elements.py`
- Test: `tests/test_parsers.py`

- [ ] **Step 1: Add failing CSV, XLSX, DOCX, and PPTX structure tests**

```python
@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_tabular_parser_preserves_cell_coordinates(tmp_path, extension):
    path = make_table_fixture(tmp_path, extension)
    elements = parse_document_layout(str(path), document_id="doc_1")
    cells = [item for item in elements if item.element_type == "table_cell"]
    assert [(item.row_index, item.column_index) for item in cells] == [
        (0, 0), (0, 1), (1, 0), (1, 1)
    ]
    assert cells[2].header_refs == [cells[0].element_id]
```

Add DOCX tests that distinguish paragraphs from table cells and PPTX tests that preserve slide and shape identity.

- [ ] **Step 2: Run parser tests and verify red**

Run: `python -m pytest tests/test_layout_elements.py tests/test_parsers.py -q`

Expected: assertions fail because current parsers group rows or flatten document structures.

- [ ] **Step 3: Implement native structure adapters**

CSV and XLSX emit a table element, then row and cell elements. DOCX emits paragraphs plus each `document.tables` cell. PPTX emits each text-bearing shape and each native table cell. Use deterministic IDs derived from document ID plus source coordinates.

```python
def element_id(document_id: str, *parts: object) -> str:
    identity = ":".join([document_id, *(str(part) for part in parts)])
    return f"element_{uuid.uuid5(uuid.NAMESPACE_URL, identity).hex}"
```

- [ ] **Step 4: Persist table provenance**

Migration adds `element_id`, `table_id`, `row_index`, `column_index`, and `header_refs_json` to `evidence_spans`. Update insert/list methods to round-trip those values.

- [ ] **Step 5: Verify parser and vault round trips**

Run: `python -m pytest tests/test_layout_elements.py tests/test_parsers.py tests/test_evidence_span_builder.py tests/test_vault_accuracy_layer.py -q`

Expected: all tests pass with stable IDs and preserved table coordinates.

- [ ] **Step 6: Commit**

```bash
git add core/accuracy/layout_elements.py core/accuracy/evidence_span_builder.py core/orchestrator.py core/storage/migrations.py core/vault.py tests/test_layout_elements.py tests/test_parsers.py tests/test_evidence_span_builder.py tests/test_vault_accuracy_layer.py
git commit -m "feat: preserve structured table evidence"
```

---

## Milestone 3: Verification and entities

### Task 7: Add selective critic review and revalidation

**Files:**
- Create: `core/accuracy/critic_agent.py`
- Modify: `core/accuracy/schemas.py`
- Modify: `core/orchestrator.py`
- Modify: `core/storage/migrations.py`
- Modify: `core/vault.py`
- Test: `tests/test_claim_critic.py`
- Test: `tests/test_orchestrator_claim_layer.py`

- [ ] **Step 1: Write failing critic-selection tests**

```python
def test_selects_needs_review_and_high_impact_claims():
    selected = select_claims_for_critic(
        claims=[passed_claim(), review_claim(), high_impact_claim()],
        validations=[passed_result(), review_result(), passed_result()],
        disagreement_claim_ids=set(),
        sample_rate=0.0,
    )
    assert {claim.claim_id for claim in selected} == {"review", "high-impact"}


def test_revised_claim_is_not_promoted_until_revalidated():
    decision = CriticDecision(
        claim_id="claim_1",
        verdict="revise",
        reason="Deadline was inferred",
        revised_claim=claim_with_explicit_deadline(),
        confidence_adjustment=-0.15,
    )
    assert apply_critic_decision(decision).validation_status == "pending"
```

- [ ] **Step 2: Run tests and verify red**

Run: `python -m pytest tests/test_claim_critic.py -q`

Expected: collection fails because critic types and selection do not exist.

- [ ] **Step 3: Add critic models and strict parser**

```python
class CriticDecision(BaseModel):
    claim_id: str
    verdict: Literal["accept", "revise", "reject", "needs_human_review"]
    reason: str
    revised_claim: ExtractedClaim | None = None
    confidence_adjustment: float = Field(ge=-1.0, le=1.0)
    critic_model: str
    reviewed_at: datetime
```

Reject `revise` decisions without `revised_claim` and reject non-revise decisions that include one.

- [ ] **Step 4: Implement selective calls**

Pass the claim and only its cited evidence to the smart model at temperature `0.0`. Include deterministic validation errors/warnings. Persist malformed critic responses as extraction failures with `agent="claim_critic"`.

- [ ] **Step 5: Revalidate revisions and persist decisions**

Accepted claims keep deterministic validation. Revised claims receive application-owned replacement IDs, are inserted with `pending`, and pass through the deterministic validator again. Rejected and human-review claims remain auditable and cannot promote.

- [ ] **Step 6: Verify critic and orchestrator behavior**

Run: `python -m pytest tests/test_claim_critic.py tests/test_orchestrator_claim_layer.py tests/test_vault_accuracy_layer.py -q`

Expected: all tests pass without live model calls.

- [ ] **Step 7: Commit**

```bash
git add core/accuracy/critic_agent.py core/accuracy/schemas.py core/orchestrator.py core/storage/migrations.py core/vault.py tests/test_claim_critic.py tests/test_orchestrator_claim_layer.py tests/test_vault_accuracy_layer.py
git commit -m "feat: add selective claim critic review"
```

### Task 8: Replace slug-only entities with an auditable registry

**Files:**
- Create: `core/accuracy/entity_registry.py`
- Modify: `core/accuracy/entity_canonicalizer.py`
- Modify: `core/accuracy/schemas.py`
- Modify: `core/storage/migrations.py`
- Modify: `core/vault.py`
- Modify: `api.py:980-1060`
- Test: `tests/test_entity_registry.py`
- Test: `tests/test_api_accuracy.py`

- [ ] **Step 1: Write failing alias, merge, and lock tests**

```python
def test_aliases_resolve_to_one_stable_entity(registry):
    entity = registry.create("Data Cleansing Programme", "initiative")
    registry.add_alias(entity.entity_id, "Customer Data Cleanse", source_span_id="span_2")
    assert registry.resolve("Customer Data Cleanse").entity_id == entity.entity_id


def test_human_locked_entity_cannot_auto_merge(registry):
    locked = registry.create("Data Team", "team", human_locked=True)
    candidate = registry.create("Customer Data Team", "team")
    with pytest.raises(HumanLockViolation):
        registry.merge(candidate.entity_id, locked.entity_id, actor="automatic")


def test_merge_history_records_actor_and_reason(registry):
    source = registry.create("CRM Programme", "initiative")
    target = registry.create("CRM", "initiative")
    registry.merge(source.entity_id, target.entity_id, actor="human", reason="Confirmed alias")
    assert registry.list_merge_history()[0]["reason"] == "Confirmed alias"
```

- [ ] **Step 2: Run tests and verify red**

Run: `python -m pytest tests/test_entity_registry.py -q`

Expected: collection fails because the registry does not exist.

- [ ] **Step 3: Add persistence models and migrations**

Create `entity_mentions`, `entity_aliases`, and `entity_merge_history` tables. Keep `canonical_entities` as the stable identity table. Alias uniqueness is scoped by document and analysis run. Merge history is append-only.

```python
class EntityMergeDecision(BaseModel):
    source_entity_id: str
    target_entity_id: str
    actor: Literal["automatic", "human"]
    reason: str
    decided_at: datetime
```

- [ ] **Step 4: Implement deterministic candidates**

Normalise articles, punctuation, case, and known programme suffixes. Exact normalised aliases resolve automatically. Token-similar names produce review candidates but do not merge automatically. Existing `canonical_entity_id()` remains a candidate helper, not the final identity generator.

- [ ] **Step 5: Add human review API operations**

Add endpoints to accept an alias, merge entities, reject a proposed merge, and lock/unlock a canonical entity. Every request records actor `local_user_01`, reason, and timestamp. Return `409` when a lock blocks an automatic operation.

- [ ] **Step 6: Verify registry and API behavior**

Run: `python -m pytest tests/test_entity_registry.py tests/test_api_accuracy.py tests/test_vault_accuracy_layer.py -q`

Expected: all tests pass and merge history survives vault restart.

- [ ] **Step 7: Commit**

```bash
git add api.py core/accuracy/entity_registry.py core/accuracy/entity_canonicalizer.py core/accuracy/schemas.py core/storage/migrations.py core/vault.py tests/test_entity_registry.py tests/test_api_accuracy.py tests/test_vault_accuracy_layer.py
git commit -m "feat: add auditable canonical entity registry"
```

### Task 9: Enforce the claim graph-promotion boundary

**Files:**
- Modify: `core/accuracy/graph_promoter.py`
- Modify: `core/accuracy/schemas.py`
- Modify: `core/storage/migrations.py`
- Modify: `core/vault.py:574-613`
- Modify: `core/orchestrator.py`
- Test: `tests/test_claim_graph_promoter.py`
- Test: `tests/test_vault_accuracy_layer.py`
- Test: `tests/test_claim_cutover.py`

- [ ] **Step 1: Write failing complete-edge and database-invariant tests**

```python
def test_promoted_edge_contains_complete_provenance(validated_claim, registry):
    edge = promote_claim(validated_claim, registry, promotion_version="2")
    assert edge.claim_id == validated_claim.claim_id
    assert edge.evidence_span_ids == validated_claim.evidence_span_ids
    assert edge.validation_status == "passed"
    assert edge.edge_origin == "claim"
    assert edge.modality == validated_claim.modality


def test_database_rejects_claim_edge_without_passed_validation(vault):
    with pytest.raises(sqlite3.IntegrityError):
        vault.insert_graph_topology(
            nodes=[],
            edges=[claim_edge(claim_id="missing")],
            source_chunk_id="claim_layer",
            document_id="doc_1",
        )
```

- [ ] **Step 2: Run tests and verify red**

Run: `python -m pytest tests/test_claim_graph_promoter.py tests/test_claim_cutover.py -q`

Expected: promoter output lacks full fields and SQLite accepts incomplete claim edges.

- [ ] **Step 3: Return typed promotion results**

```python
class PromotedGraphEdge(BaseModel):
    edge_id: str
    document_id: str
    analysis_run_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    claim_id: str
    modality: str
    certainty: str
    confidence: float
    evidence_span_ids: list[str]
    validation_status: Literal["passed"]
    edge_origin: Literal["claim"] = "claim"
    promotion_version: str
    promoted_at: datetime
```

The promoter receives a passed `ValidationResult` and resolved entities separately; it never trusts the claim's stored status alone.

- [ ] **Step 4: Add conditional SQLite triggers**

Create triggers for `edge_origin = 'claim'` that reject null/empty claim IDs, empty evidence JSON, or absent passed validation for the same document and analysis run. Legacy/shadow comparison edges use `edge_origin = 'legacy'` or `edge_origin = 'claim_shadow'` and cannot be queried as authoritative claim edges.

- [ ] **Step 5: Make promotion idempotent and transactional**

Derive edge IDs from `(analysis_run_id, claim_id, relationship_type, source_entity_id, target_entity_id)`. Promote all claims for one document inside one transaction; a failed edge rolls back that promotion batch.

- [ ] **Step 6: Verify promotion and legacy compatibility**

Run: `python -m pytest tests/test_claim_graph_promoter.py tests/test_claim_cutover.py tests/test_vault_accuracy_layer.py tests/test_simulator.py -q`

Expected: all tests pass; legacy edges remain readable while incomplete claim edges fail.

- [ ] **Step 7: Commit**

```bash
git add core/accuracy/graph_promoter.py core/accuracy/schemas.py core/orchestrator.py core/storage/migrations.py core/vault.py tests/test_claim_graph_promoter.py tests/test_claim_cutover.py tests/test_vault_accuracy_layer.py tests/test_simulator.py
git commit -m "feat: enforce claim graph promotion invariants"
```

---

## Milestone 4: Findings and consumer safety

### Task 10: Implement deterministic contradiction rules and persisted findings

**Files:**
- Create: `core/accuracy/contradiction_rules.py`
- Create: `core/accuracy/finding_store.py`
- Modify: `core/accuracy/schemas.py`
- Modify: `core/storage/migrations.py`
- Modify: `core/vault.py`
- Modify: `core/orchestrator.py`
- Test: `tests/test_contradiction_rules.py`
- Test: `tests/test_finding_store.py`

- [ ] **Step 1: Write one failing test for every required rule family**

```python
@pytest.mark.parametrize(
    ("fixture_name", "finding_type"),
    [
        ("dependency_clash", "dependency_clash"),
        ("dependency_cycle", "dependency_cycle"),
        ("temporal_clash", "temporal_clash"),
        ("scope_clash", "scope_clash"),
        ("resource_clash", "resource_clash"),
        ("governance_clash", "governance_clash"),
        ("budget_clash", "budget_clash"),
        ("owner_gap", "owner_gap"),
        ("assumption_risk", "assumption_risk"),
        ("orphan_objective", "orphan_objective"),
        ("quality_clash", "quality_clash"),
    ],
)
def test_rule_fixture_emits_expected_finding(fixture_name, finding_type):
    claims = load_rule_fixture(fixture_name)
    findings = evaluate_rules(claims)
    assert [item.finding_type for item in findings] == [finding_type]
    assert findings[0].claims_involved
    assert findings[0].evidence_span_ids
```

Add paired negative fixtures proving each rule does not fire when its critical condition is absent.

```python
@pytest.mark.parametrize(
    "fixture_name",
    [
        "dependency_without_blocker",
        "acyclic_dependencies",
        "valid_temporal_order",
        "consistent_scope",
        "resource_within_capacity",
        "approval_before_start",
        "budget_within_limit",
        "owned_critical_dependency",
        "validated_assumption",
        "objective_linked_work",
        "quality_gate_before_delivery",
    ],
)
def test_rule_negative_fixture_emits_no_finding(fixture_name):
    assert evaluate_rules(load_rule_fixture(fixture_name)) == []
```

- [ ] **Step 2: Run rule tests and verify red**

Run: `python -m pytest tests/test_contradiction_rules.py tests/test_finding_store.py -q`

Expected: collection fails because the rule modules do not exist.

- [ ] **Step 3: Define the rule interface**

```python
class RuleContext(BaseModel):
    document_id: str
    analysis_run_id: str
    claims: list[ExtractedClaim]
    entities: list[CanonicalEntity]


class ContradictionRule(Protocol):
    rule_id: str
    version: str

    def evaluate(self, context: RuleContext) -> list[Finding]: ...
```

Each rule returns candidates derived only from passed claims. Severity uses the existing 1-5 internal scale; API presentation maps it to labels.

- [ ] **Step 4: Implement pure deterministic rules**

Implement graph traversal for cycles/orphans, interval comparison for temporal conflicts, set intersections for scope/resource/owner rules, and typed predicate matching for governance, budget, assumptions, and quality. Keep recommendation text deterministic and specific to the involved entities.

- [ ] **Step 5: Persist immutable finding generations**

Store findings by `(finding_id, analysis_run_id, rule_id, rule_version)`. Human review state is a separate append-only decision table so rerunning rules does not erase prior decisions.

- [ ] **Step 6: Verify all positive and negative fixtures**

Run: `python -m pytest tests/test_contradiction_rules.py tests/test_finding_store.py tests/test_vault_reporting.py -q`

Expected: all rule families pass both positive and false-positive tests.

- [ ] **Step 7: Commit**

```bash
git add core/accuracy/contradiction_rules.py core/accuracy/finding_store.py core/accuracy/schemas.py core/orchestrator.py core/storage/migrations.py core/vault.py tests/test_contradiction_rules.py tests/test_finding_store.py tests/test_vault_reporting.py
git commit -m "feat: add evidence-backed contradiction rules"
```

### Task 11: Gate reports and simulations on claim authority and freshness

**Files:**
- Modify: `core/risk_finding.py`
- Modify: `core/simulator.py`
- Modify: `api.py:200-440`
- Modify: `api.py:724-1350`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/AccuracyWorkspace.tsx`
- Modify: `frontend/src/components/GeneratedReportsPanel.tsx`
- Test: `tests/test_risk_finding.py`
- Test: `tests/test_api_accuracy.py`
- Test: `tests/test_api_executive.py`
- Test: `tests/test_api_risk_simulation.py`
- Test: `frontend/src/components/GeneratedReportsPanel.grounding.test.tsx`
- Test: `frontend/e2e/app-v2.spec.ts`

- [ ] **Step 1: Write failing consumer-safety tests**

```python
def test_high_risk_finding_rejects_unverified_claim():
    with pytest.raises(UnverifiedFindingError):
        build_risk_finding(
            model_result(severity=5),
            risk_type="dependency",
            source_name="CRM",
            target_name="Data Cleanse",
            relationship="REQUIRES",
            claim_validation_status="needs_review",
        )


def test_stale_narrative_cannot_export(client, seeded_stale_report):
    response = client.get(f"/api/v1/export/pdf/{seeded_stale_report.document_id}")
    assert response.status_code == 409
    assert response.json()["detail"] == "Report is stale; regenerate it before export."
```

- [ ] **Step 2: Run backend tests and verify red**

Run: `python -m pytest tests/test_risk_finding.py tests/test_api_executive.py tests/test_api_risk_simulation.py -q`

Expected: unverified elevated findings and stale exports are currently accepted.

- [ ] **Step 3: Add one authority policy function**

```python
def can_elevate_finding(*, severity: int, validation_status: str, freshness_status: str) -> bool:
    if freshness_status != "current":
        return False
    if severity >= 3 and validation_status != "passed":
        return False
    return True
```

Use this policy in finding assembly, report grounding, simulators, and exports. Do not duplicate slightly different conditions in each consumer.

- [ ] **Step 4: Extend additive API types**

Accuracy responses include `pipeline_mode`, `authoritative_origin`, `analysis_run_id`, `freshness_status`, `critic_queue`, `entity_review_queue`, and `release_gate`. Existing clients may ignore these keys.

- [ ] **Step 5: Add UI states and tests**

Display stale badges, pipeline authority, review counts, and release-gate failures. Disable export for stale reports. Keep report layout and graph controls unchanged.

- [ ] **Step 6: Verify backend, frontend, and browser behavior**

Run: `python -m pytest tests/test_risk_finding.py tests/test_api_accuracy.py tests/test_api_executive.py tests/test_api_risk_simulation.py -q`

Run: `cd frontend && npm.cmd test && npm.cmd run typecheck && npm.cmd run build && npm.cmd run e2e`

Expected: all commands pass; Playwright verifies stale messaging and review navigation without live model calls.

- [ ] **Step 7: Commit**

```bash
git add api.py core/risk_finding.py core/simulator.py frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/components/AccuracyWorkspace.tsx frontend/src/components/GeneratedReportsPanel.tsx frontend/src/components/GeneratedReportsPanel.grounding.test.tsx frontend/e2e/app-v2.spec.ts tests/test_risk_finding.py tests/test_api_accuracy.py tests/test_api_executive.py tests/test_api_risk_simulation.py
git commit -m "feat: gate reports on verified current evidence"
```

---

## Milestone 5: Evaluation and measured cutover

### Task 12: Build and validate the 60-document gold corpus

**Files:**
- Create: `core/evals/__init__.py`
- Create: `core/evals/corpus.py`
- Create: `tests/fixtures/accuracy_corpus/manifest.json`
- Create: `tests/fixtures/accuracy_corpus/documents/`
- Create: `tests/fixtures/accuracy_corpus/labels/`
- Create: `tests/test_accuracy_corpus.py`

- [ ] **Step 1: Write the corpus contract test**

```python
EXPECTED_CATEGORIES = {
    "clean_structured",
    "messy_pdf",
    "table_heavy",
    "contradictory",
    "ambiguous",
    "false_positive_trap",
}


def test_gold_corpus_has_ten_labelled_documents_per_category():
    corpus = load_corpus("tests/fixtures/accuracy_corpus/manifest.json")
    assert len(corpus.documents) == 60
    assert {item.category for item in corpus.documents} == EXPECTED_CATEGORIES
    for category in EXPECTED_CATEGORIES:
        assert sum(item.category == category for item in corpus.documents) == 10
    assert all(item.labels.evidence_spans for item in corpus.documents)
    assert all(item.labels.claims is not None for item in corpus.documents)
    assert all(item.labels.findings is not None for item in corpus.documents)
```

- [ ] **Step 2: Run the contract and verify red**

Run: `python -m pytest tests/test_accuracy_corpus.py -q`

Expected: collection fails because the corpus loader and manifest do not exist.

- [ ] **Step 3: Implement strict corpus schemas**

```python
class CorpusDocument(BaseModel):
    fixture_id: str
    category: Literal[
        "clean_structured", "messy_pdf", "table_heavy",
        "contradictory", "ambiguous", "false_positive_trap"
    ]
    split: Literal["development", "holdout"]
    document_path: str
    labels_path: str
    source_sha256: str


class CorpusManifest(BaseModel):
    corpus_version: str
    documents: list[CorpusDocument]


class ExpectedEdge(BaseModel):
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    claim_id: str


class ExpectedFinding(BaseModel):
    finding_type: str
    claims_involved: list[str]
    evidence_span_ids: list[str]


class GoldLabels(BaseModel):
    evidence_spans: list[EvidenceSpan]
    entities: list[CanonicalEntity]
    claims: list[ExtractedClaim]
    promoted_edges: list[ExpectedEdge]
    findings: list[ExpectedFinding]
    forbidden_finding_types: list[str] = Field(default_factory=list)
```

The loader verifies file existence, source hashes, unique fixture IDs, valid label references, and a fixed 48-development/12-holdout split with two holdouts per category.

- [ ] **Step 4: Add the labelled fixtures category by category**

For each category, add ten documents and ten label JSON files. Labels contain exact evidence text/coordinates, canonical entities, claims, promoted edges, and expected findings. Each false-positive trap explicitly lists forbidden finding types. Each fixture is reviewed manually before its manifest hash is recorded; generated labels are not accepted as gold labels.

- [ ] **Step 5: Verify corpus completeness and determinism**

Run: `python -m pytest tests/test_accuracy_corpus.py -q`

Expected: one passing corpus test set, exactly 60 fixtures, no missing labels, and no hash mismatches.

- [ ] **Step 6: Commit**

```bash
git add core/evals/__init__.py core/evals/corpus.py tests/test_accuracy_corpus.py tests/fixtures/accuracy_corpus
git commit -m "test: add claim accuracy gold corpus"
```

### Task 13: Compute measured quality gates and shadow comparisons

**Files:**
- Create: `core/evals/metrics.py`
- Modify: `core/evaluation.py`
- Modify: `tests/test_claim_layer_evaluation.py`
- Create: `tests/test_accuracy_metrics.py`
- Modify: `.github/workflows/evaluation.yml`

- [ ] **Step 1: Write failing metric tests with known confusion matrices**

```python
def test_precision_and_recall_use_predictions_not_fixture_constants():
    result = precision_recall(
        expected={"a", "b", "c"},
        predicted={"b", "c", "d"},
    )
    assert result == {"true_positive": 2, "false_positive": 1, "false_negative": 1,
                      "precision": pytest.approx(2 / 3), "recall": pytest.approx(2 / 3)}


def test_false_positive_rate_counts_forbidden_findings():
    assert false_positive_rate(predicted={"scope_clash"}, forbidden={"scope_clash", "budget_clash"}) == 0.5
```

- [ ] **Step 2: Run tests and verify red**

Run: `python -m pytest tests/test_accuracy_metrics.py -q`

Expected: collection fails because measured metric functions do not exist.

- [ ] **Step 3: Implement metrics**

Implement exact and canonicalised matching for evidence, entities, claims, dates, dependencies, and findings. Every metric returns counts plus rates so zero denominators are explicit. Aggregate macro and micro results by corpus category and split.

- [ ] **Step 4: Execute deterministic corpus predictions**

Use stored mocked extraction responses for the normal CI evaluation. Store predictions separately from gold labels. `DIAMOND_MINER_LIVE_EVALUATION=1` enables release-candidate runs against configured models and writes an untracked result JSON.

- [ ] **Step 5: Enforce the release gate**

```python
RELEASE_THRESHOLDS = {
    "schema_valid_rate": {"min": 0.95},
    "evidence_linkage_accuracy": {"min": 0.90},
    "explicit_dependency_recall": {"min": 0.85},
    "contradiction_false_positive_rate": {"max": 0.10},
    "promoted_without_evidence": {"max": 0},
    "accepted_without_validation": {"max": 0},
    "claim_edges_without_claim_id": {"max": 0},
}
```

Require all thresholds on the holdout split for three consecutive candidate result files. Record model, prompt, parser, schema, and corpus versions with each result.

- [ ] **Step 6: Update CI and verify evaluation**

Run: `python -m pytest -m evaluation -q`

Expected: deterministic corpus and existing baseline evaluations pass. The workflow runs this command whenever accuracy, parser, graph, finding, or corpus files change.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/evaluation.yml core/evaluation.py core/evals/metrics.py tests/test_accuracy_metrics.py tests/test_claim_layer_evaluation.py
git commit -m "test: enforce measured claim accuracy gates"
```

### Task 14: Cut over authority and complete rollback verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`
- Modify: `core/accuracy/pipeline_mode.py`
- Modify: `core/orchestrator.py`
- Modify: `api.py`
- Modify: `tests/test_claim_cutover.py`
- Modify: `tests/test_run_startup.py`
- Modify: `frontend/e2e/app-v2.spec.ts`

- [ ] **Step 1: Write authority and rollback acceptance tests**

```python
def test_claims_mode_never_calls_legacy_deconstructor(monkeypatch, orchestrator, document):
    monkeypatch.setenv("DIAMOND_MINER_PIPELINE_MODE", "claims")
    legacy = Mock(side_effect=AssertionError("legacy extraction called"))
    monkeypatch.setattr(DeconstructorAgent, "extract_topology", legacy)
    orchestrator.run_ingestion_pipeline(document)
    legacy.assert_not_called()


def test_shadow_mode_keeps_legacy_authoritative(monkeypatch, orchestrator, document):
    monkeypatch.setenv("DIAMOND_MINER_PIPELINE_MODE", "shadow")
    orchestrator.run_ingestion_pipeline(document)
    assert orchestrator.vault.authoritative_edge_origin(orchestrator.document_id) == "legacy"
    assert orchestrator.vault.list_graph_agreement(orchestrator.document_id)


def test_claims_mode_can_return_to_shadow_without_losing_reviews(vault):
    review_id = seed_review_decision(vault)
    switch_pipeline_mode("shadow")
    assert vault.get_review_decision(review_id) is not None
```

- [ ] **Step 2: Run cutover tests and verify red**

Run: `python -m pytest tests/test_claim_cutover.py tests/test_run_startup.py -q`

Expected: at least the authority-default and rollback assertions fail before cutover.

- [ ] **Step 3: Require gate evidence before selecting claims authority**

Configuration may select `claims` only when a current release-gate result exists for the configured parser/schema/model/corpus versions. API returns `409` with the exact failing metrics when the gate is absent or failed. Tests may inject a signed local gate fixture.

- [ ] **Step 4: Perform the staged default transition**

First release: default unset mode to `shadow`. After three passing candidate builds recorded by Task 13, change the default to `claims` for new installations while existing `.env` files retain their explicit mode. Keep `legacy` accepted for one release and emit a deprecation warning.

- [ ] **Step 5: Document operations**

README documents mode semantics, gate inspection, reanalysis, stale artefacts, entity review, rollback, and the requirement to build `/app-v2`. CLAUDE and AGENTS guidance state that no claim authority change may bypass the evaluation marker.

- [ ] **Step 6: Run complete verification**

Run: `python -m pytest tests/ -q`

Expected: all backend tests pass with no live API calls.

Run: `python -m pytest -m evaluation -q`

Expected: all deterministic evaluation gates pass.

Run: `cd frontend && npm.cmd test && npm.cmd run typecheck && npm.cmd run build && npm.cmd run e2e`

Expected: unit tests, TypeScript, production build, and Playwright all pass.

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only intentionally preserved user-owned untracked files may remain.

- [ ] **Step 7: Perform browser smoke testing**

Start `python run.py`, open `/app-v2`, ingest one clean and one contradictory fixture in `shadow`, confirm provenance/review/gate displays, then repeat the clean fixture in `claims`. Confirm no browser console errors and that Reports and Accuracy remain usable at desktop and narrow widths.

- [ ] **Step 8: Commit**

```bash
git add .env.example README.md CLAUDE.md AGENTS.md api.py core/accuracy/pipeline_mode.py core/orchestrator.py tests/test_claim_cutover.py tests/test_run_startup.py frontend/e2e/app-v2.spec.ts
git commit -m "feat: cut over to validated claim authority"
```

---

## Completion audit

Before merging the implementation branch, verify each approved design requirement against authoritative evidence:

| Requirement | Evidence |
|---|---|
| Byte-level source identity and stale generations | `tests/test_manifest_freshness.py` plus analysis-run rows |
| Exact PDF and table provenance | parser fixtures and evidence-span round trips |
| Claims cannot self-authorise | validator and persistence tests |
| Selective critic cannot directly promote | critic and orchestrator tests |
| Auditable aliases, merges, and locks | entity registry persistence/API tests |
| Claim edges require passed validation and evidence | SQLite trigger tests |
| All contradiction families and false-positive controls | positive/negative rule fixtures |
| Reports/simulations reject stale or unverified authority | API and consumer tests |
| Sixty labelled fixtures with a holdout split | corpus contract and recorded hashes |
| Measured release thresholds pass three times | versioned candidate gate results |
| Claims mode excludes legacy authoritative writes | cutover tests and browser smoke |
| Rollback retains audit artefacts | rollback integration test |

Do not treat passing unit tests alone as evidence that the measured cutover gate passed.
