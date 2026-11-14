// Plain-language progress: five phases, an activity sentence and elapsed time.

export const phases = ["Plan", "Search", "Read", "Analyse", "Write up"] as const;

const stagePhase: Record<string, number> = {
  claim_planner: 0, v2_initial_planner: 0, planning: 0,
  discovery: 1, v2_discovery: 1, researchers: 1, supporting_researcher: 1, opposing_researcher: 1,
  scout: 1, adaptive_search: 1, gap_analysis: 1,
  acquisition: 2, probe: 2, source_evaluation: 2, source_selection: 2,
  deep_analysis: 3, evidence_analyst: 3, evidence_extraction: 3, extractor: 3, evidence_admission: 3,
  review: 3, statement_reviewer: 3, claim_ledger: 3, gap_reconciliation: 3,
  synthesis: 4, debate_synthesizer: 4, final_renderer_validator: 4, validation: 4,
};

const stageActivity: Record<string, string> = {
  claim_planner: "Planning how to research the claim",
  v2_initial_planner: "Planning how to research the claim",
  planning: "Planning how to research the claim",
  discovery: "Searching for sources",
  v2_discovery: "Searching for sources",
  researchers: "Searching for sources",
  supporting_researcher: "Searching for supporting sources",
  opposing_researcher: "Searching for challenging sources",
  scout: "Screening search results",
  gap_analysis: "Looking for open questions to search further",
  adaptive_search: "Searching for answers to open questions",
  acquisition: "Reading sources",
  probe: "Reading sources",
  source_evaluation: "Choosing which sources to read closely",
  source_selection: "Choosing which sources to read closely",
  deep_analysis: "Checking findings against the source text",
  evidence_analyst: "Checking findings against the source text",
  evidence_extraction: "Taking exact quotes from sources",
  extractor: "Taking exact quotes from sources",
  evidence_admission: "Deciding which findings to keep",
  review: "Reviewing findings",
  statement_reviewer: "Reviewing findings",
  claim_ledger: "Recording findings",
  gap_reconciliation: "Checking which open questions were answered",
  synthesis: "Writing up the brief",
  debate_synthesizer: "Writing up the brief",
  final_renderer_validator: "Checking the brief",
  validation: "Checking the brief",
};

/** Index of a stage's phase, or null when the stage is not recognized. */
export function phaseOf(stage: string): number | null {
  return stage in stagePhase ? stagePhase[stage] : null;
}

/** A plain sentence for the current activity; follow-up rounds say so instead of restarting. */
export function activitySentence(stage: string, round: number): string {
  if (round > 1 && (phaseOf(stage) === 1 || phaseOf(stage) === 0)) return `Follow-up search, round ${round}`;
  return stageActivity[stage] ?? "Working on the research";
}

export function formatElapsed(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  if (hours) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  return `${minutes}m ${String(rest).padStart(2, "0")}s`;
}
