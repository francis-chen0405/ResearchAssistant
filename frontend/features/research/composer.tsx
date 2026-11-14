import { motion } from "motion/react";
import type { FormEvent } from "react";
import { StatusPill } from "@/components/workspace";
import type { ModelOptions } from "@/lib/api";
import { ModelSelection } from "../preferences/model-selection";
import { type Settings, budgetOptions } from "../preferences/settings";
import { CancelRun, ResearchRecovery, type ResearchRecoveryProps } from "./connection";

export function ResearchView({
  claim,
  busy,
  settings,
  modelOptions,
  onSettings,
  ready,
  onSetup,
  onClaim,
  onSubmit,
}: {
  claim: string;
  busy: boolean;
  settings: Settings;
  modelOptions: ModelOptions;
  onSettings: (settings: Settings) => void;
  ready: boolean;
  onSetup: () => void;
  onClaim: (claim: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <motion.section
      className="composer-view"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className="page-heading">
        <h1>Start research</h1>
      </div>
      <form className="claim-composer" onSubmit={onSubmit}>
        <div className="composer-label">
          <label htmlFor="claim">Your research question</label>
          <StatusPill tone={ready ? "support" : "neutral"}>
            {ready ? "Providers configured" : "Setup needed"}
          </StatusPill>
        </div>
        <textarea
          id="claim"
          value={claim}
          onChange={(event) => onClaim(event.target.value)}
          placeholder="e.g. Can greener streets make cities cooler?"
          rows={3}
        />
        <div className="composer-options">
          <fieldset>
            <legend>Research direction</legend>
            <div className="direction-options">
              {[
                { label: "Support", support: true, challenge: false },
                { label: "Challenge", support: false, challenge: true },
                { label: "Both sides", support: true, challenge: true },
              ].map((item) => (
                <button
                  type="button"
                  key={item.label}
                  aria-pressed={
                    settings.supportEnabled === item.support &&
                    settings.challengeEnabled === item.challenge
                  }
                  onClick={() =>
                    onSettings({
                      ...settings,
                      supportEnabled: item.support,
                      challengeEnabled: item.challenge,
                    })
                  }
                >
                  {item.label}
                </button>
              ))}
            </div>
          </fieldset>
          <label>
            Model budget limit
            <select
              value={settings.maxCost}
              onChange={(event) =>
                onSettings({ ...settings, maxCost: event.target.value })
              }
            >
              {budgetOptions(settings.maxCost).map((value) => (
                <option key={value} value={value}>
                  ${Number(value).toFixed(2)}
                </option>
              ))}
            </select>
            <small>Search service charges are separate.</small>
          </label>
        </div>
        <ModelSelection
          idPrefix="stage-model"
          settings={settings}
          modelOptions={modelOptions}
          onSettings={onSettings}
          disabled={busy}
        />
        <div className="composer-footer">
          {ready ? (
            <button
              type="submit"
              className="primary-action"
              disabled={!claim.trim() || busy}
            >
              {busy ? "Starting…" : "Begin research"}{" "}
              <span aria-hidden="true">↗</span>
            </button>
          ) : (
            <button type="button" className="primary-action" onClick={onSetup}>
              Connect providers <span aria-hidden="true">↗</span>
            </button>
          )}
        </div>
      </form>
    </motion.section>
  );
}

export function StartingView({
  claim,
  reduceMotion,
  ...recovery
}: {
  claim: string;
  reduceMotion: boolean;
} & ResearchRecoveryProps) {
  return (
    <motion.section className="page progress-page starting-view" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <ResearchRecovery {...recovery} />
      <header className="progress-hero card">
        <div className="progress-hero-main">
          <p className="eyebrow row">
            <motion.span
              className="spinner"
              aria-hidden="true"
              animate={reduceMotion ? undefined : { rotate: 360 }}
              transition={{ duration: 1.2, repeat: Infinity, ease: "linear" }}
            />
            Starting your research
          </p>
          <h1>{claim}</h1>
          <p className="activity">Waiting for the first progress update. This usually takes a few seconds.</p>
        </div>
        <div className="progress-hero-side">
          <CancelRun cancellation={recovery.cancellation} onCancel={recovery.onCancel} canCancel={recovery.canCancel} />
        </div>
      </header>
    </motion.section>
  );
}
