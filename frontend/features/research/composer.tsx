import { motion } from "motion/react";
import type { FormEvent } from "react";
import {
  STAGE_MODEL_KEYS,
  type StageModelKey,
  type ModelChoiceId,
  type ModelOptions,
} from "@/lib/api";
import { StatusPill } from "@/components/workspace";
import { ResearchRecovery, type ResearchRecoveryProps } from "./connection";
import {
  type Settings,
  budgetOptions,
  providerRequirement,
  stageLabels,
} from "../preferences/settings";

export function ResearchView({
  claim,
  acknowledged,
  busy,
  settings,
  modelOptions,
  onSettings,
  ready,
  onSetup,
  onClaim,
  onAcknowledged,
  onSubmit,
}: {
  claim: string;
  acknowledged: boolean;
  busy: boolean;
  settings: Settings;
  modelOptions: ModelOptions;
  onSettings: (settings: Settings) => void;
  ready: boolean;
  onSetup: () => void;
  supportEnabled: boolean;
  challengeEnabled: boolean;
  reduceMotion: boolean;
  onClaim: (claim: string) => void;
  onAcknowledged: (acknowledged: boolean) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const updateStageModel = (stage: StageModelKey, choice: ModelChoiceId) =>
    onSettings({
      ...settings,
      stageModels: { ...settings.stageModels, [stage]: choice },
    });
  return (
    <motion.section
      className="composer-view"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className="page-heading">
        <p className="eyebrow">A fresh line of inquiry</p>
        <h1>What deserves a closer look?</h1>
        <p>Start with a public question or claim. We’ll follow the sources.</p>
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
            Model profile
            <select value={settings.modelProfile} disabled>
              <option value="configurable-2026-09">
                Configurable research
              </option>
            </select>
            <small>Choose each research role below.</small>
          </label>
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
        <section
          className="stage-model-settings"
          aria-labelledby="stage-model-heading"
        >
          <div>
            <p className="eyebrow">Model routing</p>
            <h2 id="stage-model-heading">
              Choose a model for each research role
            </h2>
            <p>{providerRequirement(settings.stageModels)}</p>
          </div>
          <div className="stage-model-grid">
            {STAGE_MODEL_KEYS.map((stage) => (
              <label key={stage} htmlFor={`stage-model-${stage}`}>
                {stageLabels[stage]}
                <select
                  id={`stage-model-${stage}`}
                  value={settings.stageModels[stage]}
                  onChange={(event) =>
                    updateStageModel(stage, event.target.value as ModelChoiceId)
                  }
                >
                  {modelOptions.choices.map((choice) => (
                    <option key={choice.id} value={choice.id}>
                      {choice.label}
                    </option>
                  ))}
                </select>
                <small>
                  {stage === "scout" || stage === "extractor"
                    ? "Default: Luna High"
                    : "Default: Luna XHigh"}
                </small>
              </label>
            ))}
          </div>
        </section>
        <label className="acknowledgement">
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(event) => onAcknowledged(event.target.checked)}
          />
          <span>
            This is public and non-sensitive, and I’ll review what comes back.
          </span>
        </label>
        <div className="composer-footer">
          <span>
            Exact passages. Visible limitations. Saved on this device.
          </span>
          {ready ? (
            <button
              type="submit"
              className="primary-action"
              disabled={!claim.trim() || !acknowledged || busy}
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
      <div className="composer-guide">
        <article>
          <b>01 / Ask</b>
          <p>Choose the direction and a model spending limit.</p>
        </article>
        <article>
          <b>02 / Examine</b>
          <p>Follow discovery, source checks and evidence analysis.</p>
        </article>
        <article>
          <b>03 / Understand</b>
          <p>Read the findings with quotations and their limitations.</p>
        </article>
      </div>
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
    <motion.section
      className="starting-view"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
    >
      <div className="orbital-loader" aria-hidden="true">
        <motion.i
          animate={reduceMotion ? undefined : { rotate: 360 }}
          transition={{ duration: 2.8, repeat: Infinity, ease: "linear" }}
        />
        <span>01</span>
      </div>
      <p className="eyebrow">Preparing the trail</p>
      <h2>{claim}</h2>
      <p>
        Waiting for confirmed progress from this run. The worker may already be running.
      </p>
      <ResearchRecovery {...recovery} />
    </motion.section>
  );
}
