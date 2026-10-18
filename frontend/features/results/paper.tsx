import type { V2FinalResearchOutput, V2EvidenceDisplay } from "@/lib/api";
import { AdmittedEvidence } from "./admitted-evidence";
import { CoverageResultSections, CoverageStatus } from "./coverage-status";
import { SourceSections } from "./source-sections";
import { sourceTitles } from "./source-titles";

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
  const openEvidence = (ledgerClaimId: string) => {
    const detail = document.getElementById(`evidence-${ledgerClaimId}`);
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
      <CoverageStatus result={result} evidence={evidence} />
      <p>Claim under review: {result.exact_claim}</p>
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
        />
      </SourceSections>
      <CoverageResultSections result={result} />
    </>
  );
}
