"use client";

import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "motion/react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Configuration,
  HistoryItem,
  RunSnapshot,
  ServiceDiagnostic,
  researchApi,
} from "@/lib/api";

type MainView = "research" | "history";
type Settings = {
  dbPath: string;
  runId: string;
  maxTokens: number;
  maxCost: string;
  maxCalls: number;
};

const terminalStates = new Set(["released", "blocked", "failed", "cancelled", "configuration_error", "invalid_input"]);
const stageOrder = [
  { key: "claim_planner", label: "Frame the claim" },
  { key: "researchers", label: "Follow both sides" },
  { key: "evidence_analyst", label: "Test the evidence" },
  { key: "statement_reviewer", label: "Review each statement" },
  { key: "final_renderer_validator", label: "Assemble & validate" },
];

function stageIndex(stage: string): number {
  if (["supporting_researcher", "opposing_researcher"].includes(stage)) return 1;
  if (["claim_ledger", "debate_synthesizer"].includes(stage)) return 4;
  const index = stageOrder.findIndex((item) => item.key === stage);
  return Math.max(index, 0);
}

function readableStage(stage: string): string {
  return stage.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function formatCost(value: string | number | null): string {
  if (value === null) return "Pending";
  return `$${Number(value).toFixed(4)}`;
}

export default function Home() {
  const reduceMotion = useReducedMotion();
  const [view, setView] = useState<MainView>("research");
  const [claim, setClaim] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [configuration, setConfiguration] = useState<Configuration | null>(null);
  const [settings, setSettings] = useState<Settings>({ dbPath: "", runId: "", maxTokens: 200_000, maxCost: "0.15", maxCalls: 160 });
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [activeRun, setActiveRun] = useState<{ id: string; database: string } | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [setupOpen, setSetupOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);

  const refreshConfiguration = useCallback(async () => {
    try {
      const result = await researchApi.configuration();
      setConfiguration(result);
      setOffline(false);
      setSettings((current) => ({ ...current, dbPath: current.dbPath || result.default_db_path }));
    } catch {
      setOffline(true);
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    if (!settings.dbPath) return;
    try {
      const result = await researchApi.history(settings.dbPath);
      setHistory(result.items);
      setOffline(false);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "History is not available.");
      setOffline(true);
    }
  }, [settings.dbPath]);

  useEffect(() => {
    const timer = window.setTimeout(() => void refreshConfiguration(), 0);
    return () => window.clearTimeout(timer);
  }, [refreshConfiguration]);
  useEffect(() => {
    if (view !== "history") return;
    const timer = window.setTimeout(() => void refreshHistory(), 0);
    return () => window.clearTimeout(timer);
  }, [view, refreshHistory]);

  const activeRunIsTerminal = snapshot ? terminalStates.has(snapshot.classification) : false;
  useEffect(() => {
    if (!activeRun || activeRunIsTerminal) return;
    let disposed = false;
    const poll = async () => {
      try {
        const result = await researchApi.snapshot(activeRun.id, activeRun.database);
        if (!disposed) { setSnapshot(result); setOffline(false); }
      } catch (error) {
        if (!disposed) setNotice(error instanceof Error ? error.message : "Progress is temporarily unavailable.");
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [activeRun, activeRunIsTerminal]);

  const beginResearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!claim.trim() || !acknowledged) return;
    if (!configuration?.configured) { setSetupOpen(true); return; }
    if (!configuration.service.wigolo_ready) {
      setNotice("Start the local research service in Advanced before beginning.");
      setAdvancedOpen(true);
      return;
    }
    setBusy(true); setNotice(null);
    try {
      const result = await researchApi.start({
        raw_claim: claim,
        acknowledged_public: acknowledged,
        db_path: settings.dbPath,
        run_id: settings.runId.trim() || null,
        max_tokens: settings.maxTokens,
        max_cost_usd: settings.maxCost,
        max_llm_calls: settings.maxCalls,
      });
      setActiveRun({ id: result.run_id, database: settings.dbPath });
      setSnapshot(null);
      setNotice(result.message);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Research could not start.");
    } finally { setBusy(false); }
  };

  const openHistoryRun = async (item: HistoryItem) => {
    setBusy(true);
    try {
      const result = await researchApi.snapshot(item.run_id, settings.dbPath);
      setSnapshot(result);
      setActiveRun({ id: item.run_id, database: settings.dbPath });
      setView("research");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "That research run could not be opened.");
    } finally { setBusy(false); }
  };

  const newResearch = () => {
    setActiveRun(null); setSnapshot(null); setClaim(""); setAcknowledged(false); setNotice(null); setView("research");
  };

  const providerState = offline ? "offline" : configuration?.configured ? "ready" : "setup";

  return (
    <MotionConfig reducedMotion="user" transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}>
      <main className="site-shell">
        <Header view={view} providerState={providerState} onView={setView} onSetup={() => setSetupOpen(true)} onAdvanced={() => setAdvancedOpen(true)} />
        <AnimatePresence mode="wait">
          {view === "history" ? (
            <HistoryView key="history" items={history} loading={busy} onOpen={openHistoryRun} />
          ) : snapshot ? (
            terminalStates.has(snapshot.classification) ? (
              <ResultView key={`result-${snapshot.run_id}`} snapshot={snapshot} onNew={newResearch} />
            ) : (
              <ProgressView key={`progress-${snapshot.run_id}`} snapshot={snapshot} onCancel={async () => {
                if (!activeRun) return;
                try { const result = await researchApi.cancel(activeRun.id, activeRun.database); setNotice(result.message); }
                catch (error) { setNotice(error instanceof Error ? error.message : "Cancellation could not be persisted."); }
              }} />
            )
          ) : activeRun ? (
            <StartingView key="starting" claim={claim} reduceMotion={Boolean(reduceMotion)} />
          ) : (
            <ResearchView key="new" claim={claim} acknowledged={acknowledged} busy={busy} reduceMotion={Boolean(reduceMotion)} onClaim={setClaim} onAcknowledged={setAcknowledged} onSubmit={beginResearch} />
          )}
        </AnimatePresence>
        <AnimatePresence>
          {notice && <Notice message={notice} onClose={() => setNotice(null)} />}
          {setupOpen && <ProviderSetup key="provider-setup" onClose={() => setSetupOpen(false)} onSaved={async (message) => { setNotice(message); setSetupOpen(false); await refreshConfiguration(); }} />}
          {advancedOpen && <AdvancedPanel key="advanced" settings={settings} configuration={configuration} active={Boolean(activeRun && (!snapshot || !terminalStates.has(snapshot.classification)))} onSettings={setSettings} onClose={() => setAdvancedOpen(false)} onService={async (action) => {
            try {
              const service = action === "start" ? await researchApi.startService() : await researchApi.stopService();
              setConfiguration((current) => current ? { ...current, service } : current);
              setNotice(service.message);
            } catch (error) { setNotice(error instanceof Error ? error.message : "The service state could not change."); }
          }} />}
        </AnimatePresence>
      </main>
    </MotionConfig>
  );
}

function Header({ view, providerState, onView, onSetup, onAdvanced }: { view: MainView; providerState: "offline" | "ready" | "setup"; onView: (view: MainView) => void; onSetup: () => void; onAdvanced: () => void; }) {
  return <header className="topbar">
    <button className="wordmark" type="button" onClick={() => onView("research")} aria-label="ResearchAssistant home"><span className="mark" aria-hidden="true">R</span><span>ResearchAssistant</span></button>
    <nav aria-label="Primary navigation">{(["research", "history"] as const).map((item) => <button className={`nav-link ${view === item ? "active" : ""}`} type="button" onClick={() => onView(item)} key={item}>{item === "research" ? "Research" : "History"}{view === item && <motion.span className="nav-indicator" layoutId="nav-indicator" />}</button>)}</nav>
    <div className="header-actions"><button className="advanced-link" type="button" onClick={onAdvanced}>Advanced</button><button className="setup-link" type="button" onClick={onSetup}><span className={`status-dot ${providerState}`} aria-hidden="true" />{providerState === "ready" ? "Providers ready" : providerState === "offline" ? "Local API offline" : "Provider setup"}</button></div>
  </header>;
}

function ResearchView({ claim, acknowledged, busy, reduceMotion, onClaim, onAcknowledged, onSubmit }: { claim: string; acknowledged: boolean; busy: boolean; reduceMotion: boolean; onClaim: (claim: string) => void; onAcknowledged: (acknowledged: boolean) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void; }) {
  const reveal = (delay: number) => reduceMotion ? {} : { initial: { opacity: 0, y: 18 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.65, delay, ease: [0.22, 1, 0.36, 1] as const } };
  return <motion.section className="hero" initial={reduceMotion ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, y: -10 }}>
    <motion.p className="eyebrow" {...reveal(0.02)}>Evidence, in context</motion.p>
    <h1><motion.span {...reveal(0.08)}>Research a claim.</motion.span><motion.span {...reveal(0.14)}>See the evidence.</motion.span></h1>
    <motion.p className="intro" {...reveal(0.2)}>See what supports it, what challenges it, and which sources the research used.</motion.p>
    <motion.form className="claim-composer" onSubmit={onSubmit} layout {...reveal(0.27)}>
      <motion.i className="composer-signal" aria-hidden="true" initial={reduceMotion ? false : { scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.9, delay: 0.48, ease: [0.22, 1, 0.36, 1] }} />
      <label htmlFor="claim">What would you like to examine?</label><textarea id="claim" value={claim} onChange={(event) => onClaim(event.target.value)} placeholder="e.g. Remote work makes software teams less productive." rows={3} />
      <label className="acknowledgement"><input type="checkbox" checked={acknowledged} onChange={(event) => onAcknowledged(event.target.checked)} /><span>This is public and non-sensitive, and I’ll review what comes back.</span></label>
      <div className="composer-footer"><span>Both sides · preserved sources · deterministic release</span><motion.button type="submit" className="primary-action" whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }} disabled={!claim.trim() || !acknowledged || busy}>{busy ? "Starting…" : "Begin research"} <span aria-hidden="true">↗</span></motion.button></div>
    </motion.form>
  </motion.section>;
}

function StartingView({ claim, reduceMotion }: { claim: string; reduceMotion: boolean }) {
  return <motion.section className="starting-view" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><div className="orbital-loader" aria-hidden="true"><motion.i animate={reduceMotion ? undefined : { rotate: 360 }} transition={{ duration: 2.8, repeat: Infinity, ease: "linear" }} /><span>01</span></div><p className="eyebrow">Preparing the trail</p><h2>{claim}</h2><p>The worker is starting. Progress appears only after it is persisted locally.</p></motion.section>;
}

function ProgressView({ snapshot, onCancel }: { snapshot: RunSnapshot; onCancel: () => void }) {
  const activeStage = stageIndex(snapshot.stage);
  const overall = Math.max(5, Math.round(((activeStage + 0.45) / stageOrder.length) * 100));
  return <motion.section className="progress-view" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
    <div className="progress-heading"><div><p className="eyebrow">Research in motion</p><motion.h2 layoutId={`claim-${snapshot.run_id}`}>{snapshot.raw_claim}</motion.h2><p>{snapshot.message}</p></div><div className="progress-dial" style={{ "--progress": `${overall * 3.6}deg` } as React.CSSProperties}><div><motion.strong key={overall} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }}>{overall}%</motion.strong><span>complete</span></div></div></div>
    <ol className="stage-list">{stageOrder.map((stage, index) => <li className={index < activeStage ? "done" : index === activeStage ? "current" : ""} key={stage.key}><span className="stage-number">0{index + 1}</span><span className="stage-label">{stage.label}</span>{index === activeStage && <motion.i layoutId="active-stage" />}</li>)}</ol>
    <div className="stance-grid"><StanceCard title="Evidence that supports" progress={snapshot.supporting} accent="warm" /><StanceCard title="Evidence that challenges" progress={snapshot.opposing} accent="cool" /></div>
    <div className="run-footnote"><div><span>Current stage</span><strong>{readableStage(snapshot.stage)}</strong></div><div><span>Model calls</span><strong>{snapshot.model_calls_used}</strong></div><div><span>Retrievals</span><strong>{snapshot.retrieval_attempts_used}</strong></div><div><span>Known model cost</span><strong>{formatCost(snapshot.known_cost_subtotal_usd)}</strong></div><button type="button" onClick={onCancel}>Cancel run</button></div>
  </motion.section>;
}

function StanceCard({ title, progress, accent }: { title: string; progress: RunSnapshot["supporting"]; accent: "warm" | "cool" }) {
  const fill = Math.min(100, progress.usable_snapshots * 12 + progress.candidates * 5 + progress.retrieval_attempts * 2);
  return <article className={`stance-card ${accent}`}><div className="stance-title"><span>{accent === "warm" ? "+" : "−"}</span><h3>{title}</h3></div><p>{progress.status.replaceAll("_", " ")}</p><div className="evidence-meter"><motion.i initial={{ width: 0 }} animate={{ width: `${Math.max(fill, 4)}%` }} /></div><dl><div><dt>Usable sources</dt><motion.dd key={progress.usable_snapshots} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>{progress.usable_snapshots}</motion.dd></div><div><dt>Candidates</dt><dd>{progress.candidates}</dd></div><div><dt>Retrievals</dt><dd>{progress.retrieval_attempts}</dd></div></dl></article>;
}

function ResultView({ snapshot, onNew }: { snapshot: RunSnapshot; onNew: () => void }) {
  const released = snapshot.classification === "released";
  return <motion.section className={`result-view ${released ? "released" : "unreleased"}`} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
    <div className="result-masthead"><div><p className="eyebrow">{released ? "Validated release" : readableStage(snapshot.classification)}</p><motion.h2 layoutId={`claim-${snapshot.run_id}`}>{snapshot.raw_claim}</motion.h2></div><div className="release-stamp"><span>{released ? "Released" : "Not released"}</span><small>{snapshot.exit_code === null ? "—" : `Exit ${snapshot.exit_code}`}</small></div></div>
    <div className="report-layout"><article className="brief-paper">{snapshot.final_brief ? <Brief text={snapshot.final_brief} /> : <div className="empty-brief"><h3>No brief was released.</h3><p>{snapshot.message}</p>{snapshot.validation_errors.map((error) => <p key={error}>{error}</p>)}</div>}</article><aside className="report-meta"><p>{snapshot.message}</p><dl><div><dt>Final stage</dt><dd>{readableStage(snapshot.stage)}</dd></div><div><dt>Model calls</dt><dd>{snapshot.model_calls_used}</dd></div><div><dt>Retrieval attempts</dt><dd>{snapshot.retrieval_attempts_used}</dd></div><div><dt>Known model cost</dt><dd>{formatCost(snapshot.known_cost_subtotal_usd)}</dd></div></dl>{snapshot.rendered_brief_hash && <button className="hash-button" type="button" onClick={() => void navigator.clipboard.writeText(snapshot.rendered_brief_hash ?? "")}><span>Release hash</span><code>{snapshot.rendered_brief_hash.slice(0, 12)}…</code><b>Copy</b></button>}{snapshot.final_brief && <button className="download-action" type="button" onClick={() => downloadBrief(snapshot)}><span>Download brief</span><b>↓</b></button>}<button className="secondary-action" type="button" onClick={onNew}>Start new research <span>↗</span></button></aside></div>
  </motion.section>;
}

function Brief({ text }: { text: string }) {
  const lines = useMemo(() => text.split("\n").filter((line) => line.trim()), [text]);
  return lines.map((line, index) => {
    const clean = line.trim();
    if (clean.startsWith("# ")) return <h1 key={index}>{clean.slice(2)}</h1>;
    if (clean.startsWith("## ")) return <h2 key={index}>{clean.slice(3)}</h2>;
    if (clean.startsWith("### ")) return <h3 key={index}>{clean.slice(4)}</h3>;
    const parts = clean.replace(/^[-*]\s+/, "").split(/(\[[^\]]+\])/g);
    return <p key={index}>{parts.map((part, partIndex) => /^\[[^\]]+\]$/.test(part) ? <mark key={partIndex}>{part}</mark> : part)}</p>;
  });
}

function downloadBrief(snapshot: RunSnapshot): void {
  if (!snapshot.final_brief) return;
  const blob = new Blob([snapshot.final_brief], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `research-brief-${snapshot.run_id}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function HistoryView({ items, loading, onOpen }: { items: HistoryItem[]; loading: boolean; onOpen: (item: HistoryItem) => void }) {
  return <motion.section className="history-view" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}><div className="history-heading"><p className="eyebrow">Persisted locally</p><h1>Past research</h1><p>Return to an earlier evidence trail without starting the work again.</p></div><div className="history-list">{loading ? <p className="history-empty">Opening the local archive…</p> : items.length === 0 ? <p className="history-empty">No research runs are stored in this database yet.</p> : items.map((item, index) => <motion.button type="button" onClick={() => onOpen(item)} key={item.run_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.035 }}><span className={`history-status ${item.status}`}>{item.status}</span><motion.strong layoutId={`claim-${item.run_id}`}>{item.raw_claim}</motion.strong><span>{readableStage(item.stage)}</span><time>{formatDate(item.updated_at)}</time><b aria-hidden="true">↗</b></motion.button>)}</div></motion.section>;
}

function ProviderSetup({ onClose, onSaved }: { onClose: () => void; onSaved: (message: string) => void }) {
  const [mimo, setMimo] = useState(""); const [exa, setExa] = useState(""); const [firecrawl, setFirecrawl] = useState(""); const [saving, setSaving] = useState(false); const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); setSaving(true); setError(null); try { const result = await researchApi.saveCredentials({ mimo_api_key: mimo, exa_api_key: exa, ...(firecrawl ? { firecrawl_api_key: firecrawl } : {}) }); setMimo(""); setExa(""); setFirecrawl(""); onSaved(result.message); } catch (caught) { setError(caught instanceof Error ? caught.message : "The keys could not be saved."); } finally { setSaving(false); } };
  return <Modal title="Connect the research providers" onClose={onClose}><p className="modal-intro">Keys go directly to your macOS Keychain through the local API. They are never returned to this page.</p><form className="setup-form" onSubmit={submit}><label>MiMo API key <input type="password" value={mimo} onChange={(event) => setMimo(event.target.value)} autoComplete="off" required /></label><label>Exa API key <input type="password" value={exa} onChange={(event) => setExa(event.target.value)} autoComplete="off" required /></label><label>Firecrawl API key <span>optional fallback</span><input type="password" value={firecrawl} onChange={(event) => setFirecrawl(event.target.value)} autoComplete="off" /></label>{error && <p className="form-error">{error}</p>}<button className="primary-action wide" type="submit" disabled={!mimo || !exa || saving}>{saving ? "Saving securely…" : "Save to Keychain"}<span>↗</span></button></form></Modal>;
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return <motion.div className="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><motion.section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" initial={{ opacity: 0, y: 20, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: .99 }}><button className="close-button" type="button" onClick={onClose} aria-label="Close">×</button><p className="eyebrow">Local & private</p><h2 id="modal-title">{title}</h2>{children}</motion.section></motion.div>;
}

function AdvancedPanel({ settings, configuration, active, onSettings, onClose, onService }: { settings: Settings; configuration: Configuration | null; active: boolean; onSettings: (settings: Settings) => void; onClose: () => void; onService: (action: "start" | "stop") => void; }) {
  const update = <K extends keyof Settings>(key: K, value: Settings[K]) => onSettings({ ...settings, [key]: value });
  return <motion.div className="overlay drawer-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><motion.aside className="advanced-panel" initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }} transition={{ type: "spring", stiffness: 320, damping: 34 }}><button className="close-button" type="button" onClick={onClose} aria-label="Close">×</button><p className="eyebrow">Advanced</p><h2>Run settings</h2><p className="panel-intro">Technical limits and local runtime details. The safe defaults are usually enough.</p><div className="settings-grid"><label>Token ceiling<input type="number" min="1" max="1000000" value={settings.maxTokens} onChange={(event) => update("maxTokens", Number(event.target.value))} /></label><label>MiMo cost ceiling<input type="text" inputMode="decimal" value={settings.maxCost} onChange={(event) => update("maxCost", event.target.value)} /></label><label>Call ceiling<input type="number" min="1" max="160" value={settings.maxCalls} onChange={(event) => update("maxCalls", Number(event.target.value))} /></label><label>Run ID <span>optional</span><input type="text" value={settings.runId} onChange={(event) => update("runId", event.target.value)} placeholder="Created automatically" /></label><label className="full">SQLite database<input type="text" value={settings.dbPath} onChange={(event) => update("dbPath", event.target.value)} /></label></div><ServiceCard service={configuration?.service ?? null} active={active} onService={onService} /><p className="security-note">The API and acquisition service bind only to this computer. Cancellation is cooperative; an active request may finish before the worker stops.</p></motion.aside></motion.div>;
}

function ServiceCard({ service, active, onService }: { service: ServiceDiagnostic | null; active: boolean; onService: (action: "start" | "stop") => void }) {
  const ready = Boolean(service?.wigolo_ready);
  return <section className="service-card"><div><span className={`status-dot ${ready ? "ready" : "setup"}`} /><p>Local acquisition</p><strong>{ready ? "Ready" : service ? readableStage(service.state) : "Unavailable"}</strong></div><p>{service?.message ?? "The local API is not responding."}</p><button type="button" disabled={active || service?.state === "wrong_service"} onClick={() => onService(ready ? "stop" : "start")}>{ready ? "Stop owned service" : "Start local service"}</button></section>;
}

function Notice({ message, onClose }: { message: string; onClose: () => void }) {
  return <motion.div className="notice" role="status" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}><span>{message}</span><button type="button" onClick={onClose} aria-label="Dismiss">×</button></motion.div>;
}
