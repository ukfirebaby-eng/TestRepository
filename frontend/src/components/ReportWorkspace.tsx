import type { GraphLink, GraphNode, NormalizedGraph } from "../api/types";
import { GeneratedReportsPanel } from "./GeneratedReportsPanel";
import { OperationalReportsPanel } from "./OperationalReportsPanel";

type Props = {
  documentId: string;
  documentName: string;
  graph: NormalizedGraph;
  onFocusGraphItem: (item: GraphNode | GraphLink) => void;
};

export function ReportWorkspace({ documentId, documentName, graph, onFocusGraphItem }: Props) {
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
        <section className="dm-panel report-workspace-panel operational">
          <p className="eyebrow">Operational Reports</p>
          <OperationalReportsPanel
            documentId={documentId}
            graph={graph}
            onFocusGraphItem={onFocusGraphItem}
            variant="workspace"
          />
        </section>
        <section className="dm-panel report-workspace-panel generated">
          <p className="eyebrow">Generated Intelligence</p>
          <GeneratedReportsPanel documentId={documentId} documentName={documentName} variant="workspace" />
        </section>
      </div>
    </section>
  );
}
