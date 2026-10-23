import { motion } from "motion/react";
import type { RunSnapshot } from "@/lib/api";
import { ResearchRecovery, type ResearchRecoveryProps } from "./connection";
import {
  WorkspaceFrame,
  StatusPill,
  ProgressPath,
} from "@/components/workspace";
import { ModelUsageDisclosure } from "../shared/model-usage";
import {
  readableStage,
  diagnosticCount,
  formatCost,
} from "../shared/presentation";

export const stageOrder = [
  { key: "planning", label: "Planning" },
  { key: "discovery", label: "Discovery" },
  { key: "source_evaluation", label: "Source Evaluation" },
  { key: "acquisition", label: "Acquisition" },
  { key: "evidence_extraction", label: "Evidence Extraction" },
  { key: "gap_analysis", label: "Gap Analysis" },
  { key: "adaptive_search", label: "Adaptive Search" },
  { key: "deep_analysis", label: "Deep Analysis" },
  { key: "evidence_admission", label: "Evidence Admission" },
  { key: "synthesis", label: "Synthesis" },
  { key: "validation", label: "Validation" },
];

export function stageIndex(stage: string): number {
  const stages: Record<string, number> = {
    claim_planner: 0,
    v2_initial_planner: 0,
    discovery: 1,
    v2_discovery: 1,
    researchers: 2,
    supporting_researcher: 2,
    opposing_researcher: 2,
    scout: 2,
    acquisition: 3,
    probe: 3,
    extractor: 4,
    evidence_extraction: 4,
    gap_analysis: 5,
    adaptive_search: 6,
    evidence_analyst: 7,
    deep_analysis: 7,
    evidence_admission: 8,
    statement_reviewer: 8,
    claim_ledger: 8,
    debate_synthesizer: 9,
    synthesis: 9,
    final_renderer_validator: 10,
    validation: 10,
  };
  return stages[stage] ?? 0;
}

export function ProgressView({
  snapshot,
  ...recovery
}: {
  snapshot: RunSnapshot;
} & ResearchRecoveryProps) {
  const activeStage =
    snapshot.current_research_round > 1 &&
    ["claim_planner", "supporting_researcher", "opposing_researcher"].includes(
      snapshot.stage,
    )
      ? 1
      : stageIndex(snapshot.stage);
  const overall = snapshot.progress_percent;
  return (
    <motion.section
      className="progress-view"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className="progress-heading">
        <div>
          <p className="eyebrow">
            {recovery.connection.state === "connected" ? "Research in motion" : "Last confirmed progress"} · round {snapshot.current_research_round}
          </p>
          <motion.h2 layoutId={`claim-${snapshot.run_id}`}>
            {snapshot.raw_claim}
          </motion.h2>
          <p>{snapshot.message}</p>
        </div>
        <div
          className="progress-dial"
          style={{ "--progress": `${overall * 3.6}deg` } as React.CSSProperties}
        >
          <div>
            <motion.strong
              key={overall}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
            >
              {overall}%
            </motion.strong>
            <span>complete</span>
          </div>
        </div>
      </div>
      <ResearchRecovery {...recovery} />
      <WorkspaceFrame
        title="Your research notebook"
        status={<StatusPill tone="active">{recovery.connection.state === "connected" ? "Research in progress" : "Last confirmed progress"}</StatusPill>}
      >
        <ProgressPath
          labels={stageOrder.map((stage) => stage.label)}
          current={activeStage}
        />
        <p className="workspace-description">
          {snapshot.cost_usage_complete
            ? "Known model usage"
            : "Usage incomplete; reservations retained"}
          : {formatCost(snapshot.known_cost_subtotal_usd)} · Reserved exposure:{" "}
          {formatCost(snapshot.conservative_reserved_cost_usd)}
        </p>
        <ModelUsageDisclosure snapshot={snapshot} />
      </WorkspaceFrame>
      <div
        className={`stance-grid ${snapshot.research_controls.research_mode === "focused" ? "single" : ""}`}
      >
        {snapshot.supporting.status !== "disabled" && (
          <StanceCard
            title="Evidence that supports"
            progress={snapshot.supporting}
            accent="warm"
          />
        )}
        {snapshot.opposing.status !== "disabled" &&
          snapshot.research_controls.research_mode === "balanced" && (
            <StanceCard
              title="Evidence that challenges"
              progress={snapshot.opposing}
              accent="cool"
            />
          )}
      </div>
      {snapshot.v2_diagnostics && (
        <section
          className="provider-diagnostics"
          aria-label="Discovery activity"
        >
          <span>Discovery so far</span>
          <p>
            <strong>Logical discovery operations</strong>
            <small>
              {diagnosticCount(
                snapshot.v2_diagnostics.logical_discovery_operations,
              )}
            </small>
          </p>
          <p>
            <strong>Physical provider requests/pages</strong>
            <small>
              {diagnosticCount(
                snapshot.v2_diagnostics.physical_search_requests,
              )}
            </small>
          </p>
          <p>
            <strong>Retained metadata records</strong>
            <small>
              {diagnosticCount(
                snapshot.v2_diagnostics.retained_metadata_records,
              )}
            </small>
          </p>
          <p>
            <strong>Usable captures</strong>
            <small>{snapshot.v2_diagnostics.sources_survived_probe}</small>
          </p>
          <p>
            <strong>Admitted evidence records</strong>
            <small>{snapshot.v2_diagnostics.approved_evidence_records}</small>
          </p>
          {snapshot.v2_diagnostics.diagnostic_messages?.map(
            (message, index) => (
              <p key={`${index}-${message}`}>{message}</p>
            ),
          )}
        </section>
      )}
      <div className="run-footnote">
        <div>
          <span>Current stage</span>
          <strong>{readableStage(snapshot.stage)}</strong>
        </div>
        <div>
          <span>Model calls</span>
          <strong>{snapshot.model_calls_used}</strong>
        </div>
        <div>
          <span>Acquisition attempts</span>
          <strong>{snapshot.retrieval_attempts_used}</strong>
        </div>
        <div>
          <span>Estimated model cost</span>
          <strong>{formatCost(snapshot.known_cost_subtotal_usd)}</strong>
        </div>
      </div>
    </motion.section>
  );
}

export function StanceCard({
  title,
  progress,
  accent,
}: {
  title: string;
  progress: RunSnapshot["supporting"];
  accent: "warm" | "cool";
}) {
  const fill = Math.min(
    100,
    progress.usable_snapshots * 12 +
      progress.candidates * 5 +
      progress.retrieval_attempts * 2,
  );
  return (
    <article className={`stance-card ${accent}`}>
      <div className="stance-title">
        <span>{accent === "warm" ? "+" : "−"}</span>
        <h3>{title}</h3>
      </div>
      <p>{progress.status.replaceAll("_", " ")}</p>
      <div className="evidence-meter">
        <motion.i
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(fill, 4)}%` }}
        />
      </div>
      <dl>
        <div>
          <dt>Usable captures</dt>
          <motion.dd
            key={progress.usable_snapshots}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            {progress.usable_snapshots}
          </motion.dd>
        </div>
        <div>
          <dt>Candidates</dt>
          <dd>{progress.candidates}</dd>
        </div>
        <div>
          <dt>Acquisition attempts</dt>
          <dd>{progress.retrieval_attempts}</dd>
        </div>
      </dl>
    </article>
  );
}
