import type { V2FinalResearchOutput, V2EvidenceDisplay } from "@/lib/api";
import { readableStage } from "../shared/presentation";

type EvidenceItem = V2EvidenceDisplay["items"][number];

function sourceHostLabel(sourceUrl: string): string {
  let host = "source page";
  try {
    host = new URL(sourceUrl).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return host;
  }
  const known: Record<string, string> = {
    "voiceofsandiego.org": "Voice of San Diego",
    "studydaddy.com": "StudyDaddy",
    "aclu.org": "ACLU",
    "linkedin.com": "LinkedIn",
    "x.com": "X",
    "twitter.com": "X",
  };
  if (known[host]) return known[host];
  const label = host.split(".")[0].replaceAll("-", " ");
  return label.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function evidenceReadLocation(item: EvidenceItem): string {
  return sourceHostLabel(item.source_url);
}

export function evidenceCitation(item: EvidenceItem): string {
  const authors = item.authors ?? [];
  const author = authors[0]
    ? `${authors[0]}${authors.length > 1 ? " et al." : ""}`
    : "Author not recorded";
  const year = item.publication_date?.match(/(?:18|19|20)\d{2}/)?.[0] ?? "Year not recorded";
  const venue = item.publication_venue || "Venue not recorded";
  return `${author} · ${year} · ${venue}`;
}

export function evidenceSourceType(item: EvidenceItem): string {
  const sourceType = (item.source_type ?? "").toLowerCase().replaceAll("_", " ");
  let hostname = "";
  try {
    hostname = new URL(item.source_url).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    // Keep the recorded source type when the URL is not a web address.
  }
  if (/(^|\.)flocksafety\.com$/.test(hostname)) return "Vendor blog";
  if (/(^|\.)(linkedin\.com|x\.com|twitter\.com)$/.test(hostname)) return "Social post";
  if (/op[ -]?ed|editorial|opinion/.test(sourceType)) return "Op-ed";
  if (/randomi[sz]ed/.test(sourceType)) return "Randomized trial";
  if (/peer.?review|journal|scholarly|research paper/.test(sourceType)) return "Research publication";
  if (/government summary/.test(sourceType)) return "Government summary";
  if (/advocacy group/.test(sourceType)) return "Advocacy group";
  if (/vendor|company blog/.test(sourceType)) return "Vendor source";
  if (!sourceType || sourceType === "general web") return "Source type not recorded";
  return readableStage(sourceType);
}

export function evidenceConflictNotice(item: EvidenceItem): string | null {
  let hostname = "";
  try {
    hostname = new URL(item.source_url).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return null;
  }
  return /(^|\.)flocksafety\.com$/.test(hostname)
    ? "Flock Safety publishes this source and has a commercial interest in ALPR products."
    : null;
}

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
  ) => {
    const displayTitle = sourceTitleById.get(sourceId)?.display_title;
    if (displayTitle && !displayTitle.startsWith("PDF file:")) return displayTitle;
    const evidenceItem = evidence?.items.find((item) => item.source_id === sourceId);
    if (evidenceItem) return evidenceCitation(evidenceItem);
    return capturedTitle && !/^S?\d{7,}[a-z0-9]*\s+\d+\.\.\d+/i.test(capturedTitle)
      ? capturedTitle
      : `Source page at ${sourceHostLabel(sourceUrl)}`;
  };
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
