import { motion } from "motion/react";
import { ProductPreview, StatusPill } from "@/components/workspace";
import type { MainView } from "../preferences/settings";

export function Header({
  view,
  providerState,
  onView,
  onSetup,
  onAdvanced,
}: {
  view: MainView;
  providerState: "offline" | "ready" | "saved" | "setup";
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
        <button className="advanced-link" type="button" onClick={onAdvanced}>
          Settings
        </button>
        <button className="setup-link" type="button" onClick={onSetup}>
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
        <StatusPill tone={ready ? "support" : "neutral"}>
          {ready
            ? "Ready for your next question"
            : "Your next discovery starts here"}
        </StatusPill>
        <h1>
          Research a claim.
          <br />
          <span>See the whole picture.</span>
        </h1>
        <p>
          Go beyond the first answer. Explore evidence, examine the sources,
          <br className="desktop-break" /> and build a clearer view of what
          holds up.
        </p>
        <div className="welcome-actions">
          <button
            className="primary-action"
            onClick={ready ? onStart : onSetup}
          >
            {ready ? "Start research" : "Connect providers"}{" "}
            <span aria-hidden="true">↗</span>
          </button>
          <button className="text-action" onClick={onStart}>
            {ready ? "Write a question" : "Explore the workspace"}{" "}
            <span aria-hidden="true">→</span>
          </button>
        </div>
        <div className="welcome-promises">
          <span>↗ Traceable sources</span>
          <span>⊕ Support & challenge</span>
          <span>◷ Your budget, your control</span>
        </div>
      </div>
      <ProductPreview />
    </motion.section>
  );
}

export function Notice({
  message,
  onClose,
}: {
  message: string;
  onClose: () => void;
}) {
  return (
    <motion.div
      className="notice"
      role="status"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
    >
      <span>{message}</span>
      <button type="button" onClick={onClose} aria-label="Dismiss">
        ×
      </button>
    </motion.div>
  );
}
