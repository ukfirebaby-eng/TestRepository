import type { GraphLink, GraphNode, NormalizedGraph } from "../api/types";
import type { LinkDetail, NodeDetail } from "../graph/details";
import { buildEvidenceViewModel } from "../ui/evidenceViewModel";

type Props = {
  selectedNode: GraphNode | null;
  selectedLink: GraphLink | null;
  nodeDetail: NodeDetail | null;
  linkDetail: LinkDetail | null;
  graph: NormalizedGraph | null;
  onSelectNode: (node: GraphNode) => void;
  onClearSelection: () => void;
  placement: "contextual" | "drawer";
};

const evidenceSectionTitles = ["What this is", "Why it matters", "Recommended action", "Supporting graph evidence"] as const;

function findNode(graph: NormalizedGraph | null, nodeId: string): GraphNode | null {
  return graph?.nodes.find((node) => node.id === nodeId) || null;
}

export function SelectedEvidencePanel({ selectedNode, selectedLink, nodeDetail, linkDetail, graph, onSelectNode, onClearSelection, placement }: Props) {
  const hasSelection = Boolean(selectedNode || selectedLink);
  const model = linkDetail
    ? buildEvidenceViewModel({
        selectionType: "link",
        title: linkDetail.relationship,
        riskKind: linkDetail.riskKind,
        riskScore: linkDetail.riskScore,
        severity: linkDetail.severity,
        probability: linkDetail.probability,
        sourceName: linkDetail.sourceName,
        targetName: linkDetail.targetName,
        isSelfReferential: linkDetail.isSelfReferential,
        finding: linkDetail.finding,
        plainEnglish: linkDetail.plainEnglish,
        analysis: linkDetail.analysis,
      })
    : nodeDetail
      ? buildEvidenceViewModel({
          selectionType: "node",
          title: nodeDetail.title,
          label: nodeDetail.label,
          riskKind: nodeDetail.riskKind,
          riskScore: nodeDetail.riskScore,
          connections: nodeDetail.connections,
          fragilityInsight: nodeDetail.fragility?.insight,
        })
      : null;

  return (
    <div className={`dm-panel panel-section selected-evidence-panel ${placement} ${hasSelection ? "evidence-selected" : "evidence-empty"}`}>
      <p className="eyebrow">Selected Evidence</p>
      <h2>{model?.heading || selectedNode?.name || selectedLink?.relationship || "Select a node or risk path"}</h2>
      {model ? (
        <div className="detail-stack">
          <p className="evidence-subheading">{model.subheading}</p>
          <div className="detail-pills">
            {model.badges.map((badge) => <span className="dm-chip" key={badge}>{badge}</span>)}
          </div>
          {model.sections.map((section) => (
            <div key={section.title}>
              <h3>{section.title}</h3>
              <p>{section.body}</p>
              {section.title === evidenceSectionTitles[3] && nodeDetail && (
                nodeDetail.connections.length ? (
                  <div className="connection-list">
                    {nodeDetail.connections.slice(0, 8).map((connection) => (
                      <button key={`${connection.direction}-${connection.nodeId}-${connection.relationship}`} onClick={() => {
                        const match = findNode(graph, connection.nodeId);
                        if (match) onSelectNode(match);
                      }}>
                        <span>{connection.direction === "outgoing" ? "->" : "<-"} {connection.relationship}</span>
                        {connection.nodeName}
                      </button>
                    ))}
                  </div>
                ) : <p>No direct standard connections found.</p>
              )}
              {section.title === evidenceSectionTitles[3] && selectedLink && linkDetail && (
                <div className="link-path">
                  <button onClick={() => {
                    const match = findNode(graph, selectedLink.source);
                    if (match) onSelectNode(match);
                  }}>{linkDetail.sourceName}</button>
                  {!linkDetail.isSelfReferential && (
                    <>
                      <span>-&gt;</span>
                      <button onClick={() => {
                        const match = findNode(graph, selectedLink.target);
                        if (match) onSelectNode(match);
                      }}>{linkDetail.targetName}</button>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
          {nodeDetail?.fragility && (
            <div>
              <h3>Cascade Path</h3>
              <ol className="cascade-list">
                {(nodeDetail.fragility.cascade_nodes || []).map((name) => <li key={name}>{name}</li>)}
              </ol>
            </div>
          )}
          <button className="clear-selection-action" onClick={onClearSelection}>Clear selection</button>
        </div>
      ) : (
        <p>Select a node or risk path to inspect evidence.</p>
      )}
    </div>
  );
}
