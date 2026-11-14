"use client";

import { AnimatePresence, MotionConfig, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Header, HomeView, Notice, PreferencesStatus } from "@/features/shell/views";
import { ResearchView, StartingView } from "@/features/research/composer";
import { ProgressView } from "@/features/research/progress";
import { ResultView } from "@/features/results/result";
import { HistoryView } from "@/features/history/history";
import { AdvancedPanel, type SettingsSection } from "@/features/preferences/panel";
import { usePreferences } from "@/features/preferences/use-preferences";
import { useConfiguration } from "@/features/preferences/use-configuration";
import { useResearch } from "@/features/research/use-research";
import { useHistory } from "@/features/history/use-history";
import { terminalStates } from "@/features/shared/presentation";
import type { MainView, Settings } from "@/features/preferences/settings";
import type { RetryKind } from "@/features/results/result";

type ToastTone = "info" | "success" | "warning" | "error";
const inferTone = (message: string): ToastTone =>
  /could not|couldn.t|failed|not available|unavailable|error|not ready|refus/i.test(message)
    ? "error"
    : /saved|removed|restored|copied|started/i.test(message)
      ? "success"
      : "info";

export default function Home() {
  const reduceMotion = useReducedMotion();
  const [view, setView] = useState<MainView>("home");
  const [settingsOpen, setSettingsOpen] = useState<SettingsSection | "auto" | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: ToastTone } | null>(null);
  const setNotice = useCallback(
    (message: string | null) => setToast(message ? { message, tone: inferTone(message) } : null),
    [],
  );
  const notify = useCallback(
    (message: string, tone: ToastTone = "info") => setToast({ message, tone }),
    [],
  );
  const [offline, setOffline] = useState(false);
  const { settings, setSettings, modelOptions, preferencesStatus, retryPreferences } =
    usePreferences(setNotice);
  const preferencesReady = preferencesStatus === "ready";
  const { configuration, refreshConfiguration, updateService, changeService } =
    useConfiguration(settings, setSettings, setOffline, setNotice);
  const research = useResearch(setNotice, setOffline, view === "research" && preferencesReady);
  const history = useHistory(
    settings.dbPath,
    view,
    research,
    setView,
    setNotice,
    setOffline,
  );
  const { snapshot, activeRun } = research;

  const updateSettings = (next: Settings) => {
    if (next.dbPath !== settings.dbPath) {
      history.invalidateDatabase();
      research.clearTerminalOutsideDatabase(next.dbPath);
    }
    setSettings(next);
  };
  const selectImportedDatabase = (database: string) => {
    history.invalidateDatabase();
    research.clearTerminalOutsideDatabase(database);
    setSettings((current) => ({ ...current, dbPath: database, runId: "" }));
  };
  const newResearch = () => {
    history.invalidateSelection();
    research.reset();
    setNotice(null);
    setView("home");
  };
  const goNew = () => (runActive ? navigate("research") : newResearch());
  const retryRun = (kind: RetryKind) => {
    if (!snapshot) return;
    const providers = snapshot.research_controls.discovery_providers;
    const uses = (name: string) => providers.includes(name as never);
    const frozen: Settings = {
      ...settings,
      runId: kind === "resume" ? snapshot.run_id : "",
      dbPath: snapshot.db_path,
      supportEnabled: snapshot.supporting.status !== "disabled",
      challengeEnabled: snapshot.opposing.status !== "disabled",
      sourceTarget: (snapshot.research_controls.sources_per_stance_per_round ?? settings.sourceTarget) as Settings["sourceTarget"],
      maxCost: snapshot.cost_budget_limit_usd != null ? String(snapshot.cost_budget_limit_usd) : settings.maxCost,
      ...(providers.length
        ? {
            useSerpSearch: uses("serpsearch"),
            useExa: uses("exa"),
            useOpenAlex: uses("openalex"),
            useArxiv: uses("arxiv"),
            usePubmed: uses("pubmed"),
            useBrave: uses("brave"),
            useSerper: uses("serper"),
          }
        : {}),
    };
    history.invalidateSelection();
    research.setClaim(snapshot.raw_claim);
    void research.beginResearch(null, frozen, configuration, updateService, snapshot.raw_claim);
  };
  const navigate = (next: MainView) => {
    if (next !== "history") history.invalidateSelection();
    setView(next);
    setNotice(null);
  };
  const providerState = offline
    ? "offline"
    : configuration?.configured
      ? "ready"
      : configuration?.saved_credentials.length
        ? "saved"
        : "setup";
  const runActive = Boolean(
    activeRun && (!snapshot || !terminalStates.has(snapshot.classification)) && snapshot?.worker_active !== false,
  );
  // Tell the user when a run they are watching finishes. Polling runs on the
  // research view; the header indicator keeps the run reachable from elsewhere.
  const watched = useRef<{ runId: string; terminal: boolean } | null>(null);
  useEffect(() => {
    if (!snapshot) return;
    const terminal = terminalStates.has(snapshot.classification);
    const previous = watched.current;
    watched.current = { runId: snapshot.run_id, terminal };
    if (previous?.runId !== snapshot.run_id || previous.terminal || !terminal) return;
    const timer = window.setTimeout(() => {
      if (snapshot.classification === "released") notify("Research complete. The result is ready.", "success");
      else notify("Research stopped before completing. The page explains what was saved.", "warning");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [snapshot, notify]);
  const recovery = {
    connection: research.connection,
    lastConfirmedAt: research.lastConfirmedAt,
    cancellation: research.cancellation,
    onReconnect: research.reconnect,
    onHistory: () => navigate("history"),
    onCancel: research.cancel,
    canCancel: snapshot?.worker_active !== false,
  };

  return (
    <MotionConfig
      reducedMotion="user"
      transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
    >
      <main className="site-shell">
        <Header
          view={view === "research" && !activeRun ? "home" : view}
          setupNeeded={providerState !== "ready"}
          preferencesReady={preferencesReady}
          onNew={goNew}
          onHistory={() => navigate("history")}
          onSettings={() => setSettingsOpen("auto")}
          runActive={runActive}
          onRun={() => navigate("research")}
        />
        <AnimatePresence mode="wait">
          {preferencesStatus !== "ready" ? (
            <PreferencesStatus
              key="preferences"
              status={preferencesStatus}
              onRetry={() => void retryPreferences()}
            />
          ) : view === "history" ? (
            <HistoryView
              key="history"
              items={history.history}
              loading={history.loading}
              onOpen={history.openHistoryRun}
              onNew={newResearch}
            />
          ) : view === "home" || (!snapshot && !activeRun) ? (
            <HomeView
              key="home"
              firstRun={configuration ? !configuration.configured : false}
              recent={history.history}
              recentLoading={history.loading}
              onOpen={history.openHistoryRun}
              onHistory={() => navigate("history")}
              onSettings={() => setSettingsOpen("providers")}
              checklist={[
                { label: "Add a key for your model provider", done: Boolean(configuration?.saved_credentials.some((id) => id === "mimo" || id === "openai")) },
                { label: "Turn on at least one search provider with a key", done: Boolean(configuration?.configured) },
                { label: "Write a claim and begin", done: false },
              ]}
              composer={
                <ResearchView
                  settings={settings}
                  onSettings={updateSettings}
                  ready={Boolean(configuration?.configured && !offline)}
                  onSetup={() => setSettingsOpen("providers")}
                  claim={research.claim}
                  busy={research.busy}
                  onClaim={research.setClaim}
                  onSubmit={(event) => {
                    setView("research");
                    void research.beginResearch(event, settings, configuration, updateService);
                  }}
                />
              }
            />
          ) : snapshot ? (
            terminalStates.has(snapshot.classification) ? (
              <ResultView
                key={`result-${snapshot.db_path}-${snapshot.run_id}-${snapshot.classification}`}
                snapshot={snapshot}
                onNew={newResearch}
                onRetry={retryRun}
                notify={notify}
              />
            ) : (
              <ProgressView
                key={`progress-${snapshot.db_path}-${snapshot.run_id}`}
                snapshot={snapshot}
                startedAt={research.startedAt}
                {...recovery}
              />
            )
          ) : activeRun ? (
            <StartingView
              key="starting"
              claim={research.claim}
              reduceMotion={Boolean(reduceMotion)}
              {...recovery}
            />
          ) : null}
        </AnimatePresence>
        <AnimatePresence>
          {toast && (
            <Notice message={toast.message} tone={toast.tone} onClose={() => setToast(null)} />
          )}
          {preferencesReady && settingsOpen && (
            <AdvancedPanel
              key="settings"
              settings={settings}
              configuration={configuration}
              modelOptions={modelOptions}
              initialSection={settingsOpen === "auto" ? undefined : settingsOpen}
              active={Boolean(
                research.busy ||
                  (activeRun &&
                    (!snapshot || !terminalStates.has(snapshot.classification))),
              )}
              onSettings={updateSettings}
              onImportedDatabase={selectImportedDatabase}
              onClose={() => setSettingsOpen(null)}
              onService={changeService}
              onProvidersSaved={async (message) => {
                setNotice(message);
                await refreshConfiguration();
              }}
            />
          )}
        </AnimatePresence>
      </main>
    </MotionConfig>
  );
}
