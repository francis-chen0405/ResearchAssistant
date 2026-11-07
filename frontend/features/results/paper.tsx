import type { RunSnapshot, V2FinalResearchOutput, V2EvidenceDisplay } from "@/lib/api";
import { AdmittedEvidence } from "./admitted-evidence";
import { CoverageResultSections, CoverageStatus, hasIncompleteCoverage } from "./coverage-status";
import { SourceSections } from "./source-sections";
import { sourceTitles, evidenceCitation } from "./source-titles";
import { selectedFindings as selectFindings } from "./reading-aid";

export function V2ResultPaper({
  result,
  evidence,
  run,
}: {
  result: V2FinalResearchOutput;
  evidence: V2EvidenceDisplay | null;
  run: Pick<RunSnapshot, "run_id" | "db_path">;
}) {
  const direction =
    result.directions.support_enabled && result.directions.challenge_enabled
      ? "Support and challenge research directions"
      : result.directions.support_enabled
        ? "Support-directed research only"
        : "Challenge-directed research only";
  const admittedFor = (ledgerClaimId: string) =>
    evidence?.items.find((item) => item.ledger_claim_id === ledgerClaimId);
  const { sourceHeading, capturedTitleDisclosure } = sourceTitles(
    result,
    evidence,
  );
  const selectedFindings = selectFindings(evidence);
  const openEvidence = (ledgerClaimId: string | string[]) => {
    const ids = Array.isArray(ledgerClaimId) ? ledgerClaimId : [ledgerClaimId];
    for (const id of ids) {
      const related = document.getElementById(`evidence-${id}`);
      if (related instanceof HTMLDetailsElement) related.open = true;
    }
    const detail = document.getElementById(`evidence-${ids[0]}`);
    if (detail instanceof HTMLDetailsElement) {
      const evidenceSection = detail.closest<HTMLDetailsElement>("details.brief-evidence");
      if (evidenceSection) evidenceSection.open = true;
      detail.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "center",
      });
      detail.querySelector("summary")?.focus({ preventScroll: true });
    }
  };
  const opening = evidence?.study_opening?.length
    ? evidence.study_opening.map((item) => item.text)
    : evidence?.publication_opening?.map((item) => item.text) ?? [];
  const overviewStatus = evidence === null
    ? "Detailed evidence is unavailable."
    : !evidence.items.length && !opening.length
      ? "No evidence was admitted for this result."
      : opening.length
        ? "These findings are limited to the sources and settings reviewed."
        : "The admitted evidence does not establish the claim or the balance of independent studies.";
  const coverageIncomplete = hasIncompleteCoverage(result, evidence);
  const renderFindings = (items: V2FinalResearchOutput["synthesis"]["sections"][number]["items"]) => (
    <div className="overview-items">
      {items.map((item) => (
        <p className="overview-item" key={item.ledger_claim_id}>
          {item.approved_factual_statement}{" "}
          {admittedFor(item.ledger_claim_id) && (
            <button type="button" className="text-action" onClick={() => openEvidence(item.ledger_claim_id)}>
              View admitted quote and source
            </button>
          )}
        </p>
      ))}
    </div>
  );
  const qualifications = result.synthesis.sections
    .filter((section) => section.section_type === "limitations")
    .flatMap((section) => section.items);
  return (
    <>
      <p className="eyebrow">Your research result</p>
      <h1>Research Brief</h1>
      <p>Claim under review: {result.exact_claim}</p>
      <section aria-labelledby="brief-overview-heading">
        <h2 id="brief-overview-heading">Overview</h2>
        <p>{direction}. {opening.join(" ")}{opening.length > 0 && " "}{overviewStatus}</p>
        {coverageIncomplete && (
          <p>Research coverage was incomplete. The findings apply to the evidence reviewed.</p>
        )}
        {!result.claim_coverage_map?.length && <p>Claim coverage was not assessed.</p>}
      </section>
      {result.synthesis.sections.filter((section) => section.section_type !== "limitations").map((section) => (
        <section key={section.section_type}>
          <h2>{section.section_type === "supporting" ? "Support-directed findings" : "Challenge-directed findings"}</h2>
          {renderFindings(section.items.slice(0, 1))}
          {section.items.length > 1 && (
            <details className="overview-more">
              <summary>Show {section.items.length - 1} more {section.items.length === 2 ? "finding" : "findings"}</summary>
              {renderFindings(section.items.slice(1))}
            </details>
          )}
        </section>
      ))}
      <details className="brief-disclosure result-bottom-line">
        <summary>Bottom line</summary>
        {evidence?.study_opening?.length ? (
          evidence.study_opening.map((assertion) => {
            const admitted = admittedFor(assertion.ledger_claim_id);
            return (
              <p key={assertion.role}>
                {assertion.text}{" "}{admitted && <small>{evidenceCitation(admitted)} </small>}
                <button type="button" className="text-action" onClick={() => openEvidence(assertion.ledger_claim_id)}>View evidence and source</button>
              </p>
            );
          })
        ) : evidence?.publication_opening?.length ? (
          <>
            {evidence.publication_opening.map((sentence, index) => (
              <p key={index}>
                {sentence.text}{" "}
                <button type="button" className="text-action" onClick={() => openEvidence(sentence.ledger_claim_ids)}>View evidence and source</button>
              </p>
            ))}
            <p>{evidence.opening_notice || "Grouped by publication or reading location. Separate publications do not establish independent studies."}</p>
          </>
        ) : (
          <>
            <p>{overviewStatus}</p>
            {selectedFindings.length > 0 && (
              <p>These examples were selected by recorded claim fit. Study identity and evidence balance are unverified, so the examples may not be representative.</p>
            )}
            {selectedFindings.map((item) => (
              <p key={item.ledger_claim_id}>
                <strong>{item.relationship_to_claim === "supports" ? "Supporting finding: " : item.relationship_to_claim === "challenges" ? "Contrasting finding: " : "Qualification: "}</strong>
                {item.approved_factual_statement}{" "}
                <button type="button" className="text-action" onClick={() => openEvidence(item.ledger_claim_id)}>View evidence and source</button>
              </p>
            ))}
          </>
        )}
        {evidence?.study_review_rationale && <details><summary>{evidence.study_opening?.length ? "Study selection review" : "Publication verification review"}</summary><p>{evidence.study_review_rationale}</p></details>}
      </details>
      {qualifications.length > 0 && (
        <details className="brief-disclosure">
          <summary>Evidence qualifications</summary>
          {renderFindings(qualifications)}
        </details>
      )}
      <details className="brief-disclosure">
        <summary>Research status and coverage</summary>
        <CoverageStatus result={result} evidence={evidence} />
        <CoverageResultSections result={result} />
        {!!evidence?.budget_context?.length && <details><summary>Recorded limits and usage</summary>{evidence.budget_context.map((line) => <p key={line}>{line}</p>)}</details>}
      </details>
      <details className="brief-disclosure brief-evidence">
        <summary>Admitted evidence</summary>
        <AdmittedEvidence
          evidence={evidence}
          assessment={evidence?.post_analysis_assessment ?? null}
          sourceHeading={sourceHeading}
          capturedTitleDisclosure={capturedTitleDisclosure}
          showDirection={result.directions.support_enabled === true && result.directions.challenge_enabled === true}
        />
      </details>
      <SourceSections result={result} evidence={evidence} run={run} />
    </>
  );
}
