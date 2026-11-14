import type {
  V2EvidenceDisplay,
  V2ProviderRunDiagnostics,
  RunSnapshot,
} from "@/lib/api";

export const terminalStates = new Set([
  "released",
  "blocked",
  "failed",
  "cancelled",
  "interrupted",
  "configuration_error",
  "invalid_input",
]);

export function readableStage(stage: string): string {
  return stage
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function diagnosticCount(
  value: number | null | undefined,
): string | number {
  return value == null ? "Not recorded" : value;
}

export function assessmentRelationshipLabel(
  relationship: V2EvidenceDisplay["items"][number]["relationship_to_claim"],
): string {
  return {
    supports: "Supports part of the claim",
    challenges: "Challenges part of the claim",
    qualifies: "Adds a qualification",
    unrelated: "Not relevant to the claim",
  }[relationship];
}

/** Why the search stopped, in plain words (no trailing period). */
export function researchStopLabel(reason: string): string {
  return (
    (
      {
        sufficient_source_pool: "The search stopped because further searches were unlikely to find new sources",
        no_useful_new_direction: "The search stopped because no useful new direction was found",
        no_actionable_material_gap: "The search stopped because no open question could be searched further",
        no_productive_new_search: "The search stopped because no productive new search was available",
        no_productive_search: "The search stopped because no productive new search was available",
        duplicate_heavy: "The search stopped because new results mostly repeated earlier ones",
        provider_eligibility_exhausted: "The search stopped because no search provider could run another search",
        no_eligible_provider: "The search stopped because no search provider could run another search",
        budget: "A research limit stopped further work",
        budget_limit: "A research limit stopped further work",
        cancelled: "The research was cancelled",
        hard_round_limit: "The search reached the maximum number of rounds",
        degraded_gap_search_agent: "The follow-up search could not be completed",
        invalid_search_agent_plan: "The follow-up search plan could not be used",
        gap_analysis_unusable: "The check for open questions could not be used",
        no_novel_query: "The search stopped because no new search query was available",
        unproductive: "The search stopped because the latest search added no useful evidence",
        insufficient_reservation: "The remaining budget could not cover another search",
        terminal_failure: "Research ended after a processing failure",
      } as Record<string, string>
    )[reason] ?? "The reason the search stopped was not recognized"
  );
}

export function sourceBudgetStop(reason: string | null | undefined): string {
  return ({
    physical_call_ceiling: "The recorded call limit prevented source analysis.",
    token_reserve: "The recorded token allowance could not reserve source analysis.",
    cost_reserve: "The recorded money allowance could not reserve source analysis.",
    backfill_replaced: "Another source was selected for the available analysis slot.",
  } as Record<string, string>)[reason ?? ""] ?? "The limit that prevented source analysis was not recorded.";
}

export function sourceLocalStop(outcome: string): string {
  return ({
    source_budget_blocked: "A source-specific allowance prevented further analysis. Recorded allowances are listed separately when available.",
    token_cap_blocked: "A source-specific token limit prevented further analysis. Recorded allowances are listed separately when available.",
    physical_call_cap_blocked: "A source-specific call limit prevented further analysis. Recorded allowances are listed separately when available.",
  } as Record<string, string>)[outcome] ?? "A source-specific limit prevented further analysis; its details were not recorded.";
}

export function readableProvider(provider: string): string {
  return (
    (
      {
        serpsearch: "SERP Search",
        brave: "Brave Search",
        exa: "Exa",
        openalex: "OpenAlex",
        arxiv: "arXiv",
        pubmed: "PubMed",
        serper: "Serper",
      } as Record<string, string>
    )[provider] ?? readableStage(provider)
  );
}

export function providerOutcomeLabel(
  outcome: V2ProviderRunDiagnostics,
): string {
  const details = [];
  if (outcome.query_attempts) {
    details.push(
      `${outcome.query_attempts} quer${outcome.query_attempts === 1 ? "y" : "ies"}`,
    );
  }
  if (outcome.graph_actions) {
    details.push(
      `${outcome.graph_actions} graph action${outcome.graph_actions === 1 ? "" : "s"}`,
    );
  }
  if (outcome.query_attempts || outcome.graph_actions) {
    details.push(
      `${outcome.search_results} result${outcome.search_results === 1 ? "" : "s"}`,
    );
  }
  if (outcome.empty_queries) details.push(`${outcome.empty_queries} empty`);
  if (outcome.timeout_queries)
    details.push(`${outcome.timeout_queries} timeout`);
  if (outcome.failed_queries) details.push(`${outcome.failed_queries} failed`);
  if (outcome.blocked_queries)
    details.push(`${outcome.blocked_queries} blocked before dispatch`);
  if (outcome.unknown_queries)
    details.push(
      `${outcome.unknown_queries} outcome${outcome.unknown_queries === 1 ? "" : "s"} unknown`,
    );
  if (outcome.surviving_sources) {
    details.push(
      `${outcome.surviving_sources} surviving source${outcome.surviving_sources === 1 ? "" : "s"}`,
    );
  }
  return details.join(" · ") || "Not queried";
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

/** Money to the cent for everyday display; "—" when nothing was recorded. */
export function formatCost(value: string | number | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  const amount = Number(value);
  if (amount > 0 && amount < 0.005) return "<$0.01";
  return `$${amount.toFixed(2)}`;
}

/** Full recorded precision, used only in the Method audit view. */
export function formatCostExact(value: string | number | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value))) return "Not recorded";
  return `$${String(value)}`;
}

export function formatShortDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function plannerFailureMessage(message: string, stage?: string): string | null {
  if (/planner_duplicate_coverage_dimension/.test(message)) {
    return "The planner repeated a coverage category, so research stopped before searching for sources. Start a new run to try again.";
  }
  if (stage === "claim_planner") {
    if (/v2 (physical-call|total-token|cost) ceiling/.test(message)) {
      return "The planner stopped because the remaining research budget could not cover another model call. Check the run limits before starting a new run.";
    }
    if (/schema diagnostics|semantic response contract|schema_validation_failed|V2InitialPlanner.*validation|not one complete JSON|markdown-fenced JSON/.test(message)) {
      return "The planner returned an invalid research plan, so research stopped before searching for sources. Start a new run to try again.";
    }
  }
  return null;
}

export function understandableAttemptMessage(attempt: NonNullable<RunSnapshot["attempt_diagnostic"]>): string {
  if (attempt.classification === "invalid_input") {
    return attempt.diagnostic_component === "resume"
      ? "The latest resume attempt could not use the requested settings. Resume with the original settings or start a new run."
      : "The latest attempt could not use the requested settings. Check the research settings and try again.";
  }
  if (attempt.classification === "configuration_error") return "The latest attempt could not use the provider configuration. Check Provider setup and try again.";
  return plannerFailureMessage(attempt.message) ?? "The latest attempt did not finish. See the research trail for details.";
}

export function understandableRunMessage(snapshot: RunSnapshot): string {
  if (snapshot.classification === "released") return "The saved research result is available.";
  if (snapshot.classification === "interrupted")
    return "No active worker in this app. Saved progress and reservations are unchanged; resume with the original settings or start a new run.";
  if (snapshot.attempt_diagnostic) return understandableAttemptMessage(snapshot.attempt_diagnostic);
  if (snapshot.classification === "invalid_input") return "The research settings could not be used. Check them and try again.";
  if (snapshot.classification === "configuration_error")
    return "A provider could not be reached or configured. Check Provider setup, then try again.";
  if (snapshot.classification === "failed") {
    return plannerFailureMessage(snapshot.message, snapshot.stage) ?? "This research run did not finish. See the research trail for details.";
  }
  if (snapshot.classification === "cancelled")
    return "This research run was cancelled. Its saved evidence and progress remain available for inspection.";
  if (
    snapshot.classification === "blocked" &&
    /budget|limit|ceiling/i.test(snapshot.message)
  )
    return "Stopped due to a budget limit. The result reports any evidence and gaps that were completed before the limit.";
  if (snapshot.classification === "blocked") return "Research stopped before completion. See the research trail for details.";
  return "The recorded research status is available in the research trail.";
}

export function understandableConfigurationMessage(message: string): string {
  if (
    /MIMO_V25_INPUT_USD_PER_TOKEN|MIMO_V25_OUTPUT_USD_PER_TOKEN/.test(message)
  ) {
    return "Research needs the MiMo v2.5 input and output prices. In Provider setup, enter the published USD-per-million-token amounts as plain numbers (for example, 1.25).";
  }
  if (/LUNA_INPUT_USD_PER_TOKEN|LUNA_OUTPUT_USD_PER_TOKEN/.test(message)) {
    return "Research needs the Luna input and output prices. In Provider setup, enter the published USD-per-million-token amounts as plain numbers (for example, 1.25).";
  }
  return message;
}
