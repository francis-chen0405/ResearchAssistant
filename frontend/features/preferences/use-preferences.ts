import { useEffect, useState } from "react";
import {
  DEFAULT_STAGE_MODELS,
  researchApi,
  type ModelOptions,
} from "@/lib/api";
import {
  defaultModelOptions,
  mergeStageModels,
  type Settings,
} from "./settings";

const defaultSettings: Settings = {
  modelProfile: "configurable-2026-09",
  stageModels: DEFAULT_STAGE_MODELS,
  dbPath: "",
  runId: "",
  maxTokens: 500_000,
  maxCost: "0.20",
  maxCalls: 160,
  supportEnabled: true,
  challengeEnabled: false,
  sourceTarget: 10,
  metadataDepth: 20,
  seedExpansionEnabled: true,
  scholarlySearchMode: "lexical",
  useSerpSearch: true,
  useExa: true,
  useOpenAlex: true,
  useArxiv: false,
  usePubmed: false,
  useCrossref: true,
};

export function usePreferences(notify: (message: string) => void) {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [modelOptions, setModelOptions] = useState<ModelOptions>({
    choices: defaultModelOptions,
    defaults: DEFAULT_STAGE_MODELS,
  });
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let disposed = false;
    researchApi
      .preferences()
      .then((saved) => {
        if (disposed) return;
        setSettings((current) => ({
          ...current,
          ...saved,
          modelProfile: "configurable-2026-09",
          stageModels: mergeStageModels(
            saved.stageModels,
            DEFAULT_STAGE_MODELS,
          ),
          dbPath: saved.dbPath || current.dbPath,
        }));
        setLoaded(true);
      })
      .catch(() => {
        if (!disposed)
          notify(
            "Saved settings could not be loaded. Reopen the app before changing preferences.",
          );
      });
    return () => {
      disposed = true;
    };
  }, [notify]);

  useEffect(() => {
    let disposed = false;
    researchApi
      .modelOptions()
      .then((options) => {
        if (disposed) return;
        setModelOptions(options);
        setSettings((current) => ({
          ...current,
          stageModels: mergeStageModels(current.stageModels, options.defaults),
        }));
      })
      .catch(() => {
        // Bundled defaults keep controls usable while the local API is offline.
      });
    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    if (!loaded) return;
    let disposed = false;
    const timer = window.setTimeout(() => {
      const { runId: _runId, ...preferences } = settings;
      void _runId;
      researchApi.savePreferences(preferences).catch(() => {
        if (!disposed)
          notify("Settings could not be saved. Check the local data folder.");
      });
    }, 400);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [loaded, settings, notify]);

  return { settings, setSettings, modelOptions };
}
