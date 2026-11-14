import { motion } from "motion/react";
import { ProductPreview } from "@/components/workspace";
import { Icon } from "@/components/icons";
import type { MainView } from "../preferences/settings";

export function Header({
  view,
  providerState,
  preferencesReady,
  onView,
  onSetup,
  onAdvanced,
  runActive = false,
  onRun,
}: {
  runActive?: boolean;
  onRun?: () => void;
  view: MainView;
  providerState: "offline" | "ready" | "saved" | "setup";
  preferencesReady: boolean;
  onView: (view: MainView) => void;
  onSetup: () => void;
  onAdvanced: () => void;
}) {
  return (
    <header className="topbar">
      <button
        className="wordmark"
        type="button"
        onClick={() => onView("home")}
        aria-label="ResearchAssistant home"
      >
        <span className="mark" aria-hidden="true">
          R
        </span>
        <span>ResearchAssistant</span>
      </button>
      <nav aria-label="Primary navigation">
        {(["home", "research", "history"] as const).map((item) => (
          <button
            className={`nav-link ${view === item ? "active" : ""}`}
            type="button"
            onClick={() => onView(item)}
            key={item}
          >
            {item === "home"
              ? "Home"
              : item === "research"
                ? "Research"
                : "Saved research"}
            {view === item && (
              <motion.span className="nav-indicator" layoutId="nav-indicator" />
            )}
          </button>
        ))}
      </nav>
      <div className="header-actions">
        {runActive && (
          <button type="button" className="run-indicator" onClick={onRun}>
            <span className="pulse" aria-hidden="true" />
            Research running
          </button>
        )}
        <button className="advanced-link" type="button" disabled={!preferencesReady} onClick={onAdvanced}>
          Settings
        </button>
        <button className="setup-link" type="button" disabled={!preferencesReady} onClick={onSetup}>
          <span className={`status-dot ${providerState}`} aria-hidden="true" />
          {providerState === "ready"
            ? "Provider setup · ready"
            : providerState === "saved"
              ? "Provider setup incomplete"
              : providerState === "offline"
                ? "App connection unavailable"
                : "Provider setup"}
        </button>
      </div>
    </header>
  );
}

export function PreferencesStatus({
  status,
  onRetry,
}: {
  status: "loading" | "error";
  onRetry: () => void;
}) {
  return (
    <section className="composer-view page-heading" aria-busy={status === "loading"}>
      {status === "loading" ? (
        <p role="status">Loading your saved settings…</p>
      ) : (
        <>
          <p role="alert">Your saved settings could not be loaded. Retry to continue.</p>
          <button type="button" className="primary-action" onClick={onRetry}>
            Retry settings
          </button>
        </>
      )}
    </section>
  );
}

export function WelcomeView({
  ready,
  onStart,
  onSetup,
}: {
  ready: boolean;
  onStart: () => void;
  onSetup: () => void;
}) {
  return (
    <motion.section
      className="welcome-view"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className="welcome-hero">
        <h1>Research a claim</h1>
        <div className="welcome-actions">
          <button
            className="primary-action"
            onClick={ready ? onStart : onSetup}
          >
            {ready ? "Start research" : "Connect providers"}{" "}
            <span aria-hidden="true">↗</span>
          </button>
          {!ready && (
            <button className="text-action" onClick={onStart}>
              Explore the workspace <span aria-hidden="true">→</span>
            </button>
          )}
        </div>
      </div>
      <ProductPreview />
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
