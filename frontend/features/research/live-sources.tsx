import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { researchApi, type LiveSource, type LiveSourcesResponse } from "@/lib/api";
import { safeWebUrl } from "../results/source-leads";

type Run = { runId: string; database: string };
const pageSize = 25;
const states: Record<LiveSource["state"], string> = {
  lead: "Lead",
  screened: "Screened",
  captured: "Text captured",
  full_text: "Full text",
  assessed: "Assessed",
  admitted: "Admitted",
};
const noteLabels = {
  metadata: "Discovery summary",
  scout: "Scout screening",
  analyst: "Analyst assessment",
};

function SourceLink({ source }: { source: LiveSource }) {
  const readable = source.readable_url && safeWebUrl(source.readable_url);
  const href = readable || safeWebUrl(source.url);
  const title = source.title || (href ? new URL(href).hostname : "Untitled source");
  return href ? (
    <a href={href} target="_blank" rel="noopener noreferrer">{title}</a>
  ) : title;
}

function ShortlistCard({ source }: { source: LiveSource }) {
  const href = source.readable_url && safeWebUrl(source.readable_url) || safeWebUrl(source.url);
  return (
    <li className="live-source-card">
      <div className="live-source-meta">
        <span className="live-source-state" data-state={source.state}>{states[source.state]}</span>
        {source.angle && <span>{source.angle}</span>}
      </div>
      <h3><SourceLink source={source} /></h3>
      <p className="live-source-location">
        {href ? new URL(href).hostname.replace(/^www\./, "") : "Saved discovery record"} · Round {source.first_round}
      </p>
      {(source.note || source.state === "admitted") && (
        <details>
          <summary>Source details</summary>
          {source.note_kind && source.note && (
            <p><strong>{noteLabels[source.note_kind]}</strong>{source.note}</p>
          )}
          {source.state === "admitted" && <p>Entered the evidence ledger. Report validation is separate.</p>}
        </details>
      )}
    </li>
  );
}

export function LiveSourceShortlist({ runId, database, watching }: Run & { watching: boolean }) {
  const [page, setPage] = useState<LiveSourcesResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const revision = useRef<string | undefined>(undefined);
  const [held, setHeld] = useState<LiveSource[] | null>(null);
  const grid = useRef<HTMLUListElement>(null);
  const pointerInside = useRef(false);
  const items = held ?? page?.items ?? [];

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const next = await researchApi.liveSources(runId, database, {
          known: revision.current,
          signal: controller.signal,
        });
        if (controller.signal.aborted || next.run_id !== runId) return;
        setFailed(false);
        if (!next.unchanged) {
          revision.current = next.revision;
          setPage(next);
        }
      } catch {
        if (!controller.signal.aborted) setFailed(true);
      } finally {
        if (!controller.signal.aborted && watching) timer = setTimeout(refresh, 3000);
      }
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [database, runId, watching]);

  const hold = () => setHeld((current) => current ?? items);
  const release = () => {
    if (!pointerInside.current &&
        !grid.current?.contains(document.activeElement) &&
        !grid.current?.querySelector("details[open]")) {
      setHeld(null);
    }
  };

  return (
    <section className="live-sources" aria-labelledby="live-sources-heading">
      <header>
        <h2 id="live-sources-heading">Sources found so far</h2>
        {Boolean(page?.total) && <AllLiveSources runId={runId} database={database} />}
      </header>
      {items.length === 0 ? (
        <p className="live-sources-empty" role="status">
          {failed ? "Saved sources are temporarily unavailable."
            : !watching && page ? "No promising sources were saved yet."
            : "Promising sources will appear here as they’re found."}
        </p>
      ) : (
        <ul
          className="live-source-grid"
          ref={grid}
          onPointerMove={(event) => {
            if (event.pointerType === "touch" || pointerInside.current) return;
            pointerInside.current = true;
            hold();
          }}
          onPointerLeave={() => {
            pointerInside.current = false;
            release();
          }}
          onFocus={hold}
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) queueMicrotask(release);
          }}
          onToggle={(event) => {
            if (event.target instanceof HTMLDetailsElement && event.target.open) hold();
            else release();
          }}
        >
          {items.map((item) => <ShortlistCard key={item.work_id} source={item} />)}
        </ul>
      )}
      {failed && items.length > 0 && (
        <p className="live-sources-empty" role="status">Showing the last saved sources.</p>
      )}
    </section>
  );
}

export function AllLiveSources({ runId, database, children }: Run & { children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{
    offset: number; attempt: number; page: LiveSourcesResponse | null;
  } | null>(null);
  const current = result?.offset === offset && result.attempt === attempt ? result : null;
  const page = current?.page;

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    researchApi.liveSources(runId, database, { offset, signal: controller.signal }).then(
      (page) => {
        if (!controller.signal.aborted && page.run_id === runId) setResult({ offset, attempt, page });
      },
      () => {
        if (!controller.signal.aborted) setResult({ offset, attempt, page: null });
      },
    );
    return () => controller.abort();
  }, [database, runId, offset, attempt, open]);

  return (
    <details className="all-live-sources" onToggle={(event) => {
      setOpen(event.currentTarget.open);
      if (event.currentTarget.open) {
        setOffset(0);
        setAttempt((previous) => previous + 1);
      }
    }}>
      <summary>All sources</summary>
      {open && (
        <div className="all-live-sources-body">
          {children}
          {!current ? <p role="status">Loading saved sources…</p>
            : !page ? (
              <>
                <p role="status">Saved sources are temporarily unavailable.</p>
                <button type="button" onClick={() => setAttempt((previous) => previous + 1)}>Retry</button>
              </>
            ) : page.total === 0 ? <p>No sources have been saved yet.</p>
            : (
              <>
                <p role="status">{offset + 1}–{offset + page.items.length} of {page.total} saved works</p>
                <ul>
                  {page.items.map((item) => (
                    <li key={item.work_id}>
                      <SourceLink source={item} />
                      <span>{states[item.state]} · Round {item.first_round}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          {(offset > 0 || (page && page.total > pageSize)) && (
            <nav aria-label="Saved source pages">
              <button type="button" aria-disabled={offset === 0} onClick={() => {
                if (offset > 0) setOffset(offset - pageSize);
              }}>Previous</button>
              <button type="button" aria-disabled={!page || offset + pageSize >= page.total} onClick={() => {
                if (page && offset + pageSize < page.total) setOffset(offset + pageSize);
              }}>Next</button>
            </nav>
          )}
        </div>
      )}
    </details>
  );
}
