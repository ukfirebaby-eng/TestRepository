"""Graph viewer endpoints.

GET /graph       — interactive HTML page (no auth required)
GET /graph/data  — graph definition as JSON
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(tags=["graph"])

# ---------------------------------------------------------------------------
# Graph definition (static — mirrors rag_system/agent/graph.py topology)
# ---------------------------------------------------------------------------

_GRAPH_DATA = {
    "nodes": [
        {
            "id": "ingress",
            "label": "ingress",
            "role": "entry",
            "description": "Validates query (non-empty, ≤4096 chars), generates session_id, initialises cost/latency counters.",
        },
        {
            "id": "policy_check",
            "label": "policy_check",
            "role": "conditional",
            "description": "Detects prompt-injection attempts via blocklist. Sets policy_flags. Hard errors short-circuit to finalize.",
        },
        {
            "id": "classify_query",
            "label": "classify_query",
            "role": "processing",
            "description": "Heuristic classification: keyword | temporal | multi_hop | ambiguous | semantic.",
        },
        {
            "id": "plan_retrieval",
            "label": "plan_retrieval",
            "role": "processing",
            "description": "Maps query type to retrieval mode: lexical_first | semantic_first | balanced_hybrid.",
        },
        {
            "id": "retrieve_candidates",
            "label": "retrieve_candidates",
            "role": "processing",
            "description": "Hybrid BM25 + dense retrieval. Embeds query, fires both searches concurrently, deduplicates with RRF fusion.",
        },
        {
            "id": "rerank_candidates",
            "label": "rerank_candidates",
            "role": "processing",
            "description": "Reranks top-N candidates via reranker backend, trims to final_chunks (default 8).",
        },
        {
            "id": "judge_evidence",
            "label": "judge_evidence",
            "role": "conditional",
            "description": "Checks if reranked chunks are sufficient (≥1 chunk, avg_score ≥0.01). Routes to rewrite or compose.",
        },
        {
            "id": "rewrite_query",
            "label": "rewrite_query",
            "role": "processing",
            "description": "Lightweight rewrites on retry: attempt 1 expands terms, attempt 2 extracts key phrases. Decrements budget.",
        },
        {
            "id": "compose_answer",
            "label": "compose_answer",
            "role": "processing",
            "description": "Generates answer via LLM (claude-sonnet-4-6) with evidence and in-line citations. Falls back to extractive mode.",
        },
        {
            "id": "validate_grounding",
            "label": "validate_grounding",
            "role": "processing",
            "description": "Verifies each citation resolves to a reranked chunk. Removes dangling citations. Checks answer length.",
        },
        {
            "id": "finalize",
            "label": "finalize",
            "role": "processing",
            "description": "Assembles final QueryResponse object, computes total end-to-end latency.",
        },
        {
            "id": "trace_and_feedback",
            "label": "trace_and_feedback",
            "role": "observability",
            "description": "Emits OTEL spans, saves trace JSON to document store, calls LangSmith bridge if configured.",
        },
        {
            "id": "__end__",
            "label": "END",
            "role": "terminal",
            "description": "Graph execution terminates. Response is returned to the caller.",
        },
    ],
    "edges": [
        {"source": "ingress", "target": "policy_check", "label": "", "conditional": False},
        {"source": "policy_check", "target": "classify_query", "label": "no error", "conditional": True},
        {"source": "policy_check", "target": "finalize", "label": "hard error", "conditional": True},
        {"source": "classify_query", "target": "plan_retrieval", "label": "", "conditional": False},
        {"source": "plan_retrieval", "target": "retrieve_candidates", "label": "", "conditional": False},
        {"source": "retrieve_candidates", "target": "rerank_candidates", "label": "", "conditional": False},
        {"source": "rerank_candidates", "target": "judge_evidence", "label": "", "conditional": False},
        {
            "source": "judge_evidence",
            "target": "compose_answer",
            "label": "sufficient / no budget",
            "conditional": True,
        },
        {
            "source": "judge_evidence",
            "target": "rewrite_query",
            "label": "insufficient",
            "conditional": True,
        },
        {"source": "rewrite_query", "target": "retrieve_candidates", "label": "retry loop", "conditional": False},
        {"source": "compose_answer", "target": "validate_grounding", "label": "", "conditional": False},
        {"source": "validate_grounding", "target": "finalize", "label": "", "conditional": False},
        {"source": "finalize", "target": "trace_and_feedback", "label": "", "conditional": False},
        {"source": "trace_and_feedback", "target": "__end__", "label": "", "conditional": False},
    ],
}

# ---------------------------------------------------------------------------
# HTML page (self-contained, CDN-only JS)
# ---------------------------------------------------------------------------

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RAG Agent Graph</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #0f1117; color: #e2e8f0; height: 100vh; display: flex;
         flex-direction: column; }
  #header { padding: 12px 20px; background: #1a1d27; border-bottom: 1px solid #2d3148;
            display: flex; align-items: center; gap: 16px; }
  #header h1 { font-size: 15px; font-weight: 600; color: #a5b4fc; }
  #header span { font-size: 12px; color: #64748b; }
  #main { display: flex; flex: 1; overflow: hidden; }
  #cy { flex: 1; }
  #sidebar { width: 280px; background: #1a1d27; border-left: 1px solid #2d3148;
             padding: 20px; display: flex; flex-direction: column; gap: 16px;
             overflow-y: auto; }
  #info-box h2 { font-size: 12px; font-weight: 600; text-transform: uppercase;
                 letter-spacing: .08em; color: #64748b; margin-bottom: 8px; }
  #node-name { font-size: 16px; font-weight: 600; color: #e2e8f0; margin-bottom: 6px; }
  #node-role { display: inline-block; font-size: 11px; padding: 2px 8px;
               border-radius: 9999px; margin-bottom: 10px; font-weight: 500; }
  #node-desc { font-size: 13px; color: #94a3b8; line-height: 1.5; }
  #legend { border-top: 1px solid #2d3148; padding-top: 16px; }
  #legend h2 { font-size: 12px; font-weight: 600; text-transform: uppercase;
               letter-spacing: .08em; color: #64748b; margin-bottom: 10px; }
  .legend-row { display: flex; align-items: center; gap: 8px; margin-bottom: 7px;
                font-size: 12px; color: #94a3b8; }
  .dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
  .line { width: 24px; height: 2px; flex-shrink: 0; }
  .dashed { background: repeating-linear-gradient(
              90deg, #f97316 0, #f97316 4px, transparent 4px, transparent 8px); }
  #controls { display: flex; gap: 8px; }
  button { background: #2d3148; border: 1px solid #3d4268; color: #a5b4fc;
           padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; }
  button:hover { background: #3d4268; }
  .placeholder { font-size: 13px; color: #475569; font-style: italic; }
</style>
</head>
<body>
<div id="header">
  <h1>Agentic RAG — Workflow Graph</h1>
  <span>Click a node for details &nbsp;·&nbsp; Scroll to zoom &nbsp;·&nbsp; Drag to pan</span>
</div>
<div id="main">
  <div id="cy"></div>
  <div id="sidebar">
    <div id="controls">
      <button id="btn-reset">Reset View</button>
      <button id="btn-fit">Fit Graph</button>
    </div>
    <div id="info-box">
      <h2>Node Details</h2>
      <p class="placeholder" id="placeholder">Select a node to see its description.</p>
      <div id="node-detail" style="display:none">
        <div id="node-name"></div>
        <span id="node-role"></span>
        <p id="node-desc"></p>
      </div>
    </div>
    <div id="legend">
      <h2>Legend</h2>
      <div class="legend-row"><div class="dot" style="background:#22c55e"></div>Entry point</div>
      <div class="legend-row"><div class="dot" style="background:#6366f1"></div>Processing node</div>
      <div class="legend-row"><div class="dot" style="background:#f97316"></div>Conditional gate</div>
      <div class="legend-row"><div class="dot" style="background:#a855f7"></div>Observability</div>
      <div class="legend-row"><div class="dot" style="background:#ef4444"></div>Terminal (END)</div>
      <div style="margin-top:10px">
        <div class="legend-row"><div class="line" style="background:#64748b;height:2px"></div>Sequential edge</div>
        <div class="legend-row"><div class="line dashed"></div>Conditional edge</div>
      </div>
    </div>
  </div>
</div>

<!-- Cytoscape.js -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.29.2/cytoscape.min.js"
        integrity="sha512-JoFsH5MmrNMDMRmhFIkrgZjQ6lnHdOY+Dxg3B5VCQqtLkjTfnaWpEb8l/FGVDrb5vOC3MHFsz7LNmLMxhpJw=="
        crossorigin="anonymous" referrerpolicy="no-referrer"></script>

<!-- dagre (layout) — optional, degrades gracefully -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/dagre/0.8.5/dagre.min.js"
        crossorigin="anonymous" referrerpolicy="no-referrer"></script>
<script src="https://cdn.jsdelivr.net/npm/cytoscape-dagre@2.5.0/cytoscape-dagre.min.js"
        crossorigin="anonymous" referrerpolicy="no-referrer"></script>

<script>
const ROLE_COLORS = {
  entry:         { bg: "#166534", border: "#22c55e", text: "#dcfce7" },
  processing:    { bg: "#1e1b4b", border: "#6366f1", text: "#e0e7ff" },
  conditional:   { bg: "#7c2d12", border: "#f97316", text: "#ffedd5" },
  observability: { bg: "#581c87", border: "#a855f7", text: "#f3e8ff" },
  terminal:      { bg: "#450a0a", border: "#ef4444", text: "#fee2e2" },
};

async function init() {
  const data = await fetch("/graph/data").then(r => r.json());

  const elements = [];

  for (const n of data.nodes) {
    const c = ROLE_COLORS[n.role] || ROLE_COLORS.processing;
    elements.push({
      data: {
        id: n.id,
        label: n.label,
        role: n.role,
        description: n.description,
        bgColor: c.bg,
        borderColor: c.border,
        textColor: c.text,
      }
    });
  }

  for (let i = 0; i < data.edges.length; i++) {
    const e = data.edges[i];
    elements.push({
      data: {
        id: `e${i}`,
        source: e.source,
        target: e.target,
        label: e.label || "",
        conditional: e.conditional,
      }
    });
  }

  // Detect dagre support
  let layout;
  try {
    cytoscape.use(cytoscapeDagre);
    layout = {
      name: "dagre",
      rankDir: "TB",
      nodeSep: 60,
      rankSep: 80,
      edgeSep: 20,
      padding: 40,
    };
  } catch (_) {
    layout = { name: "breadthfirst", directed: true, padding: 40, spacingFactor: 1.4 };
  }

  const cy = cytoscape({
    container: document.getElementById("cy"),
    elements,
    layout,
    style: [
      {
        selector: "node",
        style: {
          "background-color": "data(bgColor)",
          "border-color": "data(borderColor)",
          "border-width": 2,
          "color": "data(textColor)",
          "label": "data(label)",
          "text-valign": "center",
          "text-halign": "center",
          "font-size": "11px",
          "font-family": "ui-monospace, 'Cascadia Code', monospace",
          "font-weight": "500",
          "width": "label",
          "height": 36,
          "padding": "10px",
          "shape": "round-rectangle",
          "text-wrap": "wrap",
          "text-max-width": "160px",
        },
      },
      {
        selector: "node[role='terminal']",
        style: {
          shape: "ellipse",
          width: 48,
          height: 48,
          "font-size": "12px",
          "font-weight": "700",
        },
      },
      {
        selector: "node[role='entry']",
        style: {
          shape: "round-rectangle",
          "border-width": 3,
        },
      },
      {
        selector: "node:selected",
        style: {
          "border-width": 3,
          "border-color": "#f8fafc",
          "box-shadow": "0 0 0 3px rgba(248,250,252,0.3)",
        },
      },
      {
        selector: "edge",
        style: {
          "width": 1.5,
          "line-color": "#475569",
          "target-arrow-color": "#475569",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          "label": "data(label)",
          "font-size": "9px",
          "color": "#94a3b8",
          "text-background-color": "#0f1117",
          "text-background-opacity": 0.85,
          "text-background-padding": "2px",
          "text-rotation": "autorotate",
          "edge-text-rotation": "autorotate",
        },
      },
      {
        selector: "edge[?conditional]",
        style: {
          "line-style": "dashed",
          "line-dash-pattern": [6, 3],
          "line-color": "#c2410c",
          "target-arrow-color": "#c2410c",
          "color": "#fb923c",
          "width": 1.5,
        },
      },
    ],
  });

  // Node click → show details in sidebar
  const placeholder = document.getElementById("placeholder");
  const detail = document.getElementById("node-detail");
  const nameEl = document.getElementById("node-name");
  const roleEl = document.getElementById("node-role");
  const descEl = document.getElementById("node-desc");

  cy.on("tap", "node", evt => {
    const d = evt.target.data();
    const c = ROLE_COLORS[d.role] || ROLE_COLORS.processing;
    placeholder.style.display = "none";
    detail.style.display = "block";
    nameEl.textContent = d.label;
    roleEl.textContent = d.role;
    roleEl.style.background = c.bg;
    roleEl.style.color = c.text;
    roleEl.style.border = `1px solid ${c.border}`;
    descEl.textContent = d.description;
  });

  cy.on("tap", evt => {
    if (evt.target === cy) {
      placeholder.style.display = "";
      detail.style.display = "none";
    }
  });

  // Buttons
  document.getElementById("btn-reset").addEventListener("click", () => cy.reset());
  document.getElementById("btn-fit").addEventListener("click", () => cy.fit(undefined, 40));
}

init().catch(console.error);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/graph", response_class=HTMLResponse, include_in_schema=False)
async def graph_viewer() -> HTMLResponse:
    """Serve the interactive graph viewer page."""
    return HTMLResponse(content=_HTML)


@router.get("/graph/data", summary="Agent graph definition")
async def graph_data() -> JSONResponse:
    """Return the agent workflow graph as a JSON node-link structure."""
    return JSONResponse(content=_GRAPH_DATA)
