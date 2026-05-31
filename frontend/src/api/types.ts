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

export type JobStatus = {
  status: "pending" | "processing" | "completed" | "failed";
  document_id?: string;
  error?: string;
  error_code?: string;
  log?: string[];
  warnings?: string[];
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
