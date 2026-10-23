import { useCallback, useEffect, useRef, useState } from "react";
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
  sourceTarget: 20,
  metadataDepth: 50,
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
  const [preferencesStatus, setPreferencesStatus] = useState<
    "loading" | "ready" | "error"
  >("loading");
  const loadOwner = useRef({
    id: 0,
    controller: null as AbortController | null,
    ready: false,
  });

  const loadPreferences = useCallback(async () => {
    // Once hydrated, a late or accidental retry cannot replace deliberate edits.
    if (loadOwner.current.ready) return;
    loadOwner.current.controller?.abort();
    const id = ++loadOwner.current.id;
    const controller = new AbortController();
    loadOwner.current.controller = controller;
    const isCurrent = () =>
      id === loadOwner.current.id && !controller.signal.aborted;
    try {
      const saved = await researchApi.preferences(controller.signal);
      if (!isCurrent()) return;
      setSettings((current) => ({
        ...current,
        ...saved,
        modelProfile: "configurable-2026-09",
        stageModels: mergeStageModels(saved.stageModels, DEFAULT_STAGE_MODELS),
        dbPath: saved.dbPath || current.dbPath,
      }));
      loadOwner.current.ready = true;
      setPreferencesStatus("ready");
    } catch {
      if (isCurrent()) setPreferencesStatus("error");
    }
  }, []);

  const retryPreferences = useCallback(() => {
    if (loadOwner.current.ready) return Promise.resolve();
    setPreferencesStatus("loading");
    return loadPreferences();
  }, [loadPreferences]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadPreferences(), 0);
    const owner = loadOwner.current;
    return () => {
      window.clearTimeout(timer);
      owner.id += 1;
      owner.controller?.abort();
    };
  }, [loadPreferences]);

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
    if (preferencesStatus !== "ready") return;
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
  }, [preferencesStatus, settings, notify]);

  return { settings, setSettings, modelOptions, preferencesStatus, retryPreferences };
}
