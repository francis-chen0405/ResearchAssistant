import { useCallback, useEffect, useRef, useState } from "react";
import { researchApi, type HistoryItem, type RunSnapshot } from "@/lib/api";
import type { MainView } from "../preferences/settings";

type RunSelection = {
  setActiveRun: (run: { id: string; database: string } | null) => void;
  setSnapshot: (snapshot: RunSnapshot | null) => void;
  setBusy: (busy: boolean) => void;
};

export function useHistory(
  database: string,
  view: MainView,
  selection: RunSelection,
  setView: (view: MainView) => void,
  notify: (message: string | null) => void,
  setOffline: (offline: boolean) => void,
) {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const listRequestId = useRef(0);
  const selectionRequestId = useRef(0);
  const { setActiveRun, setSnapshot, setBusy } = selection;
  const invalidateSelection = () => {
    selectionRequestId.current += 1;
    setBusy(false);
  };
  const invalidateDatabase = () => {
    listRequestId.current += 1;
    invalidateSelection();
    setHistory([]);
    setLoading(false);
  };
  const refreshHistory = useCallback(async () => {
    if (!database) return;
    const id = ++listRequestId.current;
    setLoading(true);
    try {
      const result = await researchApi.history(database);
      if (id !== listRequestId.current) return;
      setHistory(result.items);
      setOffline(false);
    } catch (error) {
      if (id === listRequestId.current) {
        notify(
          error instanceof Error ? error.message : "History is not available.",
        );
        setOffline(true);
      }
    } finally {
      if (id === listRequestId.current) setLoading(false);
    }
  }, [database, notify, setOffline]);

  useEffect(() => {
    if (view !== "history") return;
    const timer = window.setTimeout(() => void refreshHistory(), 0);
    return () => window.clearTimeout(timer);
  }, [view, refreshHistory]);
  useEffect(
    () => () => {
      listRequestId.current += 1;
      selectionRequestId.current += 1;
    },
    [],
  );

  const openHistoryRun = async (item: HistoryItem) => {
    const id = ++selectionRequestId.current;
    const requestedDatabase = database;
    setActiveRun(null);
    setBusy(true);
    notify(null);
    try {
      const result = await researchApi.snapshot(item.run_id, requestedDatabase);
      if (id !== selectionRequestId.current) return;
      setSnapshot(result);
      setActiveRun({ id: item.run_id, database: requestedDatabase });
      setView("research");
    } catch (error) {
      if (id === selectionRequestId.current)
        notify(
          error instanceof Error
            ? error.message
            : "That research run could not be opened.",
        );
    } finally {
      if (id === selectionRequestId.current) setBusy(false);
    }
  };
  return {
    history,
    loading,
    openHistoryRun,
    invalidateDatabase,
    invalidateSelection,
  };
}
