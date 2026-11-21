import { motion } from "motion/react";
import type { ReactNode } from "react";
import { Icon } from "@/components/icons";
import { Button, Skeleton } from "@/components/ui";
import type { MainView } from "../preferences/settings";

export function Header({
  view,
  setupNeeded,
  preferencesReady,
  onHome,
  onNew,
  onHistory,
  onSettings,
  runActive = false,
  onRun,
}: {
  onHome: () => void;
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
      <button className="wordmark" type="button" onClick={onHome} aria-label="ResearchAssistant, home">
        <span className="mark" aria-hidden="true">R</span>
        <span className="wordmark-text">ResearchAssistant</span>
      </button>
      <nav className="primary-nav" aria-label="Primary navigation">
        <button type="button" className="nav-link" aria-current={view === "research" ? "page" : undefined} onClick={onNew}>
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

/** Minimal home: one way in, to the research page. */
export function HomeView({ onResearch }: { onResearch: () => void }) {
  return (
    <motion.section className="page home" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <Button variant="primary" icon="search" className="home-cta" onClick={onResearch}>Research a Claim</Button>
    </motion.section>
  );
}

/** The research page: the claim composer on its own. */
export function ResearchPage({ composer }: { composer: ReactNode }) {
  return (
    <motion.section className="page research-page" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <header className="page-header">
        <h1>Check a claim against the evidence</h1>
        <p>Get sourced findings for and against a claim, with exact quotes you can check.</p>
      </header>
      {composer}
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
