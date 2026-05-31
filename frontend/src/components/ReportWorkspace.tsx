import type { GraphLink, GraphNode, NormalizedGraph } from "../api/types";
import { GeneratedReportsPanel } from "./GeneratedReportsPanel";
import { OperationalReportsPanel } from "./OperationalReportsPanel";

type Props = {
  documentId: string;
  documentName: string;
  graph: NormalizedGraph;
  onSelectNode: (node: GraphNode) => void;
  onSelectLink: (link: GraphLink) => void;
};

export function ReportWorkspace({ documentId, documentName, graph, onSelectNode, onSelectLink }: Props) {
  return (
    <section className="report-workspace" aria-label="Reports workspace">
      <header className="report-workspace-header">
        <div>
          <p className="eyebrow">Reports workspace</p>
          <h2>{documentName}</h2>
        </div>
        <span>{graph.metrics.nodes.toLocaleString()} nodes analysed</span>
      </header>
      <div className="report-workspace-grid">
        <section className="report-workspace-panel operational">
          <p className="eyebrow">Operational Reports</p>
          <OperationalReportsPanel
            documentId={documentId}
            graph={graph}
            onSelectNode={onSelectNode}
            onSelectLink={onSelectLink}
            variant="workspace"
          />
        </section>
        <section className="report-workspace-panel generated">
          <p className="eyebrow">Generated Intelligence</p>
          <GeneratedReportsPanel documentId={documentId} documentName={documentName} variant="workspace" />
        </section>
      </div>
    </section>
  );
}
