import { useCallback, useLayoutEffect, useRef, useState, type FormEvent } from "react";
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

export type ProgressConnection = {
  state: "connecting" | "connected" | "retrying" | "paused";
  error: string | null;
  recovered: boolean;
};
export type Cancellation = {
  state: "idle" | "sending" | "requested" | "unconfirmed";
  message: string | null;
};
type ActiveRun = { id: string; database: string };
const POLL_INTERVAL_MS = 1_500;
const MAX_CONSECUTIVE_FAILURES = 3;

export function useResearch(
  notify: (message: string | null) => void,
  setOffline: (offline: boolean) => void,
  enabled = true,
) {
  const [claim, setClaim] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [snapshot, updateSnapshot] = useState<RunSnapshot | null>(null);
  const [received, setReceived] = useState<{ runId: string; at: number } | null>(null);
  const setSnapshot = useCallback((next: RunSnapshot | null) => {
    updateSnapshot(next);
    setReceived(next ? { runId: next.run_id, at: Date.now() } : null);
  }, []);
  const [activeRun, updateActiveRun] = useState<ActiveRun | null>(null);
  const [busy, setBusy] = useState(false);
  const activeRunIsTerminal = snapshot
    ? terminalStates.has(snapshot.classification)
    : false;

  const runKey = activeRun ? JSON.stringify([activeRun.id, activeRun.database]) : "";
  const [connectionState, setConnection] = useState<ProgressConnection & { key: string }>({
    key: "", state: "connecting", error: null, recovered: false,
  });
  const connection: ProgressConnection = connectionState.key === runKey
    ? connectionState
    : { state: "connecting", error: null, recovered: false };
  const lastConfirmedAt = received?.runId === activeRun?.id ? received?.at ?? null : null;
  const pollingSession = useRef({ key: "", failures: 0 });
  const reconnectAction = useRef<() => void>(() => {});
  const [cancellationState, setCancellation] = useState<Cancellation & { key: string }>({
    key: "", state: "idle", message: null,
  });
  const cancellation: Cancellation = cancellationState.key === runKey
    ? cancellationState : { state: "idle", message: null };
  const cancelRequest = useRef<AbortController | null>(null);
  const cancellationConfirmed = useRef("");
  const selectionEpoch = useRef(0);
  const setActiveRun = useCallback((next: ActiveRun | null) => {
    // An explicit selection starts a new UI cancellation lifecycle, even when
    // reopening the same saved run after a reset.
    selectionEpoch.current += 1;
    cancelRequest.current?.abort();
    cancelRequest.current = null;
    cancellationConfirmed.current = "";
    pollingSession.current = { key: "", failures: 0 };
    setConnection({ key: "", state: "connecting", error: null, recovered: false });
    setCancellation({ key: "", state: "idle", message: null });
    updateActiveRun(next);
  }, []);

  // Layout cleanup invalidates late responses before a changed selection paints.
  // Navigating away pauses reads, preserving the run and the retry budget.
  useLayoutEffect(() => {
    if (!activeRun || activeRunIsTerminal || !enabled) return;
    if (pollingSession.current.key !== runKey) {
      pollingSession.current = { key: runKey, failures: 0 };
    }
    const session = pollingSession.current;
    let disposed = false;
    let finished = false;
    let firstRead = true;
    let inFlight = false;
    let timer: number | undefined;
    let controller: AbortController | null = null;
    const poll = async (manual = false): Promise<void> => {
      if (disposed || finished || inFlight) return;
      if (timer !== undefined) window.clearTimeout(timer);
      if (manual) session.failures = 0;
      inFlight = true;
      controller = new AbortController();
      if (manual || firstRead) {
        setConnection({ key: runKey, state: "connecting", error: null, recovered: false });
      }
      firstRead = false;
      try {
        const result = await researchApi.snapshot(activeRun.id, activeRun.database, controller.signal);
        if (disposed) return;
        if (result.run_id !== activeRun.id) throw new Error("Progress belongs to another run.");
        const recovered = manual || session.failures > 0;
        session.failures = 0;
        setSnapshot(result);
        setOffline(false);
        setConnection(previous => ({
          key: runKey, state: "connected", error: null,
          recovered: recovered || (previous.key === runKey && previous.recovered),
        }));
        finished = terminalStates.has(result.classification);
      } catch (error) {
        if (disposed) return;
        session.failures += 1;
        setOffline(true);
        setConnection({
          key: runKey,
          state: session.failures >= MAX_CONSECUTIVE_FAILURES ? "paused" : "retrying",
          error: error instanceof Error ? error.message : "Progress is temporarily unavailable.",
          recovered: false,
        });
      } finally {
        inFlight = false;
        controller = null;
      }
      if (!disposed && !finished && session.failures < MAX_CONSECUTIVE_FAILURES) {
        timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
      }
    };
    reconnectAction.current = () => void poll(true);
    if (session.failures < MAX_CONSECUTIVE_FAILURES) {
      timer = window.setTimeout(() => void poll(), 0);
    }
    return () => {
      disposed = true;
      controller?.abort();
      if (timer !== undefined) window.clearTimeout(timer);
      reconnectAction.current = () => {};
    };
  }, [activeRun, activeRunIsTerminal, enabled, runKey, setOffline, setSnapshot]);

  useLayoutEffect(() => () => {
    selectionEpoch.current += 1;
    cancelRequest.current?.abort();
    cancelRequest.current = null;
  }, [runKey]);

  const reconnect = () => reconnectAction.current();

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
    if (!activeRun || !enabled || activeRunIsTerminal || snapshot?.worker_active === false
      || cancelRequest.current || cancellationConfirmed.current === runKey) return;
    const epoch = selectionEpoch.current;
    const controller = new AbortController();
    cancelRequest.current = controller;
    setCancellation({ key: runKey, state: "sending", message: "Sending cancellation request…" });
    try {
      const result = await researchApi.cancel(activeRun.id, activeRun.database, controller.signal);
      if (selectionEpoch.current !== epoch) return;
      if (result.cancelled) cancellationConfirmed.current = runKey;
      setCancellation({
        key: runKey,
        state: result.cancelled ? "requested" : "unconfirmed",
        message: result.cancelled
          ? "Cancellation requested. The worker may still be draining."
          : result.message,
      });
    } catch {
      if (selectionEpoch.current !== epoch) return;
      setCancellation({
        key: runKey, state: "unconfirmed",
        message: "Cancellation could not be confirmed. Check History before requesting it again.",
      });
    } finally {
      if (cancelRequest.current === controller) cancelRequest.current = null;
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
    connection,
    lastConfirmedAt,
    reconnect,
    cancellation,
    cancel,
    reset,
    clearTerminalOutsideDatabase,
  };
}
