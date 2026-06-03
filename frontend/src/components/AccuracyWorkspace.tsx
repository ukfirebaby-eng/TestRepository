import { useEffect, useState } from "react";
import { loadAccuracyPayload } from "../api/client";
import type { AccuracyPayload } from "../api/types";

type Props = {
  documentId: string;
  documentName: string;
};

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function readableId(value: string) {
  return value.replace(/^entity_/, "").replace(/_/g, " ");
}

export function AccuracyWorkspace({ documentId, documentName }: Props) {
  const [payload, setPayload] = useState<AccuracyPayload | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    setPayload(null);
    loadAccuracyPayload(documentId)
      .then((result) => {
        if (!cancelled) {
          setPayload(result);
          setState("ready");
        }
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  if (state === "loading") {
    return <div className="empty-state pulse">Loading claim accuracy artefacts...</div>;
  }

  if (state === "error" || !payload) {
    return <div className="empty-state error">Claim accuracy artefacts unavailable.</div>;
  }

  const hasArtefacts = payload.counts.claims > 0 || payload.counts.evidence_spans > 0;
  const graphAgreement = payload.quality.graph_agreement;

  return (
    <section className="accuracy-workspace" aria-label="Claim accuracy workspace">
      <header className="report-workspace-header">
        <div>
          <p className="eyebrow">Claim accuracy workspace</p>
          <h2>{documentName}</h2>
        </div>
        <span>{payload.manifest?.validation_status || "not analysed"}</span>
      </header>

      <section className="accuracy-counts">
        <div><strong>{payload.counts.evidence_spans}</strong><span>Evidence spans</span></div>
        <div><strong>{payload.counts.claims}</strong><span>Claims</span></div>
        <div><strong>{payload.counts.validated}</strong><span>Validated</span></div>
        <div><strong>{payload.counts.needs_review}</strong><span>Needs review</span></div>
        <div><strong>{payload.counts.failed}</strong><span>Failed</span></div>
        <div><strong>{payload.counts.canonical_entities}</strong><span>Canonical entities</span></div>
        <div><strong>{payload.counts.extraction_failures}</strong><span>Extraction failures</span></div>
      </section>

      {!hasArtefacts && (
        <div className="dm-panel accuracy-empty">
          Enable the claim layer in Configuration and ingest a document to populate this workspace.
        </div>
      )}

      <section className="dm-panel accuracy-quality-panel">
        <div className="accuracy-quality-header">
          <div>
            <p className="eyebrow">Claim Quality Report</p>
            <h3>Ingestion trust signals</h3>
          </div>
          <span>{payload.quality.promotion_readiness.promotable} promotion-ready</span>
        </div>
        <div className="accuracy-quality-grid">
          <div>
            <span>Extraction coverage</span>
            <strong>{percent(payload.quality.extraction_coverage.coverage_rate)}</strong>
            <small>{payload.quality.extraction_coverage.evidence_spans_with_claims}/{payload.quality.extraction_coverage.evidence_span_count} spans cited</small>
          </div>
          <div>
            <span>Validation quality</span>
            <strong>{percent(payload.quality.validation_quality.pass_rate)}</strong>
            <small>{payload.quality.validation_quality.needs_review} review, {payload.quality.validation_quality.failed} failed</small>
          </div>
          <div>
            <span>Promotion readiness</span>
            <strong>{percent(payload.quality.promotion_readiness.promotion_rate)}</strong>
            <small>{payload.quality.promotion_readiness.promotable}/{payload.validation_results.length} claims ready</small>
          </div>
          <div>
            <span>Entity normalization</span>
            <strong>{payload.quality.entity_normalization.canonical_entities}</strong>
            <small>{payload.quality.entity_normalization.raw_aliases} raw terms grouped</small>
          </div>
        </div>
        <div className="accuracy-graph-agreement">
          <div>
            <span>Graph agreement</span>
            <strong>{percent(graphAgreement.claim_vs_legacy_overlap_rate)}</strong>
            <small>Claim vs legacy overlap</small>
          </div>
          <div>
            <span>Shared evidence</span>
            <strong>{graphAgreement.shared_canonical_edge_count}</strong>
            <small>
              {graphAgreement.claim_promoted_edge_count} claim-promoted, {graphAgreement.legacy_edge_count} legacy
            </small>
          </div>
          <div>
            <span>Review candidates</span>
            <strong>{graphAgreement.claim_only_edge_count + graphAgreement.legacy_only_edge_count}</strong>
            <small>
              {graphAgreement.claim_only_edge_count} claim-only, {graphAgreement.legacy_only_edge_count} legacy-only
            </small>
          </div>
          <p>
            Claim-promoted graph edges are compared with legacy graph extraction after entity normalization. Low overlap
            means the document should be reviewed for missed, duplicated, or disputed relationships.
          </p>
        </div>
        <div className="accuracy-graph-candidates">
          <span>Graph review candidates</span>
          <div>
            <section>
              <strong>Claim-only edges</strong>
              {graphAgreement.claim_only_edges.length > 0 ? (
                graphAgreement.claim_only_edges.map((edge) => (
                  <article
                    key={`claim-${edge.canonical_source_id}-${edge.relationship}-${edge.canonical_target_id}`}
                    className="accuracy-graph-edge"
                  >
                    <b>{readableId(edge.source_id)} {edge.relationship.toLowerCase()} {readableId(edge.target_id)}</b>
                    <small>
                      Claim {edge.claim_id || "not recorded"} · {edge.evidence_span_ids.length} evidence span(s)
                    </small>
                  </article>
                ))
              ) : (
                <small>No claim-only edges found.</small>
              )}
            </section>
            <section>
              <strong>Legacy-only edges</strong>
              {graphAgreement.legacy_only_edges.length > 0 ? (
                graphAgreement.legacy_only_edges.map((edge) => (
                  <article
                    key={`legacy-${edge.canonical_source_id}-${edge.relationship}-${edge.canonical_target_id}`}
                    className="accuracy-graph-edge"
                  >
                    <b>{readableId(edge.source_id)} {edge.relationship.toLowerCase()} {readableId(edge.target_id)}</b>
                    <small>Source chunk {edge.source_chunk_id || "not recorded"}</small>
                  </article>
                ))
              ) : (
                <small>No legacy-only edges found.</small>
              )}
            </section>
          </div>
        </div>
        <div className="accuracy-review-reasons">
          <span>Top review reasons</span>
          {payload.quality.top_review_reasons.length > 0 ? (
            payload.quality.top_review_reasons.map((item) => (
              <small key={item.reason}>{item.reason} ({item.count})</small>
            ))
          ) : (
            <small>No review reasons recorded.</small>
          )}
        </div>
      </section>

      <div className="accuracy-grid">
        <section className="dm-panel accuracy-panel">
          <p className="eyebrow">Document Manifest</p>
          {payload.manifest ? (
            <dl className="accuracy-manifest">
              <div><dt>Source hash</dt><dd>{payload.manifest.source_hash}</dd></div>
              <div><dt>Parser</dt><dd>{payload.manifest.parser_version}</dd></div>
              <div><dt>Schema</dt><dd>{payload.manifest.schema_version}</dd></div>
              <div><dt>Model</dt><dd>{payload.manifest.llm_model || "not recorded"}</dd></div>
            </dl>
          ) : (
            <p>No manifest stored for this document.</p>
          )}
        </section>

        <section className="dm-panel accuracy-panel">
          <p className="eyebrow">Validated Claims</p>
          <div className="accuracy-list">
            {payload.claims.slice(0, 8).map((claim) => (
              <article key={claim.claim_id} className="accuracy-row">
                <span>{claim.claim_type} - {claim.validation_status}</span>
                <strong>{claim.subject} {claim.predicate} {claim.object}</strong>
                <small>{claim.source_quote}</small>
              </article>
            ))}
            {payload.claims.length === 0 && <p>No claims stored.</p>}
          </div>
        </section>

        <section className="dm-panel accuracy-panel">
          <p className="eyebrow">Canonical Entities</p>
          <div className="accuracy-list">
            {payload.canonical_entities.slice(0, 8).map((entity) => (
              <article key={entity.entity_id} className="accuracy-row">
                <span>{entity.entity_type} - confidence {Math.round(entity.confidence * 100)}%</span>
                <strong>{entity.canonical_name}</strong>
                <small>Raw terms: {entity.aliases.join(", ")}</small>
              </article>
            ))}
            {payload.canonical_entities.length === 0 && <p>No canonical entities stored.</p>}
          </div>
        </section>

        <section className="dm-panel accuracy-panel wide">
          <p className="eyebrow">Evidence Spans</p>
          <div className="accuracy-list">
            {payload.evidence_spans.slice(0, 10).map((span) => (
              <article key={span.span_id} className="accuracy-row">
                <span>{span.span_type} - page {span.page_number}</span>
                <strong>{span.text}</strong>
                <small>{span.span_id}</small>
              </article>
            ))}
            {payload.evidence_spans.length === 0 && <p>No evidence spans stored.</p>}
          </div>
        </section>

        <section className="dm-panel accuracy-panel wide">
          <p className="eyebrow">Extraction Failures</p>
          <div className="accuracy-list">
            {payload.extraction_failures.slice(0, 8).map((failure) => (
              <article key={failure.id} className="accuracy-row error">
                <span>{failure.agent} - {failure.span_id || "document"}</span>
                <strong>{failure.error}</strong>
                <small>{failure.raw_payload}</small>
              </article>
            ))}
            {payload.extraction_failures.length === 0 && <p>No extraction failures recorded.</p>}
          </div>
        </section>
      </div>
    </section>
  );
}
