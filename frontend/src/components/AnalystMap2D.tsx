import Graph from "graphology";
import Sigma from "sigma";
import { useEffect, useRef } from "react";
import type { GraphLink, GraphNode } from "../api/types";
import { linkMatchesLens, nodeMatchesLens, riskColor, type RiskLens } from "../graph/lenses";
import type { GraphSelection } from "../graph/selection";
import { buildFocusVisibility, type FocusVisibilityState } from "../graph/focusVisibility";

type Props = {
  nodes: GraphNode[];
  links: GraphLink[];
  lens: RiskLens;
  selection: GraphSelection;
  onSelectNode: (node: GraphNode) => void;
  onSelectLink: (link: GraphLink) => void;
  onClearSelection: () => void;
};

const lensLabels: Record<RiskLens, string> = {
  overview: "Overview",
  structural: "Structural",
  fragility: "Fragility",
  timeline: "Timeline",
  "high-risk": "High Risk",
};

const laneByRiskKind: Record<string, number> = {
  high: 1,
  structural: 2,
  timeline: 3,
  fragility: 4,
  standard: 5,
};

type AnalystNodeDrawData = {
  x: number;
  y: number;
  size: number;
  label?: unknown;
  color: string;
};

type AnalystNodeDrawSettings = {
  labelSize: number;
  labelFont: string;
  labelWeight: string;
};

function positionFor(node: GraphNode, index: number, total: number) {
  const angle = index * Math.PI * (3 - Math.sqrt(5));
  const lane = laneByRiskKind[node.riskKind] ?? 5;
  const radius = 3.2 + lane * 1.35 + Math.sqrt(index + 1) * 0.22 + node.riskScore * 0.015;
  const spread = Math.max(1, total / 90);
  return { x: Math.cos(angle) * radius * spread, y: Math.sin(angle) * radius * spread };
}

function roundedRect(context: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.lineTo(x + width - radius, y);
  context.quadraticCurveTo(x + width, y, x + width, y + radius);
  context.lineTo(x + width, y + height - radius);
  context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  context.lineTo(x + radius, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - radius);
  context.lineTo(x, y + radius);
  context.quadraticCurveTo(x, y, x + radius, y);
  context.closePath();
}

function drawAnalystNodeLabel(context: CanvasRenderingContext2D, data: AnalystNodeDrawData, settings: AnalystNodeDrawSettings) {
  if (typeof data.label !== "string") return;
  const size = settings.labelSize;
  context.font = `${settings.labelWeight} ${size}px ${settings.labelFont}`;
  context.fillStyle = "#edf4f7";
  context.textBaseline = "middle";
  context.fillText(data.label, data.x + data.size + 6, data.y);
}

function drawAnalystNodeHover(context: CanvasRenderingContext2D, data: AnalystNodeDrawData, settings: AnalystNodeDrawSettings) {
  const size = settings.labelSize;
  const label = typeof data.label === "string" ? data.label : "";
  context.font = `700 ${size}px ${settings.labelFont}`;
  context.textBaseline = "middle";

  context.save();
  context.shadowOffsetX = 0;
  context.shadowOffsetY = 10;
  context.shadowBlur = 18;
  context.shadowColor = "rgba(0, 0, 0, 0.44)";

  context.beginPath();
  context.arc(data.x, data.y, data.size + 6, 0, Math.PI * 2);
  context.fillStyle = "rgba(7, 10, 14, 0.92)";
  context.fill();
  context.lineWidth = 2;
  context.strokeStyle = "rgba(245, 201, 95, 0.82)";
  context.stroke();

  if (label) {
    const labelX = data.x + data.size + 8;
    const labelHeight = size + 12;
    const labelWidth = Math.ceil(context.measureText(label).width) + 18;
    roundedRect(context, labelX, data.y - labelHeight / 2, labelWidth, labelHeight, 5);
    context.fillStyle = "rgba(7, 10, 14, 0.94)";
    context.fill();
    context.lineWidth = 1;
    context.strokeStyle = "rgba(155, 174, 188, 0.42)";
    context.stroke();
    context.fillStyle = "#edf4f7";
    context.fillText(label, labelX + 9, data.y);
  }
  context.restore();
}

function analystNodeStyle(node: GraphNode, inLens: boolean, focusState: FocusVisibilityState) {
  if (focusState === "selected") return { color: "#f7fbff", sizeBoost: 8, zIndex: 10, highlighted: true };
  if (focusState === "context") return { color: "#f5c95f", sizeBoost: 4, zIndex: 7, highlighted: true };
  if (focusState === "dimmed") return { color: inLens ? "#34404c" : "#222a33", sizeBoost: -1, zIndex: 0, highlighted: false };
  return { color: inLens ? riskColor(node.riskKind) : "#2b3440", sizeBoost: 0, zIndex: inLens ? 2 : 0, highlighted: false };
}

function analystEdgeStyle(link: GraphLink, lens: RiskLens, inLens: boolean, focusState: FocusVisibilityState) {
  if (focusState === "selected") return { color: "#f7fbff", size: 5, hidden: false, zIndex: 10 };
  if (focusState === "context") return { color: "#f5c95f", size: link.riskKind === "standard" ? 1.2 : 2.7, hidden: false, zIndex: 7 };
  if (focusState === "dimmed") return { color: inLens ? "#34404c" : "#202833", size: 0.45, hidden: lens !== "overview" && !inLens, zIndex: 0 };
  return { color: inLens ? riskColor(link.riskKind) : "#26303b", size: link.riskKind === "standard" ? 0.6 : 2, hidden: lens !== "overview" && !inLens, zIndex: inLens ? 2 : 0 };
}

export function AnalystMap2D({ nodes, links, lens, selection, onSelectNode, onSelectLink, onClearSelection }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const graph = new Graph({ multi: true });
    const focusVisibility = buildFocusVisibility(nodes, links, selection);
    nodes.forEach((node, index) => {
      const position = positionFor(node, index, nodes.length);
      const inLens = nodeMatchesLens(node, lens);
      const focusState = focusVisibility.nodeState(node.id);
      const style = analystNodeStyle(node, inLens, focusState);
      const baseSize = node.riskKind === "high" ? 11 : node.riskKind === "fragility" ? 9 : 6;
      graph.addNode(node.id, {
        ...position,
        label: node.name,
        size: Math.max(3, baseSize + style.sizeBoost),
        color: style.color,
        highlighted: style.highlighted,
        forceLabel: focusState === "selected" || focusState === "context",
        zIndex: style.zIndex,
      });
    });

    links.forEach((link) => {
      if (!graph.hasNode(link.source) || !graph.hasNode(link.target)) return;
      const inLens = linkMatchesLens(link, lens);
      const style = analystEdgeStyle(link, lens, inLens, focusVisibility.linkState(link.id));
      graph.addDirectedEdgeWithKey(link.id, link.source, link.target, {
        size: style.size,
        color: style.color,
        hidden: style.hidden,
        zIndex: style.zIndex,
      });
    });

    const renderer = new Sigma(graph, containerRef.current, {
      allowInvalidContainer: true,
      renderEdgeLabels: false,
      labelColor: { color: "#dce7ee" },
      labelSize: 11,
      labelRenderedSizeThreshold: 7,
      defaultDrawNodeLabel: drawAnalystNodeLabel,
      defaultDrawNodeHover: drawAnalystNodeHover,
      enableEdgeEvents: true,
      zIndex: true,
    });

    renderer.on("clickNode", ({ node }) => {
      const match = nodes.find((item) => item.id === node);
      if (match) onSelectNode(match);
    });
    renderer.on("clickEdge", ({ edge }) => {
      const match = links.find((item) => item.id === edge);
      if (match) onSelectLink(match);
    });
    renderer.on("clickStage", onClearSelection);

    return () => renderer.kill();
  }, [nodes, links, lens, selection, onSelectNode, onSelectLink, onClearSelection]);

  return (
    <section className="graph-stage analyst-map-stage" aria-label="Sigma analyst map">
      <div ref={containerRef} className="sigma-container" />
      <div className="analyst-map-hud">
        <strong>{lensLabels[lens]}</strong>
        <span>{nodes.length.toLocaleString()} nodes</span>
        <span>{links.length.toLocaleString()} links</span>
        <span>{selection.type === "none" ? "No selection" : "Selection focused"}</span>
        <button onClick={onClearSelection} disabled={selection.type === "none"}>Clear selection</button>
      </div>
      <div className="analyst-map-legend">
        <span><i className="risk-high" /> High</span>
        <span><i className="risk-structural" /> Structural</span>
        <span><i className="risk-timeline" /> Timeline</span>
        <span><i className="risk-fragility" /> Fragility</span>
      </div>
      <div className="scene-caption">Analyst map - readable 2D topology - click graph elements for evidence</div>
    </section>
  );
}
