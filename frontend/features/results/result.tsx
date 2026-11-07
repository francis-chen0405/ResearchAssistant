import { AnimatePresence, motion } from "motion/react";
import { useMemo } from "react";
import type { RunSnapshot, V2EvidenceDisplay, V2FinalResearchOutput } from "@/lib/api";
import { briefWithReadingAid } from "./reading-aid";
import { formatUsageTokenCount } from "../shared/model-usage";
import {
  readableStage,
  readableProvider,
  understandableRunMessage,
  understandableAttemptMessage,
  providerOutcomeLabel,
  formatCost,
} from "../shared/presentation";
import { V2ResultPaper } from "./paper";
import { ResearchTrailDrawer } from "./trail";
import { AllLiveSources } from "../research/live-sources";
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
  const discoveryCounts = [
    ["Logical discovery operations", diagnostics?.logical_discovery_operations],
    ["Physical provider requests/pages", diagnostics?.physical_search_requests],
    ["Retained metadata records", diagnostics?.retained_metadata_records],
    ["Deduplicated work candidates", diagnostics?.deduplicated_work_candidates],
    ["Seed-derived candidates", diagnostics?.seed_derived_candidates],
    ["Acquisition shortlist", diagnostics?.shortlist_candidates],
    ["Admitted evidence records", diagnostics?.approved_evidence_records],
  ] as const;
  const recordedDiscoveryCounts = discoveryCounts.filter(([, count]) => count != null);
  const pendingReservation = snapshot.known_cost_subtotal_usd != null && snapshot.conservative_reserved_cost_usd != null
    ? Math.max(0, Number(snapshot.conservative_reserved_cost_usd) - Number(snapshot.known_cost_subtotal_usd))
    : null;
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
              ? "Released research"
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
      <div className="report-layout">
        <article className="brief-paper">
          {v2Result ? (
            <V2ResultPaper result={v2Result} evidence={v2Evidence} run={snapshot} />
          ) : snapshot.final_brief ? (
            <Brief text={snapshot.final_brief} />
          ) : (
            <div className="empty-brief">
              <h3>No brief was released.</h3>
              <p>{userStatus}</p>
              {snapshot.validation_errors.length > 0 && <p>The result did not pass release checks. Details are available in the research trail.</p>}
            </div>
          )}
        </article>
        <aside className="report-meta">
          {!released && <p>{userStatus}</p>}
          {snapshot.attempt_diagnostic &&
            !["planned", "running"].includes(
              snapshot.persisted_status ?? "",
            ) && (
              <p role="status">
                Latest execution attempt: {understandableAttemptMessage(snapshot.attempt_diagnostic)}
              </p>
            )}
          <dl>
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
            {diagnostics?.search_attempts != null && (
              <div>
                <dt>Logical query attempts</dt>
                <dd>{diagnostics.search_attempts}</dd>
              </div>
            )}
            {diagnostics?.sources_acquired != null && (
              <div>
                <dt>Sources acquired</dt>
                <dd>{diagnostics.sources_acquired}</dd>
              </div>
            )}
            <div>
              <dt>
                {snapshot.cost_usage_complete
                  ? "Known model spend"
                  : "Known model spend so far"}
              </dt>
              <dd>{snapshot.known_cost_subtotal_usd == null ? "Not recorded" : formatCost(snapshot.known_cost_subtotal_usd)}</dd>
            </div>
            {snapshot.cost_budget_limit_usd != null && (
              <div>
                <dt>Model cost budget</dt>
                <dd>{formatCost(snapshot.cost_budget_limit_usd)}</dd>
              </div>
            )}
            {!snapshot.cost_usage_complete && (
              <div>
                <dt>Held for calls without usage reports</dt>
                <dd>{pendingReservation == null ? "Not recorded" : formatCost(pendingReservation)}</dd>
              </div>
            )}
            {snapshot.model_usage_details && (
              <>
                <div>
                  <dt>Input tokens</dt>
                  <dd>{formatUsageTokenCount(snapshot.model_usage_details.input_tokens)}</dd>
                </div>
                <div>
                  <dt>Output tokens</dt>
                  <dd>{formatUsageTokenCount(snapshot.model_usage_details.output_tokens)}</dd>
                </div>
                <div>
                  <dt>Cached input tokens</dt>
                  <dd>{formatUsageTokenCount(snapshot.model_usage_details.cached_input_tokens)}</dd>
                </div>
                <div>
                  <dt>Cache-write tokens</dt>
                  <dd>{formatUsageTokenCount(snapshot.model_usage_details.cache_write_tokens)}</dd>
                </div>
              </>
            )}
          </dl>
          {recordedDiscoveryCounts.length > 0 && (
            <details className="provider-diagnostics">
              <summary>Discovery counts</summary>
              <dl>
                {recordedDiscoveryCounts.map(([label, count]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{count}</dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
          {Boolean(diagnostics?.provider_outcomes?.length) && (
            <section className="provider-diagnostics">
              <span>Provider outcomes</span>
              <dl>
                {diagnostics?.provider_outcomes.map((outcome) => (
                  <div key={outcome.provider}>
                    <dt>{readableProvider(outcome.provider)}</dt>
                    <dd>{providerOutcomeLabel(outcome)}</dd>
                  </div>
                ))}
              </dl>
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
                    briefWithReadingAid(snapshot.final_brief ?? "", v2Result, v2Evidence),
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
              onClick={() => downloadBrief(snapshot, v2Result, v2Evidence)}
            >
              <span>Download brief</span>
              <b>↓</b>
            </button>
          )}
          {!v2Result && <AllLiveSources runId={snapshot.run_id} database={snapshot.db_path} />}
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
            sourceLeads={sourceLeads}
            sourceLeadsTotal={sourceLeadsTotal}
            sourceLeadsNotice={sourceLeadsNotice}
            sourceLeadsLoading={sourceLeadsLoading}
            sourceLeadsLoadingMore={sourceLeadsLoadingMore}
            sourceLeadsError={sourceLeadsError}
            sourceLeadsHasMore={sourceLeadsHasMore}
            onLoadMoreSourceLeads={() => void loadMoreSourceLeads()}
            onRetrySourceLeads={retrySourceLeads}
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

export function downloadBrief(snapshot: RunSnapshot, result: V2FinalResearchOutput | null = null, evidence: V2EvidenceDisplay | null = null): void {
  if (!snapshot.final_brief) return;
  const blob = new Blob([briefWithReadingAid(snapshot.final_brief, result, evidence)], {
    type: "text/markdown;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `research-brief-${snapshot.run_id}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}
