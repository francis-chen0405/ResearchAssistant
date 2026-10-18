import { useEffect, useState, type FormEvent } from "react";
import {
  researchApi,
  type Configuration,
  type RunSnapshot,
  type ServiceDiagnostic,
} from "@/lib/api";
import type { Settings } from "../preferences/settings";
import {
  terminalStates,
  understandableConfigurationMessage,
} from "../shared/presentation";

export function useResearch(
  notify: (message: string | null) => void,
  setOffline: (offline: boolean) => void,
) {
  const [claim, setClaim] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [activeRun, setActiveRun] = useState<{
    id: string;
    database: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const activeRunIsTerminal = snapshot
    ? terminalStates.has(snapshot.classification)
    : false;

  useEffect(() => {
    if (!activeRun || activeRunIsTerminal) return;
    let disposed = false;
    let timer: number | undefined;
    const controller = new AbortController();
    const poll = async (): Promise<void> => {
      if (disposed) return;
      try {
        const result = await researchApi.snapshot(
          activeRun.id,
          activeRun.database,
          controller.signal,
        );
        if (disposed) return;
        setSnapshot(result);
        setOffline(false);
        if (terminalStates.has(result.classification)) return;
      } catch (error) {
        if (disposed || controller.signal.aborted) return;
        notify(
          error instanceof Error
            ? error.message
            : "Progress is temporarily unavailable.",
        );
      }
      if (!disposed) timer = window.setTimeout(() => void poll(), 1500);
    };
    void poll();
    return () => {
      disposed = true;
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [activeRun, activeRunIsTerminal, notify, setOffline]);

  const beginResearch = async (
    event: FormEvent<HTMLFormElement>,
    settings: Settings,
    configuration: Configuration | null,
    updateService: (service: ServiceDiagnostic) => void,
  ) => {
    event.preventDefault();
    const trimmedClaim = claim.trim();
    if (!trimmedClaim || !acknowledged) return;
    if (!configuration) {
      notify("The local API is not ready yet.");
      return;
    }
    setBusy(true);
    notify(null);
    try {
      if (!configuration.service.wigolo_ready) {
        const service = await researchApi.startService();
        if (!service.wigolo_ready)
          throw new Error(
            "Research tools could not start. Open Settings to retry.",
          );
        updateService(service);
      }
      const result = await researchApi.start({
        model_profile: settings.modelProfile,
        stage_models: settings.stageModels,
        raw_claim: trimmedClaim,
        acknowledged_public: acknowledged,
        db_path: settings.dbPath,
        run_id: settings.runId.trim() || null,
        max_tokens: settings.maxTokens,
        max_cost_usd: settings.maxCost,
        max_llm_calls: settings.maxCalls,
        support_enabled: settings.supportEnabled,
        challenge_enabled: settings.challengeEnabled,
        sources_per_stance_per_round: settings.sourceTarget,
        use_serpsearch: settings.useSerpSearch,
        use_exa: settings.useExa,
        use_openalex: settings.useOpenAlex,
        use_arxiv: settings.useArxiv,
        use_pubmed: settings.usePubmed,
        use_crossref: settings.useCrossref,
        metadata_depth: settings.metadataDepth,
        seed_expansion_enabled: settings.seedExpansionEnabled,
        scholarly_search_mode: settings.scholarlySearchMode,
      });
      notify(
        result.classification === "configuration_error"
          ? understandableConfigurationMessage(result.message)
          : result.message,
      );
      if (result.started) {
        setActiveRun({ id: result.run_id, database: settings.dbPath });
        setSnapshot(null);
      } else if (result.classification === "duplicate_active") {
        // A database conflict can refer to a different worker. Reconnect only
        // after the requested run's snapshot confirms ownership by this app.
        try {
          const current = await researchApi.snapshot(result.run_id, settings.dbPath);
          if (current.run_id === result.run_id && current.worker_active) {
            setSnapshot(current);
            setActiveRun({ id: current.run_id, database: current.db_path });
          }
        } catch {
          // Keep the original conflict diagnostic when this run does not exist.
        }
      }
    } catch (error) {
      notify(
        error instanceof Error ? error.message : "Research could not start.",
      );
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!activeRun) return;
    try {
      const result = await researchApi.cancel(activeRun.id, activeRun.database);
      notify(result.message);
    } catch (error) {
      notify(
        error instanceof Error
          ? error.message
          : "Cancellation could not be persisted.",
      );
    }
  };
  const reset = () => {
    setBusy(false);
    setActiveRun(null);
    setSnapshot(null);
    setClaim("");
    setAcknowledged(false);
  };
  const clearTerminalOutsideDatabase = (database: string) => {
    if (
      activeRun &&
      activeRun.database !== database &&
      snapshot &&
      terminalStates.has(snapshot.classification)
    ) {
      setActiveRun(null);
      setSnapshot(null);
    }
  };
  return {
    claim,
    setClaim,
    acknowledged,
    setAcknowledged,
    snapshot,
    setSnapshot,
    activeRun,
    setActiveRun,
    busy,
    setBusy,
    beginResearch,
    cancel,
    reset,
    clearTerminalOutsideDatabase,
  };
}
