import type { V2EvidenceDisplay, V2FinalResearchOutput } from "@/lib/api";
import type { ReactNode } from "react";
import { readableStage } from "../shared/presentation";
import { sourceTitles } from "./source-titles";

export function SourceSections({
  result,
  evidence,
  children,
}: {
  result: V2FinalResearchOutput;
  evidence: V2EvidenceDisplay | null;
  children?: ReactNode;
}) {
  const { sourceHeading, capturedTitleDisclosure } = sourceTitles(
    result,
    evidence,
  );
  const budgetOutcomeBySource = new Map(
    (evidence?.source_budget_outcomes ?? []).map((item) => [
      item.source_id,
      item.outcome,
    ]),
  );
  const sourceOutcome = (
    status: string,
    sourceId: string,
    recommended: boolean,
  ) => {
    const budgetOutcome = budgetOutcomeBySource.get(sourceId);
    if (budgetOutcome) {
      const label =
        budgetOutcome === "source_budget_blocked"
          ? "source budget blocked"
          : budgetOutcome === "token_cap_blocked"
            ? "source token-cap blocked"
            : "source call-cap blocked";
      return `${recommended ? "Recommended" : "Survived selection"} · ${label}`;
    }
    return (
      (
        {
          recommended_analyzed: "Recommended · evidence assessed",
          recommended_analyzer_admitted: "Recommended · evidence admitted",
          recommended_analyzer_rejected: "Recommended · evidence not admitted",
          recommended_analyzer_failed: "Recommended · assessment failed",
          recommended_no_ledger_evidence: "Recommended · provisional; no admitted evidence",
          surviving_analyzed: "Survived selection · evidence assessed",
          surviving_analyzer_admitted: "Survived selection · evidence admitted",
          surviving_analyzer_rejected: "Survived selection · evidence not admitted",
          surviving_analyzer_failed: "Survived selection · assessment failed",
          surviving_not_deeply_analyzed: "Survived selection · not assessed",
          budget_prevented_analysis: "Provisional · analysis prevented by budget",
        } as Record<string, string>
      )[status] ?? readableStage(status)
    );
  };
  const sourceOutcomeSummary = (
    sources: V2FinalResearchOutput["all_surviving_sources"],
  ) => {
    const counts = new Map<string, number>();
    for (const source of sources) {
      const budgetOutcome = budgetOutcomeBySource.get(source.source_id);
      const label =
        budgetOutcome === "source_budget_blocked"
          ? "source budget blocked"
          : budgetOutcome === "token_cap_blocked"
            ? "source token-cap blocked"
            : budgetOutcome === "physical_call_cap_blocked"
              ? "source call-cap blocked"
              : source.status === "recommended_analyzed" ||
                  source.status === "surviving_analyzed"
                ? "evidence assessed"
                : source.status.endsWith("analyzer_admitted")
                  ? "evidence admitted"
                  : source.status.endsWith("analyzer_failed")
                    ? "assessment failed"
                    : source.status.endsWith("analyzer_rejected")
                      ? "evidence not admitted"
                      : source.status.endsWith("no_ledger_evidence")
                        ? "no admitted evidence"
                        : source.status.endsWith("not_deeply_analyzed")
                          ? "not assessed"
                          : source.status === "budget_prevented_analysis"
                            ? "provisional; analysis prevented by budget"
                            : null;
      if (label) counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    return (
      [...counts].map(([label, count]) => `${count} ${label}`).join(", ") ||
      "No source outcomes were recorded."
    );
  };
  const sourceCards = (
    items: V2FinalResearchOutput["all_surviving_sources"],
  ) =>
    items.length ? (
      <div className="source-cards">
        {items.map((source) => {
          const details = evidence?.items.find(
            (item) => item.source_id === source.source_id,
          );
          const relatedGapCount = details?.gap_ids?.length ?? 0;
          const evidenceAssessment = details
            ? `${
                {
                  supports: details.claim_fit === 5 ? "Direct support" : "Indirect or partial support",
                  challenges: details.claim_fit === 5 ? "Direct challenge" : "Indirect or partial challenge",
                  qualifies: "Qualifying evidence",
                  unrelated: "Not relevant to the claim",
                }[details.relationship_to_claim]
              }`
            : null;
          return (
            <article className="source-card" key={source.source_id}>
              <a href={source.source_url} target="_blank" rel="noreferrer">
                {sourceHeading(
                  source.source_id,
                  source.title,
                  source.source_url,
                )}
              </a>
              {source.alternate_source_urls?.length ? (
                <div>
                  <small>
                    Alternate locations for the same paper; these are not
                    additional independent evidence.
                  </small>
                  {source.alternate_source_urls.map((url) => (
                    <p key={url}>
                      <a href={url} target="_blank" rel="noreferrer">
                        Alternate location
                      </a>
                    </p>
                  ))}
                </div>
              ) : null}
              <small>
                {source.source_type || "Source"} · discovered via{" "}
                {source.discovery_providers.join(", ") || "recorded source"} ·{" "}
                {source.recommended
                  ? "Recommended for deeper analysis"
                  : "Survived selection"}{" "}
                ·{" "}
                {sourceOutcome(
                  source.status,
                  source.source_id,
                  source.recommended,
                )}{" "}
                · round {source.discovery_round}
              </small>
              {evidenceAssessment ? (
                <p>{evidenceAssessment}</p>
              ) : source.recommended ? (
                <p>Provisional · claim relationship has not been assessed.</p>
              ) : null}
              {details?.selection_rationale ? <p>{details.selection_rationale}</p> : null}
              {capturedTitleDisclosure(source.source_id, source.title)}
              {relatedGapCount ? (
                <p>
                  <strong>Related research gaps:</strong> {relatedGapCount}
                </p>
              ) : null}
            </article>
          );
        })}
      </div>
    ) : (
      <p>No source records are available in this section.</p>
    );
  const groupedNotices = evidence?.study_lineage ?? [];
  const sharedWebsites = evidence?.shared_website_groups ?? [];
  return (
    <>
      {groupedNotices.length ? (
        <section>
          <h2>Source lineage</h2>
          <p>
            These notices cover sources that survived selection; separate links
            do not establish independent studies.
          </p>
          <aside className="result-limitation">
            {groupedNotices.map((notice) => (
              <p key={`${notice.basis}-${notice.source_ids.join("-")}`}>
                {notice.explanation}{" "}
                {notice.source_ids.map((id, index) => {
                  const source = result.all_surviving_sources.find(
                    (item) => item.source_id === id,
                  );
                  return (
                    <span key={id}>
                      {index > 0 ? " · " : ""}
                      {source ? (
                        <a
                          href={source.source_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {sourceHeading(
                            source.source_id,
                            source.title,
                            source.source_url,
                          )}
                        </a>
                      ) : (
                        "Recorded source"
                      )}
                    </span>
                  );
                })}
              </p>
            ))}
          </aside>
        </section>
      ) : null}
      {sharedWebsites.length ? (
        <section>
          <h2>Shared publisher/website</h2>
          <p>
            Pages from one website can add context, but the shared website alone
            does not establish independent corroboration.
          </p>
          <aside className="result-limitation">
            {sharedWebsites.map((group) => (
              <p key={group.host}>
                <strong>{group.host}</strong>: {" "}
                {group.source_ids.map((id, index) => {
                  const source = evidence?.items.find(
                    (item) => item.source_id === id,
                  );
                  return (
                    <span key={id}>
                      {index > 0 ? " · " : ""}
                      {source ? (
                        <a
                          href={source.source_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {sourceHeading(
                            source.source_id,
                            source.title,
                            source.source_url,
                          )}
                        </a>
                      ) : (
                        "Admitted source"
                      )}
                    </span>
                  );
                })}
              </p>
            ))}
          </aside>
        </section>
      ) : null}
      {children}
      <section>
        <h2>Recommended Sources</h2>
        {result.recommended_sources.length > 0 && (
          <p>
            <strong>Recommended outcomes:</strong>{" "}
            {sourceOutcomeSummary(result.recommended_sources)}
          </p>
        )}
        {sourceCards(result.recommended_sources)}
      </section>
      <section>
        <h2>Survivor Sources</h2>
        {result.all_surviving_sources.length > 0 && (
          <p>
            <strong>
              Outcomes among all {result.all_surviving_sources.length} surviving
              sources:
            </strong>{" "}
            {sourceOutcomeSummary(result.all_surviving_sources)}
          </p>
        )}
        {sourceCards(result.all_surviving_sources)}
      </section>
    </>
  );
}
