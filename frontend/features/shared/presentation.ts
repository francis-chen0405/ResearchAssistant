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

export function researchStopLabel(reason: string): string {
  return (
    (
      {
        sufficient_source_pool:
          "Search stopped after the source pool was considered sufficient",
        no_useful_new_direction: "No useful new research direction was found",
        no_actionable_material_gap: "No actionable research gap remained",
        no_productive_new_search: "No productive new search was available",
        no_productive_search: "No productive new search was available",
        duplicate_heavy: "Search results substantially overlapped",
        provider_eligibility_exhausted: "No eligible search provider remained",
        budget: "The research budget was reached",
        budget_limit: "The research budget was reached",
        cancelled: "Research was cancelled",
        hard_round_limit: "The maximum number of research rounds was reached",
        degraded_gap_search_agent:
          "The follow-up search could not be completed",
        invalid_search_agent_plan: "The follow-up search plan was invalid",
        gap_analysis_unusable: "The follow-up gap assessment could not be used",
        no_novel_query: "No new search query was available",
        no_eligible_provider: "No eligible search provider remained",
        unproductive: "The latest search did not add useful evidence",
        insufficient_reservation:
          "The remaining budget could not reserve another search",
        terminal_failure: "Research ended after a processing failure",
      } as Record<string, string>
    )[reason] ?? readableStage(reason)
  );
}

export function readableProvider(provider: string): string {
  return (
    (
      {
        serpsearch: "SERP Search",
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

export function formatCost(value: string | number | null): string {
  if (value === null) return "Pending";
  return `$${Number(value).toFixed(4)}`;
}

export function understandableRunMessage(snapshot: RunSnapshot): string {
  if (snapshot.attempt_diagnostic || snapshot.classification === "interrupted")
    return snapshot.message;
  if (snapshot.classification === "configuration_error")
    return "A provider could not be reached or configured. Check Provider setup, then try again.";
  if (snapshot.classification === "failed") {
    return (
      snapshot.message.trim() ||
      "This research run did not finish. Reopen the saved run after resolving the reported issue."
    );
  }
  if (snapshot.classification === "cancelled")
    return "This research run was cancelled. Its saved evidence and progress remain available for inspection.";
  if (
    snapshot.classification === "blocked" &&
    /budget|limit|ceiling/i.test(snapshot.message)
  )
    return "Stopped due to a budget limit. The result reports any evidence and gaps that were completed before the limit.";
  return snapshot.message;
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
