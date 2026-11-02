import type { V2EvidenceDisplay, V2FinalResearchOutput } from "@/lib/api";
import type { ReactNode } from "react";
import { StatusPill } from "@/components/workspace";
import {
  assessmentRelationshipLabel,
  readableStage,
} from "../shared/presentation";
import {
  evidenceCitation,
  evidenceConflictNotice,
  evidenceReadLocation,
  evidenceSourceType,
  evidenceStudyDesign,
} from "./source-titles";

function completeSentencePrefix(text: string): { text: string; omittedTail: boolean } {
  const sentences = typeof Intl.Segmenter === "function"
    ? [...new Intl.Segmenter(undefined, { granularity: "sentence" }).segment(text)].map(
        (part) => part.segment.trim(),
      )
    : (() => {
        const parts = text.split(/([.!?]["'”’)}\]]*\s+)/u);
        const fallback: string[] = [];
        for (let index = 0; index < parts.length; index += 2) {
          fallback.push(`${parts[index] ?? ""}${parts[index + 1] ?? ""}`.trim());
        }
        return fallback;
      })();
  const complete: string[] = [];
  for (const sentence of sentences) {
    if (/[.!?]["'”’)}\]]*$/u.test(sentence)) {
      complete.push(sentence);
    } else if (sentence) {
      return { text: complete.join(" "), omittedTail: true };
    }
  }
  return { text: complete.join(" "), omittedTail: complete.length !== sentences.length };
}

export function completeQuote(passage: string): { text: string; omittedTail: boolean } | null {
  const match = passage.match(/^\[[\s\S]*?\]\s+"([\s\S]+)"\s+\[[\s\S]*\]$/);
  const quotedText = (match?.[1] ?? passage).trim();
  const sourceSegments = quotedText.split(/\s+\.\.\.\s+/);
  const completeSegments: string[] = [];
  let omittedTail = false;
  for (const segment of sourceSegments) {
    const complete = completeSentencePrefix(segment);
    if (complete.text) completeSegments.push(complete.text);
    if (complete.omittedTail) {
      omittedTail = true;
      break;
    }
  }
  // A trailing fragment can contain a qualification to the preceding sentence.
  // Do not silently discard it and present the remainder as a complete quote.
  if (!completeSegments.length || omittedTail || completeSegments.length !== sourceSegments.length) return null;
  return {
    // Preserve the admitted text, including its original omission markers and spacing.
    text: quotedText,
    omittedTail: false,
  };
}

export function AdmittedEvidence({
  evidence,
  assessment,
  sourceHeading,
  capturedTitleDisclosure,
  showDirection,
}: {
  evidence: V2EvidenceDisplay | null;
  assessment: V2FinalResearchOutput["post_analysis_assessment"];
  sourceHeading: (
    sourceId: string,
    title: string | null | undefined,
    url: string,
  ) => string;
  capturedTitleDisclosure: (
    sourceId: string,
    title: string | null | undefined,
  ) => ReactNode;
  showDirection: boolean;
}) {
  return (
    <section>
      <h2>Admitted evidence</h2>
      <p>
        Only admitted evidence appears here. Each statement links to its
        analyzed passage and source. Analyzer-admitted evidence has not been
        independently Reviewer-approved. Publication metadata is recorded from
        discovery; Crossref verification is identified when available.
      </p>
      {assessment?.qualifying_count ? (
        <aside className="result-limitation">
          <h3>Context and evidence qualifications</h3>
          <p>
            Qualifications can include adjacent context. They are not supporting
            findings by themselves; each item’s proposition and recorded
            limitations show what it covers.
          </p>
        </aside>
      ) : null}
      {evidence?.items.length ? (
        <>
          <p>
            {evidence.items.length} admitted evidence item
            {evidence.items.length === 1 ? "" : "s"}.
          </p>
          <div className="evidence-list">
            {evidence.items.map((item) => (
              <details
                className={`evidence-card ${item.direction}`}
                id={`evidence-${item.ledger_claim_id}`}
                key={item.ledger_claim_id}
              >
                <summary>
                  <span className="evidence-card-summary">
                    {showDirection && (
                      <StatusPill
                        tone={
                          item.direction === "support"
                            ? "support"
                            : item.direction === "challenge"
                              ? "challenge"
                              : "neutral"
                        }
                      >
                        {item.direction === "support"
                          ? "Support-directed"
                          : "Challenge-directed"}
                      </StatusPill>
                    )}
                    <StatusPill tone="neutral">
                      {assessmentRelationshipLabel(item.relationship_to_claim)}
                    </StatusPill>
                    <span className="evidence-card-title">
                      {item.approved_factual_statement}
                    </span>
                    <small className="evidence-card-source">
                      {sourceHeading(
                        item.source_id,
                        item.title,
                        item.source_url,
                      )}
                    </small>
                    <small className="evidence-card-source">
                      {evidenceCitation(item)} · {evidenceSourceType(item)} · {evidenceStudyDesign(item)}
                    </small>
                    {evidenceConflictNotice(item) && (
                      <small className="evidence-card-source">
                        Potential conflict of interest
                      </small>
                    )}
                    {item.source_context_notice && (
                      <small className="evidence-card-source">
                        Legal scope has not been independently verified
                      </small>
                    )}
                  </span>
                  <span className="evidence-toggle" aria-hidden="true" />
                </summary>
                <div className="evidence-card-body">
                  <details><summary>Technical evidence identifier</summary><code>{item.ledger_claim_id}</code></details>
                  <p>
                    <span className="evidence-label">
                      Assessment relationship
                    </span>{" "}
                    {assessmentRelationshipLabel(item.relationship_to_claim)}
                  </p>
                  {item.claim_fit !== undefined && item.claim_fit !== null && (
                    <p>
                      <span className="evidence-label">Claim Fit</span>{" "}
                      {item.claim_fit}/5
                    </p>
                  )}
                  {item.relationship_to_claim === "qualifies" &&
                    item.claim_fit === 2 && (
                      <StatusPill tone="neutral">Limited relevance</StatusPill>
                    )}
                  <p>
                    <span className="evidence-label">Analyzed proposition</span>{" "}
                    {item.supporting_proposition}
                  </p>
                  {(() => {
                    const quote = completeQuote(item.quote_passage);
                    return quote ? (
                      <div>
                        <p>Recorded excerpt; sentence completeness and surrounding context should be checked in the source.</p>
                        <blockquote>“{quote.text}”{quote.omittedTail ? " […]" : ""}</blockquote>
                      </div>
                    ) : (
                      <div className="result-limitation">
                        <p>The recorded passage may be incomplete. Open the source page to read the passage in context.</p>
                        <details><summary>Recorded passage and context</summary><p>{item.quote_passage}</p></details>
                      </div>
                    );
                  })()}
                  <p>
                    <span className="evidence-label">{item.verified_publication ? (item.verified_publication.verification === "crossref_doi" ? "Crossref-verified DOI metadata" : "Reviewed authoritative publication metadata") : "Recorded publication metadata (not independently verified)"}</span>{" "}
                    {evidenceCitation(item)}. {sourceHeading(item.source_id, item.title, item.source_url)}.
                  </p>
                  {item.verified_publication && (
                    <p><span className="evidence-label">Original publication</span>{" "}
                      <a href={item.verified_publication.canonical_url} target="_blank" rel="noreferrer">{item.verified_publication.doi || "Canonical publication"}</a>
                      {" "}Verification basis: {item.verified_publication.verification === "crossref_doi" ? "Crossref DOI lookup" : "reviewed identifier in authoritative capture"}. The reading location is listed separately.
                    </p>
                  )}
                  {item.doi && !item.verified_publication && (
                    <p>
                      <span className="evidence-label">Recorded DOI (not independently verified)</span>{" "}
                      <a
                        href={`https://doi.org/${item.doi.replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "")}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        DOI {item.doi.replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "")}
                      </a>
                    </p>
                  )}
                  <p>
                    <span className="evidence-label">Read at</span>{" "}
                    {evidenceReadLocation(item)}
                  </p>
                  <p>
                    <span className="evidence-label">Source</span>{" "}
                    <a href={item.source_url} target="_blank" rel="noreferrer">
                      {sourceHeading(
                        item.source_id,
                        item.title,
                        item.source_url,
                      )}
                    </a>
                  </p>
                  {capturedTitleDisclosure(item.source_id, item.title)}
                  {item.source_type && (
                    <p>
                      <span className="evidence-label">Source type</span>{" "}
                      {evidenceSourceType(item)}
                    </p>
                  )}
                  <p><span className="evidence-label">Study design</span> {evidenceStudyDesign(item)}</p>
                  {!evidenceConflictNotice(item) && <p><span className="evidence-label">Publisher interest</span> Not established from the recorded metadata.</p>}
                  {evidenceConflictNotice(item) && (
                    <p className="result-limitation">
                      <span className="evidence-label">Conflict of interest</span>{" "}
                      {evidenceConflictNotice(item)}
                    </p>
                  )}
                  {item.source_context_notice && (
                    <p className="result-limitation">
                      <span className="evidence-label">Source context</span>{" "}
                      {item.source_context_notice}
                    </p>
                  )}
                  <p>
                    <span className="evidence-label">Analysis</span>{" "}
                    {item.evidence_summary}
                  </p>
                  <p>
                    <span className="evidence-label">Validation</span>{" "}
                    {readableStage(item.validation_status)}
                  </p>
                  {item.limitations?.length ? (
                    <p>
                      <span className="evidence-label">Limitations</span>{" "}
                      {(item.limitations ?? []).join(" ")}
                    </p>
                  ) : (
                    <p>
                      <span className="evidence-label">Limitations</span> No
                      additional limitations were recorded for this narrow
                      proposition.
                    </p>
                  )}
                </div>
              </details>
            ))}
          </div>
        </>
      ) : (
        <p>
          Detailed admitted passages are unavailable for this persisted result.
        </p>
      )}
    </section>
  );
}
