import { useState } from "react";
import { Button, Chip, Disclosure, type Tone } from "@/components/ui";
import type { RunSnapshot, V2EvidenceDisplay, V2FinalResearchOutput } from "@/lib/api";
import { formatUsageTokenCount, costBasisLabel } from "../shared/model-usage";
import {
  formatCostExact,
  providerOutcomeLabel,
  readableProvider,
  researchStopLabel,
} from "../shared/presentation";

const coverageTone: Record<string, Tone> = {
  covered: "success", partial: "warning", missing: "warning", conflicting: "context",
  not_applicable: "neutral", unavailable: "neutral",
};
const coverageWord: Record<string, string> = {
  covered: "Covered", partial: "Partly covered", missing: "Not found", conflicting: "Conflicting",
  not_applicable: "Not applicable", unavailable: "Could not be searched",
};
const dimensionWord: Record<string, string> = {
  effect_or_association: "Effect or association",
  population_and_setting: "Population and setting",
  mechanism_or_pathway: "Mechanism",
  limitations_and_boundaries: "Limits and boundaries",
  counterevidence_or_alternatives: "Counterevidence and alternatives",
  replication_or_generalizability: "Replication",
};

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function MethodTab({
  snapshot,
  result,
  evidence,
  onOpenTrail,
}: {
  snapshot: RunSnapshot;
  result: V2FinalResearchOutput | null;
  evidence: V2EvidenceDisplay | null;
  onOpenTrail: () => void;
}) {
  const [copied, setCopied] = useState<"hash" | "id" | null>(null);
  const diagnostics = snapshot.v2_diagnostics;
  const assessment = evidence?.post_analysis_assessment ?? result?.post_analysis_assessment ?? null;
  const usage = snapshot.model_usage_details;
  const coverageIncomplete = Boolean(
    assessment?.coverage_incomplete ||
      assessment?.search_outcome === "incomplete_coverage" ||
      (assessment?.unresolved_gap_count ?? 0) > 0 ||
      (assessment?.partial_coverage_count ?? 0) > 0 ||
      (assessment?.unavailable_coverage_count ?? 0) > 0 ||
      result?.unresolved_material_gaps.length ||
      result?.claim_coverage_map?.some((item) => !["covered", "not_applicable"].includes(item.coverage_state)) ||
      (assessment && !result?.claim_coverage_map?.length),
  );
  const statusAfterAnalysis = !assessment
    ? null
    : coverageIncomplete || assessment.search_outcome === "incomplete_coverage"
      ? "Incomplete coverage"
      : assessment.search_outcome === "limited_evidence" ||
          (!assessment.search_outcome &&
            (assessment.unadmitted_source_count > 0 || assessment.supporting_count + assessment.challenging_count === 0))
        ? "Limited evidence"
        : "Analysis complete";
  const admittedSurvivors = assessment && result
    ? new Set(assessment.admitted_source_ids.filter((id) => result.all_surviving_sources.some((source) => source.source_id === id))).size
    : 0;
  const pending =
    snapshot.known_cost_subtotal_usd != null && snapshot.conservative_reserved_cost_usd != null
      ? Math.max(0, Number(snapshot.conservative_reserved_cost_usd) - Number(snapshot.known_cost_subtotal_usd))
      : null;
  const copy = async (value: string, which: "hash" | "id") => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(which);
    } catch {
      setCopied(null);
    }
  };
  const discoveryCounts = [
    ["Search operations", diagnostics?.logical_discovery_operations],
    ["Provider requests and pages", diagnostics?.physical_search_requests],
    ["Search results kept", diagnostics?.retained_metadata_records],
    ["Distinct works", diagnostics?.deduplicated_work_candidates],
    ["Found by following citations", diagnostics?.seed_derived_candidates],
    ["Shortlisted for reading", diagnostics?.shortlist_candidates],
    ["Pages read", diagnostics?.sources_acquired],
    ["Findings", diagnostics?.approved_evidence_records],
  ].filter((entry): entry is [string, number] => entry[1] != null);
  return (
    <div className="method-tab">
      <p className="muted">
        How this result was produced, for checking and auditing. Nothing here changes the saved brief.
      </p>
      <p className="muted">
        The label and counts describe the findings collected, counting each publication once. Study design, relevance
        and limitations decide how much each finding should weigh; counts alone cannot settle where the balance lies or
        decide the claim.
      </p>

      {result && (
        <Disclosure summary="Coverage of the claim">
          {result.claim_coverage_map?.length ? (
            <ul className="coverage-list">
              {result.claim_coverage_map.map((item) => (
                <li key={`${item.dimension}-${item.claim_component}`}>
                  <div className="row">
                    <Chip tone={coverageTone[item.coverage_state] ?? "neutral"}>{coverageWord[item.coverage_state] ?? item.coverage_state}</Chip>
                    <strong>{dimensionWord[item.dimension] ?? item.dimension}</strong>
                  </div>
                  <p className="subtle">{item.claim_component}</p>
                  <p>{item.evidence_summary}</p>
                  {item.unavailable_reason && <p className="subtle">{item.unavailable_reason}</p>}
                </li>
              ))}
            </ul>
          ) : (
            <p>Coverage of the claim was not assessed for this run.</p>
          )}
          {result.unresolved_material_gaps.length > 0 ? (
            <p>
              {result.unresolved_material_gaps.length} open question
              {result.unresolved_material_gaps.length === 1 ? " remains" : "s remain"}. They are listed in the Summary.
            </p>
          ) : (
            <p>No open questions were recorded.</p>
          )}
          {assessment && (
            <div className="method-block">
              <h4>Assessment after analysis</h4>
              {statusAfterAnalysis && <p><strong>Status after analysis: {statusAfterAnalysis}</strong></p>}
              <p>
                Findings: {assessment.supporting_count} supporting, {assessment.challenging_count} challenging,{" "}
                {assessment.qualifying_count} adding context, {assessment.unrelated_count} unrelated.
                {" "}{assessment.unadmitted_source_count} shortlisted source{assessment.unadmitted_source_count === 1 ? "" : "s"} produced no finding.
              </p>
              {!assessment.search_outcome && result.all_surviving_sources.length > 0 && (
                <p>
                  Of {result.all_surviving_sources.length} shortlisted sources, {admittedSurvivors} produced findings and{" "}
                  {result.all_surviving_sources.length - admittedSurvivors} did not.
                </p>
              )}
              {assessment.limitations.map((limitation) => <p key={limitation} className="subtle">{limitation}</p>)}
              <p className="subtle">
                {result.post_analysis_assessment?.search_outcome
                  ? "This post-analysis status is included in the saved brief and export."
                  : "Supplemental post-analysis status from saved evidence. The saved brief is unchanged; new copies and exports may include a reading aid."}
              </p>
              <p className="subtle">
                {result.post_analysis_assessment
                  ? "This assessment is included in the saved brief and export."
                  : "This is an additional assessment of saved evidence. The saved brief is unchanged; new copies and exports may include a reading aid."}
              </p>
            </div>
          )}
        </Disclosure>
      )}

      {result && (
        <Disclosure summary="Search record">
          <p><strong>{researchStopLabel(result.stopping.reason)}.</strong></p>
          <p>{result.stopping.explanation}</p>
          <p className="subtle">Rounds completed: {result.stopping.completed_rounds}.</p>
          {evidence?.research_status && (
            <div className="method-block">
              <h4>Earlier search decision</h4>
              <p><strong>{researchStopLabel(evidence.research_status.reason_code)}.</strong></p>
              <p>{evidence.research_status.explanation}</p>
              <p className="subtle">
                At that point the search counted {evidence.research_status.actionable_gap_count} open question
                {evidence.research_status.actionable_gap_count === 1 ? "" : "s"} for possible follow-up, with{" "}
                {evidence.research_status.partial_coverage_count} partly covered and{" "}
                {evidence.research_status.unavailable_coverage_count} unsearchable parts of the claim. Recorded before final
                findings were known.
              </p>
            </div>
          )}
          {evidence?.study_review_rationale && (
            <div className="method-block">
              <h4>{evidence.study_opening?.length ? "Study selection review" : "Publication check"}</h4>
              <p>{evidence.study_review_rationale}</p>
            </div>
          )}
        </Disclosure>
      )}

      <Disclosure summary="Limits and usage">
        <dl className="dl">
          <Row label={snapshot.cost_usage_complete ? "Model spend" : "Model spend so far (some usage unreported)"}>{formatCostExact(snapshot.known_cost_subtotal_usd)}</Row>
          {snapshot.cost_budget_limit_usd != null && <Row label="Spend cap">{formatCostExact(snapshot.cost_budget_limit_usd)}</Row>}
          {!snapshot.cost_usage_complete && <Row label="Held for calls without usage reports">{formatCostExact(pending)}</Row>}
          <Row label="Model calls">{snapshot.model_calls_used}</Row>
          {usage && (
            <>
              <Row label="Input tokens">{formatUsageTokenCount(usage.input_tokens)}</Row>
              <Row label="Output tokens">{formatUsageTokenCount(usage.output_tokens)}</Row>
              <Row label="Cached input tokens">{formatUsageTokenCount(usage.cached_input_tokens)}</Row>
              <Row label="Cache-write tokens">{formatUsageTokenCount(usage.cache_write_tokens)}</Row>
            </>
          )}
        </dl>
        {usage && usage.cost_basis_counts.length > 0 && (
          <p className="subtle">
            Cost basis:{" "}
            {usage.cost_basis_counts
              .map((item) => `${item.physical_calls} call${item.physical_calls === 1 ? "" : "s"}: ${costBasisLabel(item.basis)}`)
              .join(" · ")}
            . These are provider-reported usage details and estimates, not an invoice.
          </p>
        )}
        {Boolean(evidence?.budget_context?.length) && (
          <Disclosure summary="Recorded limits per source">
            {evidence?.budget_context?.map((line) => <p key={line} className="subtle">{line}</p>)}
          </Disclosure>
        )}
      </Disclosure>

      {(diagnostics?.provider_outcomes?.length || discoveryCounts.length) ? (
        <Disclosure summary="Search providers">
          {Boolean(diagnostics?.provider_outcomes?.length) && (
            <dl className="dl">
              {diagnostics?.provider_outcomes.map((outcome) => (
                <Row key={outcome.provider} label={readableProvider(outcome.provider)}>{providerOutcomeLabel(outcome)}</Row>
              ))}
            </dl>
          )}
          {discoveryCounts.length > 0 && (
            <dl className="dl">
              {discoveryCounts.map(([label, count]) => <Row key={label} label={label}>{count}</Row>)}
            </dl>
          )}
        </Disclosure>
      ) : null}

      <Disclosure summary="Release and identifiers">
        <dl className="dl">
          {result && <Row label="Release checks passed">{result.release_validation.valid ? "Yes" : "No"}</Row>}
          {snapshot.rendered_brief_hash && (
            <Row label="Release hash">
              <code>{snapshot.rendered_brief_hash.slice(0, 16)}…</code>{" "}
              <Button size="sm" variant="ghost" icon="copy" onClick={() => void copy(snapshot.rendered_brief_hash ?? "", "hash")}>
                {copied === "hash" ? "Copied" : "Copy"}
              </Button>
            </Row>
          )}
          <Row label="Run ID">
            <code>{snapshot.run_id}</code>{" "}
            <Button size="sm" variant="ghost" icon="copy" onClick={() => void copy(snapshot.run_id, "id")}>
              {copied === "id" ? "Copied" : "Copy"}
            </Button>
          </Row>
          <Row label="Database"><code>{snapshot.db_path}</code></Row>
        </dl>
        <p className="subtle">
          Release checks confirm that the brief uses only recorded findings with exact wording. They do not establish that the findings are scientifically valid.
        </p>
      </Disclosure>

      <div className="method-trail">
        <Button icon="history" onClick={onOpenTrail}>Open research trail</Button>
        <span className="subtle">Every search, source and decision recorded for this run.</span>
      </div>
    </div>
  );
}
