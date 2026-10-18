import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  researchApi,
  type Configuration,
  type ServiceDiagnostic,
} from "@/lib/api";
import type { Settings } from "./settings";

export function useConfiguration(
  settings: Settings,
  setSettings: Dispatch<SetStateAction<Settings>>,
  setOffline: (offline: boolean) => void,
  notify: (message: string) => void,
) {
  const [configuration, setConfiguration] = useState<Configuration | null>(
    null,
  );
  const requestId = useRef(0);
  const selection = useMemo(() => ({
    stageModels: { ...settings.stageModels },
    providers: {
      use_serpsearch: settings.useSerpSearch,
      use_exa: settings.useExa,
      use_openalex: settings.useOpenAlex,
      use_arxiv: settings.useArxiv,
      use_pubmed: settings.usePubmed,
    },
  }), [settings.stageModels, settings.useSerpSearch, settings.useExa,
    settings.useOpenAlex, settings.useArxiv, settings.usePubmed]);
  const selectionKey = JSON.stringify(selection);
  const currentSelection = useRef({ selection, key: selectionKey });
  useLayoutEffect(() => {
    currentSelection.current = { selection, key: selectionKey };
  }, [selection, selectionKey]);
  const updateService = useCallback((service: ServiceDiagnostic) => {
    setConfiguration((current) =>
      current ? { ...current, service } : current,
    );
  }, []);
  const refreshConfiguration = useCallback(
    async (signal?: AbortSignal) => {
      const selected = currentSelection.current;
      const id = ++requestId.current;
      const isCurrent = () => id === requestId.current && !signal?.aborted &&
        selected.key === currentSelection.current.key;
      try {
        const result = await researchApi.configuration(
          selected.selection.stageModels,
          selected.selection.providers,
          signal,
        );
        if (!isCurrent()) return;
        setConfiguration(result);
        setOffline(false);
        setSettings((current) => ({
          ...current,
          dbPath: current.dbPath || result.default_db_path,
        }));
      } catch {
        if (isCurrent()) setOffline(true);
      }
    },
    [
      setSettings,
      setOffline,
    ],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(
      () => void refreshConfiguration(controller.signal),
      0,
    );
    return () => {
      controller.abort();
      requestId.current += 1;
      window.clearTimeout(timer);
    };
  }, [refreshConfiguration, selectionKey]);

  const changeService = async (action: "start" | "stop") => {
    try {
      const service =
        action === "start"
          ? await researchApi.startService()
          : await researchApi.stopService();
      updateService(service);
      notify(service.message);
    } catch (error) {
      notify(
        error instanceof Error
          ? error.message
          : "The service state could not change.",
      );
    }
  };
  return { configuration, refreshConfiguration, updateService, changeService };
}
