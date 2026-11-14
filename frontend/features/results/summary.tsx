import type { ReactNode } from "react";
import { Chip, SegmentBar } from "@/components/ui";
import { Icon } from "@/components/icons";
import type { V2EvidenceDisplay, V2FinalResearchOutput } from "@/lib/api";
import {
  type EvidenceItem,
  type Finding,
  type Relationship,
  coverageSummary,
  evidencePicture,
  foundSummary,
  publicationCounts,
  relationshipTone,
} from "./model";

const pictureIcon = {
  support: "check",
  challenge: "minus",
  context: "info",
  neutral: "circle",
} as const;

export function ResultSummary({
  result,
  evidence,
  findings,
  onOpenEvidence,
  writtenSummary,
}: {
  result: V2FinalResearchOutput;
  evidence: V2EvidenceDisplay | null;
  findings: Record<Relationship, Finding[]>;
  onOpenEvidence: (ledgerClaimId: string) => void;
  /**
   * Reserved slot for a future model-written summary (out of scope: no model
   * call exists for it). When provided it would render above "What the research
   * found", clearly labelled as model-written. Nothing passes it today.
   */
  writtenSummary?: ReactNode;
}) {
  const picture = evidencePicture(findings, result.directions);
  const counts = publicationCounts(findings);
  const found = foundSummary(result, evidence, findings);
  const coverage = coverageSummary(result, evidence);
  const openQuestions = [...new Set(result.unresolved_material_gaps.map((gap) => gap.missing_evidence.trim()))];
  const relationshipOf = (item: EvidenceItem) => item.relationship_to_claim as Relationship;
  // Without detailed evidence, the released synthesis still carries the exact statements.
  // Its sections follow search direction, not relationship to the claim, so no label is shown.
  const releasedStatements = result.synthesis.sections
    .filter((section) => section.section_type !== "limitations")
    .flatMap((section) => section.items);
  return (
    <div className="summary">
      <div className="summary-side">
      <section className="summary-picture" aria-labelledby="evidence-picture">
        <p className="eyebrow">Evidence picture</p>
        <h2 id="evidence-picture" className={`picture picture-${picture.tone}`}>
          <Icon name={pictureIcon[picture.tone]} size={20} />
          {picture.label}
        </h2>
        {evidence && (
          <div className="summary-counts">
            <SegmentBar
              label={`${counts.supports} supporting, ${counts.challenges} challenging, ${counts.qualifies} adding context`}
              segments={[
                { tone: "support", value: counts.supports, label: "Supports" },
                { tone: "challenge", value: counts.challenges, label: "Challenges" },
                { tone: "context", value: counts.qualifies, label: "Adds context" },
              ]}
            />
            <p className="legend">
              <span><i className="seg-support" />{counts.supports} support</span>
              <span><i className="seg-challenge" />{counts.challenges} challenge</span>
              <span><i className="seg-context" />{counts.qualifies} add context</span>
              <span className="legend-total">{counts.publications} distinct {counts.publications === 1 ? "publication" : "publications"}</span>
            </p>
          </div>
        )}
      </section>
      <aside className="how-to-read" aria-labelledby="how-to-read">
        <h3 id="how-to-read"><Icon name="info" /> How to read this</h3>
        <ul>
          <li>Each finding was checked against the source text by the analysis model. No person has independently reviewed it.</li>
          {picture.scopeNote && <li>{picture.scopeNote} Evidence on the other side was not researched, so its absence here means nothing.</li>}
          {coverage.level !== "complete" && <li>Coverage is incomplete, so important evidence may be missing.</li>}
          <li>The label and counts describe the findings collected, counting each publication once. Study design, relevance and limitations decide how much each finding should weigh; counts alone cannot settle where the balance lies or decide the claim.</li>
        </ul>
      </aside>
      </div>

      <div className="summary-main">
      {writtenSummary}

      <section aria-labelledby="summary-found">
        <h3 id="summary-found">What the research found</h3>
        {!evidence ? (
          <>
            {releasedStatements.length ? (
              <ul className="found-list">
                {releasedStatements.map((item) => (
                  <li key={item.ledger_claim_id} className="released-statement">
                    {item.approved_factual_statement}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No findings were released for this claim.</p>
            )}
            <p className="subtle">These are the released statements. Quotes and sources could not be loaded.</p>
          </>
        ) : (
          <>
            {found.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
            {found.items.length > 0 ? (
              <>
                {found.paragraphs.length > 0 && <h4 className="found-subhead">Strongest findings</h4>}
                <ul className="found-list">
                  {found.items.map((item) => (
                    <li key={item.ledger_claim_id}>
                      <Chip tone={relationshipTone[relationshipOf(item)] ?? "neutral"}>
                        {relationshipOf(item) === "supports" ? "Supports" : relationshipOf(item) === "challenges" ? "Challenges" : "Context"}
                      </Chip>{" "}
                      {item.approved_factual_statement}{" "}
                      <button type="button" className="link-button" onClick={() => onOpenEvidence(item.ledger_claim_id)}>
                        See evidence
                      </button>
                    </li>
                  ))}
                </ul>
                {found.selection === "top" ? (
                  <p className="subtle">The most direct finding on each side; they may not be representative of all findings.</p>
                ) : (
                  evidence.opening_notice && <p className="subtle">{evidence.opening_notice}</p>
                )}
              </>
            ) : (
              !found.paragraphs.length && <p className="muted">No findings were collected for this claim.</p>
            )}
          </>
        )}
      </section>

      {openQuestions.length > 0 && (
        <section aria-labelledby="summary-unknown">
          <h3 id="summary-unknown">What is still unknown</h3>
          <ul>{openQuestions.map((question) => <li key={question}>{question}</li>)}</ul>
        </section>
      )}

      <section aria-labelledby="summary-coverage">
        <h3 id="summary-coverage">Coverage</h3>
        <p>{coverage.sentence}</p>
      </section>
      </div>
    </div>
  );
}
