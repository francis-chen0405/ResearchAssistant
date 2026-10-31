import type { SourceLead } from "@/lib/api";

function safeWebUrl(value: string): string | null {
  try {
    const parsed = new URL(value);
    if (
      (parsed.protocol === "http:" || parsed.protocol === "https:") &&
      !parsed.username &&
      !parsed.password
    )
      return parsed.href;
  } catch {
    return null;
  }
  return null;
}

function readableValue(value: string): string {
  return value.replaceAll("_", " ").replaceAll("-", " ");
}

function readableReason(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  const reasons: Record<string, string> = {
    no_substantive_source_text: "No substantive text was available to assess.",
    empty_snapshot: "The captured page was empty.",
    shell_or_error_snapshot: "The captured page contained an error or placeholder rather than source text.",
    no_relevant_windows: "No relevant passages were found in the captured text.",
    preview_windows_selected: "Relevant passages were selected for review.",
    cap_prevented: "The run's limit prevented further review.",
  };
  if (reasons[value]) return reasons[value];
  if (/^[a-z0-9_]+$/.test(value)) return readableValue(value);
  if (/V2EvidenceAnalystFailure|_RetryableAssessmentValidationError/.test(value)) return "The evidence assessment could not be completed.";
  return value;
}

export function SourceLeads({
  items,
  total,
  notice,
  loading,
  loadingMore,
  error,
  hasMore,
  onLoadMore,
  onRetry,
}: {
  items: SourceLead[];
  total: number;
  notice: string | null;
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  hasMore: boolean;
  onLoadMore: () => void;
  onRetry: () => void;
}) {
  // Several discovery events can point to the same page. Keep their records
  // available together rather than presenting the same link as separate leads.
  const groups = new Map<string, SourceLead[]>();
  for (const lead of items) {
    const url = safeWebUrl(lead.url);
    const key = url ? url.split("#", 1)[0] : `record:${lead.lead_id}`;
    const group = groups.get(key) ?? [];
    group.push(lead);
    groups.set(key, group);
  }
  return (
    <section className="source-leads" aria-labelledby="source-leads-heading">
      <div className="source-leads-heading">
        <div>
          <p className="eyebrow">Discovery record</p>
          <h2 id="source-leads-heading">Source leads</h2>
          <p>
            These records show what discovery found. A search direction records
            where a lead came from; it does not say whether the work supports or
            challenges the claim. Leads are not evidence.
          </p>
        </div>
        {!loading && <span>{items.length} of {total} shown</span>}
      </div>
      {notice && <p className="source-leads-notice">{notice}</p>}
      {loading ? (
        <p className="source-leads-state" role="status">
          Loading source leads…
        </p>
      ) : error && items.length === 0 ? (
        <div>
          <p className="source-leads-state source-leads-error" role="alert">
            {error}
          </p>
          <button className="source-leads-more" type="button" onClick={onRetry}>
            Retry source leads
          </button>
        </div>
      ) : items.length === 0 ? (
        <p className="source-leads-state">
          No source leads were recorded for this run.
        </p>
      ) : (
        <>
          {error && (
            <p className="source-leads-error" role="alert">
              {error}
            </p>
          )}
          <div className="source-lead-list">
            {[...groups.values()].map(([lead, ...otherRecords]) => {
              const href = safeWebUrl(lead.url);
              const alternateHref = lead.readable_alternate_url
                ? safeWebUrl(lead.readable_alternate_url)
                : null;
              const title = lead.title?.trim() || "Untitled source";
              return (
                <article className="source-lead" key={lead.lead_id}>
                  <div className="source-lead-topline">
                    <div className="source-lead-title">
                      {href ? (
                        <a href={href} target="_blank" rel="noopener noreferrer">
                          {title}
                        </a>
                      ) : (
                        <strong>{title}</strong>
                      )}
                    </div>
                    <span className="source-lead-status">
                      Linked page: {readableValue(lead.capture_status)}
                    </span>
                  </div>
                  {alternateHref && (
                    <p className="source-lead-reason">
                      <a
                        href={alternateHref}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Readable alternate
                      </a>
                    </p>
                  )}
                  <div className="source-lead-provenance">
                    <span>Search direction provenance</span>
                    <p>
                      {lead.search_directions.length
                        ? lead.search_directions.map(readableValue).join(", ")
                        : "Not recorded"}
                    </p>
                  </div>
                  <p className="source-lead-reason">
                    <strong>Recorded reason</strong>
                    <span>{readableReason(lead.reason)}</span>
                  </p>
                  <details className="source-lead-details">
                    <summary>Lead metadata and history</summary>
                    <dl>
                      <div>
                        <dt>Disposition</dt>
                        <dd>{readableValue(lead.disposition)}</dd>
                      </div>
                      <div>
                        <dt>Providers</dt>
                        <dd>
                          {lead.providers.length
                            ? lead.providers.map(readableValue).join(", ")
                            : "Not recorded"}
                        </dd>
                      </div>
                      <div>
                        <dt>Rounds</dt>
                        <dd>{lead.rounds.length ? lead.rounds.join(", ") : "Not recorded"}</dd>
                      </div>
                      <div>
                        <dt>Confidence record</dt>
                        <dd>{readableValue(lead.confidence)}</dd>
                      </div>
                      <div>
                        <dt>Work ID</dt>
                        <dd>{lead.work_id ?? "Not recorded"}</dd>
                      </div>
                      <div>
                        <dt>Source ID</dt>
                        <dd>{lead.source_id ?? "Not recorded"}</dd>
                      </div>
                      {lead.unknowns.length > 0 && (
                        <div>
                          <dt>Unknowns</dt>
                          <dd>{lead.unknowns.join("; ")}</dd>
                        </div>
                      )}
                    </dl>
                    {lead.history.length > 0 && (
                      <ol className="source-lead-history">
                        {lead.history.map((entry, index) => (
                          <li key={`${entry.stage}-${entry.status}-${index}`}>
                            <strong>
                              {readableValue(entry.stage)} · {readableValue(entry.status)}
                            </strong>
                            {entry.reason && <span>{readableReason(entry.reason)}</span>}
                          </li>
                        ))}
                      </ol>
                    )}
                  </details>
                  {otherRecords.length > 0 && (
                    <details className="source-lead-details">
                      <summary>{otherRecords.length} additional discovery {otherRecords.length === 1 ? "record" : "records"} for this page</summary>
                      {otherRecords.map((record) => (
                        <div key={record.lead_id}>
                          <p>{readableValue(record.disposition)} · Linked page: {readableValue(record.capture_status)}</p>
                          {record.reason && <p>{readableReason(record.reason)}</p>}
                          <p>Search directions: {record.search_directions.map(readableValue).join(", ") || "Not recorded"}; providers: {record.providers.map(readableValue).join(", ") || "Not recorded"}; rounds: {record.rounds.join(", ") || "Not recorded"}</p>
                          <p>Confidence: {readableValue(record.confidence)}; work ID: {record.work_id ?? "Not recorded"}; source ID: {record.source_id ?? "Not recorded"}</p>
                          {record.readable_alternate_url && safeWebUrl(record.readable_alternate_url) !== alternateHref && safeWebUrl(record.readable_alternate_url) && (
                            <a href={safeWebUrl(record.readable_alternate_url)!} target="_blank" rel="noopener noreferrer">Readable alternate</a>
                          )}
                          {record.unknowns.length > 0 && <p>{record.unknowns.join("; ")}</p>}
                          {record.history.length > 0 && <ol className="source-lead-history">{record.history.map((entry, index) => <li key={`${entry.stage}-${entry.status}-${index}`}><strong>{readableValue(entry.stage)} · {readableValue(entry.status)}</strong>{entry.reason && <span>{readableReason(entry.reason)}</span>}</li>)}</ol>}
                        </div>
                      ))}
                    </details>
                  )}
                </article>
              );
            })}
          </div>
          {hasMore && (
            <button
              className="source-leads-more"
              type="button"
              onClick={onLoadMore}
              disabled={loadingMore}
            >
              {loadingMore ? "Loading…" : "Load more source leads"}
            </button>
          )}
        </>
      )}
    </section>
  );
}
