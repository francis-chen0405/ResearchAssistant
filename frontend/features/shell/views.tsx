import { motion } from "motion/react";
import type { ReactNode } from "react";
import { ProductPreview } from "@/components/workspace";
import { Icon } from "@/components/icons";
import { Button, Skeleton } from "@/components/ui";
import type { HistoryItem } from "@/lib/api";
import type { MainView } from "../preferences/settings";
import { historyOutcome } from "../history/outcome";
import { formatShortDate } from "../shared/presentation";

export function Header({
  view,
  setupNeeded,
  preferencesReady,
  onNew,
  onHistory,
  onSettings,
  runActive = false,
  onRun,
}: {
  view: MainView;
  setupNeeded: boolean;
  preferencesReady: boolean;
  onNew: () => void;
  onHistory: () => void;
  onSettings: () => void;
  runActive?: boolean;
  onRun?: () => void;
}) {
  return (
    <header className="topbar">
      <button className="wordmark" type="button" onClick={onNew} aria-label="ResearchAssistant, new research">
        <span className="mark" aria-hidden="true">R</span>
        <span className="wordmark-text">ResearchAssistant</span>
      </button>
      <nav className="primary-nav" aria-label="Primary navigation">
        <button type="button" className="nav-link" aria-current={view === "home" ? "page" : undefined} onClick={onNew}>
          <Icon name="plus" /> New research
        </button>
        <button type="button" className="nav-link" aria-current={view === "history" ? "page" : undefined} onClick={onHistory}>
          <Icon name="history" /> History
        </button>
      </nav>
      <div className="header-actions">
        {runActive && (
          <button type="button" className="run-indicator" onClick={onRun}>
            <span className="pulse" aria-hidden="true" />
            Research running
          </button>
        )}
        <button
          type="button"
          className="nav-link"
          disabled={!preferencesReady}
          onClick={onSettings}
          aria-label={setupNeeded ? "Settings, setup needs attention" : "Settings"}
        >
          <Icon name="settings" /> Settings
          {setupNeeded && <span className="attention-dot" aria-hidden="true" />}
        </button>
      </div>
    </header>
  );
}

export function PreferencesStatus({ status, onRetry }: { status: "loading" | "error"; onRetry: () => void }) {
  return (
    <section className="page page-narrow" aria-busy={status === "loading"}>
      {status === "loading" ? (
        <div className="stack">
          <p role="status">Loading your saved settings…</p>
          <Skeleton lines={4} />
        </div>
      ) : (
        <div className="stack">
          <p role="alert">Your saved settings could not be loaded. Retry to continue.</p>
          <div><Button variant="primary" onClick={onRetry}>Retry settings</Button></div>
        </div>
      )}
    </section>
  );
}

const steps = [
  { title: "Search", text: "Searches the web and scholarly sources for evidence on both sides, as you choose." },
  { title: "Read and quote", text: "Reads the most promising sources and keeps exact quotes, checked against the source text." },
  { title: "Sum up", text: "Shows what the evidence says, what is still unknown and where every finding came from." },
];

export function HomeView({
  composer,
  firstRun,
  recent,
  recentLoading,
  onOpen,
  onHistory,
  onSettings,
  checklist,
}: {
  composer: ReactNode;
  firstRun: boolean;
  recent: HistoryItem[];
  recentLoading: boolean;
  onOpen: (item: HistoryItem) => void;
  onHistory: () => void;
  onSettings: () => void;
  checklist: { label: string; done: boolean }[];
}) {
  return (
    <motion.section
      className={`page home ${firstRun ? "home-first-run" : ""}`}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className="home-main">
        <header className="page-header">
          <h1>Check a claim against the evidence</h1>
          <p>Get sourced findings for and against a claim, with exact quotes you can check.</p>
        </header>
        {composer}
      </div>
      <aside className="home-side">
        {firstRun ? (
          <>
            <section className="card checklist" aria-labelledby="setup-heading">
              <h2 id="setup-heading">Get set up</h2>
              <ol>
                {checklist.map((item) => (
                  <li key={item.label} className={item.done ? "done" : ""}>
                    <span className="check-mark" aria-hidden="true">{item.done ? <Icon name="check" size={12} /> : null}</span>
                    <span>{item.label}</span>
                    <span className="sr-only">{item.done ? "(done)" : "(to do)"}</span>
                  </li>
                ))}
              </ol>
              <Button variant="secondary" icon="settings" onClick={onSettings}>Open Settings</Button>
            </section>
            <ProductPreview />
          </>
        ) : (
          <>
            <section aria-labelledby="recent-heading" className="recent">
              <div className="row">
                <h2 id="recent-heading">Recent research</h2>
                <span className="spacer" />
                <button type="button" className="link-button" onClick={onHistory}>All history</button>
              </div>
              {recentLoading && !recent.length ? (
                <Skeleton lines={3} />
              ) : recent.length ? (
                <ul className="recent-list">
                  {recent.slice(0, 4).map((item) => {
                    const outcome = historyOutcome(item.status);
                    return (
                      <li key={item.run_id}>
                        <button type="button" onClick={() => onOpen(item)}>
                          <span className="recent-claim">{item.raw_claim}</span>
                          <span className="subtle">{outcome.label} · {formatShortDate(item.updated_at)}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="muted">Your research will appear here.</p>
              )}
            </section>
            <section aria-labelledby="how-heading" className="how-it-works">
              <h2 id="how-heading">How it works</h2>
              <ol>
                {steps.map((step, index) => (
                  <li key={step.title}>
                    <span className="step-number" aria-hidden="true">{index + 1}</span>
                    <span><strong>{step.title}.</strong> {step.text}</span>
                  </li>
                ))}
              </ol>
            </section>
          </>
        )}
      </aside>
    </motion.section>
  );
}

export function Notice({
  message,
  tone = "info",
  onClose,
}: {
  message: string;
  tone?: "info" | "success" | "warning" | "error";
  onClose: () => void;
}) {
  return (
    <motion.div
      className={`toast toast-${tone}`}
      role={tone === "error" ? "alert" : "status"}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
    >
      <Icon name={tone === "success" ? "check" : tone === "info" ? "info" : "alert"} size={18} />
      <span>{message}</span>
      <button type="button" className="toast-close" onClick={onClose} aria-label="Dismiss">
        <Icon name="x" />
      </button>
    </motion.div>
  );
}
