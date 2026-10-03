"use client";

import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "motion/react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Configuration,
  DEFAULT_STAGE_MODELS,
  HistoryItem,
  ModelUsageCostBasis,
  ModelOption,
  ModelOptions,
  ModelChoiceId,
  ResearchTrailItem,
  RunSnapshot,
  ServiceDiagnostic,
  V2EvidenceDisplay,
  V2FinalResearchOutput,
  V2ProviderRunDiagnostics,
  UsageTokenCount,
  StageModelKey,
  StageModels,
  STAGE_MODEL_KEYS,
  researchApi,
} from "@/lib/api";

import { Dialog } from "@/components/dialog";
import { ProviderSetup } from "@/components/provider-setup";
import { ProductPreview, ProgressPath, StatusPill, WorkspaceFrame } from "@/components/workspace";

type MainView = "home" | "research" | "history";
type Settings = {
  modelProfile: "configurable-2026-09";
  stageModels: StageModels;
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

function assessmentRelationshipLabel(relationship: V2EvidenceDisplay["items"][number]["relationship_to_claim"]): string {
  return ({
    supports: "Supports part of the claim",
    challenges: "Challenges part of the claim",
    qualifies: "Adds a qualification",
    unrelated: "Not relevant to the claim",
  })[relationship];
}

function researchStopLabel(reason: string): string {
  return ({
    sufficient_source_pool: "Search stopped after the source pool was considered sufficient",
    no_useful_new_direction: "No useful new research direction was found",
    no_actionable_material_gap: "No actionable research gap remained",
    no_productive_new_search: "No productive new search was available",
    no_productive_search: "No productive new search was available",
    duplicate_heavy: "Search results substantially overlapped",
    provider_eligibility_exhausted: "No eligible search provider remained",
    budget: "The research budget was reached",
    budget_limit: "The research budget was reached",
    cancelled: "Research was cancelled",
    hard_round_limit: "The maximum number of research rounds was reached",
    degraded_gap_search_agent: "The follow-up search could not be completed",
    invalid_search_agent_plan: "The follow-up search plan was invalid",
    gap_analysis_unusable: "The follow-up gap assessment could not be used",
    no_novel_query: "No new search query was available",
    no_eligible_provider: "No eligible search provider remained",
    unproductive: "The latest search did not add useful evidence",
    insufficient_reservation: "The remaining budget could not reserve another search",
    terminal_failure: "Research ended after a processing failure",
  } as Record<string, string>)[reason] ?? readableStage(reason);
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

function formatUsageTokenCount(value: UsageTokenCount): string {
  if (value.total !== null) return `${value.total.toLocaleString()}${value.complete ? "" : " reported; total incomplete"}`;
  if (value.known_subtotal > 0) return `at least ${value.known_subtotal.toLocaleString()} known; total incomplete`;
  return value.complete ? "0" : "unavailable; total incomplete";
}

function costBasisLabel(basis: ModelUsageCostBasis | null): string {
  if (basis === "published_cache_prices_reported_writes") return "published cache prices and reported cache-write tokens";
  if (basis === "published_cache_prices_assumed_all_uncached_writes") return "published cache prices; all uncached input assumed to incur cache-write charges";
  if (basis === "configured_price_cap") return "configured price cap";
  return "pricing basis not recorded";
}

function ModelUsageDisclosure({ snapshot }: { snapshot: RunSnapshot }) {
  const usage = snapshot.model_usage_details;
  if (!usage) return <p className="usage-details-unavailable">Token-level usage detail is unavailable for this saved run.</p>;
  return <details className="model-usage-details"><summary>Recorded token usage and cost basis</summary><dl><div><dt>Input tokens</dt><dd>{formatUsageTokenCount(usage.input_tokens)}</dd></div><div><dt>Output tokens</dt><dd>{formatUsageTokenCount(usage.output_tokens)}</dd></div><div><dt>Cached input tokens</dt><dd>{formatUsageTokenCount(usage.cached_input_tokens)}</dd></div><div><dt>Cache-write tokens</dt><dd>{formatUsageTokenCount(usage.cache_write_tokens)}</dd></div></dl><p><strong>Estimated cost basis:</strong> {usage.cost_basis_counts.length ? usage.cost_basis_counts.map((item) => `${item.physical_calls} call${item.physical_calls === 1 ? "" : "s"}: ${costBasisLabel(item.basis)}`).join(" · ") : "No cost-basis detail was recorded."}</p><small>These are provider-reported usage details and estimates, not an invoice.</small></details>;
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

const defaultModelOptions: ModelOption[] = [
  { id: "gpt-6-luna-high", label: "GPT-6 Luna · High", provider: "openai", input_per_million: "", output_per_million: "" },
  { id: "gpt-6-luna-xhigh", label: "GPT-6 Luna · XHigh", provider: "openai", input_per_million: "", output_per_million: "" },
  { id: "mimo-v2.6-pro", label: "MiMo v2.6 · Pro", provider: "mimo", input_per_million: "", output_per_million: "" },
  { id: "mimo-v2.6-flash", label: "MiMo v2.6 · Flash", provider: "mimo", input_per_million: "", output_per_million: "" },
  { id: "gpt-6-sol-high", label: "GPT-6 Sol · High", provider: "openai", input_per_million: "", output_per_million: "" },
  { id: "gpt-5.6-terra-high", label: "GPT-5.6 Terra · High", provider: "openai", input_per_million: "", output_per_million: "" },
];

const stageLabels: Record<StageModelKey, string> = {
  planner: "Planning",
  scout: "Scouting",
  gap_analysis: "Gap analysis",
  search_agent: "Search planning",
  source_selection: "Source selection",
  extractor: "Exact extraction",
  analyst: "Evidence analysis",
};

function mergeStageModels(current: Partial<StageModels> | undefined, defaults: StageModels): StageModels {
  return STAGE_MODEL_KEYS.reduce((result, key) => {
    result[key] = current?.[key] ?? defaults[key];
    return result;
  }, {} as StageModels);
}

function providerRequirement(stageModels: StageModels): string {
  const usesMiMo = Object.values(stageModels).some((choice) => choice.startsWith("mimo-"));
  const usesOpenAI = Object.values(stageModels).some((choice) => choice.startsWith("gpt-"));
  if (usesMiMo && usesOpenAI) return "MiMo and OpenAI keys required for the selected stages.";
  if (usesMiMo) return "A MiMo key is required for the selected stages.";
  return "An OpenAI key is required for the selected stages.";
}

function budgetOptions(current: string): string[] {
  const values = ["0.20", "0.50", "1.00", "2.00", "5.00", "10.00", "20.00"];
  const numeric = Number(current);
  if (Number.isFinite(numeric) && numeric > 0 && numeric <= 20 && !values.includes(current)) values.push(current);
  return values;
}

export default function Home() {
  const reduceMotion = useReducedMotion();
  const [view, setView] = useState<MainView>("home");
  const [claim, setClaim] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [configuration, setConfiguration] = useState<Configuration | null>(null);
  const [settings, setSettings] = useState<Settings>({ modelProfile: "configurable-2026-09", stageModels: DEFAULT_STAGE_MODELS, dbPath: "", runId: "", maxTokens: 500_000, maxCost: "0.20", maxCalls: 160, supportEnabled: true, challengeEnabled: false, sourceTarget: 10, useSerpSearch: true, useExa: true, useOpenAlex: true, useArxiv: false, usePubmed: false, useCrossref: true });
  const [modelOptions, setModelOptions] = useState<ModelOptions>({ choices: defaultModelOptions, defaults: DEFAULT_STAGE_MODELS });
  const [providerPreferencesLoaded, setProviderPreferencesLoaded] = useState(false);
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [activeRun, setActiveRun] = useState<{ id: string; database: string } | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [setupOpen, setSetupOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const configurationRequestId = useRef(0);
  const historyRequestId = useRef(0);
  const historySelectionRequestId = useRef(0);

  useEffect(() => {
    let disposed = false;
    researchApi.preferences().then((saved) => {
      if (!disposed) {
        setSettings((current) => ({ ...current, ...saved, modelProfile: "configurable-2026-09", stageModels: mergeStageModels(saved.stageModels, DEFAULT_STAGE_MODELS), dbPath: saved.dbPath || current.dbPath }));
        setProviderPreferencesLoaded(true);
      }
    }).catch(() => {
      if (!disposed) setNotice("Saved settings could not be loaded. Reopen the app before changing preferences.");
    });
    return () => { disposed = true; };
  }, []);

  useEffect(() => {
    researchApi.modelOptions().then((options) => {
      setModelOptions(options);
      setSettings((current) => ({ ...current, stageModels: mergeStageModels(current.stageModels, options.defaults) }));
    }).catch(() => {
      // The bundled defaults keep the controls usable while the local API is offline.
    });
  }, []);

  useEffect(() => {
    if (!providerPreferencesLoaded) return;
    const timer = window.setTimeout(() => {
      const { runId: _runId, ...preferences } = settings;
      void _runId;
      researchApi.savePreferences(preferences).catch(() => setNotice("Settings could not be saved. Check the local data folder."));
    }, 400);
    return () => window.clearTimeout(timer);
  }, [providerPreferencesLoaded, settings]);

  const refreshConfiguration = useCallback(async (signal?: AbortSignal) => {
    const requestId = ++configurationRequestId.current;
    const isCurrentRequest = () => requestId === configurationRequestId.current && !signal?.aborted;
    try {
      const result = await researchApi.configuration(settings.stageModels, {
        use_serpsearch: settings.useSerpSearch,
        use_exa: settings.useExa,
        use_openalex: settings.useOpenAlex,
        use_arxiv: settings.useArxiv,
        use_pubmed: settings.usePubmed,
      }, signal);
      if (!isCurrentRequest()) return;
      setConfiguration(result);
      setOffline(false);
      setSettings((current) => ({ ...current, dbPath: current.dbPath || result.default_db_path }));
    } catch {
      if (isCurrentRequest()) setOffline(true);
    }
  }, [settings.stageModels, settings.useArxiv, settings.useExa, settings.useOpenAlex, settings.usePubmed, settings.useSerpSearch]);

  const refreshHistory = useCallback(async () => {
    if (!settings.dbPath) return;
    const requestId = ++historyRequestId.current;
    const requestedDatabase = settings.dbPath;
    setHistoryLoading(true);
    try {
      const result = await researchApi.history(requestedDatabase);
      if (requestId !== historyRequestId.current) return;
      setHistory(result.items);
      setOffline(false);
    } catch (error) {
      if (requestId === historyRequestId.current) {
        setNotice(error instanceof Error ? error.message : "History is not available.");
        setOffline(true);
      }
    } finally {
      if (requestId === historyRequestId.current) setHistoryLoading(false);
    }
  }, [settings.dbPath]);

  const updateSettings = useCallback((next: Settings) => {
    if (next.dbPath !== settings.dbPath) {
      historyRequestId.current += 1;
      historySelectionRequestId.current += 1;
      setHistory([]);
      setHistoryLoading(false);
      setBusy(false);
      if (activeRun && activeRun.database !== next.dbPath && snapshot && terminalStates.has(snapshot.classification)) {
        setActiveRun(null);
        setSnapshot(null);
      }
    }
    setSettings(next);
  }, [activeRun, settings.dbPath, snapshot]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => void refreshConfiguration(controller.signal), 0);
    return () => {
      controller.abort();
      configurationRequestId.current += 1;
      window.clearTimeout(timer);
    };
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
    let timer: number | undefined;
    const controller = new AbortController();
    const poll = async (): Promise<void> => {
      if (disposed) return;
      try {
        const result = await researchApi.snapshot(activeRun.id, activeRun.database, controller.signal);
        if (disposed) return;
        setSnapshot(result);
        setOffline(false);
        if (terminalStates.has(result.classification)) return;
      } catch (error) {
        if (disposed || controller.signal.aborted) return;
        setNotice(error instanceof Error ? error.message : "Progress is temporarily unavailable.");
      }
      if (!disposed) timer = window.setTimeout(() => void poll(), 1500);
    };
    void poll();
    return () => {
      disposed = true;
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [activeRun, activeRunIsTerminal]);

  const beginResearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedClaim = claim.trim();
    if (!trimmedClaim || !acknowledged) return;
    if (!configuration) { setNotice("The local API is not ready yet."); return; }
    setBusy(true); setNotice(null);
    try {
      if (!configuration.service.wigolo_ready) {
        const service = await researchApi.startService();
        if (!service.wigolo_ready) throw new Error("Research tools could not start. Open Settings to retry.");
        setConfiguration(current => current ? { ...current, service } : current);
      }
      const result = await researchApi.start({
        model_profile: settings.modelProfile,
        stage_models: settings.stageModels,
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
    const requestId = ++historySelectionRequestId.current;
    const requestedDatabase = settings.dbPath;
    setActiveRun(null);
    setBusy(true); setNotice(null);
    try {
      const result = await researchApi.snapshot(item.run_id, requestedDatabase);
      if (requestId !== historySelectionRequestId.current) return;
      setSnapshot(result);
      setActiveRun({ id: item.run_id, database: requestedDatabase });
      setView("research");
    } catch (error) {
      if (requestId === historySelectionRequestId.current) {
        setNotice(error instanceof Error ? error.message : "That research run could not be opened.");
      }
    } finally {
      if (requestId === historySelectionRequestId.current) setBusy(false);
    }
  };

  const newResearch = () => {
    historySelectionRequestId.current += 1;
    setBusy(false);
    setActiveRun(null); setSnapshot(null); setClaim(""); setAcknowledged(false); setNotice(null); setView("research");
  };

  const navigate = (next: MainView) => {
    if (next !== "history") {
      historySelectionRequestId.current += 1;
      setBusy(false);
    }
    setView(next);
    setNotice(null);
  };

  const providerState = offline ? "offline" : configuration?.configured ? "ready" : configuration?.saved_credentials.length ? "saved" : "setup";

  return (
    <MotionConfig reducedMotion="user" transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}>
      <main className="site-shell">
        <Header view={view} providerState={providerState} onView={navigate} onSetup={() => setSetupOpen(true)} onAdvanced={() => setAdvancedOpen(true)} />
        <AnimatePresence mode="wait">
          {view === "home" ? (
            <WelcomeView key="home" ready={Boolean(configuration?.configured)} onStart={() => setView("research")} onSetup={() => setSetupOpen(true)} />
          ) : view === "history" ? (
            <HistoryView key="history" items={history} loading={historyLoading} onOpen={openHistoryRun} />
          ) : snapshot ? (
            terminalStates.has(snapshot.classification) ? (
              <ResultView key={`result-${snapshot.db_path}-${snapshot.run_id}-${snapshot.classification}`} snapshot={snapshot} onNew={newResearch} />
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
            <ResearchView key="new" settings={settings} modelOptions={modelOptions} onSettings={updateSettings} ready={Boolean(configuration?.configured && !offline)} onSetup={() => setSetupOpen(true)} claim={claim} acknowledged={acknowledged} busy={busy} supportEnabled={settings.supportEnabled} challengeEnabled={settings.challengeEnabled} reduceMotion={Boolean(reduceMotion)} onClaim={setClaim} onAcknowledged={setAcknowledged} onSubmit={beginResearch} />
          )}
        </AnimatePresence>
        <AnimatePresence>
          {notice && <Notice message={notice} onClose={() => setNotice(null)} />}
          {setupOpen && <ProviderSetup key="provider-setup" configuration={configuration} selectedProviders={{ use_serpsearch: settings.useSerpSearch, use_exa: settings.useExa, use_openalex: settings.useOpenAlex, use_arxiv: settings.useArxiv, use_pubmed: settings.usePubmed }} stageModels={settings.stageModels} onClose={() => setSetupOpen(false)} onSaved={async (message) => { setNotice(message); await refreshConfiguration(); }} />}
          {advancedOpen && <AdvancedPanel key="advanced" settings={settings} configuration={configuration} active={Boolean(activeRun && (!snapshot || !terminalStates.has(snapshot.classification)))} onSettings={updateSettings} onClose={() => setAdvancedOpen(false)} onService={async (action) => {
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
    <button className="wordmark" type="button" onClick={() => onView("home")} aria-label="ResearchAssistant home"><span className="mark" aria-hidden="true">R</span><span>ResearchAssistant</span></button>
    <nav aria-label="Primary navigation">{(["home", "research", "history"] as const).map((item) => <button className={`nav-link ${view === item ? "active" : ""}`} type="button" onClick={() => onView(item)} key={item}>{item === "home" ? "Home" : item === "research" ? "Research" : "Saved research"}{view === item && <motion.span className="nav-indicator" layoutId="nav-indicator" />}</button>)}</nav>
    <div className="header-actions"><button className="advanced-link" type="button" onClick={onAdvanced}>Settings</button><button className="setup-link" type="button" onClick={onSetup}><span className={`status-dot ${providerState}`} aria-hidden="true" />{providerState === "ready" ? "Provider setup · ready" : providerState === "saved" ? "Provider setup incomplete" : providerState === "offline" ? "App connection unavailable" : "Provider setup"}</button></div>
  </header>;
}

function WelcomeView({ ready, onStart, onSetup }: { ready: boolean; onStart: () => void; onSetup: () => void }) {
  return <motion.section className="welcome-view" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><div className="welcome-hero"><StatusPill tone={ready ? "support" : "neutral"}>{ready ? "Ready for your next question" : "Your next discovery starts here"}</StatusPill><h1>Research a claim.<br /><span>See the whole picture.</span></h1><p>Go beyond the first answer. Explore evidence, examine the sources,<br className="desktop-break" /> and build a clearer view of what holds up.</p><div className="welcome-actions"><button className="primary-action" onClick={ready ? onStart : onSetup}>{ready ? "Start research" : "Connect providers"} <span aria-hidden="true">↗</span></button><button className="text-action" onClick={onStart}>{ready ? "Write a question" : "Explore the workspace"} <span aria-hidden="true">→</span></button></div><div className="welcome-promises"><span>↗ Traceable sources</span><span>⊕ Support & challenge</span><span>◷ Your budget, your control</span></div></div><ProductPreview /></motion.section>;
}

function ResearchView({ claim, acknowledged, busy, settings, modelOptions, onSettings, ready, onSetup, onClaim, onAcknowledged, onSubmit }: { claim: string; acknowledged: boolean; busy: boolean; settings: Settings; modelOptions: ModelOptions; onSettings: (settings: Settings) => void; ready: boolean; onSetup: () => void; supportEnabled: boolean; challengeEnabled: boolean; reduceMotion: boolean; onClaim: (claim: string) => void; onAcknowledged: (acknowledged: boolean) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  const updateStageModel = (stage: StageModelKey, choice: ModelChoiceId) => onSettings({ ...settings, stageModels: { ...settings.stageModels, [stage]: choice } });
  return <motion.section className="composer-view" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><div className="page-heading"><p className="eyebrow">A fresh line of inquiry</p><h1>What deserves a closer look?</h1><p>Start with a public question or claim. We’ll follow the sources.</p></div><form className="claim-composer" onSubmit={onSubmit}><div className="composer-label"><label htmlFor="claim">Your research question</label><StatusPill tone={ready ? "support" : "neutral"}>{ready ? "Providers configured" : "Setup needed"}</StatusPill></div><textarea id="claim" value={claim} onChange={event => onClaim(event.target.value)} placeholder="e.g. Can greener streets make cities cooler?" rows={3} /><div className="composer-options"><fieldset><legend>Research direction</legend><div className="direction-options">{[{ label: "Support", support: true, challenge: false }, { label: "Challenge", support: false, challenge: true }, { label: "Both sides", support: true, challenge: true }].map(item => <button type="button" key={item.label} aria-pressed={settings.supportEnabled === item.support && settings.challengeEnabled === item.challenge} onClick={() => onSettings({ ...settings, supportEnabled: item.support, challengeEnabled: item.challenge })}>{item.label}</button>)}</div></fieldset><label>Model profile<select value={settings.modelProfile} disabled><option value="configurable-2026-09">Configurable research</option></select><small>Choose each research role below.</small></label><label>Model budget limit<select value={settings.maxCost} onChange={event => onSettings({ ...settings, maxCost: event.target.value })}>{budgetOptions(settings.maxCost).map(value => <option key={value} value={value}>${Number(value).toFixed(2)}</option>)}</select><small>Search service charges are separate.</small></label></div><section className="stage-model-settings" aria-labelledby="stage-model-heading"><div><p className="eyebrow">Model routing</p><h2 id="stage-model-heading">Choose a model for each research role</h2><p>{providerRequirement(settings.stageModels)}</p></div><div className="stage-model-grid">{STAGE_MODEL_KEYS.map((stage) => <label key={stage} htmlFor={`stage-model-${stage}`}>{stageLabels[stage]}<select id={`stage-model-${stage}`} value={settings.stageModels[stage]} onChange={event => updateStageModel(stage, event.target.value as ModelChoiceId)}>{modelOptions.choices.map(choice => <option key={choice.id} value={choice.id}>{choice.label}</option>)}</select><small>{stage === "scout" || stage === "extractor" ? "Default: Luna High" : "Default: Luna XHigh"}</small></label>)}</div></section><label className="acknowledgement"><input type="checkbox" checked={acknowledged} onChange={event => onAcknowledged(event.target.checked)} /><span>This is public and non-sensitive, and I’ll review what comes back.</span></label><div className="composer-footer"><span>Exact passages. Visible limitations. Saved on this device.</span>{ready ? <button type="submit" className="primary-action" disabled={!claim.trim() || !acknowledged || busy}>{busy ? "Starting…" : "Begin research"} <span aria-hidden="true">↗</span></button> : <button type="button" className="primary-action" onClick={onSetup}>Connect providers <span aria-hidden="true">↗</span></button>}</div></form><div className="composer-guide"><article><b>01 / Ask</b><p>Choose the direction and a model spending limit.</p></article><article><b>02 / Examine</b><p>Follow discovery, source checks and evidence analysis.</p></article><article><b>03 / Understand</b><p>Read the findings with quotations and their limitations.</p></article></div></motion.section>;
}

function StartingView({ claim, reduceMotion }: { claim: string; reduceMotion: boolean }) {
  return <motion.section className="starting-view" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><div className="orbital-loader" aria-hidden="true"><motion.i animate={reduceMotion ? undefined : { rotate: 360 }} transition={{ duration: 2.8, repeat: Infinity, ease: "linear" }} /><span>01</span></div><p className="eyebrow">Preparing the trail</p><h2>{claim}</h2><p>The worker is starting. Progress appears only after it is persisted locally.</p></motion.section>;
}

function ProgressView({ snapshot, onCancel }: { snapshot: RunSnapshot; onCancel: () => void }) {
  const activeStage = snapshot.current_research_round > 1 && ["claim_planner", "supporting_researcher", "opposing_researcher"].includes(snapshot.stage) ? 1 : stageIndex(snapshot.stage);
  const overall = snapshot.progress_percent;
  return <motion.section className="progress-view" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
    <div className="progress-heading"><div><p className="eyebrow">Research in motion · round {snapshot.current_research_round}</p><motion.h2 layoutId={`claim-${snapshot.run_id}`}>{snapshot.raw_claim}</motion.h2><p>{snapshot.message}</p></div><div className="progress-dial" style={{ "--progress": `${overall * 3.6}deg` } as React.CSSProperties}><div><motion.strong key={overall} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }}>{overall}%</motion.strong><span>complete</span></div></div></div>
    <WorkspaceFrame title="Your research notebook" status={<StatusPill tone="active">Research in progress</StatusPill>}><ProgressPath labels={stageOrder.map(stage => stage.label)} current={activeStage} /><p className="workspace-description">{snapshot.cost_usage_complete ? "Known model usage" : "Usage incomplete; reservations retained"}: {formatCost(snapshot.known_cost_subtotal_usd)} · Reserved exposure: {formatCost(snapshot.conservative_reserved_cost_usd)}</p><ModelUsageDisclosure snapshot={snapshot} /></WorkspaceFrame>
    <div className={`stance-grid ${snapshot.research_controls.research_mode === "focused" ? "single" : ""}`}>{snapshot.supporting.status !== "disabled" && <StanceCard title="Evidence that supports" progress={snapshot.supporting} accent="warm" />}{snapshot.opposing.status !== "disabled" && snapshot.research_controls.research_mode === "balanced" && <StanceCard title="Evidence that challenges" progress={snapshot.opposing} accent="cool" />}</div>
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
  const [resultError, setResultError] = useState<string | null>(null);
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
    if (!released) return () => { disposed = true; };

    void researchApi.v2Result(snapshot.run_id, snapshot.db_path)
      .then(async (result) => {
        if (disposed || !result.release_validation.valid) return;
        setV2Result(result);
        try {
          const evidence = await researchApi.v2Evidence(snapshot.run_id, snapshot.db_path);
          if (!disposed) setV2Evidence(evidence);
        } catch {
          if (!disposed) {
            setV2Evidence(null);
            setResultError("Detailed evidence could not be loaded. The validated brief remains available.");
          }
        }
      })
      .catch(() => { if (!disposed) setV2Result(null); });
    return () => { disposed = true; };
  }, [released, snapshot.db_path, snapshot.run_id]);
  return <motion.section className={`result-view ${released ? "released" : "unreleased"}`} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
    <div className="result-masthead"><div><p className="eyebrow">{released ? "Validated release" : readableStage(snapshot.classification)}</p><motion.h2 layoutId={`claim-${snapshot.run_id}`}>{snapshot.raw_claim}</motion.h2></div><div className="release-stamp"><span>{released ? "Released" : "Not released"}</span><small>{released ? "Provenance checked" : "Incomplete result"}</small></div></div>
    {resultError && <p className="setup-status" role="status">{resultError}</p>}<div className="report-layout"><article className="brief-paper">{v2Result ? <V2ResultPaper result={v2Result} evidence={v2Evidence} /> : snapshot.final_brief ? <Brief text={snapshot.final_brief} /> : <div className="empty-brief"><h3>No brief was released.</h3><p>{userStatus}</p>{snapshot.validation_errors.map((error) => <p key={error}>{error}</p>)}</div>}</article><aside className="report-meta"><p>{userStatus}</p><dl><div><dt>Final stage</dt><dd>{readableStage(snapshot.stage)}</dd></div><div><dt>Discovery sources</dt><dd>{(diagnostics?.configured_providers ?? snapshot.research_controls.discovery_providers).map(readableProvider).join(", ") || "Historical run"}</dd></div><div><dt>Model calls</dt><dd>{snapshot.model_calls_used}</dd></div><div><dt>Search attempts</dt><dd>{diagnostics?.search_attempts ?? snapshot.retrieval_attempts_used}</dd></div><div><dt>Sources acquired</dt><dd>{diagnostics?.sources_acquired ?? snapshot.retrieval_attempts_used}</dd></div><div><dt>Estimated model cost</dt><dd>{formatCost(snapshot.known_cost_subtotal_usd)}</dd></div><div><dt>Budget status</dt><dd>{!snapshot.cost_usage_complete ? "Usage incomplete; reservations retained" : snapshot.classification === "released" ? "Recorded model usage" : "Research stopped"}</dd></div></dl><ModelUsageDisclosure snapshot={snapshot} />{diagnostics && <section className="provider-diagnostics"><span>Provider outcomes</span>{diagnostics.provider_outcomes.map((outcome) => <p key={outcome.provider}><strong>{readableProvider(outcome.provider)}</strong><small>{providerOutcomeLabel(outcome)}</small></p>)}</section>}{snapshot.rendered_brief_hash && <button className="hash-button" type="button" onClick={() => void navigator.clipboard.writeText(snapshot.rendered_brief_hash ?? "")}><span>Release hash</span><code>{snapshot.rendered_brief_hash.slice(0, 12)}…</code><b>Copy</b></button>}{snapshot.final_brief && <button className="download-action" type="button" onClick={async () => { try { await navigator.clipboard.writeText(snapshot.final_brief ?? ""); setResultError("Brief copied."); } catch { setResultError("The brief could not be copied. Use Download brief instead."); } }}>Copy brief <span aria-hidden="true">↗</span></button>}{snapshot.final_brief && <button className="download-action" type="button" onClick={() => downloadBrief(snapshot)}><span>Download brief</span><b>↓</b></button>}<button className="trail-action" type="button" onClick={() => void openTrail()}><span>Research trail</span><b>↗</b></button><button className="secondary-action" type="button" onClick={onNew}>Start new research <span aria-hidden="true">↗</span></button></aside></div>
    <AnimatePresence>{trailOpen && <ResearchTrailDrawer items={trail} error={trailError} onClose={() => setTrailOpen(false)} />}</AnimatePresence>
  </motion.section>;
}

function V2ResultPaper({ result, evidence }: { result: V2FinalResearchOutput; evidence: V2EvidenceDisplay | null }) {
  const direction = result.directions.support_enabled && result.directions.challenge_enabled ? "Support and challenge research directions" : result.directions.support_enabled ? "Support-directed research only" : "Challenge-directed research only";
  const heading = (section: "supporting" | "opposing" | "limitations") => section === "supporting" ? "Support-directed findings" : section === "opposing" ? "Challenge-directed findings" : "Evidence qualifications";
  const admittedFor = (ledgerClaimId: string) => evidence?.items.find((item) => item.ledger_claim_id === ledgerClaimId);
  const sourceTitleById = new Map((evidence?.source_titles ?? []).map((item) => [item.source_id, item]));
  const sourceHeading = (sourceId: string, capturedTitle: string | null, sourceUrl: string) =>
    sourceTitleById.get(sourceId)?.display_title ?? capturedTitle ?? sourceUrl;
  const capturedTitleDisclosure = (sourceId: string, capturedTitle: string | null) => {
    const projected = sourceTitleById.get(sourceId);
    if (!projected || !capturedTitle || projected.display_title === capturedTitle) return null;
    return <details className="source-provenance"><summary>Captured title and provenance</summary><p><span className="evidence-label">Original captured title</span> {capturedTitle}</p><p><span className="evidence-label">Source URL</span> {result.all_surviving_sources.find((source) => source.source_id === sourceId)?.source_url ?? "Recorded source"}</p></details>;
  };
  const openEvidence = (ledgerClaimId: string) => { const detail = document.getElementById(`evidence-${ledgerClaimId}`); if (detail instanceof HTMLDetailsElement) { detail.open = true; detail.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "center" }); detail.querySelector("summary")?.focus({ preventScroll: true }); } };
  const budgetOutcomeBySource = new Map((evidence?.source_budget_outcomes ?? []).map((item) => [item.source_id, item.outcome]));
  const sourceOutcome = (status: string, sourceId: string, recommended: boolean) => {
    const budgetOutcome = budgetOutcomeBySource.get(sourceId);
    if (budgetOutcome) {
      const label = budgetOutcome === "source_budget_blocked" ? "source budget blocked" : budgetOutcome === "token_cap_blocked" ? "source token-cap blocked" : "source call-cap blocked";
      return `${recommended ? "Recommended" : "Survived selection"} · ${label}`;
    }
    return ({
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
    } as Record<string, string>)[status] ?? readableStage(status);
  };
  const sourceOutcomeSummary = (sources: V2FinalResearchOutput["all_surviving_sources"]) => {
    const counts = new Map<string, number>();
    for (const source of sources) {
      const budgetOutcome = budgetOutcomeBySource.get(source.source_id);
      const label = budgetOutcome === "source_budget_blocked" ? "source budget blocked"
        : budgetOutcome === "token_cap_blocked" ? "source token-cap blocked"
          : budgetOutcome === "physical_call_cap_blocked" ? "source call-cap blocked"
            : source.status === "recommended_analyzed" || source.status === "surviving_analyzed" ? "Reviewer-approved"
              : source.status.endsWith("analyzer_admitted") ? "analyzer-admitted"
                : source.status.endsWith("analyzer_failed") ? "analysis failed"
                  : source.status.endsWith("analyzer_rejected") ? "analyst-rejected"
                    : source.status.endsWith("no_ledger_evidence") ? "no admitted evidence"
                      : source.status.endsWith("not_deeply_analyzed") ? "not analyzed"
                        : source.status === "budget_prevented_analysis" ? "analysis prevented by budget" : null;
      if (label) counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    return [...counts].map(([label, count]) => `${count} ${label}`).join(", ") || "No source outcomes were recorded.";
  };
  const sourceCards = (items: V2FinalResearchOutput["all_surviving_sources"]) => items.length ? <div className="source-cards">{items.map((source) => { const details = evidence?.items.find((item) => item.source_id === source.source_id); return <article className="source-card" key={source.source_id}><a href={source.source_url} target="_blank" rel="noreferrer">{sourceHeading(source.source_id, source.title, source.source_url)}</a><small>{source.source_type || "Source"} · discovered via {source.discovery_providers.join(", ") || "recorded source"} · {source.recommended ? "Recommended for deeper analysis" : "Survived selection"} · {sourceOutcome(source.status, source.source_id, source.recommended)} · round {source.discovery_round}</small><p>{details?.selection_rationale || (source.recommended ? "Selected for deeper analysis from the surviving source pool." : "Passed selection but was not recommended for deeper analysis.")}</p>{capturedTitleDisclosure(source.source_id, source.title)}{details?.gap_ids.length ? <p><strong>Related research gaps:</strong> {details.gap_ids.length}</p> : null}</article>; })}</div> : <p>No source records are available in this section.</p>;
  const coverage = evidence?.research_status;
  const groupedNotices = evidence?.study_lineage ?? [];
  const sharedWebsites = evidence?.shared_website_groups ?? [];
  const lineageSection = groupedNotices.length ? <section><h2>Source lineage</h2><p>These notices cover sources that survived selection; separate links do not establish independent studies.</p><aside className="result-limitation">{groupedNotices.map((notice) => <p key={`${notice.basis}-${notice.source_ids.join("-")}`}>{notice.explanation} {notice.source_ids.map((id, index) => { const source = result.all_surviving_sources.find((item) => item.source_id === id); return <span key={id}>{index > 0 ? " · " : ""}{source ? <a href={source.source_url} target="_blank" rel="noreferrer">{sourceHeading(source.source_id, source.title, source.source_url)}</a> : "Recorded source"}</span>; })}</p>)}</aside></section> : null;
  const statusLabel = coverage ? researchStopLabel(coverage.reason_code) : "";
  const assessment = evidence?.post_analysis_assessment;
  const coverageIncomplete = assessment?.coverage_incomplete ?? (
    !!assessment && (
      assessment.unresolved_gap_count > 0
      || assessment.partial_coverage_count > 0
      || assessment.unavailable_coverage_count > 0
      || !result.claim_coverage_map?.length
      || result.claim_coverage_map.some((item) => !["covered", "not_applicable"].includes(item.coverage_state))
    )
  );
  const searchOutcome = assessment
    ? assessment.search_outcome ?? (
      coverageIncomplete
        ? "incomplete_coverage"
        : assessment.unadmitted_source_count > 0
          || assessment.supporting_count + assessment.challenging_count === 0
            ? "limited_evidence"
            : "analysis_complete"
    )
    : null;
  const searchOutcomeLabel = searchOutcome === "incomplete_coverage"
    ? "Incomplete coverage"
    : searchOutcome === "limited_evidence"
      ? "Limited evidence"
      : searchOutcome === "analysis_complete"
        ? "Analysis complete"
        : "";
  const searchOutcomeExplanation = searchOutcome === "incomplete_coverage"
    ? "Recorded gaps or incomplete dimensions remain, so conclusions are limited."
    : searchOutcome === "limited_evidence"
      ? "Some evidence was not admitted, or the admitted findings do not include direct support or challenge. The source outcomes and limitations below show what was retained."
      : searchOutcome === "analysis_complete"
        ? "Research met the recorded coverage checks. This does not prove the claim."
        : "";
  const admittedSurvivorCount = assessment
    ? new Set(assessment.admitted_source_ids.filter((id) => result.all_surviving_sources.some((source) => source.source_id === id))).size
    : 0;
  const noAdmittedSurvivorCount = Math.max(0, result.all_surviving_sources.length - admittedSurvivorCount);
  const assessmentLimitations = (assessment?.limitations ?? []).filter((limitation) =>
    !/^\d+ selected source\(s\) produced no admitted evidence;/.test(limitation),
  );
  const assessmentOrigin = result.post_analysis_assessment
    ? "This assessment is included in the saved brief and export."
    : "This is an additional assessment of saved evidence. The saved brief and export are unchanged.";
  const terminalStatusOrigin = result.post_analysis_assessment?.search_outcome
    ? "This post-analysis status is included in the saved brief and export."
    : "Supplemental post-analysis status from saved evidence. The saved brief and export are unchanged.";
  const claimStatus = assessment
    ? assessment.supporting_count > 0
      ? "Supporting findings observed; claim not established"
      : assessment.challenging_count > 0
        ? "Challenging findings observed; claim not established"
        : "Inconclusive: no admitted supporting finding"
    : null;
  const sharedWebsiteSection = sharedWebsites.length ? <section><h2>Shared publisher/website</h2><p>Pages from one website can add context, but the shared website alone does not establish independent corroboration.</p><aside className="result-limitation">{sharedWebsites.map((group) => <p key={group.host}><strong>{group.host}</strong> — {group.explanation} {group.source_ids.map((id, index) => { const source = evidence?.items.find((item) => item.source_id === id); return <span key={id}>{index > 0 ? " · " : ""}{source ? <a href={source.source_url} target="_blank" rel="noreferrer">{sourceHeading(source.source_id, source.title, source.source_url)}</a> : "Admitted source"}</span>; })}</p>)}</aside></section> : null;
  return <><p className="eyebrow">Your research result</p><h1>Research Brief</h1>{assessment && <div className="result-limitation" role="status"><strong>Post-analysis research status · {searchOutcomeLabel}</strong><p>{searchOutcomeExplanation}</p><p>Admitted findings: {assessment.supporting_count} supporting, {assessment.challenging_count} challenging, {assessment.qualifying_count} qualifying, and {assessment.unrelated_count} unrelated. These relationships do not independently prove the claim.</p>{!assessment.search_outcome && result.all_surviving_sources.length > 0 && <p>Among {result.all_surviving_sources.length} surviving sources, {noAdmittedSurvivorCount} had no admitted evidence and {admittedSurvivorCount} had admitted evidence.</p>}{assessmentLimitations.map((limitation) => <p key={limitation}>{limitation}</p>)}<small>{terminalStatusOrigin}</small></div>}{coverage && <div className="result-limitation" role="status"><details><summary>Earlier search decision · {statusLabel}</summary><p>{coverage.explanation}</p><p>The search assessment counted {coverage.actionable_gap_count} unresolved evidence gap{coverage.actionable_gap_count === 1 ? "" : "s"} for possible follow-up. Coverage separately recorded {coverage.partial_coverage_count} partial and {coverage.unavailable_coverage_count} unavailable dimensions.</p><small>Recorded before final evidence outcomes were available.</small></details></div>}{assessment && <div className="result-limitation" role="status"><strong>Claim status · {claimStatus}</strong><p>These counts describe admitted findings; they do not independently prove the claim.</p><small>{assessmentOrigin}</small></div>}<p>Claim under review: {result.exact_claim}</p><p><strong>Research direction:</strong> {direction}. This describes where research was directed, not whether an admitted finding supports or challenges the claim. Disabled directions were not examined.</p>{result.synthesis.sections.map((section) => <section key={section.section_type}><h2>{heading(section.section_type)}</h2><div className="overview-items">{section.items.slice(0, 3).map((item) => <p className="overview-item" key={item.ledger_claim_id}>{item.approved_factual_statement}{admittedFor(item.ledger_claim_id) && <button type="button" className="text-action" onClick={() => openEvidence(item.ledger_claim_id)}>View admitted quote and source</button>}</p>)}</div>{section.items.length > 3 && <details className="overview-more"><summary>Show {section.items.length - 3} more findings</summary><div className="overview-items">{section.items.slice(3).map((item) => <p className="overview-item" key={item.ledger_claim_id}>{item.approved_factual_statement}{admittedFor(item.ledger_claim_id) && <button type="button" className="text-action" onClick={() => openEvidence(item.ledger_claim_id)}>View admitted quote and source</button>}</p>)}</div></details>}</section>)}{lineageSection}{sharedWebsiteSection}<section><h2>Admitted evidence</h2><p>Only admitted evidence appears here. Each statement links to its analyzed passage and source. Analyzer-admitted evidence has not been independently Reviewer-approved.</p>{assessment?.qualifying_count ? <aside className="result-limitation"><h3>Context and evidence qualifications</h3><p>Qualifications can include adjacent context. They are not supporting findings by themselves; each item’s proposition and recorded limitations show what it covers.</p></aside> : null}{evidence?.items.length ? <><p>{evidence.items.length} admitted evidence item{evidence.items.length === 1 ? "" : "s"}.</p><div className="evidence-list">{evidence.items.map((item) => <details className={`evidence-card ${item.direction}`} id={`evidence-${item.ledger_claim_id}`} key={item.ledger_claim_id}><summary><span className="evidence-card-summary"><StatusPill tone={item.direction}>{item.direction === "support" ? "Support-directed" : "Challenge-directed"}</StatusPill><StatusPill tone="neutral">{assessmentRelationshipLabel(item.relationship_to_claim)}</StatusPill><span className="evidence-card-title">{item.approved_factual_statement}</span><small className="evidence-card-source">{sourceHeading(item.source_id, item.title, item.source_url)}</small>{item.source_context_notice && <small className="evidence-card-source">Legal scope has not been independently verified</small>}</span><span className="evidence-toggle" aria-hidden="true" /></summary><div className="evidence-card-body"><p><span className="evidence-label">Ledger ID</span> <code>{item.ledger_claim_id}</code></p><p><span className="evidence-label">Assessment relationship</span> {assessmentRelationshipLabel(item.relationship_to_claim)}</p>{item.claim_fit !== undefined && item.claim_fit !== null && <p><span className="evidence-label">Claim Fit</span> {item.claim_fit}/5</p>}{item.relationship_to_claim === "qualifies" && item.claim_fit === 2 && <StatusPill tone="neutral">Limited relevance</StatusPill>}<p><span className="evidence-label">Analyzed proposition</span> {item.supporting_proposition}</p><blockquote>{item.quote_passage}</blockquote><p><span className="evidence-label">Source</span> <a href={item.source_url} target="_blank" rel="noreferrer">{sourceHeading(item.source_id, item.title, item.source_url)}</a></p>{capturedTitleDisclosure(item.source_id, item.title)}{item.source_type && <p><span className="evidence-label">Source type</span> {readableStage(item.source_type)}</p>}{item.source_context_notice && <p className="result-limitation"><span className="evidence-label">Source context</span> {item.source_context_notice}</p>}<p><span className="evidence-label">Analysis</span> {item.evidence_summary}</p><p><span className="evidence-label">Validation</span> {readableStage(item.validation_status)}</p>{item.limitations.length ? <p><span className="evidence-label">Limitations</span> {item.limitations.join(" ")}</p> : <p><span className="evidence-label">Limitations</span> No additional limitations were recorded for this narrow proposition.</p>}</div></details>)}</div></> : <p>Detailed admitted passages are unavailable for this persisted result.</p>}</section><section><h2>Recommended Sources</h2>{result.recommended_sources.length > 0 && <p><strong>Recommended outcomes:</strong> {sourceOutcomeSummary(result.recommended_sources)}</p>}{sourceCards(result.recommended_sources)}</section><section><h2>Survivor Sources</h2>{result.all_surviving_sources.length > 0 && <p><strong>Outcomes among all {result.all_surviving_sources.length} surviving sources:</strong> {sourceOutcomeSummary(result.all_surviving_sources)}</p>}{sourceCards(result.all_surviving_sources)}</section><section><h2>Unresolved evidence gaps</h2>{result.unresolved_material_gaps.length ? <><p>{result.unresolved_material_gaps.length} gap{result.unresolved_material_gaps.length === 1 ? " remains" : "s remain"} unresolved.</p><ul>{result.unresolved_material_gaps.map((gap) => <li key={gap.gap_id}>{gap.direction}: {gap.missing_evidence} </li>)}</ul></> : <p>No specific unresolved evidence gaps were recorded. This does not establish that the claim is proven.</p>}</section>{!!result.claim_coverage_map?.length && <section><h2>Latest research coverage assessment</h2><p>This assessment guides research; it is not proof that the claim is established.</p><ul>{result.claim_coverage_map.map((item) => <li key={item.dimension}><strong>{readableStage(item.coverage_state)}:</strong> {item.claim_component}<p>{item.evidence_summary}</p></li>)}</ul></section>}<section><h2>Saved brief status</h2><p>Release validation passed: {result.release_validation.valid ? "yes" : "no"}. The status above reports the latest saved research decision.</p></section></>;
}

function ResearchTrailDrawer({ items, error, onClose }: { items: ResearchTrailItem[] | null; error: string | null; onClose: () => void }) {
  return <Dialog title="Research trail" onClose={onClose} wide><p className="panel-intro">Provider discoveries, the selection decision, and any subsequent acquisition attempt.</p>{error ? <p className="form-error">{error}</p> : items === null ? <p className="trail-empty">Opening the persisted trail…</p> : items.length === 0 ? <p className="trail-empty">This run has no persisted discovery trail yet.</p> : <div className="trail-list">{items.map((item, index) => <details className={`trail-item ${item.decision}`} key={`${item.research_round}-${item.stance}-${item.url}-${index}`}><summary><span className="trail-score">{item.score ?? "—"}</span><span><small>Round {item.research_round} · {item.provider} · {item.decision}</small><strong>{item.title || item.url}</strong></span></summary><p>{item.query_text}</p>{item.acquisition_state && <p><b>Acquisition:</b> {item.acquisition_state.replaceAll("_", " ")}</p>}{item.acquired_score !== null && <p><b>After acquisition:</b> {item.acquired_score}/100 · extraction order {item.extraction_rank}</p>}<a href={item.url} target="_blank" rel="noreferrer">Open source ↗</a>{item.breakdown && <dl><div><dt>Relevance</dt><dd>{item.breakdown.relevance}</dd></div><div><dt>Intent</dt><dd>{item.breakdown.intent_match}</dd></div><div><dt>Directness</dt><dd>{item.breakdown.directness}</dd></div><div><dt>Metadata</dt><dd>{item.breakdown.metadata_completeness}</dd></div><div><dt>Access</dt><dd>{item.breakdown.likely_accessibility}</dd></div><div><dt>Novelty</dt><dd>{item.breakdown.source_novelty}</dd></div><div><dt>Penalties</dt><dd>{item.breakdown.penalties}</dd></div></dl>}{item.acquired_breakdown && <dl className="acquired-breakdown"><div><dt>Readability</dt><dd>{item.acquired_breakdown.readability}</dd></div><div><dt>Claim terms</dt><dd>{item.acquired_breakdown.claim_term_coverage}</dd></div><div><dt>Specificity</dt><dd>{item.acquired_breakdown.document_specificity}</dd></div><div><dt>Evidence terms</dt><dd>{item.acquired_breakdown.evidence_language}</dd></div><div><dt>Page penalties</dt><dd>{item.acquired_breakdown.penalties}</dd></div></dl>}</details>)}</div>}</Dialog>;
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
  return <motion.section className="history-view" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}><div className="history-heading"><p className="eyebrow">Persisted locally</p><h1>Past research</h1><p>Return to an earlier evidence trail without starting the work again.</p></div><div className="history-list">{loading ? <p className="history-empty">Opening the local archive…</p> : items.length === 0 ? <p className="history-empty">Your saved research will appear here. Start a question to build your first evidence trail.</p> : items.map((item, index) => <motion.button type="button" onClick={() => onOpen(item)} key={item.run_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.035 }}><span className={`history-status ${item.status}`}>{item.status}</span><motion.strong layoutId={`claim-${item.run_id}`}>{item.raw_claim}</motion.strong><span>{readableStage(item.stage)}</span><time>{formatDate(item.updated_at)}</time><b aria-hidden="true">↗</b></motion.button>)}</div></motion.section>;
}

function AdvancedPanel({ settings, configuration, active, onSettings, onClose, onService }: { settings: Settings; configuration: Configuration | null; active: boolean; onSettings: (settings: Settings) => void; onClose: () => void; onService: (action: "start" | "stop") => void; }) {
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const importDatabase = async () => {
    try {
      const result = await researchApi.importHistory(settings.dbPath);
      onSettings({ ...settings, dbPath: result.db_path, runId: "" });
      setImportMessage(`Imported ${result.run_count} saved runs into application data. The source database was preserved.`);
    } catch { setImportMessage("Import failed. Enter an existing ResearchAssistant database path and ensure no research is running in it."); }
  };
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
  return <Dialog title="Research preferences" onClose={onClose}><p className="panel-intro">Choose the research direction, discovery providers, and local limits. At least one source is required.</p><section className="research-options"><div className="option-copy"><strong>Support</strong><span>Look for evidence that supports the claim.</span></div><button type="button" role="switch" aria-label="Support research" aria-checked={settings.supportEnabled} className={`switch ${settings.supportEnabled ? "on" : ""}`} disabled={active || (directionCount === 1 && settings.supportEnabled)} onClick={() => update("supportEnabled", !settings.supportEnabled)}><i /></button><div className="option-copy"><strong>Challenge</strong><span>Look for evidence that challenges or limits the claim.</span></div><button type="button" role="switch" aria-label="Challenge research" aria-checked={settings.challengeEnabled} className={`switch ${settings.challengeEnabled ? "on" : ""}`} disabled={active || (directionCount === 1 && settings.challengeEnabled)} onClick={() => update("challengeEnabled", !settings.challengeEnabled)}><i /></button>{sources.map(([key, label, copy]) => <div className="option-row" key={key}><div className="option-copy"><strong>{label}</strong><span>{copy}</span></div><button type="button" role="switch" aria-label={label} aria-checked={settings[key]} className={`switch ${settings[key] ? "on" : ""}`} disabled={active || (selectedCount === 1 && settings[key])} onClick={() => update(key, !settings[key])}><i /></button></div>)}<div className="option-row"><div className="option-copy"><strong>Crossref metadata</strong><span>Verify DOI bibliographic details for discovered sources. Crossref is metadata only, not evidence.</span></div><button type="button" role="switch" aria-label="Crossref metadata enrichment" aria-checked={settings.useCrossref} className={`switch ${settings.useCrossref ? "on" : ""}`} disabled={active} onClick={() => update("useCrossref", !settings.useCrossref)}><i /></button></div><div className="option-copy"><strong>Sources to examine</strong><span>Use the highest-ranked sources from each enabled direction, with bounded fallbacks.</span></div><div className="source-target" role="group" aria-label="Sources to examine">{([5, 10, 15, 20] as const).map((value) => <button type="button" key={value} className={settings.sourceTarget === value ? "active" : ""} disabled={active} onClick={() => update("sourceTarget", value)}>{value}</button>)}</div></section><details className="advanced-details"><summary>Advanced limits & history import</summary><div className="settings-grid"><label>Token ceiling<input type="number" min="1" max="500000" value={settings.maxTokens} onChange={(event) => update("maxTokens", Number(event.target.value))} /></label><label>Model cost ceiling<select value={settings.maxCost} onChange={(event) => update("maxCost", event.target.value)}>{budgetOptions(settings.maxCost).map(value => <option key={value} value={value}>${Number(value).toFixed(2)}</option>)}</select></label><label>Call ceiling<input type="number" min="1" max="160" value={settings.maxCalls} onChange={(event) => update("maxCalls", Number(event.target.value))} /></label><label>Run ID <span>optional</span><input type="text" value={settings.runId} onChange={(event) => update("runId", event.target.value)} placeholder="Created automatically" /></label><label className="full">SQLite database<input type="text" value={settings.dbPath} disabled={active} onChange={(event) => update("dbPath", event.target.value)} /></label></div><button type="button" disabled={active || !settings.dbPath} onClick={() => void importDatabase()}>Import this database into app storage</button>{importMessage && <p role="status">{importMessage}</p>}</details><ServiceCard service={configuration?.service ?? null} active={active} onService={onService} /><p className="security-note">Directions determine the scope of research. A disabled direction is not searched or inferred in the result.</p></Dialog>;
}

function ServiceCard({ service, active, onService }: { service: ServiceDiagnostic | null; active: boolean; onService: (action: "start" | "stop") => void }) {
  const ready = Boolean(service?.wigolo_ready);
  return <section className="service-card"><div><span className={`status-dot ${ready ? "ready" : "setup"}`} /><p>Local acquisition</p><strong>{ready ? "Ready" : service ? readableStage(service.state) : "Unavailable"}</strong></div><p>{service?.message ?? "The local API is not responding."}</p><button type="button" disabled={active || service?.state === "wrong_service"} onClick={() => onService(ready ? "stop" : "start")}>{ready ? "Stop owned service" : "Start local service"}</button></section>;
}

function Notice({ message, onClose }: { message: string; onClose: () => void }) {
  return <motion.div className="notice" role="status" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}><span>{message}</span><button type="button" onClick={onClose} aria-label="Dismiss">×</button></motion.div>;
}
