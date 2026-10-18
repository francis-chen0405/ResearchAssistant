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
            {items.map((lead) => {
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
                      {href && <span className="source-lead-url">{lead.url}</span>}
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
                      <span>{alternateHref}</span>
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
                    <span>{lead.reason || "Not recorded"}</span>
                  </p>
                  <details className="source-lead-details">
                    <summary>Lead metadata and history</summary>
                    <dl>
                      <div>
                        <dt>Disposition</dt>
                        <dd>{readableValue(lead.disposition)}</dd>
                      </div>
                      <div>
                        <dt>Reason</dt>
                        <dd>{lead.reason || "Not recorded"}</dd>
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
                            {entry.reason && <span>{entry.reason}</span>}
                          </li>
                        ))}
                      </ol>
                    )}
                  </details>
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
