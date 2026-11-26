import { Chip, type Tone } from "@/components/ui";
import { Icon } from "@/components/icons";
import type { RunSnapshot, V2EvidenceDisplay, V2FinalResearchOutput } from "@/lib/api";
import { AllLiveSources } from "../research/live-sources";
import { readableProvider, sourceBudgetStop } from "../shared/presentation";
import { safeWebUrl } from "./source-leads";
import { relationshipLabel, relationshipTone, strengthLabel, type Relationship, type SourceTitle } from "./model";

type ResultSource = V2FinalResearchOutput["all_surviving_sources"][number];

const budgetOutcomeText: Record<string, string> = {
  source_budget_blocked: "A per-source allowance stopped the reading",
  token_cap_blocked: "A per-source token limit stopped the reading",
  physical_call_cap_blocked: "A per-source call limit stopped the reading",
};

/** One plain outcome per shortlisted source. */
export function sourceOutcome(
  source: Pick<ResultSource, "status" | "budget_prevented_reason" | "analysis_skip_reason">,
  budgetOutcome?: string,
): { label: string; tone: Tone } {
  if (source.analysis_skip_reason === "exact_body_mirror") return { label: "Duplicate text; separate assessment skipped", tone: "neutral" };
  if (budgetOutcome) return { label: budgetOutcomeText[budgetOutcome] ?? "A per-source limit stopped the reading", tone: "warning" };
  const status = source.status;
  if (status === "budget_prevented_analysis") return { label: sourceBudgetStop(source.budget_prevented_reason).replace(/\.$/, ""), tone: "warning" };
  if (status.endsWith("analyzer_admitted")) return { label: "Used as evidence", tone: "success" };
  if (status.endsWith("not_deeply_analyzed")) return { label: "Shortlisted; not read in depth", tone: "neutral" };
  if (status === "recommended_analyzed" || status === "surviving_analyzed") return { label: "Read and assessed", tone: "neutral" };
  if (status.endsWith("analyzer_rejected")) return { label: "Read; no finding kept", tone: "neutral" };
  if (status.endsWith("analyzer_failed")) return { label: "Assessment failed", tone: "warning" };
  if (status.endsWith("no_ledger_evidence")) return { label: "Not yet assessed", tone: "neutral" };
  return { label: "Outcome not recognized", tone: "neutral" };
}

export function SourceRow({
  source,
  title,
  evidence,
  budgetOutcome,
  showReason,
}: {
  source: ResultSource;
  title: SourceTitle | undefined;
  evidence: V2EvidenceDisplay | null;
  budgetOutcome?: string;
  showReason: boolean;
}) {
  const href = safeWebUrl(source.source_url);
  const outcome = sourceOutcome(source, budgetOutcome);
  const item = evidence?.items
    .filter((entry) => entry.source_id === source.source_id && entry.relationship_to_claim !== "unrelated")
    .sort((a, b) => (b.claim_fit ?? 0) - (a.claim_fit ?? 0))[0];
  const relationship = item?.relationship_to_claim as Relationship | undefined;
  const strength = strengthLabel(item?.claim_fit);
  const reason = relationship
    ? `${strength ? `${strength} · ` : ""}${relationshipLabel[relationship]}`
    : source.recommended
      ? "Not yet assessed; recommended from its search ranking."
      : null;
  const meta = [title?.source_name, title?.year, title?.source_kind].filter(Boolean).join(" · ");
  const heading = title?.heading ?? title?.display_title ?? source.title ?? source.source_url;
  return (
    <li className="source-row">
      <div className="source-row-main">
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer" className="source-title">{heading}</a>
        ) : (
          <span className="source-title">{heading}</span>
        )}
        {meta && <span className="subtle">{meta}</span>}
        {showReason && (item?.selection_rationale || reason) && (
          <p className="source-reason">
            {relationship && <Chip tone={relationshipTone[relationship]}>{reason}</Chip>}{" "}
            {item?.selection_rationale ?? (!relationship ? reason : null)}
          </p>
        )}
        {Boolean(source.alternate_source_urls?.length) && (
          <p className="subtle">
            Also available at{" "}
            {source.alternate_source_urls?.map((url, index) => {
              const safe = safeWebUrl(url);
              return (
                <span key={url}>
                  {index > 0 && ", "}
                  {safe ? <a href={safe} target="_blank" rel="noopener noreferrer">Alternate location</a> : "Alternate location"}
                </span>
              );
            })}
            . Same paper, not separate evidence.
          </p>
        )}
        {title?.captured_title && title.captured_title !== heading && title.captured_title !== title.display_title && (
          <p className="subtle">Title as captured: {title.captured_title}</p>
        )}
      </div>
      <Chip tone={outcome.tone}>{outcome.label}</Chip>
    </li>
  );
}

export function SourcesTab({
  result,
  evidence,
  run,
}: {
  result: V2FinalResearchOutput;
  evidence: V2EvidenceDisplay | null;
  run: Pick<RunSnapshot, "run_id" | "db_path">;
}) {
  const titles = new Map((evidence?.source_titles ?? []).map((item) => [item.source_id, item]));
  const budget = new Map((evidence?.source_budget_outcomes ?? []).map((item) => [item.source_id, item.outcome]));
  const recommendedIds = new Set(result.recommended_sources.map((source) => source.source_id));
  const others = result.all_surviving_sources.filter((source) => !recommendedIds.has(source.source_id));
  const headingFor = (id: string) => {
    const source = result.all_surviving_sources.find((item) => item.source_id === id);
    return { source, label: titles.get(id)?.heading ?? source?.title ?? "Saved source" };
  };
  const notices = [
    ...(evidence?.study_lineage ?? []).map((notice) => ({ key: `lineage-${notice.source_ids.join("-")}`, text: notice.explanation, ids: notice.source_ids.map(String) })),
    ...(evidence?.shared_website_groups ?? []).map((group) => ({ key: `site-${group.host}`, text: group.explanation, ids: group.source_ids.map(String) })),
  ];
  const providers = [...new Set(result.all_surviving_sources.flatMap((source) => source.discovery_providers))];
  return (
    <div className="sources-tab">
      <section aria-labelledby="recommended-reading">
        <h3 id="recommended-reading">Recommended reading</h3>
        <p className="subtle">The sources most worth reading first, with why each one matters.</p>
        {result.recommended_sources.length ? (
          <ul className="source-list">
            {result.recommended_sources.map((source) => (
              <SourceRow key={source.source_id} source={source} title={titles.get(source.source_id)} evidence={evidence} budgetOutcome={budget.get(source.source_id)} showReason />
            ))}
          </ul>
        ) : (
          <p className="muted">No sources were recommended for this run.</p>
        )}
      </section>
      {others.length > 0 && (
        <section aria-labelledby="other-sources">
          <h3 id="other-sources">Other shortlisted sources <span className="count">{others.length}</span></h3>
          <ul className="source-list">
            {others.map((source) => (
              <SourceRow key={source.source_id} source={source} title={titles.get(source.source_id)} evidence={evidence} budgetOutcome={budget.get(source.source_id)} showReason={false} />
            ))}
          </ul>
        </section>
      )}
      {notices.length > 0 && (
        <section aria-labelledby="source-relationships">
          <h3 id="source-relationships">Related sources</h3>
          <ul className="notice-list">
            {notices.map((notice) => (
              <li key={notice.key}>
                <Icon name="info" />
                <span>
                  {notice.text}{" "}
                  {notice.ids.map((id, index) => {
                    const { source, label } = headingFor(id);
                    const href = source ? safeWebUrl(source.source_url) : null;
                    return (
                      <span key={id}>
                        {index > 0 ? " · " : ""}
                        {href ? <a href={href} target="_blank" rel="noopener noreferrer">{label}</a> : label}
                      </span>
                    );
                  })}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section aria-labelledby="all-sources-found">
        <h3 id="all-sources-found">All sources found</h3>
        <p className="subtle">
          Everything the search turned up{providers.length ? ` from ${providers.map(readableProvider).join(", ")}` : ""}, including sources that were not shortlisted.
        </p>
        <AllLiveSources runId={run.run_id} database={run.db_path} />
      </section>
    </div>
  );
}
