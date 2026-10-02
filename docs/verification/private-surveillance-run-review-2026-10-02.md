# Private-surveillance run review — 2026-10-02

Read-only review with two Luna helpers. Run: `8685028b-770f-495a-8feb-40af39308f17`. No provider calls, app changes, or saved-data writes.

## Cost

The user's run-only counts yield $0.0295: 120,000 input × $0.10/million = $0.012; 35,000 output × $0.50/million = $0.0175. No previous usage was subtracted.

The app recorded 40 physical calls (38 succeeded, two failed), 139,611 input tokens, 39,109 output tokens, 14,349 cached input tokens, and 125,142 cache-write tokens. All calls have known input/output/cache/write usage and reported-write cost basis. Failed calls retain usage and cost.

Recorded estimate reconciles exactly: ordinary input/output cost $0.033515600, cached-input discount −$0.001291410, cache-write premium +$0.003128550 = $0.035352740, displayed as $0.0354. No accounting defect found; this is an estimate, not invoice verification.

## Result and verification

All 172 persisted artifact payload hashes passed. Pure reconstruction of final validation preserved release hash `008daa79235eb5cf9d7c064dbd47022610e969af212773489b6d85c60d311190`. Seven admitted cards match seven distinct Ledger citations. All seven assessment relationships are `qualifies`; none establish the universal claim. Independent Reviewer approval is absent and disclosed.

Sixteen survivor outcomes reconcile: seven admitted, five Analyst failures, three extraction failures, one source-budget block. The five Analyst failures consist of four unrelated assessments rejected after bounded retries and one output missing its final statement. The extraction failures selected 8, 26, and 2 words against a 30-word requirement. Unrelated findings were not admitted. The source-budget preflight made no physical call for the blocked source and later sources proceeded.

## Findings for approval

1. **Direction/relationship contract mismatch.** The result page describes search direction as independent of evidence relationship, while the Analyst prompt and `agents/v2_evidence_analyst.py:578` forbid CHALLENGES for support-directed research and SUPPORTS for challenge-directed research. The Sweden passage states statutory restrictions but is labeled Qualifies for the universal no-restrictions claim. Existing direction tests pass (two cases), confirming the current restriction. Align the product policy, prompt, validators, and display explicitly; do not simply weaken a gate.
2. **Sentence fragmentation.** `agents/v2_acquisition.py:39` and `_sentence_spans` split periods in decimals, abbreviations, and DOI/URL text. Offline probes split `1.6`, `U.S.`, `Web 2.0`, and DOI links. This run's selected probes contain the same fragments and page controls. Improve segmentation and relevance selection while preserving immutable snapshot offsets and historical artifacts.
3. **Outcome classification and retry waste.** Four unrelated assessments are presented as analysis failures and retried, despite a valid irrelevance decision. Distinguish ordinary relevance rejection from malformed model output and transport/validation failure. Keep unrelated material excluded.
4. **Stopping label regression.** `web/app/page.tsx:607` relies on wording to relabel sufficient-source-pool stops. The saved explanation says “revisit those families,” which fails the regex. Derive a clear search-stop label from typed state rather than model prose.

## Research-quality limitations

The one-round search stop occurred before deep analysis and was not reconsidered after analysis failures. One dimension remains partially covered, with zero explicit follow-up gaps. These can validly differ, but source-pool sufficiency is not proof of the claim or of admitted-evidence sufficiency.

Three admitted pages discuss the same Swedish authority's domestic-purpose exemption; they are distinct pages, not three independent corroborations. The first overview statement oversimplifies the exemption: the authority's detailed guidance describes a narrow, fact-dependent boundary. The broad all-50-states statement is attributed to a secondary surveillance guide and lacks primary legal verification. Both warrant stronger context/authority handling.

Primary guidance checked: https://www.imy.se/en/individuals/camera-surveillance/to-be-a-controller-of-personal-data/video-surveillance-under-the-domestic-purpose-exemption/

No fixes were applied during this review. No full test-suite rerun was needed for a read-only review; the two direction-policy tests and isolated segmentation/label probes were run.
