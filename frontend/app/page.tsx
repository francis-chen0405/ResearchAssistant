"use client";

import { AnimatePresence, MotionConfig, useReducedMotion } from "motion/react";
import { useCallback, useState } from "react";
import { ProviderSetup } from "@/components/provider-setup";
import { Header, Notice, PreferencesStatus, WelcomeView } from "@/features/shell/views";
import { ResearchView, StartingView } from "@/features/research/composer";
import { ProgressView } from "@/features/research/progress";
import { ResultView } from "@/features/results/result";
import { HistoryView } from "@/features/history/history";
import { AdvancedPanel } from "@/features/preferences/panel";
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
  const [setupOpen, setSetupOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
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
    setView("research");
  };
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
          view={view}
          providerState={providerState}
          preferencesReady={preferencesReady}
          onView={navigate}
          onSetup={() => setSetupOpen(true)}
          onAdvanced={() => setAdvancedOpen(true)}
        />
        <AnimatePresence mode="wait">
          {preferencesStatus !== "ready" ? (
            <PreferencesStatus
              key="preferences"
              status={preferencesStatus}
              onRetry={() => void retryPreferences()}
            />
          ) : view === "home" ? (
            <WelcomeView
              key="home"
              ready={Boolean(configuration?.configured)}
              onStart={() => setView("research")}
              onSetup={() => setSetupOpen(true)}
            />
          ) : view === "history" ? (
            <HistoryView
              key="history"
              items={history.history}
              loading={history.loading}
              onOpen={history.openHistoryRun}
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
          ) : (
            <ResearchView
              key="new"
              settings={settings}
              modelOptions={modelOptions}
              onSettings={updateSettings}
              ready={Boolean(configuration?.configured && !offline)}
              onSetup={() => setSetupOpen(true)}
              claim={research.claim}
              busy={research.busy}
              onClaim={research.setClaim}
              onSubmit={(event) =>
                research.beginResearch(
                  event,
                  settings,
                  configuration,
                  updateService,
                )
              }
            />
          )}
        </AnimatePresence>
        <AnimatePresence>
          {toast && (
            <Notice message={toast.message} tone={toast.tone} onClose={() => setToast(null)} />
          )}
          {preferencesReady && setupOpen && (
            <ProviderSetup
              key="provider-setup"
              configuration={configuration}
              selectedProviders={{
                use_serpsearch: settings.useSerpSearch,
                use_exa: settings.useExa,
                use_openalex: settings.useOpenAlex,
                use_arxiv: settings.useArxiv,
                use_pubmed: settings.usePubmed,
                use_brave: settings.useBrave,
                use_serper: settings.useSerper,
              }}
              stageModels={settings.stageModels}
              onClose={() => setSetupOpen(false)}
              onSaved={async (message) => {
                setNotice(message);
                await refreshConfiguration();
              }}
            />
          )}
          {preferencesReady && advancedOpen && (
            <AdvancedPanel
              key="advanced"
              settings={settings}
              configuration={configuration}
              active={Boolean(
                research.busy ||
                  (activeRun &&
                    (!snapshot || !terminalStates.has(snapshot.classification))),
              )}
              onSettings={updateSettings}
              onImportedDatabase={selectImportedDatabase}
              onClose={() => setAdvancedOpen(false)}
              onService={changeService}
            />
          )}
        </AnimatePresence>
      </main>
    </MotionConfig>
  );
}
