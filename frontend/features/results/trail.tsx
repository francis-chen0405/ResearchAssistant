import type { ResearchTrailItem } from "@/lib/api";
import { Dialog } from "@/components/dialog";
import type { SourceLead } from "@/lib/api";
import { SourceLeads } from "./source-leads";

export function ResearchTrailDrawer({
  items,
  error,
  onClose,
  sourceLeads,
  sourceLeadsTotal,
  sourceLeadsNotice,
  sourceLeadsLoading,
  sourceLeadsLoadingMore,
  sourceLeadsError,
  sourceLeadsHasMore,
  onLoadMoreSourceLeads,
  onRetrySourceLeads,
}: {
  items: ResearchTrailItem[] | null;
  error: string | null;
  onClose: () => void;
  sourceLeads: SourceLead[];
  sourceLeadsTotal: number;
  sourceLeadsNotice: string | null;
  sourceLeadsLoading: boolean;
  sourceLeadsLoadingMore: boolean;
  sourceLeadsError: string | null;
  sourceLeadsHasMore: boolean;
  onLoadMoreSourceLeads: () => void;
  onRetrySourceLeads: () => void;
}) {
  return (
    <Dialog title="Research trail" onClose={onClose} wide>
      <p className="panel-intro">
        Persisted trail records: {items?.length ?? "not available"}. Counts
        describe trail rows, not unique works or admitted evidence.
      </p>
      {error ? (
        <p className="form-error">{error}</p>
      ) : items === null ? (
        <p className="trail-empty">Opening the persisted trail…</p>
      ) : items.length === 0 ? (
        <p className="trail-empty">
          This run has no persisted discovery trail yet.
        </p>
      ) : (
        <div className="trail-list">
          {items.map((item, index) => (
            <details
              className={`trail-item ${item.decision}`}
              key={`${item.research_round}-${item.stance}-${item.url}-${index}`}
            >
              <summary>
                <span className="trail-score">{item.score ?? "—"}</span>
                <span>
                  <small>
                    Round {item.research_round} · {item.provider} ·{" "}
                    {item.decision}
                  </small>
                  <strong>{item.title || item.url}</strong>
                </span>
              </summary>
              {item.graph_action ? (
                <div className="preview-detail">
                  <p>
                    <b>
                      {item.graph_action.relationship === "citing"
                        ? "Citation expansion"
                        : item.graph_action.relationship === "references"
                          ? "Reference expansion"
                          : "Related-work expansion"}
                    </b>{" "}
                    from seed “
                    {item.graph_action.seed.work.title ||
                      item.graph_action.seed.work.provider_work_id ||
                      item.graph_action.seed.source_id ||
                      "untitled work"}
                    ”.
                  </p>
                  <p>
                    Action ID: {item.graph_action.artifact_id} ·{" "}
                    {item.graph_action.provider} · {item.graph_action.direction}{" "}
                    lane · round {item.graph_action.round_number}
                    {(item.graph_action.target_gap_ids ?? []).length
                      ? ` · Gap IDs: ${(item.graph_action.target_gap_ids ?? []).join(", ")}`
                      : ""}
                  </p>
                  <p>
                    Graph expansion metadata describes how this item was found;
                    it does not establish a citation relationship or count as
                    evidence.
                  </p>
                </div>
              ) : (
                (item.compiled_query || item.query_text) && (
                  <p>{item.compiled_query || item.query_text}</p>
                )
              )}
              {item.compiled_query &&
                item.query_text &&
                item.compiled_query !== item.query_text && (
                  <p>
                    <b>Original intent:</b> {item.query_text}
                  </p>
                )}
              {item.requested_metadata_depth !== null &&
                item.requested_metadata_depth !== undefined && (
                  <p>
                    <b>Metadata depth:</b> requested{" "}
                    {item.requested_metadata_depth}
                    {item.effective_metadata_depth != null
                      ? ` · effective ${item.effective_metadata_depth}`
                      : " · effective depth not recorded"}
                  </p>
                )}
              {item.acquisition_state && (
                <p>
                  <b>Acquisition:</b>{" "}
                  {item.acquisition_state.replaceAll("_", " ")}
                </p>
              )}
              {item.metadata_rank && (
                <p>
                  <b>Metadata priority:</b> {item.metadata_rank.rank} ·{" "}
                  {(item.metadata_rank.rationale ?? []).join("; ")}
                </p>
              )}
              {item.source_selection_status && (
                <p>
                  <b>Source selection:</b>{" "}
                  {item.source_selection_status.replaceAll("_", " ")}
                  {item.source_selection_rank
                    ? ` · priority ${item.source_selection_rank}`
                    : ""}
                  {item.selection_rationale
                    ? ` · ${item.selection_rationale}`
                    : ""}
                </p>
              )}
              {item.selection_input_reason && (
                <p>
                  <b>Selection input:</b> {item.selection_input_reason}
                </p>
              )}
              {item.preview && (
                <div className="preview-detail">
                  <p>
                    <b>Captured content:</b>{" "}
                    {item.preview.content_classification.replaceAll("_", " ")} ·{" "}
                    {item.preview.capture_usable === false
                      ? "unusable capture"
                      : item.preview.capture_usable === true
                        ? "substantive capture"
                        : "usability unknown"}
                    {item.preview.relevance_score !== undefined
                      ? ` · preview relevance ${item.preview.relevance_score}/100`
                      : ""}
                  </p>
                  {item.preview.snapshot_truncated && (
                    <p>
                      The saved source is incomplete. Pages or passages omitted
                      from this capture may contain additional findings.
                    </p>
                  )}
                  {Boolean(item.preview.missing_sections?.length) && (
                    <p>
                      Not observed in saved capture:{" "}
                      {item.preview.missing_sections?.join(", ")}
                    </p>
                  )}
                  <p>
                    Selection preview only; these passages have not been
                    admitted as evidence.
                  </p>
                  {item.preview.outcome === "unavailable" ? (
                    <p>{item.preview.reason.replaceAll("_", " ")}</p>
                  ) : (
                    (item.preview.spans ?? []).map((span) => (
                      <details key={`${span.start}-${span.end}`}>
                        <summary>
                          {span.section === "unknown"
                            ? "Section unknown"
                            : span.section}{" "}
                          · exact source passage
                        </summary>
                        {span.context_before && (
                          <p>
                            <small>
                              Preceding context: {span.context_before}
                            </small>
                          </p>
                        )}
                        <p>
                          {span.omitted_before ? "… " : ""}
                          {span.text}
                          {span.omitted_after ? " …" : ""}
                        </p>
                        {span.context_after && (
                          <p>
                            <small>
                              Following context: {span.context_after}
                            </small>
                          </p>
                        )}
                      </details>
                    ))
                  )}
                </div>
              )}
              {item.acquired_score !== null && (
                <p>
                  <b>After acquisition:</b> {item.acquired_score}/100 ·
                  extraction order {item.extraction_rank}
                </p>
              )}
              <a href={item.url} target="_blank" rel="noreferrer">
                Open source ↗
              </a>
              {item.breakdown && (
                <dl>
                  <div>
                    <dt>Relevance</dt>
                    <dd>{item.breakdown.relevance}</dd>
                  </div>
                  <div>
                    <dt>Intent</dt>
                    <dd>{item.breakdown.intent_match}</dd>
                  </div>
                  <div>
                    <dt>Directness</dt>
                    <dd>{item.breakdown.directness}</dd>
                  </div>
                  <div>
                    <dt>Metadata</dt>
                    <dd>{item.breakdown.metadata_completeness}</dd>
                  </div>
                  <div>
                    <dt>Access</dt>
                    <dd>{item.breakdown.likely_accessibility}</dd>
                  </div>
                  <div>
                    <dt>Novelty</dt>
                    <dd>{item.breakdown.source_novelty}</dd>
                  </div>
                  <div>
                    <dt>Penalties</dt>
                    <dd>{item.breakdown.penalties}</dd>
                  </div>
                </dl>
              )}
              {item.acquired_breakdown && (
                <dl className="acquired-breakdown">
                  <div>
                    <dt>Readability</dt>
                    <dd>{item.acquired_breakdown.readability}</dd>
                  </div>
                  <div>
                    <dt>Claim terms</dt>
                    <dd>{item.acquired_breakdown.claim_term_coverage}</dd>
                  </div>
                  <div>
                    <dt>Specificity</dt>
                    <dd>{item.acquired_breakdown.document_specificity}</dd>
                  </div>
                  <div>
                    <dt>Evidence terms</dt>
                    <dd>{item.acquired_breakdown.evidence_language}</dd>
                  </div>
                  <div>
                    <dt>Page penalties</dt>
                    <dd>{item.acquired_breakdown.penalties}</dd>
                  </div>
                </dl>
              )}
            </details>
          ))}
        </div>
      )}
      <details className="trail-source-leads">
        <summary>
          Source leads · {sourceLeads.length} of {sourceLeadsTotal} loaded
        </summary>
        <SourceLeads
          items={sourceLeads}
          total={sourceLeadsTotal}
          notice={sourceLeadsNotice}
          loading={sourceLeadsLoading}
          loadingMore={sourceLeadsLoadingMore}
          error={sourceLeadsError}
          hasMore={sourceLeadsHasMore}
          onLoadMore={onLoadMoreSourceLeads}
          onRetry={onRetrySourceLeads}
        />
      </details>
    </Dialog>
  );
}
