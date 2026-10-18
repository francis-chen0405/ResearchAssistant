import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { researchApi } from "@/lib/api";

export function useHistoryImport(
  database: string,
  active: boolean,
  onImported: (database: string) => void,
) {
  const [importing, setImporting] = useState(false);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const owner = useRef({ id: 0, controller: null as AbortController | null });
  const inputs = useRef({ database, active, onImported });
  useLayoutEffect(() => {
    inputs.current = { database, active, onImported };
  }, [database, active, onImported]);
  useEffect(() => {
    const request = owner.current;
    return () => {
      request.id += 1;
      request.controller?.abort();
      request.controller = null;
    };
  }, []);

  const importDatabase = async () => {
    if (active || !database || owner.current.controller) return;
    const id = ++owner.current.id;
    const controller = new AbortController();
    owner.current.controller = controller;
    const isCurrent = () => id === owner.current.id && !controller.signal.aborted;
    setImporting(true);
    setImportMessage(null);
    try {
      const result = await researchApi.importHistory(database, controller.signal);
      if (!isCurrent()) return;
      const latest = inputs.current;
      if (latest.database === database && !latest.active) {
        latest.onImported(result.db_path);
        setImportMessage(
          `Imported ${result.run_count} saved runs into application data. The source database was preserved.`,
        );
      } else {
        setImportMessage(
          `Import completed at ${result.db_path}. Your current database selection was kept.`,
        );
      }
    } catch {
      if (isCurrent())
        setImportMessage(
          "Import failed. Enter an existing ResearchAssistant database path and ensure no research is running in it.",
        );
    } finally {
      if (isCurrent()) {
        owner.current.controller = null;
        setImporting(false);
      }
    }
  };
  return { importing, importMessage, importDatabase };
}
