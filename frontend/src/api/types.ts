export type DocumentSummary = {
  id: string;
  name: string;
  created_at?: string;
};

export type RawNode = {
  id: string;
  name?: string;
  label?: string;
  start_date?: string;
  end_date?: string;
};

export type RawEdge = {
  source: string;
  target: string;
  relationship?: string;
};

export type RawIssue = {
  source: string;
  target: string;
  diamond?: string;
  severity?: number | string;
  probability?: number | string;
  finding?: RawRiskFinding;
};

export type RawRiskFinding = {
  title?: string;
  risk_type?: string;
  affected_entity?: string;
  blocked_work?: string;
  blocking_condition?: string;
  relationship?: string;
  evidence_summary?: string;
  why_it_matters?: string;
  recommended_action?: string;
  confidence?: number | string;
  confidence_score?: number | string;
  confidence_level?: string;
  confidence_factors?: {
    model_confidence?: number;
    evidence_completeness?: number;
    graph_specificity?: number;
    risk_score_availability?: number;
    claim_provenance_strength?: number;
  };
  claim_ids?: string[];
  evidence_span_ids?: string[];
  claim_validation_status?: string;
  graph_agreement?: string;
  assumptions?: string[];
};

export type RawFragility = {
  hub_node_id: string;
  insight?: string;
  dependency_count?: number;
  cascade_nodes?: string[];
};

export type CanvasPayload = {
  nodes?: RawNode[];
  edges?: RawEdge[];
  friction_lines?: RawIssue[];
  chronological_friction_lines?: RawIssue[];
  fragility_lines?: RawFragility[];
};

export type RiskKind = "standard" | "structural" | "timeline" | "fragility" | "high";

export type GraphNode = RawNode & {
  name: string;
  riskKind: RiskKind;
  riskScore: number;
};

export type GraphLink = {
  id: string;
  source: string;
  target: string;
  relationship: string;
  diamond: string;
  severity?: number | string;
  probability?: number | string;
  finding?: RawRiskFinding;
  riskKind: RiskKind;
  riskScore: number;
};

export type NormalizedGraph = {
  nodes: GraphNode[];
  links: GraphLink[];
  metrics: {
    nodes: number;
    edges: number;
    structuralConflicts: number;
    timelineConflicts: number;
    fragilityPoints: number;
    highRiskIssues: number;
  };
  topRisks: Array<GraphLink | RawFragility>;
};

export type UploadResult = {
  job_id: string;
  document_id: string;
  status: string;
};

export type JobAccuracyTelemetry = {
  evidence_spans: number;
  claims: number;
  validated: number;
  needs_review: number;
  failed: number;
  promotable?: number;
  batches_attempted?: number;
  batches_succeeded?: number;
  batches_failed?: number;
  claims_before_dedupe?: number;
  claims_after_dedupe?: number;
};

export type JobStatus = {
  status: "pending" | "processing" | "completed" | "failed";
  document_id?: string;
  error?: string;
  error_code?: string;
  log?: string[];
  warnings?: string[];
  accuracy?: JobAccuracyTelemetry;
};

export type DeleteDocumentResult = {
  status: "deleted";
  document_id: string;
};

export type ClearVaultResult = {
  status: "cleared";
};

export type AppConfig = {
  LLM_PROVIDER: "openai" | "openrouter" | "";
  OPENAI_API_KEY: string;
  OPENROUTER_API_KEY: string;
  FAST_MODEL: string;
  SMART_MODEL: string;
  VAULT_PATH: string;
  DIAMOND_MINER_CLAIM_LAYER: "" | "0" | "1";
};

export type ConfigUpdate = Omit<AppConfig, "LLM_PROVIDER"> & {
  LLM_PROVIDER: "openai" | "openrouter";
};

export type ConfigUpdateResult = {
  status: "applied";
};

export type FrictionQueueItem = RawIssue & {
  type: "structural" | "chronological";
};

export type BottleneckItem = {
  id: string;
  name: string;
  label?: string;
  dependency_count?: number;
};

export type ScheduleCollapseItem = {
  predecessor_name: string;
  successor_name: string;
  pred_end_date: string;
  succ_start_date: string;
  days_at_risk: number;
  analysis: string;
};

export type RiskMatrixItem = {
  type: "structural" | "chronological";
  source: string;
  target: string;
  analysis: string;
  severity: number | string;
  probability: number | string;
};

export type OperationalReports = {
  frictionQueue: FrictionQueueItem[];
  bottlenecks: BottleneckItem[];
  scheduleCollapse: ScheduleCollapseItem[];
  riskMatrix: RiskMatrixItem[];
};

export type AccuracyCounts = {
  evidence_spans: number;
  claims: number;
  validated: number;
  needs_review: number;
  failed: number;
  extraction_failures: number;
  canonical_entities: number;
};

export type AccuracyManifest = {
  document_id: string;
  filename: string;
  source_hash: string;
  ingested_at: string;
  parser_version: string;
  schema_version: string;
  embedding_model: string;
  llm_model: string;
  document_anchor_date?: string | null;
  validation_status: string;
};

export type AccuracyEvidenceSpan = {
  span_id: string;
  document_id: string;
  chunk_id: string;
  page_number: number;
  section_title?: string;
  text: string;
  span_type: string;
  bbox_json?: string | null;
  source_hash: string;
};

export type AccuracyClaim = {
  claim_id: string;
  document_id: string;
  claim_type: string;
  subject: string;
  predicate: string;
  object: string;
  modality: string;
  certainty: string;
  status: string;
  evidence_span_ids: string[];
  source_quote: string;
  confidence: number;
  validation_status: string;
};

export type AccuracyValidationResult = {
  claim_id: string;
  document_id: string;
  status: string;
  reasons: string[];
  can_promote: number;
};

export type AccuracyCanonicalEntity = {
  entity_id: string;
  document_id: string;
  canonical_name: string;
  entity_type: string;
  aliases: string[];
  source_span_ids: string[];
  confidence: number;
  human_locked: number;
};

export type AccuracyGraphAgreementEdge = {
  source_id: string;
  target_id: string;
  relationship: string;
  canonical_source_id: string;
  canonical_target_id: string;
  source_chunk_id: string;
  claim_id?: string | null;
  evidence_span_ids: string[];
  review_state?: AccuracyReviewState;
};

export type AccuracyReviewState = "needs_review" | "accepted" | "ignored";
export type AccuracyReviewDecisionKind = "claim-only" | "legacy-only";

export type AccuracyReviewDecisionUpdate = {
  candidate_id: string;
  state: AccuracyReviewState;
  kind: AccuracyReviewDecisionKind;
  label: string;
};

export type AccuracyReviewDecision = AccuracyReviewDecisionUpdate & {
  document_id: string;
  updated_at: string;
};

export type AccuracyReviewDecisionResult = {
  decision: AccuracyReviewDecision;
  review_decisions: AccuracyReviewDecision[];
  review_states: Record<string, AccuracyReviewState>;
};

export type AccuracyQuality = {
  extraction_coverage: {
    evidence_span_count: number;
    evidence_spans_with_claims: number;
    coverage_rate: number;
    claims_per_evidence_span: number;
  };
  validation_quality: {
    passed: number;
    needs_review: number;
    failed: number;
    pass_rate: number;
    review_rate: number;
    fail_rate: number;
  };
  promotion_readiness: {
    promotable: number;
    promotion_rate: number;
    human_accepted_claim_only_edges: number;
    effective_promotable: number;
    review_adjusted_denominator: number;
    effective_promotion_rate: number;
  };
  entity_normalization: {
    canonical_entities: number;
    raw_aliases: number;
    average_aliases_per_entity: number;
  };
  graph_agreement: {
    legacy_edge_count: number;
    claim_promoted_edge_count: number;
    shared_canonical_edge_count: number;
    legacy_only_edge_count: number;
    claim_only_edge_count: number;
    accepted_claim_only_edge_count: number;
    ignored_claim_only_edge_count: number;
    accepted_legacy_only_edge_count: number;
    ignored_legacy_only_edge_count: number;
    active_claim_only_edge_count: number;
    active_legacy_only_edge_count: number;
    human_promoted_edge_count: number;
    claim_vs_legacy_overlap_rate: number;
    legacy_only_edges: AccuracyGraphAgreementEdge[];
    claim_only_edges: AccuracyGraphAgreementEdge[];
  };
  report_confidence: {
    active_mismatch_count: number;
    accepted_mismatch_count: number;
    ignored_mismatch_count: number;
    review_adjusted_overlap_rate: number;
    confidence_level: "high" | "medium" | "low";
  };
  top_review_reasons: Array<{
    reason: string;
    count: number;
  }>;
};

export type AccuracyExtractionFailure = {
  id: string;
  document_id: string;
  span_id: string;
  agent: string;
  error: string;
  raw_payload: string;
  created_at: string;
};

export type AccuracyPayload = {
  document_id: string;
  manifest: AccuracyManifest | null;
  counts: AccuracyCounts;
  evidence_spans: AccuracyEvidenceSpan[];
  claims: AccuracyClaim[];
  canonical_entities: AccuracyCanonicalEntity[];
  validation_results: AccuracyValidationResult[];
  extraction_failures: AccuracyExtractionFailure[];
  review_decisions: AccuracyReviewDecision[];
  review_states: Record<string, AccuracyReviewState>;
  quality: AccuracyQuality;
};
