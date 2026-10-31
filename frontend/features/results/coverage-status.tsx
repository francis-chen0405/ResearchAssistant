import type { V2EvidenceDisplay, V2FinalResearchOutput } from "@/lib/api";
import { readableStage, researchStopLabel } from "../shared/presentation";

export function CoverageStatus({
  result,
  evidence,
}: {
  result: V2FinalResearchOutput;
  evidence: V2EvidenceDisplay | null;
}) {
  const coverage = evidence?.research_status;
  const statusLabel = coverage ? researchStopLabel(coverage.reason_code) : "";
  const assessment = evidence?.post_analysis_assessment;
  const coverageIncomplete =
    assessment?.coverage_incomplete ??
    (!!assessment &&
      (assessment.unresolved_gap_count > 0 ||
        assessment.partial_coverage_count > 0 ||
        assessment.unavailable_coverage_count > 0 ||
        !result.claim_coverage_map?.length ||
        result.claim_coverage_map.some(
          (item) =>
            !["covered", "not_applicable"].includes(item.coverage_state),
        )));
  const searchOutcome = assessment
    ? (assessment.search_outcome ??
      (coverageIncomplete
        ? "incomplete_coverage"
        : assessment.unadmitted_source_count > 0 ||
            assessment.supporting_count + assessment.challenging_count === 0
          ? "limited_evidence"
          : "analysis_complete"))
    : null;
  const searchOutcomeLabel =
    searchOutcome === "incomplete_coverage"
      ? "Incomplete coverage"
      : searchOutcome === "limited_evidence"
        ? "Limited evidence"
        : searchOutcome === "analysis_complete"
          ? "Analysis complete"
          : "";
  const searchOutcomeExplanation =
    searchOutcome === "incomplete_coverage"
      ? !result.claim_coverage_map?.length
        ? `${
            assessment?.unresolved_gap_count === 0
              ? "No unresolved evidence gaps were recorded."
              : `${assessment?.unresolved_gap_count ?? 0} unresolved evidence gaps were recorded.`
          } Claim coverage was not assessed because the saved result contains no claim-coverage assessment.`
        : "The saved coverage assessment records gaps or incomplete dimensions, so conclusions are limited."
      : searchOutcome === "limited_evidence"
        ? "Some evidence was not admitted, or the admitted findings do not include direct support or challenge. The source outcomes and limitations below show what was retained."
        : searchOutcome === "analysis_complete"
          ? "Research met the recorded coverage checks. This does not prove the claim."
          : "";
  const admittedSurvivorCount = assessment
    ? new Set(
        assessment.admitted_source_ids.filter((id) =>
          result.all_surviving_sources.some(
            (source) => source.source_id === id,
          ),
        ),
      ).size
    : 0;
  const noAdmittedSurvivorCount = Math.max(
    0,
    result.all_surviving_sources.length - admittedSurvivorCount,
  );
  const assessmentLimitations = (assessment?.limitations ?? []).filter(
    (limitation) =>
      !/^\d+ selected source\(s\) produced no admitted evidence;/.test(
        limitation,
      ),
  );
  const assessmentOrigin = result.post_analysis_assessment
    ? "This assessment is included in the saved brief and export."
    : "This is an additional assessment of saved evidence. The saved brief and export are unchanged.";
  const terminalStatusOrigin = result.post_analysis_assessment?.search_outcome
    ? "This post-analysis status is included in the saved brief and export."
    : "Supplemental post-analysis status from saved evidence. The saved brief and export are unchanged.";
  const claimStatus = assessment
    ? assessment.supporting_count > assessment.challenging_count
      ? "Supporting findings observed; claim not established"
      : assessment.challenging_count > assessment.supporting_count
        ? "Challenging findings observed; claim not established"
        : assessment.supporting_count > 0
          ? "Mixed supporting and challenging findings; claim not established"
          : "Inconclusive: no admitted supporting or challenging finding"
    : null;
  return (
    <>
      {assessment && (
        <div className="result-limitation" role="status">
          <strong>Post-analysis research status · {searchOutcomeLabel}</strong>
          <p>{searchOutcomeExplanation}</p>
          <p>
            Admitted findings: {assessment.supporting_count} supporting,{" "}
            {assessment.challenging_count} challenging,{" "}
            {assessment.qualifying_count} qualifying, and{" "}
            {assessment.unrelated_count} unrelated. These relationships do not
            independently prove the claim.
          </p>
          {!assessment.search_outcome &&
            result.all_surviving_sources.length > 0 && (
              <p>
                Among {result.all_surviving_sources.length} surviving sources,{" "}
                {noAdmittedSurvivorCount} had no admitted evidence and{" "}
                {admittedSurvivorCount} had admitted evidence.
              </p>
            )}
          {assessmentLimitations.map((limitation) => (
            <p key={limitation}>{limitation}</p>
          ))}
          <small>{terminalStatusOrigin}</small>
        </div>
      )}
      {coverage && (
        <div className="result-limitation" role="status">
          <details>
            <summary>Earlier search decision · {statusLabel}</summary>
            <p>{coverage.explanation}</p>
            <p>
              The search assessment counted {coverage.actionable_gap_count}{" "}
              unresolved evidence gap
              {coverage.actionable_gap_count === 1 ? "" : "s"} for possible
              follow-up. Coverage separately recorded{" "}
              {coverage.partial_coverage_count} partial and{" "}
              {coverage.unavailable_coverage_count} unavailable dimensions.
            </p>
            <small>
              Recorded before final evidence outcomes were available.
            </small>
          </details>
        </div>
      )}
      {assessment && (
        <div className="result-limitation" role="status">
          <strong>Claim status · {claimStatus}</strong>
          <p>
            These counts describe admitted findings; they do not independently
            prove the claim.
          </p>
          <small>{assessmentOrigin}</small>
        </div>
      )}
    </>
  );
}

export function CoverageResultSections({
  result,
}: {
  result: V2FinalResearchOutput;
}) {
  return (
    <>
      <section>
        <h2>Unresolved evidence gaps</h2>
        {result.unresolved_material_gaps.length ? (
          <>
            <p>
              {result.unresolved_material_gaps.length} gap
              {result.unresolved_material_gaps.length === 1
                ? " remains"
                : "s remain"}{" "}
              unresolved.
            </p>
            <ul>
              {result.unresolved_material_gaps.map((gap) => (
                <li key={gap.gap_id}>
                  {gap.direction}: {gap.missing_evidence}{" "}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p>
            No specific unresolved evidence gaps were recorded. This does not
            establish that the claim is proven.
          </p>
        )}
      </section>
      {!!result.claim_coverage_map?.length && (
        <section>
          <h2>Latest research coverage assessment</h2>
          <p>
            This assessment guides research; it is not proof that the claim is
            established.
          </p>
          <ul>
            {result.claim_coverage_map.map((item) => (
              <li key={item.dimension}>
                <strong>{readableStage(item.coverage_state)}:</strong>{" "}
                {item.claim_component}
                <p>{item.evidence_summary}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section>
        <h2>Saved brief status</h2>
        <p>
          Release validation passed:{" "}
          {result.release_validation.valid ? "yes" : "no"}. The status above
          reports the latest saved research decision.
        </p>
      </section>
    </>
  );
}
