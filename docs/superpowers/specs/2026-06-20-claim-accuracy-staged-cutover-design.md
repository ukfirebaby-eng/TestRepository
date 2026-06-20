# Claim-Accuracy Staged Cutover Design

**Date:** 2026-06-20

**Status:** Approved for implementation planning

## Purpose

Bring Diamond Miner into conformance with the claim-centred evidence requirement without replacing a working extraction pipeline before accuracy is measured. The completed system will build authoritative graph topology from validated, evidence-backed claims. The existing chunk-to-graph path will remain available temporarily as a comparison and rollback mechanism.

## Problem

Diamond Miner already contains a first claim-accuracy slice: document manifests, evidence spans, typed claims, deterministic validation, basic entity canonicalisation, graph promotion, extraction-failure storage, accuracy telemetry, review decisions, and evaluation thresholds. It is not yet the authoritative pipeline.

The remaining gaps are material:

- legacy topology extraction still runs for every chunk;
- claim promotion is controlled by a hidden secondary flag;
- sentence evidence reuses block-level geometry;
- table structure is reduced to text rows;
- deterministic validation does not prove quote containment, document ownership, or predicate compatibility;
- canonicalisation is string normalisation rather than a managed entity registry;
- there is no selective claim critic;
- graph provenance rules are not enforced by the database;
- contradiction coverage is narrow;
- the evaluation corpus is too small to justify cutover.

## Goals

1. Make every authoritative graph edge traceable to a validated claim and exact source evidence.
2. Reject malformed or unsupported claims without hiding extraction failures.
3. Preserve tables, dates, owners, modality, certainty, and source geometry accurately.
4. Resolve entity aliases through an auditable, human-correctable registry.
5. Generate medium-, high-, and critical-risk findings only from verified claims.
6. Measure extraction and finding accuracy against a labelled corpus before cutover.
7. Replace direct topology extraction through a reversible staged rollout.

## Non-Goals

- removing the existing simulators;
- adding graph neural networks;
- redesigning the command-centre visual language;
- making prompt changes the primary accuracy control;
- requiring critic calls for claims that deterministic checks can conclusively accept or reject;
- reorganising all existing `core/` modules before behavior is stable.

## Architectural Decision

Use a staged cutover with three explicit pipeline modes:

- `legacy`: current chunk-to-graph extraction is authoritative;
- `shadow`: legacy remains authoritative while the claim pipeline runs, records metrics, and compares graph outputs;
- `claims`: validated claim promotion is authoritative; legacy extraction may run only when an explicit diagnostic option is enabled.

Expose this as `DIAMOND_MINER_PIPELINE_MODE`. During migration, map the existing `DIAMOND_MINER_CLAIM_LAYER` and `DIAMOND_MINER_USE_CLAIM_PROMOTION` settings to compatible modes and emit a deprecation warning. Do not maintain three independent Boolean switches.

The mode transition is one-way by release policy, not by schema: production moves from `legacy` to `shadow`, then to `claims` after the quality gate passes. Operators can return to the previous mode for one release without deleting claim artefacts.

## Target Data Flow

```text
Document bytes
  -> manifest and source hash
  -> layout-aware parser
  -> evidence spans and table structure
  -> typed claim proposals
  -> deterministic validation
  -> selective critic review
  -> canonical entity resolution
  -> validated graph promotion
  -> deterministic contradiction rules
  -> evidence-backed findings
  -> reports and simulations
```

In `shadow` mode, legacy topology extraction runs beside this flow. Comparison metrics never mutate the authoritative graph.

## Component Design

### 1. Manifest and freshness service

Extend the existing manifest model and vault methods rather than introducing a parallel store.

Responsibilities:

- hash original document bytes before parsing;
- record MIME type, parser/schema/model versions, anchor date, and validation state;
- detect an existing document identity with a changed source hash;
- mark all derived spans, claims, graph edges, findings, and reports stale;
- require re-analysis before stale artefacts are presented as current.

`validation_status` remains `pending | partial | passed | failed`. Freshness is represented separately as `current | stale`, avoiding misuse of validation status.

### 2. Layout-aware evidence service

Keep format-specific parsing in the orchestrator initially, but return a common layout element structure before evidence spans are built.

The common structure contains:

- stable element ID;
- document/page/slide/sheet coordinates;
- section hierarchy;
- element type;
- text;
- exact geometry where available;
- table, row, column, and header identifiers where applicable.

PDF sentence spans must derive geometry from PyMuPDF words or spans rather than inheriting a full block box. CSV/XLSX/DOCX/PPTX parsers preserve their native row, cell, paragraph, or shape identity even when physical page geometry is unavailable.

### 3. Claim extraction service

Retain `ExtractedClaim` as the LLM boundary. Extraction accepts bounded evidence batches and returns only typed Pydantic objects or persisted failures.

Required behavior:

- claim IDs are assigned or normalised by application code;
- all evidence span IDs belong to the same document;
- source quotes are exact substrings of cited evidence after defined whitespace normalisation;
- output is deduplicated by semantic claim identity, not source quote alone;
- raw malformed payloads are retained with sensitive values redacted;
- batch metrics are included in ingestion telemetry.

The legacy `DeconstructorAgent` is not rewritten to emit claims. It remains the legacy adapter until cutover and is then removed from the authoritative ingestion path.

### 4. Deterministic validation service

Validation receives the claim plus its resolved evidence and entity context. It performs:

- schema and required-field validation;
- claim-type/predicate compatibility;
- document and evidence ownership checks;
- source-quote containment;
- ISO date and date-order checks;
- confidence bounds;
- explicit/implied/inferred promotion policy;
- generic/self-edge rejection;
- entity-resolution readiness;
- promotion provenance completeness.

Validation results store validator name/version, status, errors, warnings, promotion decision, and timestamp. Errors fail the claim; warnings route it to review. A claim cannot set its own final validation status.

### 5. Selective critic service

The critic reviews only claims that are:

- deterministically marked `needs_review`;
- proposed for medium-, high-, or critical-impact findings;
- involved in a graph disagreement during shadow mode; or
- sampled for ongoing quality assurance.

The critic returns `accept | revise | reject | needs_human_review`, a reason, corrected structured fields when revising, and a confidence adjustment. Revised claims run through deterministic validation again. The critic cannot directly promote graph data.

### 6. Canonical entity registry

Replace slug-only canonicalisation with four auditable stores:

- canonical entities;
- entity mentions;
- aliases;
- merge history.

Deterministic normalisation proposes candidates first. Similarity and contextual matching may propose merges, but ambiguous merges require human review. Human-locked entities cannot be automatically renamed or merged. Graph edges reference stable entity IDs; aliases never become permanent node IDs.

### 7. Graph promotion boundary

Create a single promotion service that accepts only a validated claim projection. It creates or reuses canonical nodes and writes edges carrying:

- claim ID;
- evidence span IDs;
- modality;
- certainty;
- confidence;
- validation status;
- promotion timestamp and promoter version.

During `legacy` and `shadow` modes, nullable provenance columns remain for legacy edges. Before `claims` becomes authoritative, migrate legacy and claim edges into distinguishable stores or add an edge-origin discriminator. Once legacy writes are disabled, database triggers reject claim-origin edges without a passed claim and evidence.

### 8. Contradiction and finding engine

Rules operate on validated claims and canonical entities, not raw LLM topology. Implement the following deterministic families:

- dependency clash and cycle;
- temporal clash;
- scope inclusion/exclusion clash;
- resource-capacity clash;
- governance/approval ordering clash;
- budget constraint clash;
- owner gap;
- unvalidated assumption risk;
- orphan objective linkage;
- quality/deadline clash.

Each finding stores involved claims, evidence spans, confidence components, reasoning summary, recommended action, rule/version, and human review state. LLMs may explain or recommend mitigations after the deterministic rule identifies the candidate; they do not decide whether the underlying contradiction exists.

### 9. Evaluation and release gate

Create a versioned gold corpus with at least 60 documents:

- 10 clean structured strategies;
- 10 messy PDFs;
- 10 table-heavy documents;
- 10 deliberate contradictions;
- 10 ambiguous documents;
- 10 false-positive traps.

Every fixture includes labelled evidence spans, entities, claims, relationships, and expected findings. Training/prompt-development and holdout sets are separate.

The cutover gate requires:

- at least 95% schema-valid output;
- at least 90% evidence linkage accuracy;
- at least 85% explicit dependency recall;
- less than 10% contradiction false-positive rate;
- zero promoted claims without evidence;
- zero accepted claims without completed validation;
- zero claim-origin edges without claim IDs;
- no regression beyond an agreed tolerance in ingestion completion and latency;
- a passing holdout run on three consecutive candidate builds.

Metrics report precision and recall separately for entities, claims, dates, dependencies, and contradiction families. Fixture constants cannot substitute for measured predictions.

## Persistence Changes

Use explicit SQLite migrations, applied transactionally and recorded in a schema-migrations table. Migrations extend the current database without deleting legacy data.

Required additions:

- manifest freshness and supersession metadata;
- evidence layout/table coordinates;
- versioned validation results with errors and warnings;
- critic decisions;
- entity mentions, aliases, and merge history;
- graph edge origin and complete claim provenance;
- persisted findings and rule versions;
- artefact freshness markers.

Vault methods remain the storage API. Route and agent code must not issue ad hoc SQL.

## API and UI Behavior

Extend existing additive APIs rather than replacing response shapes.

- ingestion status reports parser, extraction, validation, critic, and promotion counts;
- the accuracy endpoint exposes failed spans, review queues, freshness, gate metrics, and graph agreement;
- review APIs support claim and entity decisions with an audit timestamp;
- reports exclude rejected claims and identify human-confirmed evidence;
- stale reports and findings are visibly marked and cannot be exported as current without regeneration;
- configuration exposes pipeline mode and explains the current authority/rollback state.

The command centre remains responsible for review and provenance presentation; no general UI redesign is included.

## Failure Handling

- Parser failure marks the manifest failed and stops authoritative promotion.
- Individual span extraction failure is persisted and permits partial ingestion.
- Validation and critic failures never silently become empty success.
- Promotion is idempotent and transactional per document.
- A failed claim-pipeline run in `shadow` mode leaves the legacy result available but visibly records the accuracy failure.
- A failed claim-pipeline run in `claims` mode does not fall back silently; the document remains partial/failed until retried or an operator explicitly selects legacy mode.
- Re-analysis supersedes prior artefacts rather than mixing generations.

## Testing Strategy

All implementation uses red-green-refactor with focused tests before broader suites.

Test layers:

1. Pydantic and pure-function unit tests for schemas, validators, rules, and canonicalisation.
2. SQLite contract tests for migrations, invariants, supersession, and deletion.
3. Parser fixtures for PDF geometry and table-preserving formats.
4. Orchestrator integration tests with mocked LLM responses and all pipeline modes.
5. API tests for telemetry, review, stale-state, and configuration compatibility.
6. Frontend component and Playwright tests for review and provenance workflows.
7. Deterministic evaluation runs for every commit affecting extraction or findings.
8. Explicitly enabled live-model evaluation for release candidates.

No automated test may require a live model call unless marked as live evaluation.

## Delivery Milestones

### Milestone 1: Integrity foundation

Add versioned migrations, byte-level source identity, freshness propagation, validator context, and unified pipeline mode. Continue legacy authority.

### Milestone 2: Source fidelity

Implement common layout elements, exact PDF sentence geometry, and structured table evidence across supported formats.

### Milestone 3: Verification and entities

Add selective critic review, the canonical entity registry, human overrides, and revised-claim revalidation.

### Milestone 4: Findings

Introduce the deterministic contradiction library, persisted evidence-backed findings, and report/simulation gating.

### Milestone 5: Measured cutover

Complete the gold corpus, run shadow comparisons, satisfy the release gate, switch the default to `claims`, retain rollback for one release, then remove authoritative legacy writes.

Each milestone must leave the application runnable and independently testable. No milestone may depend on uncommitted work from a later milestone.

## Rollout and Rollback

1. Ship `shadow` mode with no change to user-visible authoritative results.
2. Collect quality, disagreement, latency, and review metrics.
3. Resolve systematic mismatch classes and pass three consecutive holdout gates.
4. Change new installations to `claims`; retain existing installations in `shadow` until explicitly migrated.
5. After one stable release, default all installations to `claims` while retaining explicit legacy rollback.
6. After the rollback window, remove legacy writes and enforce database provenance invariants.

Rollback changes pipeline authority only. It never deletes claim artefacts, review decisions, or evaluation evidence.

## Completion Criteria

The upgrade is complete when:

- claim mode is the default authoritative ingestion path;
- every claim-origin edge is database-enforced to reference passed validation and evidence;
- exact evidence can be retrieved for every promoted claim and finding;
- table claims retain row/cell provenance;
- entity merges and human overrides are auditable;
- all required contradiction families have deterministic tests;
- the full evaluation corpus and holdout gate pass for three consecutive candidate builds;
- reports and simulations cannot elevate rejected, stale, or unverified claims;
- legacy mode has completed its rollback window and no longer writes authoritative topology.
