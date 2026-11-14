import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Banner, Button, Chip, TabPanel, Tabs, type Tone } from "@/components/ui";
import { Icon } from "@/components/icons";
import { researchApi, type RunSnapshot, type V2EvidenceDisplay, type V2FinalResearchOutput } from "@/lib/api";
import { briefWithReadingAid } from "./reading-aid";
import { formatCost, formatShortDate, understandableAttemptMessage, understandableRunMessage } from "../shared/presentation";
import { ResearchTrailDrawer } from "./trail";
import { AllLiveSources } from "../research/live-sources";
import { useResult } from "./use-result";
import { findingsByRelationship, relationshipOrder, scopeLabel, type Relationship } from "./model";
import { ResultSummary } from "./summary";
import { EvidenceGroups, VISIBLE_PER_GROUP } from "./evidence-list";
import { SourcesTab } from "./sources-tab";
import { MethodTab } from "./method-tab";

type TabId = "summary" | "evidence" | "sources" | "method";
export type RetryKind = "resume" | "retry";
export type Notify = (message: string, tone?: "info" | "success" | "warning" | "error") => void;

export function runStatus(snapshot: Pick<RunSnapshot, "classification" | "message">): { label: string; tone: Tone } {
  switch (snapshot.classification) {
    case "released":
      return { label: "Research complete", tone: "success" };
    case "blocked":
      return /budget|limit|ceiling/i.test(snapshot.message)
        ? { label: "Stopped early – budget reached", tone: "warning" }
        : { label: "Stopped early", tone: "warning" };
    case "cancelled":
      return { label: "Cancelled", tone: "neutral" };
    case "interrupted":
      return { label: "Interrupted", tone: "warning" };
    case "configuration_error":
      return { label: "Could not start – setup problem", tone: "error" };
    case "invalid_input":
      return { label: "Could not start – settings problem", tone: "error" };
    default:
      return { label: "Failed", tone: "error" };
  }
}

function snapshotScope(snapshot: RunSnapshot, result: V2FinalResearchOutput | null): string {
  if (result) return scopeLabel(result.directions);
  return scopeLabel({
    support_enabled: snapshot.supporting.status !== "disabled",
    challenge_enabled: snapshot.opposing.status !== "disabled",
  });
}

function saveFile(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function ResultView({
  snapshot,
  onNew,
  onRetry,
  notify,
}: {
  snapshot: RunSnapshot;
  onNew: () => void;
  onRetry?: (kind: RetryKind) => void;
  notify?: Notify;
}) {
  const released = snapshot.classification === "released";
  const {
    v2Result,
    v2Evidence,
    trailOpen,
    setTrailOpen,
    trail,
    resultError,
    trailError,
    openTrail,
    sourceLeads,
    sourceLeadsTotal,
    sourceLeadsNotice,
    sourceLeadsLoading,
    sourceLeadsLoadingMore,
    sourceLeadsError,
    sourceLeadsHasMore,
    loadMoreSourceLeads,
    retrySourceLeads,
  } = useResult(snapshot);
  const [tab, setTab] = useState<TabId>("summary");
  const [expanded, setExpanded] = useState<Set<Relationship>>(new Set());
  const [target, setTarget] = useState<string | null>(null);
  const findings = useMemo(() => findingsByRelationship(v2Evidence), [v2Evidence]);
  const status = runStatus(snapshot);
  const date = formatShortDate(v2Result?.created_at);
  const say: Notify = notify ?? (() => {});

  const openEvidence = (ledgerClaimId: string) => {
    for (const relationship of relationshipOrder) {
      const index = findings[relationship].findIndex(
        (finding) =>
          finding.item.ledger_claim_id === ledgerClaimId ||
          finding.related.some((item) => item.ledger_claim_id === ledgerClaimId),
      );
      if (index >= VISIBLE_PER_GROUP) setExpanded((current) => new Set(current).add(relationship));
    }
    setTab("evidence");
    setTarget(ledgerClaimId);
  };
  useEffect(() => {
    if (!target || tab !== "evidence") return;
    const frame = window.requestAnimationFrame(() => {
      const element = document.getElementById(`evidence-${target}`);
      const card = element instanceof HTMLDetailsElement ? element : element?.closest("details");
      if (card instanceof HTMLDetailsElement) {
        card.open = true;
        card.scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
          block: "center",
        });
        card.querySelector("summary")?.focus({ preventScroll: true });
      }
      setTarget(null);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [target, tab, expanded]);

  const briefText = snapshot.final_brief ? briefWithReadingAid(snapshot.final_brief, v2Result, v2Evidence) : null;
  const copyBrief = async () => {
    if (!briefText) return;
    try {
      await navigator.clipboard.writeText(briefText);
      say("Brief copied.", "success");
    } catch {
      say("The brief could not be copied. Use Export instead.", "error");
    }
  };

  const hasV2 = Boolean(v2Result);
  const tabs = [
    { id: "summary" as const, label: "Summary" },
    ...(hasV2 ? [{ id: "evidence" as const, label: "Evidence", count: relationshipOrder.reduce((sum, key) => sum + findings[key].length, 0) }] : []),
    ...(hasV2 ? [{ id: "sources" as const, label: "Sources", count: v2Result?.all_surviving_sources.length }] : []),
    { id: "method" as const, label: "Method" },
  ];

  return (
    <motion.section
      className="page result-page"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
    >
      <header className="result-header">
        <div className="result-heading">
          <div className="row result-status">
            <Chip tone={status.tone} icon={status.tone === "success" ? "check" : status.tone === "error" ? "alert" : "info"}>{status.label}</Chip>
            {date && <span className="subtle">{date}</span>}
            <span className="subtle">{snapshotScope(snapshot, v2Result)}</span>
          </div>
          <motion.h1 layoutId={`claim-${snapshot.run_id}`}>{snapshot.raw_claim}</motion.h1>
        </div>
        <div className="result-actions">
          {briefText && <ExportMenu snapshot={snapshot} brief={briefText} notify={say} />}
          {briefText && <Button icon="copy" onClick={() => void copyBrief()}>Copy</Button>}
          <Button variant="primary" icon="plus" onClick={onNew}>New research</Button>
        </div>
      </header>

      {resultError && <Banner tone="warning" role="status">{resultError}</Banner>}
      {released && snapshot.attempt_diagnostic && !["planned", "running"].includes(snapshot.persisted_status ?? "") && (
        <Banner tone="neutral" role="status">
          <p>Latest execution attempt: {understandableAttemptMessage(snapshot.attempt_diagnostic)}</p>
        </Banner>
      )}

      {!released && (
        <IncompleteRun snapshot={snapshot} onRetry={onRetry} onOpenTrail={() => void openTrail()} />
      )}

      {(released || snapshot.final_brief) && (
        <>
          <div className="result-tabs">
            <Tabs tabs={tabs} value={tab} onChange={setTab} label="Result sections" idPrefix="result" />
          </div>
          <TabPanel idPrefix="result" id="summary" active={tab === "summary"}>
            {v2Result ? (
              <ResultSummary result={v2Result} evidence={v2Evidence} findings={findings} onOpenEvidence={openEvidence} />
            ) : snapshot.final_brief ? (
              <article className="brief-text"><Brief text={snapshot.final_brief} /></article>
            ) : null}
          </TabPanel>
          {hasV2 && (
            <TabPanel idPrefix="result" id="evidence" active={tab === "evidence"}>
              <EvidenceGroups
                findings={findings}
                evidence={v2Evidence}
                expanded={expanded}
                onExpand={(relationship) => setExpanded((current) => new Set(current).add(relationship))}
              />
            </TabPanel>
          )}
          {hasV2 && v2Result && (
            <TabPanel idPrefix="result" id="sources" active={tab === "sources"}>
              <SourcesTab result={v2Result} evidence={v2Evidence} run={snapshot} />
            </TabPanel>
          )}
          <TabPanel idPrefix="result" id="method" active={tab === "method"}>
            <MethodTab snapshot={snapshot} result={v2Result} evidence={v2Evidence} onOpenTrail={() => void openTrail()} />
            {!hasV2 && (
              <section className="method-sources">
                <h3>All sources found</h3>
                <AllLiveSources runId={snapshot.run_id} database={snapshot.db_path} />
              </section>
            )}
          </TabPanel>
        </>
      )}

      <AnimatePresence>
        {trailOpen && (
          <ResearchTrailDrawer
            items={trail}
            error={trailError}
            onClose={() => setTrailOpen(false)}
            sourceLeads={sourceLeads}
            sourceLeadsTotal={sourceLeadsTotal}
            sourceLeadsNotice={sourceLeadsNotice}
            sourceLeadsLoading={sourceLeadsLoading}
            sourceLeadsLoadingMore={sourceLeadsLoadingMore}
            sourceLeadsError={sourceLeadsError}
            sourceLeadsHasMore={sourceLeadsHasMore}
            onLoadMoreSourceLeads={() => void loadMoreSourceLeads()}
            onRetrySourceLeads={retrySourceLeads}
          />
        )}
      </AnimatePresence>
    </motion.section>
  );
}

function IncompleteRun({
  snapshot,
  onRetry,
  onOpenTrail,
}: {
  snapshot: RunSnapshot;
  onRetry?: (kind: RetryKind) => void;
  onOpenTrail: () => void;
}) {
  const found = snapshot.supporting.candidates + snapshot.opposing.candidates;
  const read = snapshot.supporting.usable_snapshots + snapshot.opposing.usable_snapshots;
  const resumeFirst = ["interrupted", "cancelled", "blocked"].includes(snapshot.classification);
  const canStart = Boolean(onRetry) && snapshot.worker_active !== true;
  const resume = (
    <Button key="resume" variant={resumeFirst ? "primary" : "secondary"} icon="refresh" disabled={!canStart} onClick={() => onRetry?.("resume")}>
      Resume this run
    </Button>
  );
  const retry = (
    <Button key="retry" variant={resumeFirst ? "secondary" : "primary"} disabled={!canStart} onClick={() => onRetry?.("retry")}>
      Retry with the same settings
    </Button>
  );
  return (
    <section className="incomplete card" aria-labelledby="incomplete-heading">
      <h2 id="incomplete-heading">{snapshot.final_brief ? "This run did not finish cleanly" : "No brief was produced"}</h2>
      <div className="incomplete-grid">
        <div>
          <h3>What happened</h3>
          <p>{understandableRunMessage(snapshot)}</p>
        </div>
        <div>
          <h3>What was saved</h3>
          <p>
            {found} source{found === 1 ? "" : "s"} found, {read} page{read === 1 ? "" : "s"} read,{" "}
            {snapshot.model_calls_used} model call{snapshot.model_calls_used === 1 ? "" : "s"} ({formatCost(snapshot.known_cost_subtotal_usd)}).
            Saved progress stays in History.
          </p>
        </div>
        <div>
          <h3>What to do next</h3>
          <p>
            Resuming continues this run with its original settings and reuses completed work. Retrying starts a fresh run
            for the same claim.
          </p>
        </div>
      </div>
      <div className="row">
        {resumeFirst ? [resume, retry] : [retry, resume]}
        <Button variant="ghost" icon="history" onClick={onOpenTrail}>Research trail</Button>
      </div>
      <div className="incomplete-sources">
        <h3>Sources saved so far</h3>
        <AllLiveSources runId={snapshot.run_id} database={snapshot.db_path} />
      </div>
    </section>
  );
}

function ExportMenu({ snapshot, brief, notify }: { snapshot: RunSnapshot; brief: string; notify: Notify }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !menu.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  const exportFile = async (format: "pdf" | "docx") => {
    setBusy(format);
    try {
      const blob = await researchApi.exportBrief(snapshot.run_id, snapshot.db_path, format);
      saveFile(blob, `research-brief-${snapshot.run_id}.${format}`);
      setOpen(false);
    } catch (error) {
      notify(error instanceof Error ? error.message : "The export could not be created.", "error");
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="menu" ref={menu}>
      <Button icon="download" iconAfter="chevronDown" aria-expanded={open} aria-haspopup="true" onClick={() => setOpen(!open)}>
        Export
      </Button>
      {open && (
        <div className="menu-panel" role="group" aria-label="Export formats">
          <button
            type="button"
            className="menu-item"
            onClick={() => {
              saveFile(new Blob([brief], { type: "text/markdown;charset=utf-8" }), `research-brief-${snapshot.run_id}.md`);
              setOpen(false);
            }}
          >
            <Icon name="doc" /> Download brief (Markdown)
          </button>
          {snapshot.classification === "released" && (
            <>
              <button type="button" className="menu-item" disabled={busy !== null} onClick={() => void exportFile("pdf")}>
                <Icon name="doc" /> {busy === "pdf" ? "Preparing PDF…" : "PDF"}
              </button>
              <button type="button" className="menu-item" disabled={busy !== null} onClick={() => void exportFile("docx")}>
                <Icon name="doc" /> {busy === "docx" ? "Preparing Word document…" : "Word (DOCX)"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function Brief({ text }: { text: string }) {
  const lines = useMemo(() => text.split("\n").filter((line) => line.trim()), [text]);
  return lines.map((line, index) => {
    const clean = line.trim();
    if (clean.startsWith("# ")) return <h2 key={index}>{clean.slice(2)}</h2>;
    if (clean.startsWith("## ")) return <h3 key={index}>{clean.slice(3)}</h3>;
    if (clean.startsWith("### ")) return <h4 key={index}>{clean.slice(4)}</h4>;
    const parts = clean.replace(/^[-*]\s+/, "").split(/(\[[^\]]+\])/g);
    return (
      <p key={index}>
        {parts.map((part, partIndex) => (/^\[[^\]]+\]$/.test(part) ? <mark key={partIndex}>{part}</mark> : part))}
      </p>
    );
  });
}

export function downloadBrief(
  snapshot: RunSnapshot,
  result: V2FinalResearchOutput | null = null,
  evidence: V2EvidenceDisplay | null = null,
): void {
  if (!snapshot.final_brief) return;
  saveFile(
    new Blob([briefWithReadingAid(snapshot.final_brief, result, evidence)], { type: "text/markdown;charset=utf-8" }),
    `research-brief-${snapshot.run_id}.md`,
  );
}
