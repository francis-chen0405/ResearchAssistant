import {
  STAGE_MODEL_KEYS,
  type ModelChoiceId,
  type ModelOptions,
} from "@/lib/api";
import { type Settings, providerRequirement, stageLabels } from "./settings";

export function ModelSelection({
  settings,
  modelOptions,
  onSettings,
  disabled,
  idPrefix,
}: {
  settings: Settings;
  modelOptions: ModelOptions;
  onSettings: (settings: Settings) => void;
  disabled: boolean;
  idPrefix: string;
}) {
  return (
    <details className="settings-disclosure model-selection">
      <summary>Research models</summary>
      <p className="provider-options-note">
        {providerRequirement(settings.stageModels)}
      </p>
      {STAGE_MODEL_KEYS.map((stage) => (
        <label className="model-selection-row" key={stage}>
          <span>{stageLabels[stage]}</span>
          <select
            id={`${idPrefix}-${stage}`}
            disabled={disabled}
            value={settings.stageModels[stage]}
            onChange={(event) =>
              onSettings({
                ...settings,
                stageModels: {
                  ...settings.stageModels,
                  [stage]: event.target.value as ModelChoiceId,
                },
              })
            }
          >
            {modelOptions.choices.map((choice) => (
              <option key={choice.id} value={choice.id}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>
      ))}
    </details>
  );
}
