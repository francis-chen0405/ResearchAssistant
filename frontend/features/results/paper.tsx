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
  const studyGroups = (() => {
    const parentBySource = new Map<string, string>();
    const findRoot = (id: string): string => {
      const parent = parentBySource.get(id);
      if (!parent || parent === id) {
        parentBySource.set(id, id);
        return id;
      }
      const root = findRoot(parent);
      parentBySource.set(id, root);
      return root;
    };
    const joinSources = (sourceIds: string[]) => {
      const [first, ...rest] = sourceIds;
      if (!first) return;
      for (const id of rest) parentBySource.set(findRoot(id), findRoot(first));
    };
    for (const notice of evidence?.study_lineage ?? []) {
      joinSources(notice.source_ids);
    }
    const groups = new Map<
      string,
      {
        sources: Map<string, string>;
        relationships: Set<string>;
        findings: Map<string, string[]>;
      }
    >();
    for (const item of evidence?.items ?? []) {
      const root = findRoot(item.source_id);
      const group = groups.get(root) ?? {
        sources: new Map<string, string>(),
        relationships: new Set<string>(),
        findings: new Map<string, string[]>(),
      };
      group.sources.set(
        item.source_id,
        sourceHeading(item.source_id, item.title, item.source_url),
      );
      group.relationships.add(item.relationship_to_claim);
      const statements = group.findings.get(item.relationship_to_claim) ?? [];
      const citation = sourceHeading(item.source_id, item.title, item.source_url);
      const statement = `${item.approved_factual_statement.replace(/[.!?]+$/, "")} (${citation})`;
      if (!statements.includes(statement)) {
        statements.push(statement);
      }
      group.findings.set(item.relationship_to_claim, statements);
      groups.set(root, group);
    }
    return [...groups.values()];
  })();
  const studiesWith = (relationship: string) =>
    studyGroups.filter((group) => group.relationships.has(relationship));
  const findingSummaries = (relationship: string) =>
    studiesWith(relationship)
      .map((group) => {
        const findings = group.findings.get(relationship);
        return findings?.length ? findings.join("; ") : null;
      })
      .filter((summary): summary is string => Boolean(summary));
  const supportingSummaries = findingSummaries("supports");
  const challengingSummaries = findingSummaries("challenges");
  const firstRelationship =
    challengingSummaries.length > supportingSummaries.length
      ? "challenges"
      : "supports";
  const orderedSummaries =
    firstRelationship === "challenges"
      ? [challengingSummaries, supportingSummaries]
      : [supportingSummaries, challengingSummaries];
  const orderedLabels =
    firstRelationship === "challenges"
      ? ["Challenging", "Supporting"]
      : ["Supporting", "Challenging"];
  const qualifyingGroupCount = studiesWith("qualifies").length;
  const claimBottomLine =
    evidence?.post_analysis_assessment?.claim_established === false
      ? "The claim is not established by this evidence review."
      : "This evidence review does not determine whether the claim is established.";
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
      {evidence?.items.length ? (
        <section
          className="result-bottom-line"
          aria-labelledby="bottom-line-heading"
        >
          <h2 id="bottom-line-heading">Bottom line</h2>
          <p>
            {orderedLabels.map((label, index) => {
              const summaries = orderedSummaries[index];
              return (
                <span key={label}>
                  {label} findings: {summaries.length
                    ? summaries.slice(0, 3).join("; ")
                    : "none in the admitted evidence"}.
                  {summaries.length > 3 &&
                    ` ${summaries.length - 3} additional ${label.toLowerCase()} evidence groups appear below.`}{" "}
                </span>
              );
            })}
            {qualifyingGroupCount > 0 &&
              `${qualifyingGroupCount} evidence ${qualifyingGroupCount === 1 ? "group qualifies" : "groups qualify"} these findings. `}
            {claimBottomLine}
          </p>
          <small>
            Sources with matching study identifiers are grouped together where
            available; other evidence sources appear separately. A metadata
            match does not prove that two records are the same study.
          </small>
        </section>
      ) : null}
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
