import type { V2FinalResearchOutput, V2EvidenceDisplay } from "@/lib/api";
import { AdmittedEvidence } from "./admitted-evidence";
import { CoverageResultSections, CoverageStatus } from "./coverage-status";
import { SourceSections } from "./source-sections";
import { sourceTitles, evidenceCitation } from "./source-titles";
import { selectedFindings as selectFindings } from "./reading-aid";

export function V2ResultPaper({
  result,
  evidence,
}: {
  result: V2FinalResearchOutput;
  evidence: V2EvidenceDisplay | null;
}) {
  const direction =
    result.directions.support_enabled && result.directions.challenge_enabled
      ? "Support and challenge research directions"
      : result.directions.support_enabled
        ? "Support-directed research only"
        : "Challenge-directed research only";
  const heading = (section: "supporting" | "opposing" | "limitations") =>
    section === "supporting"
      ? "Support-directed findings"
      : section === "opposing"
        ? "Challenge-directed findings"
        : "Evidence qualifications";
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
      detail.open = true;
      detail.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "center",
      });
      detail.querySelector("summary")?.focus({ preventScroll: true });
    }
  };
  return (
    <>
      <p className="eyebrow">Your research result</p>
      <h1>Research Brief</h1>
      <p>Claim under review: {result.exact_claim}</p>
      <section className="result-bottom-line" aria-labelledby="bottom-line-heading">
        <h2 id="bottom-line-heading">Bottom line</h2>
        {evidence?.study_opening?.length ? (
          <p>{evidence.study_opening.map((assertion) => <span key={assertion.role}>{assertion.text}{" "}<small>{admittedFor(assertion.ledger_claim_id) ? evidenceCitation(admittedFor(assertion.ledger_claim_id)!) : ""}</small>{" "}<button type="button" className="text-action" onClick={() => openEvidence(assertion.ledger_claim_id)}>View evidence and source</button>{" "}</span>)}</p>
        ) : evidence?.publication_opening?.length ? (
          <>
            <p>{evidence.publication_opening.map((sentence, index) => <span key={index}>{sentence.text}{" "}<button type="button" className="text-action" onClick={() => openEvidence(sentence.ledger_claim_ids)}>View evidence and source</button>{" "}</span>)}</p>
            <details><summary>How these findings were selected</summary><p>{evidence.opening_notice || "Grouped by verified publication; separate publications do not establish independent studies."}</p></details>
          </>
        ) : <p>
          {evidence === null
            ? "The detailed evidence has not loaded, so a conclusion cannot be assessed here."
            : evidence.items.length
              ? "The claim is not established by the admitted evidence. The available assessment does not establish the balance of evidence across independent studies."
              : "No evidence was admitted for this result, so the claim cannot be established from it."}
        </p>}
        { !evidence?.study_opening?.length && !evidence?.publication_opening?.length && selectedFindings.length > 0 && (
          <p>Study identity and evidence balance have not been verified. The following examples are selected by recorded claim fit, with a stable identifier used to break ties; they are not necessarily representative.</p>
        )}
        {(!evidence?.study_opening?.length && !evidence?.publication_opening?.length ? selectedFindings : []).map((item) => (
          <p key={item.ledger_claim_id}>
            <strong>{item.relationship_to_claim === "supports" ? "Supporting finding: " : item.relationship_to_claim === "challenges" ? "Contrasting finding: " : "Qualification: "}</strong>
            {item.approved_factual_statement}{" "}
            <button type="button" className="text-action" onClick={() => openEvidence(item.ledger_claim_id)}>
              View evidence and source
            </button>
          </p>
        ))}
        {evidence?.study_review_rationale && <details><summary>{evidence.study_opening?.length ? "Study selection review" : "Publication verification review"}</summary><p>{evidence.study_review_rationale}</p></details>}
      </section>
      <CoverageStatus result={result} evidence={evidence} />
      {!!evidence?.budget_context?.length && <details><summary>Recorded limits and usage</summary>{evidence.budget_context.map((line) => <p key={line}>{line}</p>)}</details>}
      <p>
        <strong>Research direction:</strong> {direction}. This describes where
        research was directed, not whether an admitted finding supports or
        challenges the claim. Disabled directions were not examined.
      </p>
      {result.synthesis.sections.map((section) => (
        <section key={section.section_type}>
          <h2>{heading(section.section_type)}</h2>
          <div className="overview-items">
            {section.items.slice(0, 3).map((item) => (
              <p className="overview-item" key={item.ledger_claim_id}>
                {item.approved_factual_statement}
                {admittedFor(item.ledger_claim_id) && (
                  <button
                    type="button"
                    className="text-action"
                    onClick={() => openEvidence(item.ledger_claim_id)}
                  >
                    View admitted quote and source
                  </button>
                )}
              </p>
            ))}
          </div>
          {section.items.length > 3 && (
            <details className="overview-more">
              <summary>Show {section.items.length - 3} more findings</summary>
              <div className="overview-items">
                {section.items.slice(3).map((item) => (
                  <p className="overview-item" key={item.ledger_claim_id}>
                    {item.approved_factual_statement}
                    {admittedFor(item.ledger_claim_id) && (
                      <button
                        type="button"
                        className="text-action"
                        onClick={() => openEvidence(item.ledger_claim_id)}
                      >
                        View admitted quote and source
                      </button>
                    )}
                  </p>
                ))}
              </div>
            </details>
          )}
        </section>
      ))}
      <SourceSections result={result} evidence={evidence}>
        <AdmittedEvidence
          evidence={evidence}
          assessment={evidence?.post_analysis_assessment ?? null}
          sourceHeading={sourceHeading}
          capturedTitleDisclosure={capturedTitleDisclosure}
          showDirection={
            result.directions.support_enabled === true &&
            result.directions.challenge_enabled === true
          }
        />
      </SourceSections>
      <CoverageResultSections result={result} />
    </>
  );
}
