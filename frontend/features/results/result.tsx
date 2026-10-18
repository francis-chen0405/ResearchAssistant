import { AnimatePresence, motion } from "motion/react";
import { useMemo } from "react";
import type { RunSnapshot } from "@/lib/api";
import { ModelUsageDisclosure } from "../shared/model-usage";
import {
  readableStage,
  readableProvider,
  understandableRunMessage,
  diagnosticCount,
  providerOutcomeLabel,
  formatCost,
} from "../shared/presentation";
import { V2ResultPaper } from "./paper";
import { SourceLeads } from "./source-leads";
import { ResearchTrailDrawer } from "./trail";
import { useResult } from "./use-result";

export function ResultView({
  snapshot,
  onNew,
}: {
  snapshot: RunSnapshot;
  onNew: () => void;
}) {
  const released = snapshot.classification === "released";
  const userStatus = understandableRunMessage(snapshot);
  const diagnostics = snapshot.v2_diagnostics;
  const {
    v2Result,
    v2Evidence,
    trailOpen,
    setTrailOpen,
    trail,
    resultError,
    setResultError,
    trailError,
    openTrail,
    sourceLeads,
    sourceLeadsTotal,
    sourceLeadsNotice,
    sourceLeadsLoading,
    sourceLeadsLoadingMore,
    sourceLeadsError,
    sourceLeadsHasMore,
    loadMoreSourceLeads,
    retrySourceLeads,
  } = useResult(snapshot);
  return (
    <motion.section
      className={`result-view ${released ? "released" : "unreleased"}`}
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
    >
      <div className="result-masthead">
        <div>
          <p className="eyebrow">
            {released
              ? "Validated release"
              : readableStage(snapshot.classification)}
          </p>
          <motion.h2 layoutId={`claim-${snapshot.run_id}`}>
            {snapshot.raw_claim}
          </motion.h2>
        </div>
        <div className="release-stamp">
          <span>{released ? "Released" : "Not released"}</span>
          <small>{released ? "Provenance checked" : "Incomplete result"}</small>
        </div>
      </div>
      {resultError && (
        <p className="setup-status" role="status">
          {resultError}
        </p>
      )}
      <SourceLeads
        items={sourceLeads}
        total={sourceLeadsTotal}
        notice={sourceLeadsNotice}
        loading={sourceLeadsLoading}
        loadingMore={sourceLeadsLoadingMore}
        error={sourceLeadsError}
        hasMore={sourceLeadsHasMore}
        onLoadMore={() => void loadMoreSourceLeads()}
        onRetry={retrySourceLeads}
      />
      <div className="report-layout">
        <article className="brief-paper">
          {v2Result ? (
            <V2ResultPaper result={v2Result} evidence={v2Evidence} />
          ) : snapshot.final_brief ? (
            <Brief text={snapshot.final_brief} />
          ) : (
            <div className="empty-brief">
              <h3>No brief was released.</h3>
              <p>{userStatus}</p>
              {snapshot.validation_errors.map((error) => (
                <p key={error}>{error}</p>
              ))}
            </div>
          )}
        </article>
        <aside className="report-meta">
          <p>{userStatus}</p>
          {snapshot.attempt_diagnostic &&
            !["planned", "running"].includes(
              snapshot.persisted_status ?? "",
            ) && (
              <p role="status">
                Latest execution attempt: {snapshot.attempt_diagnostic.message}
              </p>
            )}
          <section className="provider-diagnostics">
            <span>Frozen research settings</span>
            <p>
              <strong>Sources per direction per round</strong>
              <small>
                {snapshot.research_controls.sources_per_stance_per_round ??
                  "Not recorded"}
              </small>
            </p>
            <p>
              <strong>Metadata depth</strong>
              <small>
                {snapshot.research_controls.metadata_depth ?? "Not recorded"}
              </small>
            </p>
            <p>
              <strong>Paper expansion</strong>
              <small>
                {snapshot.research_controls.seed_expansion_enabled === null ||
                snapshot.research_controls.seed_expansion_enabled === undefined
                  ? "Not recorded"
                  : snapshot.research_controls.seed_expansion_enabled
                    ? "Enabled"
                    : "Disabled"}
              </small>
            </p>
            <p>
              <strong>Scholarly search</strong>
              <small>
                {snapshot.research_controls.scholarly_search_mode ??
                  "Not recorded"}
              </small>
            </p>
          </section>
          <dl>
            <div>
              <dt>Final stage</dt>
              <dd>{readableStage(snapshot.stage)}</dd>
            </div>
            <div>
              <dt>Discovery sources</dt>
              <dd>
                {(
                  diagnostics?.configured_providers ??
                  snapshot.research_controls.discovery_providers
                )
                  .map(readableProvider)
                  .join(", ") || "Historical run"}
              </dd>
            </div>
            <div>
              <dt>Model calls</dt>
              <dd>{snapshot.model_calls_used}</dd>
            </div>
            <div>
              <dt>Logical query attempts</dt>
              <dd>{diagnostics?.search_attempts ?? "Not recorded"}</dd>
            </div>
            <div>
              <dt>Graph actions</dt>
              <dd>{diagnostics?.graph_actions ?? "Not recorded"}</dd>
            </div>
            <div>
              <dt>Sources acquired</dt>
              <dd>{diagnostics?.sources_acquired ?? "Not recorded"}</dd>
            </div>
            <div>
              <dt>Estimated model cost</dt>
              <dd>{formatCost(snapshot.known_cost_subtotal_usd)}</dd>
            </div>
            <div>
              <dt>Budget status</dt>
              <dd>
                {!snapshot.cost_usage_complete
                  ? "Usage incomplete; reservations retained"
                  : snapshot.classification === "released"
                    ? "Recorded model usage"
                    : "Research stopped"}
              </dd>
            </div>
          </dl>
          <ModelUsageDisclosure snapshot={snapshot} />
          {diagnostics && (
            <section className="provider-diagnostics">
              <span>Discovery counts</span>
              <p>
                <strong>Logical discovery operations</strong>
                <small>
                  {diagnosticCount(diagnostics.logical_discovery_operations)}
                </small>
              </p>
              <p>
                <strong>Physical provider requests/pages</strong>
                <small>
                  {diagnosticCount(diagnostics.physical_search_requests)}
                </small>
              </p>
              <p>
                <strong>Retained metadata records</strong>
                <small>
                  {diagnosticCount(diagnostics.retained_metadata_records)}
                </small>
              </p>
              <p>
                <strong>Deduplicated work candidates</strong>
                <small>
                  {diagnosticCount(diagnostics.deduplicated_work_candidates)}
                </small>
              </p>
              <p>
                <strong>Seed-derived candidates</strong>
                <small>
                  {diagnosticCount(diagnostics.seed_derived_candidates)}
                </small>
              </p>
              <p>
                <strong>Acquisition shortlist</strong>
                <small>
                  {diagnosticCount(diagnostics.shortlist_candidates)}
                </small>
              </p>
              <p>
                <strong>Admitted evidence records</strong>
                <small>{diagnostics.approved_evidence_records}</small>
              </p>
            </section>
          )}
          {Boolean(diagnostics?.diagnostic_messages?.length) && (
            <section className="provider-diagnostics">
              <span>Research notes</span>
              {diagnostics?.diagnostic_messages?.map((message, index) => (
                <p key={`${index}-${message}`}>{message}</p>
              ))}
            </section>
          )}
          {diagnostics && (
            <section className="provider-diagnostics">
              <span>Provider outcomes</span>
              {diagnostics.provider_outcomes.map((outcome) => (
                <p key={outcome.provider}>
                  <strong>{readableProvider(outcome.provider)}</strong>
                  <small>{providerOutcomeLabel(outcome)}</small>
                </p>
              ))}
            </section>
          )}
          {snapshot.rendered_brief_hash && (
            <button
              className="hash-button"
              type="button"
              onClick={() =>
                void navigator.clipboard.writeText(
                  snapshot.rendered_brief_hash ?? "",
                )
              }
            >
              <span>Release hash</span>
              <code>{snapshot.rendered_brief_hash.slice(0, 12)}…</code>
              <b>Copy</b>
            </button>
          )}
          {snapshot.final_brief && (
            <button
              className="download-action"
              type="button"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(
                    snapshot.final_brief ?? "",
                  );
                  setResultError("Brief copied.");
                } catch {
                  setResultError(
                    "The brief could not be copied. Use Download brief instead.",
                  );
                }
              }}
            >
              Copy brief <span aria-hidden="true">↗</span>
            </button>
          )}
          {snapshot.final_brief && (
            <button
              className="download-action"
              type="button"
              onClick={() => downloadBrief(snapshot)}
            >
              <span>Download brief</span>
              <b>↓</b>
            </button>
          )}
          <button
            className="trail-action"
            type="button"
            onClick={() => void openTrail()}
          >
            <span>Research trail</span>
            <b>↗</b>
          </button>
          <button className="secondary-action" type="button" onClick={onNew}>
            Start new research <span aria-hidden="true">↗</span>
          </button>
        </aside>
      </div>
      <AnimatePresence>
        {trailOpen && (
          <ResearchTrailDrawer
            items={trail}
            error={trailError}
            onClose={() => setTrailOpen(false)}
          />
        )}
      </AnimatePresence>
    </motion.section>
  );
}

export function Brief({ text }: { text: string }) {
  const lines = useMemo(
    () => text.split("\n").filter((line) => line.trim()),
    [text],
  );
  return lines.map((line, index) => {
    const clean = line.trim();
    if (clean.startsWith("# ")) return <h1 key={index}>{clean.slice(2)}</h1>;
    if (clean.startsWith("## ")) return <h2 key={index}>{clean.slice(3)}</h2>;
    if (clean.startsWith("### ")) return <h3 key={index}>{clean.slice(4)}</h3>;
    const parts = clean.replace(/^[-*]\s+/, "").split(/(\[[^\]]+\])/g);
    return (
      <p key={index}>
        {parts.map((part, partIndex) =>
          /^\[[^\]]+\]$/.test(part) ? (
            <mark key={partIndex}>{part}</mark>
          ) : (
            part
          ),
        )}
      </p>
    );
  });
}

export function downloadBrief(snapshot: RunSnapshot): void {
  if (!snapshot.final_brief) return;
  const blob = new Blob([snapshot.final_brief], {
    type: "text/markdown;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `research-brief-${snapshot.run_id}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}
