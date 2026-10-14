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
          recommended_analyzed: "Recommended · Reviewer-approved",
          recommended_analyzer_admitted: "Recommended · analyzer-admitted",
          recommended_analyzer_rejected: "Recommended · analyst-rejected",
          recommended_analyzer_failed: "Recommended · analysis failed",
          recommended_no_ledger_evidence: "Recommended · no admitted evidence",
          surviving_analyzed: "Survived selection · Reviewer-approved",
          surviving_analyzer_admitted: "Survived selection · analyzer-admitted",
          surviving_analyzer_rejected: "Survived selection · analyst-rejected",
          surviving_analyzer_failed: "Survived selection · analysis failed",
          surviving_not_deeply_analyzed: "Survived selection · not analyzed",
          budget_prevented_analysis: "Analysis prevented by budget",
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
                ? "Reviewer-approved"
                : source.status.endsWith("analyzer_admitted")
                  ? "analyzer-admitted"
                  : source.status.endsWith("analyzer_failed")
                    ? "analysis failed"
                    : source.status.endsWith("analyzer_rejected")
                      ? "analyst-rejected"
                      : source.status.endsWith("no_ledger_evidence")
                        ? "no admitted evidence"
                        : source.status.endsWith("not_deeply_analyzed")
                          ? "not analyzed"
                          : source.status === "budget_prevented_analysis"
                            ? "analysis prevented by budget"
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
          return (
            <article className="source-card" key={source.source_id}>
              <a href={source.source_url} target="_blank" rel="noreferrer">
                {sourceHeading(
                  source.source_id,
                  source.title,
                  source.source_url,
                )}
              </a>
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
              <p>
                {details?.selection_rationale ||
                  (source.recommended
                    ? "Selected for deeper analysis from the surviving source pool."
                    : "Passed selection but was not recommended for deeper analysis.")}
              </p>
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
                <strong>{group.host}</strong> — {group.explanation}{" "}
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
