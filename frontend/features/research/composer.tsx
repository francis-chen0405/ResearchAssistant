import { motion } from "motion/react";
import type { FormEvent } from "react";
import { Button } from "@/components/ui";
import { Icon } from "@/components/icons";
import { type Settings, budgetOptions } from "../preferences/settings";
import { depthPresets, presetOf } from "./presets";
import { readableProvider } from "../shared/presentation";
import { CancelRun, ResearchRecovery, type ResearchRecoveryProps } from "./connection";

const directions = [
  { label: "Both sides", support: true, challenge: true, hint: "Look for evidence for and against the claim." },
  { label: "Support", support: true, challenge: false, hint: "Look only for evidence that backs the claim." },
  { label: "Challenge", support: false, challenge: true, hint: "Look only for evidence that cuts against it." },
];

export function enabledProviders(settings: Settings): string[] {
  return [
    ["serpsearch", settings.useSerpSearch],
    ["brave", settings.useBrave],
    ["serper", settings.useSerper],
    ["exa", settings.useExa],
    ["openalex", settings.useOpenAlex],
    ["arxiv", settings.useArxiv],
    ["pubmed", settings.usePubmed],
  ]
    .filter(([, on]) => on)
    .map(([id]) => readableProvider(id as string));
}

export function ResearchView({
  claim,
  busy,
  settings,
  onSettings,
  ready,
  onSetup,
  onClaim,
  onSubmit,
}: {
  claim: string;
  busy: boolean;
  settings: Settings;
  onSettings: (settings: Settings) => void;
  ready: boolean;
  onSetup: () => void;
  onClaim: (claim: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const trimmed = claim.trim();
  const preset = presetOf(settings);
  const direction = directions.find(
    (item) => item.support === settings.supportEnabled && item.challenge === settings.challengeEnabled,
  );
  const providers = enabledProviders(settings);
  const blocked = !ready ? "Set up providers to begin." : !trimmed ? "Enter a claim to begin." : busy ? "Starting…" : null;
  return (
    <form
      className="composer card"
      onSubmit={onSubmit}
      onKeyDown={(event) => {
        if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && ready && trimmed && !busy) {
          event.preventDefault();
          event.currentTarget.requestSubmit();
        }
      }}
    >
      <div className="field">
        <label htmlFor="claim" className="composer-label">What claim do you want to check?</label>
        <small className="field-hint" id="claim-hint">
          Write it as a statement. The app looks for sources, quotes them exactly and shows what the evidence says.
        </small>
        <textarea
          id="claim"
          value={claim}
          aria-describedby="claim-hint"
          onChange={(event) => onClaim(event.target.value)}
          placeholder="e.g. Urban tree cover lowers summer street temperatures."
          rows={3}
        />
        {trimmed.endsWith("?") && (
          <p className="composer-tip" role="note">
            <Icon name="info" /> Tip: claims work best as statements, for example &ldquo;{trimmed.slice(0, -1).replace(/^(does|do|is|are|can|will)\s+/i, "")}.&rdquo; You can still begin as written.
          </p>
        )}
      </div>

      <div className="composer-row">
      <fieldset className="composer-choice">
        <legend>Research direction</legend>
        <div className="segmented" role="group" aria-label="Research direction">
          {directions.map((item) => (
            <button
              type="button"
              key={item.label}
              aria-pressed={settings.supportEnabled === item.support && settings.challengeEnabled === item.challenge}
              onClick={() => onSettings({ ...settings, supportEnabled: item.support, challengeEnabled: item.challenge })}
            >
              {item.label}
            </button>
          ))}
        </div>
        <small className="field-hint">{direction?.hint}</small>
      </fieldset>
        <fieldset className="composer-choice">
          <legend>Depth</legend>
          <div className="segmented" role="group" aria-label="Depth">
            {depthPresets.map((item) => (
              <button
                type="button"
                key={item.id}
                aria-pressed={preset === item.id}
                onClick={() =>
                  onSettings({ ...settings, sourceTarget: item.sourceTarget, metadataDepth: item.metadataDepth, maxCost: item.maxCost })
                }
              >
                {item.id}
              </button>
            ))}
            {preset === "Custom" && <span className="segmented-note" aria-live="polite">Custom</span>}
          </div>
          <small className="field-hint">
            {depthPresets.find((item) => item.id === preset)?.hint ?? "Your own mix of sources, depth and spend cap."}
          </small>
        </fieldset>
        <div className="field spend-field">
          <label htmlFor="spend-cap">Spend cap</label>
          <div className="select">
            <select
              id="spend-cap"
              value={settings.maxCost}
              onChange={(event) => onSettings({ ...settings, maxCost: event.target.value })}
            >
              {budgetOptions(settings.maxCost).map((value) => (
                <option key={value} value={value}>${Number(value).toFixed(2)}</option>
              ))}
            </select>
            <Icon name="chevronDown" />
          </div>
          <small className="field-hint">Model spend only; search services bill separately.</small>
        </div>
      </div>

      <p className="run-summary">
        {providers.length ? `Searches ${providers.join(", ")}` : "No search provider selected"} · up to {settings.sourceTarget} sources per
        side per round · spend cap ${Number(settings.maxCost).toFixed(2)}
      </p>

      <div className="composer-footer">
        {blocked && !busy && <span className="subtle" id="begin-reason">{blocked}</span>}
        {ready ? (
          <Button type="submit" variant="primary" iconAfter="arrowRight" disabled={!trimmed || busy} aria-describedby={blocked ? "begin-reason" : undefined}>
            {busy ? "Starting…" : "Begin research"}
          </Button>
        ) : (
          <Button variant="primary" icon="key" onClick={onSetup}>Connect providers</Button>
        )}
        {ready && <kbd className="shortcut" aria-hidden="true">⌘/Ctrl + Enter</kbd>}
      </div>
    </form>
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
