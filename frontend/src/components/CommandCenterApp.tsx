import { lazy, Suspense, useEffect, useMemo, useReducer, useState } from "react";
import type { CanvasPayload, ConfigUpdate, DocumentSummary, GraphLink, GraphNode, NormalizedGraph, RawFragility } from "../api/types";
import { clearVault, deleteDocument, getJobStatus, listDocuments, loadCanvas, loadConfig, saveConfig, uploadDocument } from "../api/client";
import { normalizeCanvasPayload } from "../graph/normalize";
import { type RiskLens } from "../graph/lenses";
import { isAttentionItemSelected, selectionReducer, type GraphSelection } from "../graph/selection";
import { buildLinkDetail, buildNodeDetail, searchNodes } from "../graph/details";
import { buildReportActions } from "../reports/navigation";
import { ReportWorkspace } from "./ReportWorkspace";

const SpatialCanvas3D = lazy(() => import("./SpatialCanvas3D").then((module) => ({ default: module.SpatialCanvas3D })));
const AnalystMap2D = lazy(() => import("./AnalystMap2D").then((module) => ({ default: module.AnalystMap2D })));

type ViewMode = "spatial" | "analyst" | "reports";
type LoadState = "idle" | "loading" | "ready" | "error";
type UploadStage = "Uploading" | "Queued" | "Processing" | "Loading canvas" | "Complete" | "Failed" | "Timed out";
type UploadProgress = {
  fileName: string;
  stage: UploadStage;
  status: string;
  startedAt: number;
  log: string[];
};
type ConfigForm = ConfigUpdate;

const lenses: Array<{ id: RiskLens; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "structural", label: "Structural" },
  { id: "fragility", label: "Fragility" },
  { id: "timeline", label: "Timeline" },
  { id: "high-risk", label: "High Risk" },
];

function isGraphLink(item: GraphLink | RawFragility): item is GraphLink {
  return "riskKind" in item;
}

function metricLabel(value: number) {
  return value.toLocaleString();
}

function selectedTitle(selection: GraphSelection, graph: NormalizedGraph | null) {
  if (!graph || selection.type === "none") return "Select a node or risk path";
  if (selection.type === "node") return graph.nodes.find((node) => node.id === selection.id)?.name || "Selected node";
  return graph.links.find((link) => link.id === selection.id)?.relationship || "Selected link";
}

function deleteErrorMessage(err: unknown): string {
  const message = err instanceof Error ? err.message : "";
  if (message.includes("409")) return "Cannot delete while ingestion is still in progress.";
  if (message.includes("404")) return "Document was already removed.";
  return "Delete failed. Please try again.";
}

function elapsedSeconds(startedAt: number): string {
  return `${Math.max(0, Math.floor((Date.now() - startedAt) / 1000))}s`;
}

const emptyConfigForm: ConfigForm = {
  LLM_PROVIDER: "openrouter",
  OPENAI_API_KEY: "",
  OPENROUTER_API_KEY: "",
  FAST_MODEL: "",
  SMART_MODEL: "",
  VAULT_PATH: "",
};

export function CommandCenterApp() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [activeDocument, setActiveDocument] = useState<DocumentSummary | null>(null);
  const [payload, setPayload] = useState<CanvasPayload | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("spatial");
  const [lens, setLens] = useState<RiskLens>("overview");
  const [nodeSearch, setNodeSearch] = useState("");
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [documentActionError, setDocumentActionError] = useState("");
  const [clearVaultArmed, setClearVaultArmed] = useState(false);
  const [documentActionBusy, setDocumentActionBusy] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [configForm, setConfigForm] = useState<ConfigForm>(emptyConfigForm);
  const [configBusy, setConfigBusy] = useState(false);
  const [configStatus, setConfigStatus] = useState("");
  const [configError, setConfigError] = useState("");
  const [selection, dispatchSelection] = useReducer(selectionReducer, { type: "none" } as GraphSelection);

  const graph = useMemo(() => (payload ? normalizeCanvasPayload(payload) : null), [payload]);
  const nodeSearchResults = useMemo(() => (graph ? searchNodes(graph, nodeSearch) : []), [graph, nodeSearch]);
  const reportActions = useMemo(() => (activeDocument ? buildReportActions(activeDocument.id) : []), [activeDocument]);
  const exportReportActions = useMemo(() => reportActions.filter((action) => action.kind === "export"), [reportActions]);

  useEffect(() => {
    listDocuments()
      .then(setDocuments)
      .catch(() => setError("Document list unavailable. Check that the FastAPI server is running."));
  }, []);

  async function openDocument(document: DocumentSummary) {
    setActiveDocument(document);
    setLoadState("loading");
    setError("");
    dispatchSelection({ type: "clear" });
    try {
      const data = await loadCanvas(document.id);
      setPayload(data);
      setViewMode("spatial");
      setLoadState("ready");
      setUploadProgress(null);
    } catch (err) {
      setLoadState("error");
      setError(err instanceof Error ? err.message : "Canvas load failed.");
    }
  }

  async function handleUpload(file: File) {
    setLoadState("loading");
    setError("");
    setDocumentActionError("");
    setUploadProgress({ fileName: file.name, stage: "Uploading", status: "Uploading document...", startedAt: Date.now(), log: [] });
    try {
      const upload = await uploadDocument(file);
      setUploadProgress((current) => current && {
        ...current,
        stage: "Queued",
        status: "Queued for analysis.",
      });
      const started = Date.now();
      while (Date.now() - started < 10 * 60 * 1000) {
        const status = await getJobStatus(upload.job_id);
        setUploadProgress((current) => current && {
          ...current,
          stage: status.status === "pending" ? "Queued" : status.status === "processing" ? "Processing" : status.status === "completed" ? "Loading canvas" : "Failed",
          status: status.status,
          log: status.log ?? [],
        });
        if (status.status === "completed") {
          const refreshed = await listDocuments();
          setDocuments(refreshed);
          const doc = refreshed.find((item) => item.id === upload.document_id) || { id: upload.document_id, name: file.name };
          setUploadProgress((current) => current && { ...current, stage: "Loading canvas", status: "Loading canvas..." });
          await openDocument(doc);
          setUploadProgress({ fileName: file.name, stage: "Complete", status: "Analysis complete.", startedAt: started, log: status.log ?? [] });
          window.setTimeout(() => setUploadProgress(null), 1800);
          return;
        }
        if (status.status === "failed") throw new Error(status.error || "Ingestion failed.");
        await new Promise((resolve) => window.setTimeout(resolve, 1200));
      }
      setUploadProgress((current) => current && { ...current, stage: "Timed out", status: "Ingestion timed out." });
      throw new Error("Ingestion timed out.");
    } catch (err) {
      setLoadState("error");
      const message = err instanceof Error ? err.message : "Upload failed.";
      setError(message);
      setUploadProgress((current) => current && { ...current, stage: "Failed", status: message });
    }
  }

  function resetActiveDocumentState() {
    setActiveDocument(null);
    setPayload(null);
    setLoadState("idle");
    setViewMode("spatial");
    setNodeSearch("");
    dispatchSelection({ type: "clear" });
  }

  async function refreshDocuments() {
    const refreshed = await listDocuments();
    setDocuments(refreshed);
    return refreshed;
  }

  async function handleDeleteDocument(document: DocumentSummary) {
    setDocumentActionBusy(true);
    setDocumentActionError("");
    try {
      await deleteDocument(document.id);
      const refreshed = await refreshDocuments();
      setConfirmDeleteId(null);
      if (activeDocument?.id === document.id) {
        resetActiveDocumentState();
      } else if (!refreshed.length) {
        resetActiveDocumentState();
      }
    } catch (err) {
      setDocumentActionError(deleteErrorMessage(err));
    } finally {
      setDocumentActionBusy(false);
    }
  }

  async function handleClearVault() {
    if (!clearVaultArmed) {
      setClearVaultArmed(true);
      setDocumentActionError("");
      return;
    }
    setDocumentActionBusy(true);
    setDocumentActionError("");
    try {
      await clearVault();
      setDocuments([]);
      setConfirmDeleteId(null);
      setClearVaultArmed(false);
      resetActiveDocumentState();
    } catch (err) {
      setDocumentActionError(err instanceof Error && err.message.includes("409") ? "Cannot clear while generation or ingestion is in progress." : "Clear vault failed. Please try again.");
    } finally {
      setDocumentActionBusy(false);
    }
  }

  async function openConfiguration() {
    setConfigOpen(true);
    setConfigBusy(true);
    setConfigStatus("");
    setConfigError("");
    try {
      const config = await loadConfig();
      setConfigForm({
        LLM_PROVIDER: config.LLM_PROVIDER === "openai" ? "openai" : "openrouter",
        OPENAI_API_KEY: config.OPENAI_API_KEY ?? "",
        OPENROUTER_API_KEY: config.OPENROUTER_API_KEY ?? "",
        FAST_MODEL: config.FAST_MODEL ?? "",
        SMART_MODEL: config.SMART_MODEL ?? "",
        VAULT_PATH: config.VAULT_PATH ?? "",
      });
    } catch {
      setConfigError("Could not load configuration.");
    } finally {
      setConfigBusy(false);
    }
  }

  function closeConfiguration() {
    setConfigOpen(false);
    setConfigStatus("");
    setConfigError("");
  }

  function updateConfigField<K extends keyof ConfigForm>(field: K, value: ConfigForm[K]) {
    setConfigForm((current) => ({ ...current, [field]: value }));
    setConfigStatus("");
    setConfigError("");
  }

  async function handleSaveConfiguration() {
    setConfigBusy(true);
    setConfigStatus("");
    setConfigError("");
    try {
      await saveConfig(configForm);
      setConfigStatus("Configuration applied.");
    } catch {
      setConfigError("Could not save configuration.");
    } finally {
      setConfigBusy(false);
    }
  }

  function selectNode(node: GraphNode) {
    dispatchSelection({ type: "select-node", id: node.id });
    setNodeSearch("");
  }

  function selectLink(link: GraphLink) {
    dispatchSelection({ type: "select-link", id: link.id });
  }

  function clearSelection() {
    dispatchSelection({ type: "clear" });
  }

  function focusAttentionItem(item: GraphLink | RawFragility) {
    if (isGraphLink(item)) {
      selectLink(item);
      return;
    }
    const match = graph?.nodes.find((node) => node.id === item.hub_node_id);
    if (match) selectNode(match);
    else dispatchSelection({ type: "select-node", id: item.hub_node_id });
  }

  const selectedLink = graph && selection.type === "link" ? graph.links.find((link) => link.id === selection.id) : null;
  const selectedNode = graph && selection.type === "node" ? graph.nodes.find((node) => node.id === selection.id) : null;
  const nodeDetail = graph && selectedNode ? buildNodeDetail(graph, selectedNode.id) : null;
  const linkDetail = graph && selectedLink ? buildLinkDetail(graph, selectedLink.id) : null;

  return (
    <main className="command-center">
      <aside className="document-rail">
        <div className="brand-lockup">
          <span>Diamond Miner</span>
          <strong>Command Center</strong>
        </div>
        <label className="upload-drop">
          <input type="file" accept=".pdf,.txt,.md,.docx,.xlsx,.csv,.pptx" onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleUpload(file);
            event.currentTarget.value = "";
          }} />
          <span>Ingest strategy document</span>
          <small>PDF, Office, CSV, Markdown, text</small>
        </label>
        {uploadProgress && (
          <div className={`ingestion-progress-panel ${uploadProgress.stage === "Failed" || uploadProgress.stage === "Timed out" ? "error" : ""}`}>
            <div className="ingestion-progress-header">
              <span>{uploadProgress.stage}</span>
              <small>{elapsedSeconds(uploadProgress.startedAt)}</small>
            </div>
            <strong>{uploadProgress.fileName}</strong>
            <p>{uploadProgress.status}</p>
            {uploadProgress.log.length > 0 && (
              <ol>
                {uploadProgress.log.slice(-5).map((line, index) => <li key={`${line}-${index}`}>{line}</li>)}
              </ol>
            )}
          </div>
        )}
        <div className="document-rail-header">
          <div className="rail-heading">Analysed Documents</div>
          <button className={clearVaultArmed ? "clear-vault-action armed" : "clear-vault-action"} disabled={documentActionBusy || documents.length === 0} onClick={() => void handleClearVault()}>
            {clearVaultArmed ? "Confirm Clear" : "Clear Vault"}
          </button>
        </div>
        {clearVaultArmed && (
          <button className="clear-vault-cancel" disabled={documentActionBusy} onClick={() => setClearVaultArmed(false)}>Cancel clear vault</button>
        )}
        {documentActionError && <p className="document-action-error">{documentActionError}</p>}
        <div className="document-list">
          {documents.map((document) => {
            const confirming = confirmDeleteId === document.id;
            return (
              <div key={document.id} className={activeDocument?.id === document.id ? "doc-row active" : "doc-row"}>
                {confirming ? (
                  <div className="doc-confirm-row">
                    <span>Delete this document?</span>
                    <button disabled={documentActionBusy} onClick={() => setConfirmDeleteId(null)}>Cancel</button>
                    <button className="danger" disabled={documentActionBusy} onClick={() => void handleDeleteDocument(document)}>Delete</button>
                  </div>
                ) : (
                  <>
                    <button className="doc-button" onClick={() => void openDocument(document)}>
                      <span>{document.name}</span>
                      <small>{document.created_at ? new Date(document.created_at).toLocaleDateString() : document.id}</small>
                    </button>
                    <button className="doc-delete-action" title={`Delete ${document.name}`} aria-label={`Delete ${document.name}`} disabled={documentActionBusy} onClick={() => {
                      setConfirmDeleteId(document.id);
                      setDocumentActionError("");
                    }}>Delete</button>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </aside>

      <section className="workspace">
        <header className="top-command">
          <div>
            <p className="eyebrow">Cinematic spatial risk model</p>
            <h1>{activeDocument?.name || "Load a document to open command view"}</h1>
            <span className="status-line">{loadState === "ready" && graph ? `${graph.metrics.nodes} nodes analysed · ${graph.metrics.highRiskIssues} high-risk signals` : "Beta route · backend APIs unchanged"}</span>
          </div>
          <nav className="command-actions">
            <button onClick={() => setViewMode("spatial")} className={viewMode === "spatial" ? "active" : ""}>3D Canvas</button>
            <button onClick={() => setViewMode("analyst")} className={viewMode === "analyst" ? "active" : ""}>Analyst Map</button>
            <button onClick={() => setViewMode("reports")} className={viewMode === "reports" ? "active" : ""}>Reports</button>
            <button type="button" className="config-action" onClick={() => void openConfiguration()}>Configuration</button>
            {exportReportActions.map((action) => (
              <a key={action.href} href={action.href} target="_blank" rel="noreferrer" className="command-export">
                {action.label}
              </a>
            ))}
          </nav>
        </header>

        {graph && (
          <section className="metrics-strip">
            <div><strong>{metricLabel(graph.metrics.nodes)}</strong><span>Nodes</span></div>
            <div><strong>{metricLabel(graph.metrics.edges)}</strong><span>Edges</span></div>
            <div><strong>{metricLabel(graph.metrics.structuralConflicts)}</strong><span>Structural</span></div>
            <div><strong>{metricLabel(graph.metrics.timelineConflicts)}</strong><span>Timeline</span></div>
            <div><strong>{metricLabel(graph.metrics.fragilityPoints)}</strong><span>Fragility</span></div>
          </section>
        )}

        {viewMode !== "reports" && (
          <section className="lens-bar">
            {lenses.map((item) => (
              <button key={item.id} className={lens === item.id ? "active" : ""} onClick={() => setLens(item.id)}>{item.label}</button>
            ))}
          </section>
        )}

        {graph && viewMode !== "reports" && (
          <section className="node-search-panel">
            <input
              id="node-search-input"
              value={nodeSearch}
              onChange={(event) => setNodeSearch(event.target.value)}
              placeholder="Search nodes by name, type, risk, or id"
              autoComplete="off"
            />
            {nodeSearchResults.length > 0 && (
              <div className="node-search-results">
                {nodeSearchResults.map((node) => (
                  <button key={node.id} onClick={() => selectNode(node)}>
                    <span>{node.name}</span>
                    <small>{node.label || "node"} · {node.riskKind}</small>
                  </button>
                ))}
              </div>
            )}
          </section>
        )}

        <section className={viewMode === "reports" ? "stage-shell reports-stage" : "stage-shell"}>
          {loadState === "idle" && <div className="empty-state">Choose a stored document or ingest a new strategy file.</div>}
          {loadState === "loading" && <div className="empty-state pulse">{uploadProgress ? `${uploadProgress.stage}: ${uploadProgress.fileName}` : "Building command model..."}</div>}
          {loadState === "error" && <div className="empty-state error">{error}</div>}
          {loadState === "ready" && graph && viewMode === "spatial" && (
            <Suspense fallback={<div className="empty-state pulse">Loading 3D renderer...</div>}>
              <SpatialCanvas3D nodes={graph.nodes} links={graph.links} lens={lens} selection={selection} onSelectNode={selectNode} onSelectLink={selectLink} onClearSelection={clearSelection} />
            </Suspense>
          )}
          {loadState === "ready" && graph && viewMode === "analyst" && (
            <Suspense fallback={<div className="empty-state pulse">Loading Analyst Map...</div>}>
              <AnalystMap2D nodes={graph.nodes} links={graph.links} lens={lens} selection={selection} onSelectNode={selectNode} onSelectLink={selectLink} onClearSelection={clearSelection} />
            </Suspense>
          )}
          {loadState === "ready" && graph && activeDocument && viewMode === "reports" && (
            <ReportWorkspace
              documentId={activeDocument.id}
              documentName={activeDocument.name}
              graph={graph}
              onSelectNode={selectNode}
              onSelectLink={selectLink}
            />
          )}
        </section>
      </section>

      <aside className="insight-panel">
        <div className="panel-section">
          <p className="eyebrow">Selected Evidence</p>
          <h2>{selectedTitle(selection, graph)}</h2>
          {nodeDetail && (
            <div className="detail-stack">
              <div className="detail-pills">
                <span>{nodeDetail.label}</span>
                <span>{nodeDetail.riskKind}</span>
                <span>Risk Score {nodeDetail.riskScore}</span>
              </div>
              <div>
                <h3>Connected Nodes</h3>
                {nodeDetail.connections.length ? (
                  <div className="connection-list">
                    {nodeDetail.connections.slice(0, 8).map((connection) => (
                      <button key={`${connection.direction}-${connection.nodeId}-${connection.relationship}`} onClick={() => {
                        const match = graph?.nodes.find((node) => node.id === connection.nodeId);
                        if (match) selectNode(match);
                      }}>
                        <span>{connection.direction === "outgoing" ? "->" : "<-"} {connection.relationship}</span>
                        {connection.nodeName}
                      </button>
                    ))}
                  </div>
                ) : <p>No direct standard connections found.</p>}
              </div>
              {nodeDetail.fragility && (
                <div>
                  <h3>Cascade Path</h3>
                  <p>{nodeDetail.fragility.insight}</p>
                  <ol className="cascade-list">
                    {(nodeDetail.fragility.cascade_nodes || []).map((name) => <li key={name}>{name}</li>)}
                  </ol>
                </div>
              )}
            </div>
          )}
          {linkDetail && (
            <div className="detail-stack">
              <div className="detail-pills">
                <span>{linkDetail.riskKind}</span>
                <span>Risk Score {linkDetail.riskScore || "n/a"}</span>
                <span>Severity {linkDetail.severity || "n/a"}</span>
                <span>Probability {linkDetail.probability || "n/a"}</span>
              </div>
              <div className="plain-english-panel">
                <span>Plain English</span>
                <h3>{linkDetail.plainEnglish.heading}</h3>
                <p>{linkDetail.plainEnglish.meaning}</p>
                <p>{linkDetail.plainEnglish.impact}</p>
                <p>{linkDetail.plainEnglish.scoreMeaning}</p>
                {linkDetail.plainEnglish.actions.length > 0 && (
                  <ol>
                    {linkDetail.plainEnglish.actions.map((action) => <li key={action}>{action}</li>)}
                  </ol>
                )}
              </div>
              <div className="link-path">
                <button onClick={() => {
                  const match = graph?.nodes.find((node) => node.name === linkDetail.sourceName);
                  if (match) selectNode(match);
                }}>{linkDetail.sourceName}</button>
                <span>-&gt;</span>
                <button onClick={() => {
                  const match = graph?.nodes.find((node) => node.name === linkDetail.targetName);
                  if (match) selectNode(match);
                }}>{linkDetail.targetName}</button>
              </div>
              <div>
                <h3>Analysis</h3>
                <p>{linkDetail.analysis}</p>
              </div>
            </div>
          )}
          {selectedNode && !nodeDetail && <p>{selectedNode.label || "Concept"} · {selectedNode.riskKind}</p>}
          {selectedLink && !linkDetail && <p>{selectedLink.diamond || selectedLink.relationship}</p>}
          {!selectedNode && !selectedLink && <p>Click a node or risk path in either graph view to inspect it here.</p>}
        </div>
        <div className="panel-section">
          <p className="eyebrow">Critical Attention</p>
          <div className="risk-list">
            {graph?.topRisks.slice(0, 6).map((item, index) => (
              <button
                key={isGraphLink(item) ? item.id : `${item.hub_node_id}-${index}`}
                className={isAttentionItemSelected(item, selection) ? "attention-item active" : "attention-item"}
                aria-pressed={isAttentionItemSelected(item, selection)}
                onClick={() => focusAttentionItem(item)}
              >
                <span>{isGraphLink(item) ? item.riskKind : "fragility"}</span>
                {isGraphLink(item) ? (item.diamond || item.relationship) : (item.insight || item.hub_node_id)}
              </button>
            )) || <p>No graph loaded.</p>}
          </div>
        </div>
      </aside>

      {configOpen && <button className="config-backdrop" aria-label="Close configuration" onClick={closeConfiguration} />}
      <aside className={configOpen ? "config-drawer open" : "config-drawer"} aria-hidden={!configOpen}>
        <div className="config-drawer-header">
          <div>
            <p className="eyebrow">Runtime</p>
            <h2>Configuration</h2>
          </div>
          <button type="button" onClick={closeConfiguration}>Close</button>
        </div>

        <div className="config-section">
          <span className="config-label">LLM_PROVIDER</span>
          <div className="provider-toggle">
            <button
              type="button"
              className={configForm.LLM_PROVIDER === "openrouter" ? "active" : ""}
              onClick={() => updateConfigField("LLM_PROVIDER", "openrouter")}
            >
              OpenRouter
            </button>
            <button
              type="button"
              className={configForm.LLM_PROVIDER === "openai" ? "active" : ""}
              onClick={() => updateConfigField("LLM_PROVIDER", "openai")}
            >
              OpenAI
            </button>
          </div>
        </div>

        <label className="config-field">
          <span>OPENROUTER_API_KEY</span>
          <input
            type="password"
            value={configForm.OPENROUTER_API_KEY}
            onChange={(event) => updateConfigField("OPENROUTER_API_KEY", event.target.value)}
            placeholder="sk-or-..."
          />
        </label>

        <label className="config-field">
          <span>OPENAI_API_KEY</span>
          <input
            type="password"
            value={configForm.OPENAI_API_KEY}
            onChange={(event) => updateConfigField("OPENAI_API_KEY", event.target.value)}
            placeholder="sk-proj-..."
          />
        </label>

        <label className="config-field">
          <span>FAST_MODEL</span>
          <input
            value={configForm.FAST_MODEL}
            onChange={(event) => updateConfigField("FAST_MODEL", event.target.value)}
            placeholder="Fast extraction model"
          />
        </label>

        <label className="config-field">
          <span>SMART_MODEL</span>
          <input
            value={configForm.SMART_MODEL}
            onChange={(event) => updateConfigField("SMART_MODEL", event.target.value)}
            placeholder="Reasoning/report model"
          />
        </label>

        <label className="config-field">
          <span>VAULT_PATH</span>
          <input
            value={configForm.VAULT_PATH}
            onChange={(event) => updateConfigField("VAULT_PATH", event.target.value)}
            placeholder="./vaults"
          />
        </label>

        {configError && <p className="config-message error">{configError}</p>}
        {configStatus && <p className="config-message">{configStatus}</p>}

        <div className="config-actions">
          <button type="button" onClick={closeConfiguration}>Cancel</button>
          <button type="button" className="primary" disabled={configBusy} onClick={() => void handleSaveConfiguration()}>
            {configBusy ? "Working..." : "Save & Apply"}
          </button>
        </div>
      </aside>
    </main>
  );
}
