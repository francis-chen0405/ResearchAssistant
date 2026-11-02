import type { V2EvidenceDisplay, V2FinalResearchOutput } from "@/lib/api";
import { researchStopLabel, sourceBudgetStop, sourceLocalStop } from "../shared/presentation";

export function selectedFindings(evidence: V2EvidenceDisplay | null) {
  return ["supports", "challenges", "qualifies"]
    .map((relationship) => evidence?.items
      .filter((item) => item.relationship_to_claim === relationship)
      .sort((a, b) => (b.claim_fit ?? 0) - (a.claim_fit ?? 0) || a.ledger_claim_id.localeCompare(b.ledger_claim_id))[0])
    .filter((item): item is V2EvidenceDisplay["items"][number] => Boolean(item));
}

/** Add a reading aid to a copy; the saved release and its hash are untouched. */
export function briefWithReadingAid(brief: string, result: V2FinalResearchOutput | null, evidence: V2EvidenceDisplay | null): string {
  if (!result) return brief;
  if (evidence?.reading_aid_markdown) return evidence.reading_aid_markdown;
  const findings = evidence?.study_opening?.length ? [] : selectedFindings(evidence);
  const lines = ["# Reading aid", "", `Claim under review: ${result.exact_claim}`, "", "## Bottom line",
    !evidence
      ? "The detailed evidence is unavailable, so a conclusion cannot be assessed here."
      : evidence.items.length
        ? "The claim is not established by the admitted evidence. The available assessment does not establish the balance of evidence across independent studies."
        : "No evidence was admitted for this result, so the claim cannot be established from it."];
  if (findings.length) lines.push("Study identity and evidence balance have not been verified. These examples are selected by recorded claim fit, with a stable identifier used to break ties; they are not necessarily representative.");
  for (const item of findings) {
    const label = item.relationship_to_claim === "supports" ? "Supporting finding" : item.relationship_to_claim === "challenges" ? "Contrasting finding" : "Qualification";
    lines.push(`- ${label}: ${item.approved_factual_statement} (Read at: ${item.source_url}; publication identity not independently verified.)`);
  }
  if (evidence?.study_opening?.length) {
    lines.splice(5);
    for (const assertion of evidence.study_opening) {
      const item = evidence.items.find((item) => item.ledger_claim_id === assertion.ledger_claim_id);
      lines.push(`${assertion.text} (Read at: ${item?.source_url || "Not recorded"})`);
    }
  }
  lines.push("", "## Coverage", !result.claim_coverage_map?.length
    ? "Claim coverage was not assessed; the reason was not recorded."
    : evidence?.post_analysis_assessment?.coverage_incomplete || result.unresolved_material_gaps.length || result.claim_coverage_map.some((item) => !["covered", "not_applicable"].includes(item.coverage_state))
      ? "Coverage was assessed and gaps or incomplete dimensions remain."
      : "Coverage was assessed and no gaps were recorded; this does not prove complete coverage.",
    "", `Research direction: ${result.directions.support_enabled && result.directions.challenge_enabled ? "supporting and challenging evidence" : result.directions.support_enabled ? "supporting evidence only" : "challenging evidence only"}`,
    "", "## Earlier search decision", researchStopLabel(result.stopping.reason),
    "", "## Admitted evidence and reading locations");
  lines.push(...(evidence?.budget_context ?? []));
  for (const outcome of evidence?.source_budget_outcomes ?? []) {
    const source = result.all_surviving_sources.find((item) => item.source_id === outcome.source_id);
    lines.push(`- ${source?.title || "Source"}: ${sourceLocalStop(outcome.outcome)}`);
  }
  for (const source of result.all_surviving_sources) {
    if (source.status === "budget_prevented_analysis" && !(evidence?.source_budget_outcomes ?? []).some((item) => item.source_id === source.source_id)) lines.push(`- ${source.title || "Source"}: ${sourceBudgetStop(source.budget_prevented_reason)}`);
  }
  for (const item of evidence?.items ?? []) {
    const publication = item.verified_publication;
    const citation = publication
      ? `${publication.title || "Title not recorded"}; ${(publication.authors ?? []).join(", ") || "Author not recorded"}; ${publication.publication_date || "Year not recorded"}; ${publication.venue || "Venue not recorded"}; ${publication.canonical_url} (${publication.verification === "crossref_doi" ? "Crossref DOI metadata" : "reviewed authoritative identifier"})`
      : `Recorded title: ${item.title || "Not recorded"}; Publication identity is not verified here`;
    lines.push(`- ${item.approved_factual_statement}\n  ${citation}. Read at: ${item.source_url}.`, "  The recorded passage may be incomplete; check the reading location for context.");
  }
  if (!evidence?.items.length) lines.push("- Detailed admitted passages are unavailable or none were admitted.");
  lines.push("", "## Original released brief", "The original released brief and its recorded hash remain unchanged in the research history. This report is generated from saved evidence.");
  return lines.join("\n");
}
