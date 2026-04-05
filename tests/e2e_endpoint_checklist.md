# End-to-End Endpoint Testing Checklist

**Test Document:** `tests/e2e_test_document.md` (Project Apex)
**Upload via:** UI drag-and-drop or `curl -X POST http://localhost:8000/api/v1/ingest -F "file=@tests/e2e_test_document.md"`

After ingestion completes, replace `{doc_id}` below with the returned `document_id`.

---

## Pre-requisites

- [ ] Server running (`python run.py`)
- [ ] Valid LLM API key configured (`.env`)
- [ ] Document uploaded and ingestion complete (check `GET /api/v1/status/{job_id}`)

---

## 1. Document Management

### GET /api/v1/documents
- [ ] Returns 200
- [ ] Response contains `documents` array
- [ ] Project Apex document appears with `id`, `name`, `created_at`

### DELETE /api/v1/documents/{doc_id}
- [ ] Returns `{status: "deleted"}` (test last, after all other checks)

---

## 2. Canvas (Graph Topology)

### GET /api/v1/canvas/{doc_id}
- [ ] Returns 200
- [ ] `nodes` array is non-empty (expect 10+ nodes)
- [ ] `edges` array is non-empty (expect 15+ edges)
- [ ] Edge types include: REQUIRES, BLOCKS, PRODUCES, MODIFIES, CONTRADICTS, RELATES_TO
- [ ] `friction_lines` array is non-empty
- [ ] `fragility_lines` array is non-empty
- [ ] `chronological_friction_lines` array is non-empty
- [ ] At least one node has `start_date` and `end_date` in temporal metadata

### Expected Nodes (verify by name)
- [ ] Central Authentication Service
- [ ] API Gateway
- [ ] Customer Portal
- [ ] Payment Processing Module
- [ ] Analytics Engine
- [ ] Notification Service
- [ ] Database Cluster
- [ ] Legacy Data Warehouse Migration (or similar)
- [ ] Regulatory Compliance Audit (or similar)

### Expected Edge Types
- [ ] REQUIRES: API Gateway -> Central Authentication Service
- [ ] BLOCKS: Regulatory Compliance Audit -> Payment Processing Module
- [ ] PRODUCES: API Gateway -> (response payloads)
- [ ] MODIFIES: Notification Service -> Database Cluster
- [ ] CONTRADICTS: Analytics Engine <-> GDPR compliance (data retention)
- [ ] RELATES_TO: Legacy Data Warehouse -> Analytics Engine

---

## 3. Friction Queue (ITDO Dashboard)

### GET /api/v1/reports/friction-queue/{doc_id}
- [ ] Returns 200
- [ ] `friction_queue` array is non-empty
- [ ] Contains items with `type: "structural"` (contradictions)
- [ ] Contains items with `type: "chronological"` (schedule conflicts)
- [ ] Each item has: `source_node_id`, `target_node_id`, `diamond`, `provenance_ids`

### Expected Friction Lines
- [ ] Customer Portal vs Regulatory Compliance Audit (launch before audit completes)
- [ ] Payment Processing Module vs Regulatory Compliance Audit (PCI-DSS timing)
- [ ] Analytics Engine vs Legacy Data Warehouse Migration (schedule overlap)
- [ ] Analytics Engine vs GDPR data retention contradiction
- [ ] Payment Processing Module vs Central Authentication Service (token expiry conflict)

---

## 4. Bottlenecks (Hub & Spoke)

### GET /api/v1/reports/bottlenecks/{doc_id}
- [ ] Returns 200
- [ ] `bottlenecks` array is non-empty
- [ ] Central Authentication Service appears as a hub (in-degree >= 3)
- [ ] Each bottleneck has: `node_id`, `name`, `dependency_count`

---

## 5. Schedule Collapse

### GET /api/v1/reports/schedule-collapse/{doc_id}
- [ ] Returns 200
- [ ] `schedule_collapse` array is non-empty
- [ ] At least one entry with negative slack (Analytics Engine starts before Data Migration ends)
- [ ] Each entry has: `predecessor`, `successor`, `pred_end`, `succ_start`, `negative_slack_days`

---

## 6. Risk Matrix

### GET /api/v1/reports/risk-matrix/{doc_id}
- [ ] Returns 200
- [ ] `risk_matrix` array is non-empty
- [ ] Each entry has: `source_node_id`, `target_node_id`, `severity` (1-5), `probability` (1-5), `type`
- [ ] Both structural and chronological types present

---

## 7. Executive Summary

### POST /api/v1/reports/executive-summary/{doc_id}
- [ ] Returns 200 with SSE stream
- [ ] Stream includes stages: analysing, drafting, auditing, verifying, complete
- [ ] Final event has `stage: "complete"` with `report` object
- [ ] Report contains: `overall_assessment`, `executive_summary`, `issues`

### GET /api/v1/reports/executive-summary/{doc_id}
- [ ] Returns 200 with `{cached: true, report: {...}}`
- [ ] Report matches what was streamed

### DELETE /api/v1/reports/executive-summary/{doc_id}
- [ ] Returns 204
- [ ] Subsequent GET returns `{cached: false}`

---

## 8. Narrative Report

### POST /api/v1/reports/narrative/{doc_id}
- [ ] Returns 200 with SSE stream
- [ ] Stream includes stages: outlining, drafting_chapter_N, auditing, verifying, complete
- [ ] Final event has `stage: "complete"` with `report` object
- [ ] Report contains: `chapters` array (multi-chapter)

### GET /api/v1/reports/narrative/{doc_id}
- [ ] Returns 200 with `{cached: true, report: {...}}`
- [ ] `chapters` array has 2+ entries

### DELETE /api/v1/reports/narrative/{doc_id}
- [ ] Returns 204

---

## 9. Risk Simulation

### POST /api/v1/reports/risk-simulation/{doc_id}
- [ ] Returns 200 with SSE stream
- [ ] Stream includes blast_radius, black_swan, monte_carlo stages
- [ ] Final event has `stage: "complete"` with `result` object

### GET /api/v1/reports/risk-simulation/{doc_id}
- [ ] Returns 200 with `{cached: true, result: {...}}`

#### Blast Radius (`result.blast_radius`)
- [ ] `svi` is a float > 0
- [ ] `nodes` array is non-empty, each has `ripa` sub-object
- [ ] `centrality_scores` dict is non-empty
- [ ] `ripa_summary.total_systemic_risk` > 0
- [ ] `ripa_summary.top_vulnerabilities` is non-empty
- [ ] `cascade_paths` array is non-empty

#### Black Swan (`result.black_swan`)
- [ ] `scenarios` array has 3 entries
- [ ] Each scenario has: `title`, `trigger_node`, `cascade_path`, `impact_radius`, `mitigation`

#### Monte Carlo (`result.monte_carlo`)
- [ ] `available` is true
- [ ] `p50_delay_days`, `p80_delay_days`, `p95_delay_days` are present
- [ ] `at_risk_nodes` array is non-empty

### DELETE /api/v1/reports/risk-simulation/{doc_id}
- [ ] Returns 204

---

## 10. Targeted Mitigation

### POST /api/v1/reports/mitigation/{doc_id}?source_node_id={src}&target_node_id={tgt}
- [ ] Use node IDs from a friction line in the friction queue
- [ ] Returns 200 with SSE stream
- [ ] Final event has `stage: "complete"` with `mitigation` object
- [ ] Mitigation contains: `is_genuine`, `confidence`, `analysis`, `severity`, `probability`

---

## 11. Concurrency Guards

### POST (duplicate) any report endpoint while generation is active
- [ ] Returns 409 with error message

---

## 12. Configuration

### GET /api/v1/config
- [ ] Returns 200
- [ ] Contains: `LLM_PROVIDER`, `FAST_MODEL`, `SMART_MODEL`
- [ ] API keys are masked (truncated with ellipsis)

### POST /api/v1/config
- [ ] Returns 200 with `{success: true}`
- [ ] Updated value reflected in subsequent GET

---

## Summary Counts

After full ingestion and report generation:

| Metric | Expected Minimum |
|---|---|
| Nodes | 10 |
| Edges | 15 |
| Edge types used | 6 (all) |
| Friction lines (structural) | 3 |
| Friction lines (chronological) | 2 |
| Hub nodes (in-degree >= 3) | 1 |
| Temporal nodes with dates | 4 |
| Schedule collapse items | 1 |
| Risk matrix entries | 5 |
| Black Swan scenarios | 3 |
| Cascade paths | 5 |
