import type { V2FinalResearchOutput, V2EvidenceDisplay } from "@/lib/api";

export function sourceTitles(
  result: V2FinalResearchOutput,
  evidence: V2EvidenceDisplay | null,
) {
  const sourceTitleById = new Map(
    (evidence?.source_titles ?? []).map((item) => [item.source_id, item]),
  );
  const sourceHeading = (
    sourceId: string,
    capturedTitle: string | null | undefined,
    sourceUrl: string,
  ) =>
    sourceTitleById.get(sourceId)?.display_title ?? capturedTitle ?? sourceUrl;
  const capturedTitleDisclosure = (
    sourceId: string,
    capturedTitle: string | null | undefined,
  ) => {
    const projected = sourceTitleById.get(sourceId);
    if (
      !projected ||
      !capturedTitle ||
      projected.display_title === capturedTitle
    )
      return null;
    return (
      <details className="source-provenance">
        <summary>Captured title and provenance</summary>
        <p>
          <span className="evidence-label">Original captured title</span>{" "}
          {capturedTitle}
        </p>
        <p>
          <span className="evidence-label">Source URL</span>{" "}
          {result.all_surviving_sources.find(
            (source) => source.source_id === sourceId,
          )?.source_url ?? "Recorded source"}
        </p>
      </details>
    );
  };
  return { sourceHeading, capturedTitleDisclosure };
}
