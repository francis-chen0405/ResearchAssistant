import { useState } from "react";
import { Chip } from "@/components/ui";
import { Icon } from "@/components/icons";
import type { V2EvidenceDisplay } from "@/lib/api";
import { safeWebUrl } from "./source-leads";
import { completeQuote } from "./quote";
import {
  type Finding,
  type Relationship,
  type SourceTitle,
  relationshipLabel,
  relationshipOrder,
  relationshipTone,
} from "./model";

const groupHeading: Record<Relationship, string> = {
  supports: "Supports the claim",
  challenges: "Challenges the claim",
  qualifies: "Adds context",
};
const groupIntro: Record<Relationship, string> = {
  supports: "Findings that back part of the claim.",
  challenges: "Findings that cut against part of the claim. Challenging evidence is as useful as support.",
  qualifies: "Findings that limit, qualify or set the scene for the claim without backing or opposing it.",
};
const strengthHelp = {
  Direct: "Addresses the claim directly",
  Partial: "Addresses part of the claim",
  Background: "Related background",
} as const;

export const VISIBLE_PER_GROUP = 3;

export function sourceLine(title: SourceTitle | undefined, item: Finding["item"]): string {
  const parts = [
    title?.source_name,
    title?.lead_author,
    title?.year,
    title?.source_kind,
    title?.study_design,
  ].filter((part): part is string => Boolean(part));
  if (parts.length) return parts.join(" · ");
  try {
    return new URL(item.source_url).hostname.replace(/^www\./, "");
  } catch {
    return "Saved source";
  }
}

/** The exact stored passage; one that may be cut off is flagged, never trimmed or repaired. */
export function Passage({ passage }: { passage: string }) {
  const quote = completeQuote(passage);
  return quote ? (
    <figure className="quote">
      <blockquote>“{quote.text}”</blockquote>
      <figcaption>Exact passage from the source.</figcaption>
    </figure>
  ) : (
    <figure className="quote quote-partial">
      <figcaption>This saved passage may be cut off. Read it in context at the source.</figcaption>
      <blockquote>{passage}</blockquote>
    </figure>
  );
}

export function FindingCard({
  finding,
  titles,
}: {
  finding: Finding;
  titles: Map<string, SourceTitle>;
}) {
  const { item } = finding;
  const title = titles.get(item.source_id);
  const href = safeWebUrl(item.source_url);
  const publication = item.verified_publication;
  const publicationHref = publication ? safeWebUrl(publication.canonical_url) : null;
  return (
    <details
      className={`finding finding-${relationshipTone[finding.relationship]}`}
      id={`evidence-${item.ledger_claim_id}`}
      data-relationship={finding.relationship}
    >
      <summary>
        <span className="finding-head">
          <span className="finding-statement">{item.approved_factual_statement}</span>
          <span className="finding-meta">
            <span className="finding-source">{title?.heading ?? item.title ?? sourceLine(title, item)}</span>
            <span className="finding-source-line">{sourceLine(title, item)}</span>
          </span>
        </span>
        <span className="finding-chips">
          <Chip tone={relationshipTone[finding.relationship]}>{relationshipLabel[finding.relationship]}</Chip>
          {finding.strength && (
            <Chip tone="neutral">
              <span title={strengthHelp[finding.strength]}>{finding.strength}</span>
            </Chip>
          )}
          <Icon name="chevronDown" className="icon finding-chevron" />
        </span>
      </summary>
      <div className="finding-body">
        <Passage passage={item.quote_passage} />
        <div className="finding-section">
          <h4>Why it matters</h4>
          <p>{item.evidence_summary}</p>
        </div>
        {Boolean(item.limitations?.length) && (
          <div className="finding-section">
            <h4>Limitations</h4>
            <ul>{item.limitations?.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
          </div>
        )}
        {title?.publisher_interest && (
          <p className="finding-note"><Icon name="info" /> {title.publisher_interest}</p>
        )}
        {item.source_context_notice && (
          <p className="finding-note"><Icon name="info" /> {item.source_context_notice}</p>
        )}
        {finding.related.length > 0 && (
          <div className="finding-section">
            <h4>Also from this publication</h4>
            <ul className="related-records">
              {finding.related.map((related) => (
                <li key={related.ledger_claim_id} id={`evidence-${related.ledger_claim_id}`}>
                  <p>{related.approved_factual_statement}</p>
                  <Passage passage={related.quote_passage} />
                  {Boolean(related.limitations?.length) && (
                    <ul>{related.limitations?.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
                  )}
                  {related.source_context_notice && <p className="finding-note">{related.source_context_notice}</p>}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="finding-links">
          {href && (
            <a href={href} target="_blank" rel="noopener noreferrer" className="btn btn-secondary btn-sm">
              Open source <Icon name="external" />
            </a>
          )}
          {publication && publicationHref && (
            <a href={publicationHref} target="_blank" rel="noopener noreferrer">
              {publication.doi || "Canonical publication"}
            </a>
          )}
        </div>
        {finding.alsoAt.length > 0 && (
          <p className="subtle">
            Also available at{" "}
            {finding.alsoAt.map((location, index) => {
              const url = safeWebUrl(location.url);
              const label = location.name ?? (url ? new URL(url).hostname.replace(/^www\./, "") : "another location");
              return (
                <span key={location.sourceId}>
                  {index > 0 && ", "}
                  {url ? <a href={url} target="_blank" rel="noopener noreferrer">{label}</a> : label}
                </span>
              );
            })}
            .
          </p>
        )}
        {finding.mergeBasis && (finding.alsoAt.length > 0 || finding.related.length > 0) && (
          <p className="subtle">
            {finding.mergeBasis === "matching title"
              ? "Records grouped because the titles match; not independently confirmed as the same publication. They count once."
              : finding.mergeBasis === "matching study details"
              ? "Accounts grouped because sample counts and study details match; shared study identity is unconfirmed. They count once."
              : "These records come from the same publication and count once."}
          </p>
        )}
      </div>
    </details>
  );
}

export function EvidenceGroups({
  findings,
  evidence,
  expanded,
  onExpand,
}: {
  findings: Record<Relationship, Finding[]>;
  evidence: V2EvidenceDisplay | null;
  expanded: Set<Relationship>;
  onExpand: (relationship: Relationship) => void;
}) {
  const titles = new Map((evidence?.source_titles ?? []).map((item) => [item.source_id, item]));
  if (!evidence) {
    return <p className="muted">Detailed evidence could not be loaded. The saved brief is still available from Export.</p>;
  }
  const groups = relationshipOrder.filter((relationship) => findings[relationship].length > 0);
  if (!groups.length) return <p className="muted">No findings were collected for this claim.</p>;
  return (
    <div className="evidence-groups">
      {groups.map((relationship) => {
        const all = findings[relationship];
        const visible = expanded.has(relationship) ? all : all.slice(0, VISIBLE_PER_GROUP);
        return (
          <section key={relationship} className="evidence-group" aria-labelledby={`group-${relationship}`}>
            <header>
              <h3 id={`group-${relationship}`}>
                <span className={`group-mark mark-${relationshipTone[relationship]}`} aria-hidden="true" />
                {groupHeading[relationship]} <span className="count">{all.length}</span>
              </h3>
              <p className="subtle">{groupIntro[relationship]}</p>
            </header>
            <div className="finding-list">
              {visible.map((finding) => (
                <FindingCard key={finding.item.ledger_claim_id} finding={finding} titles={titles} />
              ))}
            </div>
            {all.length > visible.length && (
              <ShowAll count={all.length} onClick={() => onExpand(relationship)} />
            )}
          </section>
        );
      })}
    </div>
  );
}

function ShowAll({ count, onClick }: { count: number; onClick: () => void }) {
  const [pressed, setPressed] = useState(false);
  return (
    <button
      type="button"
      className="btn btn-ghost btn-sm show-all"
      aria-pressed={pressed}
      onClick={() => {
        setPressed(true);
        onClick();
      }}
    >
      Show all {count}
    </button>
  );
}
