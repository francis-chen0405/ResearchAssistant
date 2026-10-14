import { useEffect, useRef, useState } from "react";
import {
  researchApi,
  type ResearchTrailItem,
  type RunSnapshot,
  type SourceLead,
  type V2EvidenceDisplay,
  type V2FinalResearchOutput,
} from "@/lib/api";

// ResultView is keyed by database, run and classification. Each mount owns its
// result/trail requests; cleanup also protects against transports ignoring abort.
export function useResult(snapshot: RunSnapshot) {
  const [v2Result, setV2Result] = useState<V2FinalResearchOutput | null>(null);
  const [v2Evidence, setV2Evidence] = useState<V2EvidenceDisplay | null>(null);
  const [trailOpen, setTrailOpen] = useState(false);
  const [trail, setTrail] = useState<ResearchTrailItem[] | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);
  const [trailError, setTrailError] = useState<string | null>(null);
  const [sourceLeads, setSourceLeads] = useState<SourceLead[]>([]);
  const [sourceLeadsTotal, setSourceLeadsTotal] = useState(0);
  const [sourceLeadsNotice, setSourceLeadsNotice] = useState<string | null>(null);
  const [sourceLeadsLoading, setSourceLeadsLoading] = useState(true);
  const [sourceLeadsLoadingMore, setSourceLeadsLoadingMore] = useState(false);
  const [sourceLeadsError, setSourceLeadsError] = useState<string | null>(null);
  const [sourceLeadsHasMore, setSourceLeadsHasMore] = useState(false);
  const [sourceLeadsReload, setSourceLeadsReload] = useState(0);
  const nextSourceLeadsOffset = useRef(0);
  const sourceLeadsRequest = useRef<{
    controller: AbortController;
    id: number;
  } | null>(null);
  const sourceLeadsMorePending = useRef(false);
  const trailRequest = useRef<{
    controller: AbortController;
    id: number;
  } | null>(null);

  const openTrail = async () => {
    setTrailOpen(true);
    if (trail !== null) return;
    trailRequest.current?.controller.abort();
    const request = {
      controller: new AbortController(),
      id: (trailRequest.current?.id ?? 0) + 1,
    };
    trailRequest.current = request;
    try {
      const result = await researchApi.trail(
        snapshot.run_id,
        snapshot.db_path,
        request.controller.signal,
      );
      if (trailRequest.current !== request || request.controller.signal.aborted)
        return;
      setTrail(result.items);
    } catch (error) {
      if (trailRequest.current !== request || request.controller.signal.aborted)
        return;
      setTrailError(
        error instanceof Error
          ? error.message
          : "The research trail could not be opened.",
      );
    }
  };

  useEffect(() => {
    let disposed = false;
    const controller = new AbortController();
    nextSourceLeadsOffset.current = 0;
    const sourceRequest = {
      controller,
      id: (sourceLeadsRequest.current?.id ?? 0) + 1,
    };
    sourceLeadsRequest.current = sourceRequest;
    void researchApi
      .sourceLeads(snapshot.run_id, snapshot.db_path, 0, 50, controller.signal)
      .then((result) => {
        if (
          disposed ||
          sourceLeadsRequest.current !== sourceRequest ||
          controller.signal.aborted
        )
          return;
        const seen = new Set<string>();
        const uniqueItems = result.items.filter((item) => {
          if (seen.has(item.lead_id)) return false;
          seen.add(item.lead_id);
          return true;
        });
        setSourceLeads(uniqueItems);
        setSourceLeadsTotal(result.total);
        setSourceLeadsNotice(result.notice);
        setSourceLeadsHasMore(result.has_more);
        nextSourceLeadsOffset.current = result.offset + result.items.length;
      })
      .catch((error: unknown) => {
        if (
          disposed ||
          sourceLeadsRequest.current !== sourceRequest ||
          controller.signal.aborted
        )
          return;
        setSourceLeadsError(
          error instanceof Error
            ? error.message
            : "Discovered source leads could not be loaded.",
        );
      })
      .finally(() => {
        if (!disposed && sourceLeadsRequest.current === sourceRequest)
          setSourceLeadsLoading(false);
      });
    if (snapshot.classification === "released") {
      void researchApi
        .v2Result(snapshot.run_id, snapshot.db_path, controller.signal)
        .then(async (result) => {
          if (disposed || !result.release_validation.valid) return;
          setV2Result(result);
          try {
            const evidence = await researchApi.v2Evidence(
              snapshot.run_id,
              snapshot.db_path,
              controller.signal,
            );
            if (!disposed) setV2Evidence(evidence);
          } catch {
            if (!disposed) {
              setV2Evidence(null);
              setResultError(
                "Detailed evidence could not be loaded. The validated brief remains available.",
              );
            }
          }
        })
        .catch(() => {
          if (!disposed) setV2Result(null);
        });
    }
    return () => {
      disposed = true;
      controller.abort();
      sourceLeadsRequest.current?.controller.abort();
      sourceLeadsRequest.current = null;
      sourceLeadsMorePending.current = false;
      trailRequest.current?.controller.abort();
    };
  }, [
    snapshot.classification,
    snapshot.db_path,
    snapshot.run_id,
    sourceLeadsReload,
  ]);

  const retrySourceLeads = () => {
    if (sourceLeadsLoading || sourceLeadsLoadingMore) return;
    setSourceLeads([]);
    setSourceLeadsTotal(0);
    setSourceLeadsNotice(null);
    setSourceLeadsError(null);
    setSourceLeadsLoading(true);
    setSourceLeadsHasMore(false);
    nextSourceLeadsOffset.current = 0;
    setSourceLeadsReload((current) => current + 1);
  };

  const loadMoreSourceLeads = async () => {
    if (
      sourceLeadsMorePending.current ||
      !sourceLeadsHasMore ||
      sourceLeadsLoading
    )
      return;
    sourceLeadsMorePending.current = true;
    setSourceLeadsLoadingMore(true);
    setSourceLeadsError(null);
    const controller = new AbortController();
    const request = {
      controller,
      id: (sourceLeadsRequest.current?.id ?? 0) + 1,
    };
    sourceLeadsRequest.current = request;
    try {
      const result = await researchApi.sourceLeads(
        snapshot.run_id,
        snapshot.db_path,
        nextSourceLeadsOffset.current,
        50,
        controller.signal,
      );
      if (sourceLeadsRequest.current !== request || controller.signal.aborted)
        return;
      setSourceLeads((previous) => {
        const seen = new Set(previous.map((item) => item.lead_id));
        const appended = result.items.filter((item) => {
          if (seen.has(item.lead_id)) return false;
          seen.add(item.lead_id);
          return true;
        });
        return [...previous, ...appended];
      });
      setSourceLeadsNotice(result.notice);
      setSourceLeadsTotal(result.total);
      setSourceLeadsHasMore(result.has_more);
      nextSourceLeadsOffset.current = result.offset + result.items.length;
    } catch (error) {
      if (sourceLeadsRequest.current !== request || controller.signal.aborted)
        return;
      setSourceLeadsError(
        error instanceof Error
          ? error.message
          : "More source leads could not be loaded.",
      );
    } finally {
      if (sourceLeadsRequest.current === request) {
        sourceLeadsMorePending.current = false;
        sourceLeadsRequest.current = null;
        setSourceLeadsLoadingMore(false);
      }
    }
  };
  return {
    v2Result,
    v2Evidence,
    trailOpen,
    setTrailOpen,
    trail,
    resultError,
    setResultError,
    trailError,
    openTrail,
    sourceLeads,
    sourceLeadsTotal,
    sourceLeadsNotice,
    sourceLeadsLoading,
    sourceLeadsLoadingMore,
    sourceLeadsError,
    sourceLeadsHasMore,
    loadMoreSourceLeads,
    retrySourceLeads,
  };
}
