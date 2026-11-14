import type { V2EvidenceDisplay, V2FinalResearchOutput } from "@/lib/api";
import { researchStopLabel } from "../shared/presentation";

// Read-only display projection of a released result. Nothing here changes the
// saved brief; statements and quotes are passed through exactly as stored.

export type EvidenceItem = V2EvidenceDisplay["items"][number];
export type SourceTitle = NonNullable<V2EvidenceDisplay["source_titles"]>[number];
export type Relationship = "supports" | "challenges" | "qualifies";
export type Strength = "Direct" | "Partial" | "Background";

export const relationshipOrder: Relationship[] = ["supports", "challenges", "qualifies"];
export const relationshipLabel: Record<Relationship, string> = {
  supports: "Supports",
  challenges: "Challenges",
  qualifies: "Adds context",
};
export const relationshipTone = {
  supports: "support",
  challenges: "challenge",
  qualifies: "context",
} as const;

/** Claim fit in words: 4–5 Direct, 3 Partial, 2 Background (admission requires at least 2). */
export function strengthLabel(claimFit: number | null | undefined): Strength | null {
  if (claimFit == null) return null;
  if (claimFit >= 4) return "Direct";
  if (claimFit === 3) return "Partial";
  return "Background";
}

const normalizedTitle = (title: string | null | undefined) => {
  const value = (title ?? "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "");
  return value.length >= 24 ? value : null;
};

class UnionFind {
  private parent = new Map<string, string>();
  find(id: string): string {
    if (!this.parent.has(id)) this.parent.set(id, id);
    const parent = this.parent.get(id) as string;
    if (parent === id) return id;
    const root = this.find(parent);
    this.parent.set(id, root);
    return root;
  }
  union(a: string, b: string) {
    const left = this.find(a);
    const right = this.find(b);
    if (left !== right) this.parent.set(right < left ? left : right, right < left ? right : left);
  }
}

export type PublicationGroups = {
  groupOf: (sourceId: string) => string;
  /** Why sources in a group were treated as one publication; null when a single source. */
  basisOf: (groupId: string) => "same publication" | "matching title" | null;
};

/**
 * Treat pages as one publication when they share a data family, a verified DOI or
 * canonical URL, a recorded lineage notice, or the same normalized title. This is
 * a display merge only; it makes counts smaller (more conservative), never larger.
 */
export function publicationGroups(
  evidence: Pick<V2EvidenceDisplay, "items"> & Partial<Pick<V2EvidenceDisplay, "study_lineage" | "source_titles">>,
): PublicationGroups {
  const union = new UnionFind();
  // Sources joined only by a title match; a group containing one is labelled as such.
  const titleLinked = new Set<string>();
  const firstBy = new Map<string, string>();
  const link = (key: string | null | undefined, sourceId: string, kind: "strong" | "title") => {
    if (!key) return;
    const existing = firstBy.get(key);
    if (!existing) {
      firstBy.set(key, sourceId);
      return;
    }
    if (union.find(existing) === union.find(sourceId)) return;
    union.union(existing, sourceId);
    if (kind === "title") titleLinked.add(sourceId);
  };
  const titles = new Map((evidence.source_titles ?? []).map((item) => [item.source_id, item]));
  for (const item of evidence.items) {
    union.find(item.source_id);
    link(`family:${item.source_family}`, item.source_id, "strong");
    const publication = item.verified_publication;
    if (publication?.doi) link(`doi:${publication.doi.toLowerCase()}`, item.source_id, "strong");
    if (publication?.canonical_url) link(`url:${publication.canonical_url}`, item.source_id, "strong");
  }
  for (const notice of evidence.study_lineage ?? []) {
    const [first, ...rest] = notice.source_ids;
    for (const other of rest) {
      if (union.find(first) === union.find(other)) continue;
      union.union(first, other);
      if (notice.basis === "matching_title") titleLinked.add(other);
    }
  }
  for (const item of evidence.items) {
    const heading = item.verified_publication?.title ?? titles.get(item.source_id)?.heading ?? item.title;
    const key = normalizedTitle(heading);
    link(key && `title:${key}`, item.source_id, "title");
  }
  const sizes = new Map<string, Set<string>>();
  for (const item of evidence.items) {
    const root = union.find(item.source_id);
    sizes.set(root, (sizes.get(root) ?? new Set()).add(item.source_id));
  }
  const titleRoots = new Set([...titleLinked].map((id) => union.find(id)));
  return {
    groupOf: (sourceId) => union.find(sourceId),
    basisOf: (groupId) => {
      const root = union.find(groupId);
      if ((sizes.get(root)?.size ?? 1) < 2) return null;
      return titleRoots.has(root) ? "matching title" : "same publication";
    },
  };
}

export type Finding = {
  /** The card's primary record; its statement and quote are shown verbatim. */
  item: EvidenceItem;
  relationship: Relationship;
  strength: Strength | null;
  groupId: string;
  /** Other records from the same publication with the same relationship. */
  related: EvidenceItem[];
  /** Other reading locations for the same publication. */
  alsoAt: { sourceId: string; url: string; name: string | null }[];
  mergeBasis: "same publication" | "matching title" | null;
};

const byStrength = (a: EvidenceItem, b: EvidenceItem) =>
  (b.claim_fit ?? 0) - (a.claim_fit ?? 0) ||
  Number(Boolean(b.verified_publication)) - Number(Boolean(a.verified_publication)) ||
  a.ledger_claim_id.localeCompare(b.ledger_claim_id);

export function findingsByRelationship(evidence: V2EvidenceDisplay | null): Record<Relationship, Finding[]> {
  const result: Record<Relationship, Finding[]> = { supports: [], challenges: [], qualifies: [] };
  if (!evidence) return result;
  const groups = publicationGroups(evidence);
  const titles = new Map((evidence.source_titles ?? []).map((item) => [item.source_id, item]));
  for (const relationship of relationshipOrder) {
    const buckets = new Map<string, EvidenceItem[]>();
    for (const item of evidence.items) {
      if (item.relationship_to_claim !== relationship) continue;
      const group = groups.groupOf(item.source_id);
      buckets.set(group, [...(buckets.get(group) ?? []), item]);
    }
    for (const [groupId, items] of buckets) {
      const [primary, ...rest] = [...items].sort(byStrength);
      const seenUrls = new Set([primary.source_url]);
      const alsoAt = rest
        .filter((item) => !seenUrls.has(item.source_url) && seenUrls.add(item.source_url))
        .map((item) => ({ sourceId: item.source_id, url: item.source_url, name: titles.get(item.source_id)?.source_name ?? null }));
      result[relationship].push({
        item: primary,
        relationship,
        strength: strengthLabel(primary.claim_fit),
        groupId,
        related: rest.filter((item) => item.approved_factual_statement.trim() !== primary.approved_factual_statement.trim()),
        alsoAt,
        mergeBasis: groups.basisOf(groupId),
      });
    }
    result[relationship].sort((a, b) => byStrength(a.item, b.item));
  }
  return result;
}

export type EvidencePicture = {
  label:
    | "Evidence mostly supports"
    | "Evidence mostly challenges"
    | "Evidence is mixed"
    | "Evidence is limited or indirect"
    | "No usable evidence found";
  tone: "support" | "challenge" | "context" | "neutral";
  scopeNote: string | null;
};

export type Directions = { support_enabled?: boolean; challenge_enabled?: boolean };

export function scopeLabel(directions: Directions): string {
  if (directions.support_enabled !== false && directions.challenge_enabled) return "Both sides";
  if (directions.challenge_enabled && directions.support_enabled === false) return "Challenging evidence only";
  return "Supporting evidence only";
}

/**
 * The fixed evidence-picture rules (docs/project/DECISIONS.md). Each publication
 * counts once; only Direct findings (claim fit 4+) can earn a "mostly" label.
 * The label describes the findings collected and never says a claim is true or false.
 */
export function evidencePicture(
  findings: Record<Relationship, Finding[]>,
  directions: Directions,
): EvidencePicture {
  const publications = (relationships: Relationship[], directOnly = false) =>
    new Set(
      relationships.flatMap((relationship) =>
        findings[relationship]
          .filter((finding) => !directOnly || finding.strength === "Direct")
          .map((finding) => finding.groupId),
      ),
    );
  const all = publications(relationshipOrder);
  const supportDirect = publications(["supports"], true).size;
  const challengeDirect = publications(["challenges"], true).size;
  const supportAll = publications(["supports"]).size;
  const challengeAll = publications(["challenges"]).size;
  const scopeNote =
    directions.support_enabled !== false && !directions.challenge_enabled
      ? "Only supporting evidence was searched for."
      : directions.challenge_enabled && directions.support_enabled === false
        ? "Only challenging evidence was searched for."
        : null;
  const mostly = (direct: number, otherDirect: number, side: number) =>
    direct >= 2 && direct >= 2 * otherDirect && side * 3 >= all.size * 2;
  if (all.size === 0) return { label: "No usable evidence found", tone: "neutral", scopeNote };
  if (mostly(supportDirect, challengeDirect, supportAll))
    return { label: "Evidence mostly supports", tone: "support", scopeNote };
  if (mostly(challengeDirect, supportDirect, challengeAll))
    return { label: "Evidence mostly challenges", tone: "challenge", scopeNote };
  if (supportDirect > 0 && challengeDirect > 0) return { label: "Evidence is mixed", tone: "context", scopeNote };
  return { label: "Evidence is limited or indirect", tone: "neutral", scopeNote };
}

export type Coverage = { level: "complete" | "partial" | "limited"; sentence: string };

export function coverageSummary(result: V2FinalResearchOutput, evidence: V2EvidenceDisplay | null): Coverage {
  const map = result.claim_coverage_map ?? [];
  const assessment = evidence?.post_analysis_assessment ?? result.post_analysis_assessment;
  const openQuestions = result.unresolved_material_gaps.length;
  const incompleteDimensions = map.filter((item) => !["covered", "not_applicable"].includes(item.coverage_state));
  const level: Coverage["level"] =
    !map.length || map.every((item) => ["missing", "unavailable"].includes(item.coverage_state))
      ? "limited"
      : incompleteDimensions.length || openQuestions || assessment?.coverage_incomplete
        ? "partial"
        : "complete";
  const what =
    level === "complete"
      ? "Coverage is complete for the parts of the claim that were assessed"
      : level === "partial"
        ? `Coverage is partial${openQuestions ? `, with ${openQuestions} open question${openQuestions === 1 ? "" : "s"}` : ""}`
        : map.length
          ? "Coverage is limited"
          : "Coverage is limited; it was not assessed for this run";
  return { level, sentence: `${what}. ${researchStopLabel(result.stopping.reason)}.` };
}

/**
 * What the research found: coverage summaries first (prose), then key findings
 * from a recorded reviewed opening, else the most direct finding in each group.
 */
export function foundSummary(result: V2FinalResearchOutput, evidence: V2EvidenceDisplay | null, findings: Record<Relationship, Finding[]>) {
  const paragraphs = [
    ...new Set(
      (result.claim_coverage_map ?? [])
        .filter((item) => item.kind !== "evidence_audit" && item.evidence_summary.trim())
        .map((item) => item.evidence_summary.trim()),
    ),
  ];
  const opening = evidence?.study_opening?.length
    ? evidence.study_opening.map((assertion) => assertion.ledger_claim_id)
    : evidence?.publication_opening?.flatMap((sentence) => sentence.ledger_claim_ids) ?? [];
  const openingItems = [...new Set(opening)]
    .map((id) => evidence?.items.find((item) => item.ledger_claim_id === id))
    .filter((item): item is EvidenceItem => Boolean(item));
  if (openingItems.length) return { paragraphs, items: openingItems, selection: "opening" as const };
  const top = relationshipOrder
    .map((relationship) => findings[relationship][0]?.item)
    .filter((item): item is EvidenceItem => Boolean(item));
  return { paragraphs, items: top, selection: "top" as const };
}

export function publicationCounts(findings: Record<Relationship, Finding[]>) {
  const distinct = new Set(relationshipOrder.flatMap((relationship) => findings[relationship].map((finding) => finding.groupId)));
  return {
    supports: findings.supports.length,
    challenges: findings.challenges.length,
    qualifies: findings.qualifies.length,
    publications: distinct.size,
  };
}
