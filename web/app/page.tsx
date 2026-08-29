"use client";

import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "motion/react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Configuration,
  HistoryItem,
  ProviderSelection,
  ResearchTrailItem,
  RunSnapshot,
  ServiceDiagnostic,
  V2EvidenceDisplay,
  V2FinalResearchOutput,
  V2ProviderRunDiagnostics,
  researchApi,
} from "@/lib/api";

type MainView = "research" | "history";
type Settings = {
  dbPath: string;
  runId: string;
  maxTokens: number;
  maxCost: string;
  maxCalls: number;
  supportEnabled: boolean;
  challengeEnabled: boolean;
  sourceTarget: 5 | 10 | 15 | 20;
  useSerpSearch: boolean;
  useExa: boolean;
  useOpenAlex: boolean;
  useArxiv: boolean;
  usePubmed: boolean;
  useCrossref: boolean;
};

const PROVIDER_PREFERENCES_KEY = "researchassistant.provider-preferences.v1";

const terminalStates = new Set(["released", "blocked", "failed", "cancelled", "configuration_error", "invalid_input"]);
const stageOrder = [
  { key: "planning", label: "Planning" },
  { key: "discovery", label: "Discovery" },
  { key: "source_evaluation", label: "Source Evaluation" },
  { key: "acquisition", label: "Acquisition" },
  { key: "evidence_extraction", label: "Evidence Extraction" },
  { key: "gap_analysis", label: "Gap Analysis" },
  { key: "adaptive_search", label: "Adaptive Search" },
  { key: "deep_analysis", label: "Deep Analysis" },
  { key: "evidence_admission", label: "Evidence Admission" },
  { key: "synthesis", label: "Synthesis" },
  { key: "validation", label: "Validation" },
];

function stageIndex(stage: string): number {
  const stages: Record<string, number> = {
    claim_planner: 0, v2_initial_planner: 0,
    discovery: 1, v2_discovery: 1,
    researchers: 2, supporting_researcher: 2, opposing_researcher: 2, scout: 2,
    acquisition: 3, probe: 3,
    extractor: 4, evidence_extraction: 4,
    gap_analysis: 5,
    adaptive_search: 6,
    evidence_analyst: 7, deep_analysis: 7, evidence_admission: 8,
    statement_reviewer: 8, claim_ledger: 8,
    debate_synthesizer: 9, synthesis: 9,
    final_renderer_validator: 10, validation: 10,
  };
  return stages[stage] ?? 0;
}

function readableStage(stage: string): string {
  return stage.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function readableProvider(provider: string): string {
  return ({
    serpsearch: "SERP Search",
    exa: "Exa",
    openalex: "OpenAlex",
    arxiv: "arXiv",
    pubmed: "PubMed",
    serper: "Serper",
  } as Record<string, string>)[provider] ?? readableStage(provider);
}

function providerOutcomeLabel(outcome: V2ProviderRunDiagnostics): string {
  if (outcome.query_attempts === 0) return "Not queried";
  const details = [
    `${outcome.query_attempts} quer${outcome.query_attempts === 1 ? "y" : "ies"}`,
    `${outcome.search_results} result${outcome.search_results === 1 ? "" : "s"}`,
  ];
  if (outcome.empty_queries) details.push(`${outcome.empty_queries} empty`);
  if (outcome.timeout_queries) details.push(`${outcome.timeout_queries} timeout`);
  if (outcome.failed_queries) details.push(`${outcome.failed_queries} failed`);
  if (outcome.surviving_sources) {
    details.push(`${outcome.surviving_sources} surviving source${outcome.surviving_sources === 1 ? "" : "s"}`);
  }
  return details.join(" · ");
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function formatCost(value: string | number | null): string {
  if (value === null) return "Pending";
  return `$${Number(value).toFixed(4)}`;
}

function understandableRunMessage(snapshot: RunSnapshot): string {
  if (snapshot.classification === "configuration_error") return "A provider could not be reached or configured. Check Provider setup, then try again.";
  if (snapshot.classification === "failed") {
    return snapshot.message.trim() || "This research run did not finish. Reopen the saved run after resolving the reported issue.";
  }
  if (snapshot.classification === "cancelled") return "This research run was cancelled. Its saved evidence and progress remain available for inspection.";
  if (snapshot.classification === "blocked" && /budget|limit|ceiling/i.test(snapshot.message)) return "Stopped due to a budget limit. The result reports any evidence and gaps that were completed before the limit.";
  return snapshot.message;
}

function understandableConfigurationMessage(message: string): string {
  if (/MIMO_V25_INPUT_USD_PER_TOKEN|MIMO_V25_OUTPUT_USD_PER_TOKEN/.test(message)) {
    return "Research needs the MiMo v2.5 input and output prices. In Provider setup, enter the published USD-per-million-token amounts as plain numbers (for example, 1.25).";
  }
  if (/LUNA_INPUT_USD_PER_TOKEN|LUNA_OUTPUT_USD_PER_TOKEN/.test(message)) {
    return "Research needs the Luna input and output prices. In Provider setup, enter the published USD-per-million-token amounts as plain numbers (for example, 1.25).";
  }
  return message;
}

export default function Home() {
  const reduceMotion = useReducedMotion();
  const [view, setView] = useState<MainView>("research");
  const [claim, setClaim] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [configuration, setConfiguration] = useState<Configuration | null>(null);
  const [settings, setSettings] = useState<Settings>({ dbPath: "", runId: "", maxTokens: 500_000, maxCost: "0.20", maxCalls: 160, supportEnabled: true, challengeEnabled: false, sourceTarget: 10, useSerpSearch: true, useExa: true, useOpenAlex: true, useArxiv: false, usePubmed: false, useCrossref: true });
  const [providerPreferencesLoaded, setProviderPreferencesLoaded] = useState(false);
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [activeRun, setActiveRun] = useState<{ id: string; database: string } | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [setupOpen, setSetupOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let disposed = false;
    const timer = window.setTimeout(() => {
      try {
        const saved = window.localStorage.getItem(PROVIDER_PREFERENCES_KEY);
        if (saved && !disposed) {
          const parsed = JSON.parse(saved) as Partial<Pick<Settings, "useSerpSearch" | "useExa" | "useOpenAlex" | "useArxiv" | "usePubmed" | "useCrossref">>;
          setSettings((current) => ({
            ...current,
            ...(typeof parsed.useSerpSearch === "boolean" ? { useSerpSearch: parsed.useSerpSearch } : {}),
            ...(typeof parsed.useExa === "boolean" ? { useExa: parsed.useExa } : {}),
            ...(typeof parsed.useOpenAlex === "boolean" ? { useOpenAlex: parsed.useOpenAlex } : {}),
            ...(typeof parsed.useArxiv === "boolean" ? { useArxiv: parsed.useArxiv } : {}),
            ...(typeof parsed.usePubmed === "boolean" ? { usePubmed: parsed.usePubmed } : {}),
            ...(typeof parsed.useCrossref === "boolean" ? { useCrossref: parsed.useCrossref } : {}),
          }));
        }
      } catch {
        // Keep the safe all-provider defaults when local preference storage is unavailable.
      } finally {
        if (!disposed) setProviderPreferencesLoaded(true);
      }
    }, 0);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (!providerPreferencesLoaded) return;
    try {
      window.localStorage.setItem(
        PROVIDER_PREFERENCES_KEY,
        JSON.stringify({
          useSerpSearch: settings.useSerpSearch,
          useExa: settings.useExa,
          useOpenAlex: settings.useOpenAlex,
          useArxiv: settings.useArxiv,
          usePubmed: settings.usePubmed,
          useCrossref: settings.useCrossref,
        }),
      );
    } catch {
      // Preferences remain available for this page session if storage is unavailable.
    }
  }, [providerPreferencesLoaded, settings.useSerpSearch, settings.useExa, settings.useOpenAlex, settings.useArxiv, settings.usePubmed, settings.useCrossref]);

  const refreshConfiguration = useCallback(async () => {
    try {
      const result = await researchApi.configuration({
        use_serpsearch: settings.useSerpSearch,
        use_exa: settings.useExa,
        use_openalex: settings.useOpenAlex,
        use_arxiv: settings.useArxiv,
        use_pubmed: settings.usePubmed,
      });
      setConfiguration(result);
      setOffline(false);
      setSettings((current) => ({ ...current, dbPath: current.dbPath || result.default_db_path }));
    } catch {
      setOffline(true);
    }
  }, [settings.useArxiv, settings.useExa, settings.useOpenAlex, settings.usePubmed, settings.useSerpSearch]);

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
    const trimmedClaim = claim.trim();
    if (!trimmedClaim || !acknowledged) return;
    if (!configuration) { setNotice("The local API is not ready yet."); return; }
    if (!configuration.service.wigolo_ready) {
      setNotice("Start the local research service in Advanced before beginning.");
      setAdvancedOpen(true);
      return;
    }
    setBusy(true); setNotice(null);
    try {
      const result = await researchApi.start({
        raw_claim: trimmedClaim,
        acknowledged_public: acknowledged,
        db_path: settings.dbPath,
        run_id: settings.runId.trim() || null,
        max_tokens: settings.maxTokens,
        max_cost_usd: settings.maxCost,
        max_llm_calls: settings.maxCalls,
        support_enabled: settings.supportEnabled,
        challenge_enabled: settings.challengeEnabled,
        sources_per_stance_per_round: settings.sourceTarget,
        use_serpsearch: settings.useSerpSearch,
        use_exa: settings.useExa,
        use_openalex: settings.useOpenAlex,
        use_arxiv: settings.useArxiv,
        use_pubmed: settings.usePubmed,
        use_crossref: settings.useCrossref,
      });
      setNotice(result.classification === "configuration_error" ? understandableConfigurationMessage(result.message) : result.message);
      if (result.started) {
        setActiveRun({ id: result.run_id, database: settings.dbPath });
        setSnapshot(null);
      }
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

  const providerState = offline ? "offline" : configuration?.configured ? "ready" : configuration?.saved_credentials.length ? "saved" : "setup";

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
            <ResearchView key="new" claim={claim} acknowledged={acknowledged} busy={busy} supportEnabled={settings.supportEnabled} challengeEnabled={settings.challengeEnabled} reduceMotion={Boolean(reduceMotion)} onClaim={setClaim} onAcknowledged={setAcknowledged} onSubmit={beginResearch} />
          )}
        </AnimatePresence>
        <AnimatePresence>
          {notice && <Notice message={notice} onClose={() => setNotice(null)} />}
          {setupOpen && <ProviderSetup key="provider-setup" configuration={configuration} selectedProviders={{ use_serpsearch: settings.useSerpSearch, use_exa: settings.useExa, use_openalex: settings.useOpenAlex, use_arxiv: settings.useArxiv, use_pubmed: settings.usePubmed }} onClose={() => setSetupOpen(false)} onSaved={async (message) => { setNotice(message); await refreshConfiguration(); }} />}
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

function Header({ view, providerState, onView, onSetup, onAdvanced }: { view: MainView; providerState: "offline" | "ready" | "saved" | "setup"; onView: (view: MainView) => void; onSetup: () => void; onAdvanced: () => void; }) {
  return <header className="topbar">
    <button className="wordmark" type="button" onClick={() => onView("research")} aria-label="ResearchAssistant home"><span className="mark" aria-hidden="true">R</span><span>ResearchAssistant</span></button>
    <nav aria-label="Primary navigation">{(["research", "history"] as const).map((item) => <button className={`nav-link ${view === item ? "active" : ""}`} type="button" onClick={() => onView(item)} key={item}>{item === "research" ? "Research" : "History"}{view === item && <motion.span className="nav-indicator" layoutId="nav-indicator" />}</button>)}</nav>
    <div className="header-actions"><button className="advanced-link" type="button" onClick={onAdvanced}>Advanced</button><button className="setup-link" type="button" onClick={onSetup}><span className={`status-dot ${providerState}`} aria-hidden="true" />{providerState === "ready" ? "Providers configured" : providerState === "saved" ? "Provider setup incomplete" : providerState === "offline" ? "Local API offline" : "Provider setup"}</button></div>
  </header>;
}

function ResearchView({ claim, acknowledged, busy, supportEnabled, challengeEnabled, reduceMotion, onClaim, onAcknowledged, onSubmit }: { claim: string; acknowledged: boolean; busy: boolean; supportEnabled: boolean; challengeEnabled: boolean; reduceMotion: boolean; onClaim: (claim: string) => void; onAcknowledged: (acknowledged: boolean) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void; }) {
  const reveal = (delay: number) => reduceMotion ? {} : { initial: { opacity: 0, y: 18 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.65, delay, ease: [0.22, 1, 0.36, 1] as const } };
  return <motion.section className="hero" initial={reduceMotion ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, y: -10 }}>
    <motion.p className="eyebrow" {...reveal(0.02)}>Evidence, in context</motion.p>
    <h1><motion.span {...reveal(0.08)}>Research a claim.</motion.span><motion.span {...reveal(0.14)}>See the evidence.</motion.span></h1>
    <motion.p className="intro" {...reveal(0.2)}>See which sources hold up, what they show, and how they were chosen.</motion.p>
    <motion.form className="claim-composer" onSubmit={onSubmit} layout {...reveal(0.27)}>
      <motion.i className="composer-signal" aria-hidden="true" initial={reduceMotion ? false : { scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.9, delay: 0.48, ease: [0.22, 1, 0.36, 1] }} />
      <label htmlFor="claim">What would you like to examine?</label><textarea id="claim" value={claim} onChange={(event) => onClaim(event.target.value)} placeholder="e.g. Remote work makes software teams less productive." rows={3} />
      <label className="acknowledgement"><input type="checkbox" checked={acknowledged} onChange={(event) => onAcknowledged(event.target.checked)} /><span>This is public and non-sensitive, and I’ll review what comes back.</span></label>
      <div className="composer-footer"><span>{supportEnabled && challengeEnabled ? "Support + challenge" : supportEnabled ? "Support only" : "Challenge only"} · preserved sources</span><motion.button type="submit" className="primary-action" whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }} disabled={!claim.trim() || !acknowledged || busy}>{busy ? "Starting…" : "Begin research"} <span aria-hidden="true">↗</span></motion.button></div>
    </motion.form>
  </motion.section>;
}

function StartingView({ claim, reduceMotion }: { claim: string; reduceMotion: boolean }) {
  return <motion.section className="starting-view" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><div className="orbital-loader" aria-hidden="true"><motion.i animate={reduceMotion ? undefined : { rotate: 360 }} transition={{ duration: 2.8, repeat: Infinity, ease: "linear" }} /><span>01</span></div><p className="eyebrow">Preparing the trail</p><h2>{claim}</h2><p>The worker is starting. Progress appears only after it is persisted locally.</p></motion.section>;
}

function ProgressView({ snapshot, onCancel }: { snapshot: RunSnapshot; onCancel: () => void }) {
  const activeStage = snapshot.current_research_round > 1 && ["claim_planner", "supporting_researcher", "opposing_researcher"].includes(snapshot.stage) ? 1 : stageIndex(snapshot.stage);
  const overall = Math.max(5, snapshot.progress_percent);
  return <motion.section className="progress-view" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
    <div className="progress-heading"><div><p className="eyebrow">Research in motion · round {snapshot.current_research_round}</p><motion.h2 layoutId={`claim-${snapshot.run_id}`}>{snapshot.raw_claim}</motion.h2><p>{snapshot.message}</p></div><div className="progress-dial" style={{ "--progress": `${overall * 3.6}deg` } as React.CSSProperties}><div><motion.strong key={overall} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }}>{overall}%</motion.strong><span>complete</span></div></div></div>
    <ol className="stage-list">{stageOrder.map((stage, index) => <li className={index < activeStage ? "done" : index === activeStage ? "current" : ""} key={stage.key}><span className="stage-number">0{index + 1}</span><span className="stage-label">{stage.label}</span>{index === activeStage && <motion.i layoutId="active-stage" />}</li>)}</ol>
    <div className={`stance-grid ${snapshot.research_controls.research_mode === "focused" ? "single" : ""}`}><StanceCard title="Evidence that supports" progress={snapshot.supporting} accent="warm" />{snapshot.research_controls.research_mode === "balanced" && <StanceCard title="Evidence that challenges" progress={snapshot.opposing} accent="cool" />}</div>
    <div className="run-footnote"><div><span>Current stage</span><strong>{readableStage(snapshot.stage)}</strong></div><div><span>Model calls</span><strong>{snapshot.model_calls_used}</strong></div><div><span>Retrievals</span><strong>{snapshot.retrieval_attempts_used}</strong></div><div><span>Estimated model cost</span><strong>{formatCost(snapshot.known_cost_subtotal_usd)}</strong></div><button type="button" onClick={onCancel}>Cancel run</button></div>
  </motion.section>;
}

function StanceCard({ title, progress, accent }: { title: string; progress: RunSnapshot["supporting"]; accent: "warm" | "cool" }) {
  const fill = Math.min(100, progress.usable_snapshots * 12 + progress.candidates * 5 + progress.retrieval_attempts * 2);
  return <article className={`stance-card ${accent}`}><div className="stance-title"><span>{accent === "warm" ? "+" : "−"}</span><h3>{title}</h3></div><p>{progress.status.replaceAll("_", " ")}</p><div className="evidence-meter"><motion.i initial={{ width: 0 }} animate={{ width: `${Math.max(fill, 4)}%` }} /></div><dl><div><dt>Usable sources</dt><motion.dd key={progress.usable_snapshots} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>{progress.usable_snapshots}</motion.dd></div><div><dt>Candidates</dt><dd>{progress.candidates}</dd></div><div><dt>Retrievals</dt><dd>{progress.retrieval_attempts}</dd></div></dl></article>;
}

function ResultView({ snapshot, onNew }: { snapshot: RunSnapshot; onNew: () => void }) {
  const released = snapshot.classification === "released";
  const userStatus = understandableRunMessage(snapshot);
  const diagnostics = snapshot.v2_diagnostics;
  const [v2Result, setV2Result] = useState<V2FinalResearchOutput | null>(null);
  const [v2Evidence, setV2Evidence] = useState<V2EvidenceDisplay | null>(null);
  const [trailOpen, setTrailOpen] = useState(false);
  const [trail, setTrail] = useState<ResearchTrailItem[] | null>(null);
  const [trailError, setTrailError] = useState<string | null>(null);
  const openTrail = async () => {
    setTrailOpen(true);
    if (trail !== null) return;
    try {
      const result = await researchApi.trail(snapshot.run_id, snapshot.db_path);
      setTrail(result.items);
    } catch (error) {
      setTrailError(error instanceof Error ? error.message : "The research trail could not be opened.");
    }
  };
  useEffect(() => {
    let disposed = false;
    void researchApi.v2Result(snapshot.run_id, snapshot.db_path)
      .then((result) => { if (!disposed) setV2Result(result); })
      .catch(() => { if (!disposed) setV2Result(null); });
    void researchApi.v2Evidence(snapshot.run_id, snapshot.db_path)
      .then((result) => { if (!disposed) setV2Evidence(result); })
      .catch(() => { if (!disposed) setV2Evidence(null); });
    return () => { disposed = true; };
  }, [snapshot.db_path, snapshot.run_id]);
  return <motion.section className={`result-view ${released ? "released" : "unreleased"}`} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
    <div className="result-masthead"><div><p className="eyebrow">{released ? "Validated release" : readableStage(snapshot.classification)}</p><motion.h2 layoutId={`claim-${snapshot.run_id}`}>{snapshot.raw_claim}</motion.h2></div><div className="release-stamp"><span>{released ? "Released" : "Not released"}</span><small>{snapshot.exit_code === null ? "—" : `Exit ${snapshot.exit_code}`}</small></div></div>
    <div className="report-layout"><article className="brief-paper">{v2Result ? <V2ResultPaper result={v2Result} evidence={v2Evidence} /> : snapshot.final_brief ? <Brief text={snapshot.final_brief} /> : <div className="empty-brief"><h3>No brief was released.</h3><p>{userStatus}</p>{snapshot.validation_errors.map((error) => <p key={error}>{error}</p>)}</div>}</article><aside className="report-meta"><p>{userStatus}</p><dl><div><dt>Final stage</dt><dd>{readableStage(snapshot.stage)}</dd></div><div><dt>Discovery sources</dt><dd>{(diagnostics?.configured_providers ?? snapshot.research_controls.discovery_providers).map(readableProvider).join(", ") || "Historical run"}</dd></div><div><dt>Model calls</dt><dd>{snapshot.model_calls_used}</dd></div><div><dt>Search attempts</dt><dd>{diagnostics?.search_attempts ?? snapshot.retrieval_attempts_used}</dd></div><div><dt>Sources acquired</dt><dd>{diagnostics?.sources_acquired ?? snapshot.retrieval_attempts_used}</dd></div><div><dt>Estimated model cost</dt><dd>{formatCost(snapshot.known_cost_subtotal_usd)}</dd></div><div><dt>Budget status</dt><dd>{snapshot.classification === "blocked" ? "Stopped" : "Within run limit"}</dd></div></dl>{diagnostics && <section className="provider-diagnostics"><span>Provider outcomes</span>{diagnostics.provider_outcomes.map((outcome) => <p key={outcome.provider}><strong>{readableProvider(outcome.provider)}</strong><small>{providerOutcomeLabel(outcome)}</small></p>)}</section>}{snapshot.rendered_brief_hash && <button className="hash-button" type="button" onClick={() => void navigator.clipboard.writeText(snapshot.rendered_brief_hash ?? "")}><span>Release hash</span><code>{snapshot.rendered_brief_hash.slice(0, 12)}…</code><b>Copy</b></button>}{snapshot.final_brief && <button className="download-action" type="button" onClick={() => downloadBrief(snapshot)}><span>Download brief</span><b>↓</b></button>}<button className="trail-action" type="button" onClick={() => void openTrail()}><span>Research trail</span><b>↗</b></button><button className="secondary-action" type="button" onClick={onNew}>Start new research <span>↗</span></button></aside></div>
    <AnimatePresence>{trailOpen && <ResearchTrailDrawer items={trail} error={trailError} onClose={() => setTrailOpen(false)} />}</AnimatePresence>
  </motion.section>;
}

function V2ResultPaper({ result, evidence }: { result: V2FinalResearchOutput; evidence: V2EvidenceDisplay | null }) {
  const direction = result.directions.support_enabled && result.directions.challenge_enabled ? "Supporting and challenging evidence" : result.directions.support_enabled ? "Supporting evidence only" : "Challenging evidence only";
  const analyzerAdmitted = result.synthesis.sections.some((section) => section.items.some((item) => item.admission_method === "analyzer_admitted"));
  const heading = (section: "supporting" | "opposing" | "limitations") => section === "supporting" ? "Supporting evidence" : section === "opposing" ? "Challenging evidence" : "Evidence qualifications";
  const sourceCards = (items: V2FinalResearchOutput["all_surviving_sources"]) => <div className="source-cards">{items.map((source) => { const details = evidence?.items.find((item) => item.source_id === source.source_id); return <article className="source-card" key={source.source_id}><a href={source.source_url} target="_blank" rel="noreferrer">{source.title || source.source_url}</a><small>{details?.source_family || source.source_type || "Source family unavailable"} · discovered via {source.discovery_providers.join(", ") || "recorded source"} · {details?.recommendation_status || (source.recommended ? "Recommended for deep analysis" : "Survived selection")} · round {source.discovery_round}</small><p>{details?.selection_rationale || (source.recommended ? "Selected for deeper analysis from the surviving source pool." : "Passed selection but was not recommended for deeper analysis.")}</p>{details?.gap_ids.length ? <p><strong>Related gaps:</strong> {details.gap_ids.join(", ")}</p> : null}</article>; })}</div>;
  return <><p className="eyebrow">V2 validated research result</p><h1>Research Brief</h1><p>Claim under review: {result.exact_claim}</p><p><strong>Research direction:</strong> {direction}. This result does not imply that disabled directions were examined.</p>{result.synthesis.sections.map((section) => <section key={section.section_type}><h2>{heading(section.section_type)}</h2><div className="overview-items">{section.items.slice(0, 3).map((item, index) => <p className="overview-item" key={index}>{item.approved_factual_statement}</p>)}</div>{section.items.length > 3 && <details className="overview-more"><summary>Show {section.items.length - 3} more findings</summary><div className="overview-items">{section.items.slice(3).map((item, index) => <p className="overview-item" key={index + 3}>{item.approved_factual_statement}</p>)}</div></details>}</section>)}<section><h2>Evidence</h2><p>Each item is limited to the narrow proposition supported by the analyzed passage; {analyzerAdmitted ? "analyzer-admitted evidence is not independently reviewer-approved." : "historical evidence retains its original Reviewer-admission status."}</p>{evidence?.items.length ? <div className="evidence-list">{evidence.items.map((item) => <details className="evidence-card" key={item.source_id}><summary><span className="evidence-card-summary"><span className="evidence-card-title">{item.supporting_proposition}</span><small className="evidence-card-source">{item.title || item.source_url} · {item.source_family}</small></span><span className="evidence-toggle" aria-hidden="true" /></summary><div className="evidence-card-body"><p>{item.evidence_summary}</p><blockquote>{item.quote_passage}</blockquote><p><span className="evidence-label">Source</span> <a href={item.source_url} target="_blank" rel="noreferrer">{item.title || item.source_url}</a> · {item.source_family}</p><p><span className="evidence-label">Validation</span> {readableStage(item.validation_status)}</p>{item.limitations.length ? <p><span className="evidence-label">Limitations</span> {item.limitations.join(" ")}</p> : <p><span className="evidence-label">Limitations</span> No additional limitations were recorded for this narrow proposition.</p>}</div></details>)}</div> : <p>Detailed passage display is unavailable for this persisted result.</p>}</section><section><h2>Recommended Sources</h2>{sourceCards(result.recommended_sources)}</section><section><h2>Survivor Sources</h2>{sourceCards(result.all_surviving_sources)}</section><section><h2>Remaining Gaps</h2>{result.unresolved_material_gaps.length ? <ul>{result.unresolved_material_gaps.map((gap) => <li key={gap.gap_id}>{gap.direction}: {gap.missing_evidence} <small>({gap.gap_id})</small></li>)}</ul> : <p>No unresolved material gaps were recorded.</p>}</section><section><h2>Research Status</h2><p><strong>{result.stopping.reason === "sufficient_source_pool" ? "Stopped after sufficient evidence coverage" : readableStage(result.stopping.reason)}.</strong> {result.stopping.explanation}</p><p>{result.release_validation.valid ? "Validation completed successfully." : "Validation did not complete successfully."}</p></section></>;
}

function ResearchTrailDrawer({ items, error, onClose }: { items: ResearchTrailItem[] | null; error: string | null; onClose: () => void }) {
  return <motion.div className="overlay drawer-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><motion.aside className="advanced-panel trail-panel" initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }} transition={{ type: "spring", stiffness: 320, damping: 34 }}><button className="close-button" type="button" onClick={onClose} aria-label="Close">×</button><p className="eyebrow">Advanced · post-run</p><h2>Research trail</h2><p className="panel-intro">Provider discoveries, the selection decision, and any subsequent acquisition attempt.</p>{error ? <p className="form-error">{error}</p> : items === null ? <p className="trail-empty">Opening the persisted trail…</p> : items.length === 0 ? <p className="trail-empty">This run has no persisted discovery trail yet.</p> : <div className="trail-list">{items.map((item, index) => <details className={`trail-item ${item.decision}`} key={`${item.research_round}-${item.stance}-${item.url}-${index}`}><summary><span className="trail-score">{item.score ?? "—"}</span><span><small>Round {item.research_round} · {item.provider} · {item.decision}</small><strong>{item.title || item.url}</strong></span></summary><p>{item.query_text}</p>{item.acquisition_state && <p><b>Acquisition:</b> {item.acquisition_state.replaceAll("_", " ")}</p>}{item.acquired_score !== null && <p><b>After acquisition:</b> {item.acquired_score}/100 · extraction order {item.extraction_rank}</p>}<a href={item.url} target="_blank" rel="noreferrer">Open source ↗</a>{item.breakdown && <dl><div><dt>Relevance</dt><dd>{item.breakdown.relevance}</dd></div><div><dt>Intent</dt><dd>{item.breakdown.intent_match}</dd></div><div><dt>Directness</dt><dd>{item.breakdown.directness}</dd></div><div><dt>Metadata</dt><dd>{item.breakdown.metadata_completeness}</dd></div><div><dt>Access</dt><dd>{item.breakdown.likely_accessibility}</dd></div><div><dt>Novelty</dt><dd>{item.breakdown.source_novelty}</dd></div><div><dt>Penalties</dt><dd>{item.breakdown.penalties}</dd></div></dl>}{item.acquired_breakdown && <dl className="acquired-breakdown"><div><dt>Readability</dt><dd>{item.acquired_breakdown.readability}</dd></div><div><dt>Claim terms</dt><dd>{item.acquired_breakdown.claim_term_coverage}</dd></div><div><dt>Specificity</dt><dd>{item.acquired_breakdown.document_specificity}</dd></div><div><dt>Evidence terms</dt><dd>{item.acquired_breakdown.evidence_language}</dd></div><div><dt>Page penalties</dt><dd>{item.acquired_breakdown.penalties}</dd></div></dl>}</details>)}</div>}</motion.aside></motion.div>;
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

function ProviderSetup({ configuration, selectedProviders, onClose, onSaved }: { configuration: Configuration | null; selectedProviders: ProviderSelection; onClose: () => void; onSaved: (message: string) => Promise<void> }) {
  const [mimo, setMimo] = useState(""); const [luna, setLuna] = useState(""); const [lunaBaseUrl, setLunaBaseUrl] = useState(""); const [lunaModel, setLunaModel] = useState(""); const [mimoInputPrice, setMimoInputPrice] = useState(""); const [mimoOutputPrice, setMimoOutputPrice] = useState(""); const [lunaInputPrice, setLunaInputPrice] = useState(""); const [lunaOutputPrice, setLunaOutputPrice] = useState(""); const [serpsearch, setSerpsearch] = useState(""); const [exa, setExa] = useState(""); const [openalex, setOpenalex] = useState(""); const [pubmed, setPubmed] = useState(""); const [firecrawl, setFirecrawl] = useState(""); const [saving, setSaving] = useState(false); const [saved, setSaved] = useState(false); const [savedSettings, setSavedSettings] = useState<string[] | null>(null); const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); setSaving(true); setSaved(false); setError(null); try { const result = await researchApi.saveCredentials({ ...(mimo ? { mimo_api_key: mimo } : {}), ...(luna ? { luna_api_key: luna } : {}), ...(lunaBaseUrl ? { luna_base_url: lunaBaseUrl } : {}), ...(lunaModel ? { luna_model: lunaModel } : {}), ...(mimoInputPrice ? { mimo_v25_input_usd_per_million: mimoInputPrice } : {}), ...(mimoOutputPrice ? { mimo_v25_output_usd_per_million: mimoOutputPrice } : {}), ...(lunaInputPrice ? { luna_input_usd_per_million: lunaInputPrice } : {}), ...(lunaOutputPrice ? { luna_output_usd_per_million: lunaOutputPrice } : {}), ...(serpsearch ? { serpsearch_api_key: serpsearch } : {}), ...(exa ? { exa_api_key: exa } : {}), ...(openalex ? { openalex_api_key: openalex } : {}), ...(pubmed ? { pubmed_api_key: pubmed } : {}), ...(firecrawl ? { firecrawl_api_key: firecrawl } : {}), }, selectedProviders); setMimo(""); setLuna(""); setSerpsearch(""); setExa(""); setOpenalex(""); setPubmed(""); setFirecrawl(""); setSavedSettings(result.saved_settings); setSaved(true); await onSaved(result.message); } catch (caught) { setError(caught instanceof Error ? caught.message : "The provider details could not be saved."); } finally { setSaving(false); } };
  const confirmedSettings = savedSettings ?? configuration?.saved_settings ?? [];
  const missingBudgetPrices = ["MiMo input price", "MiMo output price", "Luna input price", "Luna output price"].filter((name) => !confirmedSettings.includes(name));
  return <Modal title="Connect the research providers" onClose={onClose}><p className="modal-intro">Keys go directly to your macOS Keychain through the local API. They are never returned to this page. Luna uses the standard OpenAI-compatible route and the v2 Luna model by default; only enter overrides when your deployment specifies different values. Price caps are used only to enforce your local run budget—enter the published on-demand USD price per million tokens. arXiv and Crossref do not require keys; Crossref supplies metadata only, never evidence.</p><form className="setup-form" onSubmit={submit}>{saved && <p className="setup-saved">Saved in Keychain. Password fields stay empty by design; the checklist below is the API’s confirmation of the non-secret route settings it received.</p>}<p className={missingBudgetPrices.length ? "setup-status missing" : "setup-status ready"}>{missingBudgetPrices.length ? `Still needed to start research: ${missingBudgetPrices.join(", ")}.` : "Budget pricing is saved; the local run configuration can proceed."}</p><label>MiMo API key <span>leave blank to keep the saved key</span><input type="password" value={mimo} onChange={(event) => setMimo(event.target.value)} autoComplete="off" /></label><label>MiMo v2.5 input price <span>USD per million tokens; enter only a number, for example 1.25</span><input type="number" min="0" step="any" value={mimoInputPrice} onChange={(event) => setMimoInputPrice(event.target.value)} placeholder="Published input price" autoComplete="off" /></label><label>MiMo v2.5 output price <span>USD per million tokens; enter only a number, for example 1.25</span><input type="number" min="0" step="any" value={mimoOutputPrice} onChange={(event) => setMimoOutputPrice(event.target.value)} placeholder="Published output price" autoComplete="off" /></label><label>OpenAI API key <span>for GPT-5.6 Luna gap analysis and evidence analysis</span><input type="password" value={luna} onChange={(event) => setLuna(event.target.value)} autoComplete="off" /></label><label>Luna input price <span>USD per million tokens; enter only a number, for example 1.25</span><input type="number" min="0" step="any" value={lunaInputPrice} onChange={(event) => setLunaInputPrice(event.target.value)} placeholder="Published input price" autoComplete="off" /></label><label>Luna output price <span>USD per million tokens; enter only a number, for example 1.25</span><input type="number" min="0" step="any" value={lunaOutputPrice} onChange={(event) => setLunaOutputPrice(event.target.value)} placeholder="Published output price" autoComplete="off" /></label><label>Luna API base URL <span>optional override; defaults to the standard OpenAI-compatible route</span><input type="url" value={lunaBaseUrl} onChange={(event) => setLunaBaseUrl(event.target.value)} placeholder="https://api.openai.com/v1" autoComplete="off" /></label><label>Luna model ID <span>optional override; use only when your deployment specifies a different model</span><input type="text" value={lunaModel} onChange={(event) => setLunaModel(event.target.value)} placeholder="gpt-5.6-luna" autoComplete="off" /></label><label>SERP Search API key <span>optional until selected</span><input type="password" value={serpsearch} onChange={(event) => setSerpsearch(event.target.value)} autoComplete="off" /></label><label>Exa API key <span>optional until selected</span><input type="password" value={exa} onChange={(event) => setExa(event.target.value)} autoComplete="off" /></label><label>OpenAlex API key <span>optional until selected</span><input type="password" value={openalex} onChange={(event) => setOpenalex(event.target.value)} autoComplete="off" /></label><label>PubMed API key <span>optional; higher request allowance when PubMed is selected</span><input type="password" value={pubmed} onChange={(event) => setPubmed(event.target.value)} autoComplete="off" /></label><label>Firecrawl API key <span>optional fallback</span><input type="password" value={firecrawl} onChange={(event) => setFirecrawl(event.target.value)} autoComplete="off" /></label>{error && <p className="form-error">{error}</p>}<button className="primary-action wide" type="submit" disabled={!(mimo || luna || lunaBaseUrl || lunaModel || mimoInputPrice || mimoOutputPrice || lunaInputPrice || lunaOutputPrice || serpsearch || exa || openalex || pubmed || firecrawl) || saving}>{saving ? "Saving securely…" : "Save to Keychain"}<span>↗</span></button></form></Modal>;
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return <motion.div className="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><motion.section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" initial={{ opacity: 0, y: 20, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: .99 }}><button className="close-button" type="button" onClick={onClose} aria-label="Close">×</button><p className="eyebrow">Local & private</p><h2 id="modal-title">{title}</h2>{children}</motion.section></motion.div>;
}

function AdvancedPanel({ settings, configuration, active, onSettings, onClose, onService }: { settings: Settings; configuration: Configuration | null; active: boolean; onSettings: (settings: Settings) => void; onClose: () => void; onService: (action: "start" | "stop") => void; }) {
  const update = <K extends keyof Settings>(key: K, value: Settings[K]) => onSettings({ ...settings, [key]: value });
  const sources = [
    ["useSerpSearch", "SERP Search", "Best for familiar Google results across the wider web, including current pages and everyday sources."],
    ["useExa", "Exa", "Best for finding relevant pages by meaning, not just exact keywords."],
    ["useOpenAlex", "OpenAlex", "Best for academic studies, papers, and other scholarly research."],
    ["useArxiv", "arXiv", "Best for research preprints. arXiv does not require an API key."],
    ["usePubmed", "PubMed", "Best for biomedical literature. It works without a key; a key raises its request allowance."],
  ] as const;
  const selectedCount = sources.filter(([key]) => settings[key]).length;
  const directionCount = Number(settings.supportEnabled) + Number(settings.challengeEnabled);
  return <motion.div className="overlay drawer-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><motion.aside className="advanced-panel" initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }} transition={{ type: "spring", stiffness: 320, damping: 34 }}><button className="close-button" type="button" onClick={onClose} aria-label="Close">×</button><p className="eyebrow">Advanced</p><h2>Run settings</h2><p className="panel-intro">Choose the research direction, discovery providers, and local limits. At least one source is required.</p><section className="research-options"><div className="option-copy"><strong>Support</strong><span>Look for evidence that supports the claim.</span></div><button type="button" role="switch" aria-label="Support research" aria-checked={settings.supportEnabled} className={`switch ${settings.supportEnabled ? "on" : ""}`} disabled={active || (directionCount === 1 && settings.supportEnabled)} onClick={() => update("supportEnabled", !settings.supportEnabled)}><i /></button><div className="option-copy"><strong>Challenge</strong><span>Look for evidence that challenges or limits the claim.</span></div><button type="button" role="switch" aria-label="Challenge research" aria-checked={settings.challengeEnabled} className={`switch ${settings.challengeEnabled ? "on" : ""}`} disabled={active || (directionCount === 1 && settings.challengeEnabled)} onClick={() => update("challengeEnabled", !settings.challengeEnabled)}><i /></button>{sources.map(([key, label, copy]) => <div className="option-row" key={key}><div className="option-copy"><strong>{label}</strong><span>{copy}</span></div><button type="button" role="switch" aria-label={label} aria-checked={settings[key]} className={`switch ${settings[key] ? "on" : ""}`} disabled={active || (selectedCount === 1 && settings[key])} onClick={() => update(key, !settings[key])}><i /></button></div>)}<div className="option-row"><div className="option-copy"><strong>Crossref metadata</strong><span>Verify DOI bibliographic details for discovered sources. Crossref is metadata only, not evidence.</span></div><button type="button" role="switch" aria-label="Crossref metadata enrichment" aria-checked={settings.useCrossref} className={`switch ${settings.useCrossref ? "on" : ""}`} disabled={active} onClick={() => update("useCrossref", !settings.useCrossref)}><i /></button></div><div className="option-copy"><strong>Sources to examine</strong><span>Use the highest-ranked sources from each enabled direction, with bounded fallbacks.</span></div><div className="source-target" role="group" aria-label="Sources to examine">{([5, 10, 15, 20] as const).map((value) => <button type="button" key={value} className={settings.sourceTarget === value ? "active" : ""} disabled={active} onClick={() => update("sourceTarget", value)}>{value}</button>)}</div></section><div className="settings-grid"><label>Token ceiling<input type="number" min="1" max="500000" value={settings.maxTokens} onChange={(event) => update("maxTokens", Number(event.target.value))} /></label><label>MiMo cost ceiling<input type="text" inputMode="decimal" value={settings.maxCost} onChange={(event) => update("maxCost", event.target.value)} /></label><label>Call ceiling<input type="number" min="1" max="160" value={settings.maxCalls} onChange={(event) => update("maxCalls", Number(event.target.value))} /></label><label>Run ID <span>optional</span><input type="text" value={settings.runId} onChange={(event) => update("runId", event.target.value)} placeholder="Created automatically" /></label><label className="full">SQLite database<input type="text" value={settings.dbPath} onChange={(event) => update("dbPath", event.target.value)} /></label></div><ServiceCard service={configuration?.service ?? null} active={active} onService={onService} /><p className="security-note">Directions determine the scope of research. A disabled direction is not searched or inferred in the result.</p></motion.aside></motion.div>;
}

function ServiceCard({ service, active, onService }: { service: ServiceDiagnostic | null; active: boolean; onService: (action: "start" | "stop") => void }) {
  const ready = Boolean(service?.wigolo_ready);
  return <section className="service-card"><div><span className={`status-dot ${ready ? "ready" : "setup"}`} /><p>Local acquisition</p><strong>{ready ? "Ready" : service ? readableStage(service.state) : "Unavailable"}</strong></div><p>{service?.message ?? "The local API is not responding."}</p><button type="button" disabled={active || service?.state === "wrong_service"} onClick={() => onService(ready ? "stop" : "start")}>{ready ? "Stop owned service" : "Start local service"}</button></section>;
}

function Notice({ message, onClose }: { message: string; onClose: () => void }) {
  return <motion.div className="notice" role="status" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}><span>{message}</span><button type="button" onClick={onClose} aria-label="Dismiss">×</button></motion.div>;
}
