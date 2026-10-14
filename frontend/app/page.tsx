"use client";

import { AnimatePresence, MotionConfig, useReducedMotion } from "motion/react";
import { useState } from "react";
import { ProviderSetup } from "@/components/provider-setup";
import { Header, Notice, WelcomeView } from "@/features/shell/views";
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

export default function Home() {
  const reduceMotion = useReducedMotion();
  const [view, setView] = useState<MainView>("home");
  const [setupOpen, setSetupOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const { settings, setSettings, modelOptions } = usePreferences(setNotice);
  const { configuration, refreshConfiguration, updateService, changeService } =
    useConfiguration(settings, setSettings, setOffline, setNotice);
  const research = useResearch(setNotice, setOffline);
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
  const newResearch = () => {
    history.invalidateSelection();
    research.reset();
    setNotice(null);
    setView("research");
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

  return (
    <MotionConfig
      reducedMotion="user"
      transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
    >
      <main className="site-shell">
        <Header
          view={view}
          providerState={providerState}
          onView={navigate}
          onSetup={() => setSetupOpen(true)}
          onAdvanced={() => setAdvancedOpen(true)}
        />
        <AnimatePresence mode="wait">
          {view === "home" ? (
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
              />
            ) : (
              <ProgressView
                key={`progress-${snapshot.run_id}`}
                snapshot={snapshot}
                onCancel={research.cancel}
              />
            )
          ) : activeRun ? (
            <StartingView
              key="starting"
              claim={research.claim}
              reduceMotion={Boolean(reduceMotion)}
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
              acknowledged={research.acknowledged}
              busy={research.busy}
              supportEnabled={settings.supportEnabled}
              challengeEnabled={settings.challengeEnabled}
              reduceMotion={Boolean(reduceMotion)}
              onClaim={research.setClaim}
              onAcknowledged={research.setAcknowledged}
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
          {notice && (
            <Notice message={notice} onClose={() => setNotice(null)} />
          )}
          {setupOpen && (
            <ProviderSetup
              key="provider-setup"
              configuration={configuration}
              selectedProviders={{
                use_serpsearch: settings.useSerpSearch,
                use_exa: settings.useExa,
                use_openalex: settings.useOpenAlex,
                use_arxiv: settings.useArxiv,
                use_pubmed: settings.usePubmed,
              }}
              stageModels={settings.stageModels}
              onClose={() => setSetupOpen(false)}
              onSaved={async (message) => {
                setNotice(message);
                await refreshConfiguration();
              }}
            />
          )}
          {advancedOpen && (
            <AdvancedPanel
              key="advanced"
              settings={settings}
              configuration={configuration}
              active={Boolean(
                activeRun &&
                  (!snapshot || !terminalStates.has(snapshot.classification)),
              )}
              onSettings={updateSettings}
              onClose={() => setAdvancedOpen(false)}
              onService={changeService}
            />
          )}
        </AnimatePresence>
      </main>
    </MotionConfig>
  );
}
