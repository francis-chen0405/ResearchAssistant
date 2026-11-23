// Detailed stages emitted by the research pipeline, in execution order.
export const phases = [
  "Planning",
  "Searching",
  "Scouting",
  "Evaluating sources",
  "Scraping sources",
  "Extracting evidence",
  "Finding gaps",
  "Searching follow-ups",
  "Selecting sources",
  "Analyzing evidence",
  "Reviewing findings",
  "Writing up",
  "Validating",
] as const;

const phaseWords = [
  "planning", "searching", "scouting", "source evaluation", "scraping",
  "evidence extraction", "gap analysis", "follow-up searching", "source selection",
  "analysis", "review", "writing up", "validation",
] as const;

const stagePhase: Record<string, number> = {
  claim_planner: 0, v2_initial_planner: 0, planning: 0, planner: 0,
  discovery: 1, v2_discovery: 1, researchers: 1, supporting_researcher: 1, opposing_researcher: 1,
  scout: 2,
  source_evaluation: 3,
  acquisition: 4, probe: 4,
  evidence_extraction: 5, extractor: 5,
  gap_analysis: 6,
  adaptive_search: 7, search_agent: 7,
  source_selection: 8,
  deep_analysis: 9, evidence_analyst: 9, analyst: 9,
  evidence_admission: 10, review: 10, statement_reviewer: 10, claim_ledger: 10, gap_reconciliation: 10, reviewer: 10,
  synthesis: 11, debate_synthesizer: 11, synthesizer: 11,
  final_renderer_validator: 12, validation: 12,
};

const stageActivity: Record<string, string> = {
  claim_planner: "Planning how to research the claim",
  planner: "Planning how to research the claim",
  v2_initial_planner: "Planning how to research the claim",
  planning: "Planning how to research the claim",
  discovery: "Searching for sources",
  search_agent: "Planning follow-up searches",
  v2_discovery: "Searching for sources",
  researchers: "Searching for sources",
  supporting_researcher: "Searching for supporting sources",
  opposing_researcher: "Searching for challenging sources",
  scout: "Scouting search results",
  acquisition: "Scraping and capturing sources",
  probe: "Checking which sources can be read",
  gap_analysis: "Finding questions the current sources leave open",
  adaptive_search: "Searching for answers to open questions",
  source_selection: "Selecting sources for closer analysis",
  source_evaluation: "Evaluating search results",
  deep_analysis: "Analyzing source evidence",
  evidence_analyst: "Analyzing source evidence",
  analyst: "Analyzing source evidence",
  evidence_extraction: "Extracting evidence from sources",
  extractor: "Extracting evidence from sources",
  evidence_admission: "Checking which findings meet the evidence standard",
  review: "Reviewing findings",
  statement_reviewer: "Reviewing findings",
  reviewer: "Reviewing findings",
  claim_ledger: "Recording reviewed findings",
  gap_reconciliation: "Checking which open questions were answered",
  synthesis: "Writing up the research brief",
  debate_synthesizer: "Writing up the research brief",
  synthesizer: "Writing up the research brief",
  final_renderer_validator: "Validating the research brief",
  validation: "Validating the research brief",
};

/** Index of a stage's phase, or null when the stage is not recognized. */
export function phaseOf(stage: string): number | null {
  return stage in stagePhase ? stagePhase[stage] : null;
}

/** A short phase name for saved-run summaries. */
export function phaseWordOf(stage: string): string | null {
  const phase = phaseOf(stage);
  return phase === null ? null : phaseWords[phase];
}

/** A plain sentence for the current activity, with follow-up context when relevant. */
export function activitySentence(stage: string, round: number): string {
  const activity = stageActivity[stage] ?? "Working on the research";
  return round > 1 && phaseOf(stage) !== null ? `${activity} · follow-up round ${round}` : activity;
}

export function formatElapsed(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  if (hours) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  return `${minutes}m ${String(rest).padStart(2, "0")}s`;
}
