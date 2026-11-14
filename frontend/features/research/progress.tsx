import { motion } from "motion/react";
import { useEffect, useState } from "react";
import type { RunSnapshot } from "@/lib/api";
import { Meter } from "@/components/ui";
import { Icon } from "@/components/icons";
import { CancelRun, ResearchRecovery, type ResearchRecoveryProps } from "./connection";
import { LiveSourceShortlist } from "./live-sources";
import { formatCost } from "../shared/presentation";
import { activitySentence, formatElapsed, phaseOf, phases } from "./phases";
import { ModelUsageDisclosure } from "../shared/model-usage";

function useElapsed(startedAt: number | null): string | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (startedAt === null) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  return startedAt === null ? null : formatElapsed(now - startedAt);
}

export function ProgressView({
  snapshot,
  startedAt = null,
  ...recovery
}: {
  snapshot: RunSnapshot;
  startedAt?: number | null;
} & ResearchRecoveryProps) {
  // Phases never move backwards: a later round's search keeps the furthest phase
  // reached, and an unrecognized stage keeps the last known phase.
  const reported = phaseOf(snapshot.stage);
  const [furthest, setFurthest] = useState(reported ?? 0);
  if (reported !== null && reported > furthest) setFurthest(reported);
  const current = Math.max(furthest, reported ?? 0);
  const round = snapshot.current_research_round ?? 1;
  const elapsed = useElapsed(startedAt);
  const spent = Number(snapshot.known_cost_subtotal_usd ?? 0);
  const cap = snapshot.cost_budget_limit_usd != null ? Number(snapshot.cost_budget_limit_usd) : null;
  const found = snapshot.supporting.candidates + snapshot.opposing.candidates;
  const read = snapshot.supporting.usable_snapshots + snapshot.opposing.usable_snapshots;
  const findings = snapshot.v2_diagnostics?.approved_evidence_records;
  const live = snapshot.worker_active !== false && recovery.connection.state === "connected";
  return (
    <motion.section className="page progress-page" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <ResearchRecovery {...recovery} />
      <header className="progress-hero card">
        <div className="progress-hero-main">
          <p className="eyebrow row">
            {live ? <span className="pulse" aria-hidden="true" /> : <Icon name="clock" size={14} />}
            {live ? "Research running" : "Last confirmed progress"}
            {elapsed && <span className="subtle">· {elapsed} elapsed</span>}
          </p>
          <motion.h1 layoutId={`claim-${snapshot.run_id}`}>{snapshot.raw_claim}</motion.h1>
          <p className="activity">{activitySentence(snapshot.stage, round)}</p>
        </div>
        <div className="progress-hero-side">
          <div className="spend">
            <span className="spend-label">
              <strong>{formatCost(spent)}</strong>
              {cap != null && <> of {formatCost(cap)}</>} spent
            </span>
            {cap != null && <Meter value={spent} max={cap} label={`Model spend ${formatCost(spent)} of ${formatCost(cap)} cap`} />}
            {!snapshot.cost_usage_complete && <small className="subtle">Some usage is not reported yet; the cap still holds.</small>}
          </div>
          <CancelRun cancellation={recovery.cancellation} onCancel={recovery.onCancel} canCancel={recovery.canCancel} />
        </div>
      </header>

      <ol className="phases" aria-label="Research phases">
        {phases.map((label, index) => (
          <li
            key={label}
            className={index < current ? "done" : index === current ? "current" : ""}
            aria-current={index === current ? "step" : undefined}
          >
            <span className="phase-dot" aria-hidden="true">
              {index < current ? <Icon name="check" size={12} /> : index + 1}
            </span>
            <span>{index === 1 && round > 1 && current >= 1 ? `${label} · round ${round}` : label}</span>
          </li>
        ))}
      </ol>

      <dl className="counters">
        <div><dt>Sources found</dt><dd>{found}</dd></div>
        <div><dt>Sources read</dt><dd>{read}</dd></div>
        <div><dt>Findings so far</dt><dd>{findings ?? "—"}</dd></div>
      </dl>

      <div className="usage-row">
        <ModelUsageDisclosure snapshot={snapshot} />
      </div>

      <LiveSourceShortlist
        key={JSON.stringify([snapshot.db_path, snapshot.run_id])}
        runId={snapshot.run_id}
        database={snapshot.db_path}
        watching={live}
      />
    </motion.section>
  );
}
