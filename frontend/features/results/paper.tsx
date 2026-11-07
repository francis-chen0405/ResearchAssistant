import type { RunSnapshot, V2FinalResearchOutput, V2EvidenceDisplay } from "@/lib/api";
import { AdmittedEvidence } from "./admitted-evidence";
import { CoverageResultSections, CoverageStatus } from "./coverage-status";
import { SourceSections } from "./source-sections";
import {
  evidenceCitation, evidenceReadLocation, evidenceSourceType, evidenceStudyDesign, sourceTitles,
} from "./source-titles";
import { selectedFindings as selectFindings } from "./reading-aid";
import { safeWebUrl } from "./source-leads";

export function V2ResultPaper({
  result,
  evidence,
  run,
}: {
  result: V2FinalResearchOutput;
  evidence: V2EvidenceDisplay | null;
  run: Pick<RunSnapshot, "run_id" | "db_path">;
}) {
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
  const overviewCandidates = (evidence?.items ?? [])
    .filter((item) => item.relationship_to_claim !== "unrelated" && item.approved_factual_statement.trim())
    .sort((a, b) =>
      Number(a.relationship_to_claim === "qualifies") - Number(b.relationship_to_claim === "qualifies") ||
      (b.claim_fit ?? 0) - (a.claim_fit ?? 0) ||
      Number(Boolean(b.verified_publication)) - Number(Boolean(a.verified_publication)) ||
      a.ledger_claim_id.localeCompare(b.ledger_claim_id)
    );
  const primaryFinding = overviewCandidates[0];
  const otherFindings = overviewCandidates.slice(1).filter(
    (item) => item.approved_factual_statement.trim() !== primaryFinding.approved_factual_statement.trim(),
  );
  const contrastingFinding = otherFindings.find((item) =>
    (primaryFinding.relationship_to_claim === "supports" && item.relationship_to_claim === "challenges") ||
    (primaryFinding.relationship_to_claim === "challenges" && item.relationship_to_claim === "supports")
  );
  const secondFinding = contrastingFinding ?? otherFindings.find((item) => item.source_id !== primaryFinding.source_id);
  const overviewFindings = [primaryFinding, secondFinding].filter((item) => item !== undefined);
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
        {overviewFindings.length > 0 ? (
          <p className="overview-synthesis">
            {overviewFindings.map((item, index) => {
              const href = safeWebUrl(item.verified_publication?.canonical_url ?? "")
                ?? safeWebUrl(item.source_url);
              const sourceTitle = sourceHeading(item.source_id, item.title, item.source_url);
              const title = /not recorded/i.test(sourceTitle) ? evidenceReadLocation(item) : sourceTitle;
              const reviewedDesign = evidence?.study_opening?.find(
                (assertion) => assertion.ledger_claim_id === item.ledger_claim_id,
              )?.design;
              const labels = [evidenceSourceType(item), reviewedDesign || evidenceStudyDesign(item)]
                .filter((label) => label && !/not recorded|unknown/i.test(label));
              const statement = item.approved_factual_statement.trim().replace(/(?<!\.)\.$/, "");
              return (
                <span key={item.ledger_claim_id}>
                  {index > 0 && " "}{statement}{" "}
                  ({href ? <a href={href} target="_blank" rel="noreferrer">{title}</a> : title}
                  {labels.length > 0 && `, ${labels.join(", ")}`}).
                </span>
              );
            })}
          </p>
        ) : (
          <p>{evidence === null ? "Detailed evidence is unavailable." : "No relevant admitted findings are available for this result."}</p>
        )}
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
            <p>{evidence === null ? "Detailed evidence is unavailable." : !evidence.items.length ? "No evidence was admitted for this result." : "The available evidence is summarized below."}</p>
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
