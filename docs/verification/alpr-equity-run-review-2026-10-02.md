# ALPR equity result review — 2026-10-02

## Outcome and scope

The user requested review of the result for “ALPRs discriminate against people of color and impoverished people,” saved run `2518837c-fc8e-41f8-ad48-25ccb372b7ab`. The result presents limited supporting observations, not an established claim. Its main weakness is low evidence yield after a search stop that preceded deep analysis. Confirmed presentation issues and proposed quality improvements are separated below.

The database was opened with SQLite `mode=ro`. Two Luna helpers independently reviewed pipeline outcomes and the derived result display. The primary review verified saved hashes, typed reconstruction, quotation bindings, usage accounting and selected primary-source metadata. No product code, prompts, tests, saved research, credentials or app installation changed; no application/provider research calls were made. The advisory graph was refreshed in fast mode without writing an index artifact, and relevant conclusions were checked against live source and saved artifacts. This review does not independently peer-review the studies or establish legal or causal conclusions.

## What the evidence establishes

- **Hampton Roads:** The admitted study reports disproportionate deployment of 614 Flock ALPR cameras in predominantly Black and high-poverty neighborhoods. It supports an exposure/geography disparity; its statement explicitly excludes established discriminatory intent or downstream treatment. The [author-supplied abstract](https://ideas.repec.org/p/osf/socarx/5ckgv_v1.html) agrees with that narrow description.
- **Oak Park:** The captured local article reports that 25 Flock stops involving 29 people disproportionately affected Black community members. This is a small, localized descriptive finding; the admitted statement expressly says it provides no poverty evidence. The central selected passage does not supply an appropriate population/exposure benchmark or a causal comparison. The live page could not be independently fetched during review; this assessment uses the immutable captured passage and its limitations.
- **Five qualifications:** These are a civil-rights overview, an IACP responsible-use statement, a general traffic-stop search study, NYC speed-camera findings, and one historical ALPR misread/stop incident. They are labeled as qualifications, not direct supporting evidence. The general traffic-stop and speed-camera findings do not establish ALPR-specific demographic outcomes. The single incident does not measure comparative error rates. Claim Fit 2 qualified context is permitted by the current admission policy; these are not confirmed policy violations.

The result reports **2 supporting, 5 qualifying, 0 challenging and 0 unrelated admitted findings**. Support research was enabled and challenge research disabled. **Two material gaps and two partial coverage dimensions remain:** ALPR-specific race/income outcomes with exposure denominators or comparison groups, and separate evidence for both named populations beyond localized settings. “Released”/“provenance checked” describes artifact validation, not verification that the claim is true. Analyzer admission is explicitly distinguished from independent Reviewer approval.

## Findings and proposed priorities

### A. Search-stop timing — confirmed workflow limitation, highest priority

The Round 2 `sufficient_source_pool` decision preceded deep-analysis outcomes. Of 25 surviving sources, 18 ultimately yielded no admitted evidence, yet no subsequent search/gap reconciliation occurred. The final post-analysis assessment correctly preserves and discloses the two remaining gaps; there is no artifact disagreement. This is not proof that additional searching would succeed, but the stop decision did not incorporate the eventual evidence yield.

Suggested repair: explicitly distinguish search saturation from evidence sufficiency and evaluate the final admitted outcomes before choosing a terminal research status. Any bounded continuation must retain existing caps and direction controls; no extra paid allowance is authorized by this review.

### B. Unusable captures reaching extraction — confirmed early-filter defect

The 25 source outcomes reconcile as **7 admitted, 8 Analyst-rejected, 6 extraction-failed, 2 Analyst-failed and 2 source-budget-blocked**. The UI's 8 “analysis failed” total combines the six extraction failures and two exhausted Analyst failures. The source-local budget blocks had no physical model calls and are expected enforcement, not global budget exhaustion.

The extraction failures include two one-word captures, a 23-word selection, an invalid start marker, and two sources whose bounded extractor attempts remained too short. Seven physical extractor attempts were recorded failed with `selected_sentence_ranges:too_short`; this identifies response/selection validation failures, not evidence of a provider outage. Six Analyst contract-validation failures occurred across four sources: two recovered, while two exhausted their two attempts for Claim Fit 2 scope qualification. A site-load notice also reached analysis but was correctly rejected as unrelated. Fail-closed checks prevented these failures from becoming admitted evidence.

Both failed OSF snapshots contained exactly `OSF`. In `agents/v2_acquisition.py:220`, `probe_snapshot` filters substantive passages, but only replaces the original candidates when at least one substantive candidate exists. When every candidate is rejected by `_is_substantive_passage` (which rejects fewer than five words), the weak originals remain. A successful probe with any passage then becomes a survivor at `agents/v2_acquisition.py:168`; selection accepts a positive snapshot word count and queues within budget. Each OSF source reached extraction twice before the 30-word quote minimum rejected it. This is a confirmed early-filter defect that wasted four model attempts, not a bypass of evidence admission.

Suggested repair: fail the usability gate when no substantive content remains, before model analysis. Separately improve bounded sentence selection and qualification recovery without relaxing quote length, exact offsets, relevance checks or budgets. Provide clearer failure diagnostics for priority sources rather than repeatedly analyzing unusable captures.

A recommended Hampton Roads source, `osf.io/preprints/socarxiv/d6j3b_v2`, failed after a shell capture. Its [author-supplied alternate abstract](https://ideas.repec.org/p/osf/socarx/d6j3b_v2.html) describes population-adjusted models with demographic and other controls, making it a useful missed lead for the review question. It shares authors/setting with the admitted Hampton Roads work; it should not be counted as independent replication. The alternate page was inspected only for this review and was not added to the app's evidence or saved run. Any alternate retrieval behavior is a proposal requiring a separate implementation scope.

### C. Missing shared-work notice — confirmed presentation defect

Both RePEc `ideas.repec.org/p/osf/socarx/5ckgv_v1.html` and OSF `osf.io/preprints/socarxiv/5ckgv_v1` survived selection. They share the archive identifier `5ckgv_v1`, but the derived display returns no lineage notice. Their titles differ/truncate and both stored DOI fields are absent; `study_lineage.py` currently matches DOI, normalized title and dated article slugs, not this archive identifier.

Suggested repair: a conservative recognized-archive identifier notice, with conflicting metadata safeguards and without merging immutable source families. Only the RePEc entry was admitted, so this run did not double-count admitted evidence from the pair.

### D. Count wording and source headings — confirmed clarity issues

“18 selected source(s) produced no admitted evidence” counts all unadmitted survivors, not just the five sources labeled Recommended. Its denominator is 25; 16 of the 18 were not recommended and two were recommended. The count is correct but the wording is ambiguous beside the Recommended Sources section. Suggested wording should name the survivor pool and denominator explicitly.

Two source headings are raw PDF citation/header strings: `S2056608520000082jra 1..28` and `751 F.3d 1039, *; 2014 U.S. App. LEXIS 8824, **`. Their links/quotes remain correct. A verified title or informative host/file fallback would improve readability; retain the captured title and legal citation as provenance rather than inventing replacements.

### E. Adjacent context prominence — optional presentation improvement

The general traffic-stop study and NYC speed-camera item are permissible qualifications, but five adjacent qualifications outnumber two direct supporting findings. Consider grouping general policing/different-technology context separately and stating the technology boundary in collapsed overview sentences. This is a relevance/presentation proposal, not a confirmed false-support classification. The Brennan legal-context notice is conservative and does not create a false legal conclusion.

## Accounting and integrity verification

All **263 saved artifact payload hashes** verify. Typed reconstruction passes current final validation and reproduces release hash `d62e08e52f9ce1c97b3fb863f1723f0ec2de5d6e50d179cbd52457c8aa4c2f0e`. All **7 admitted cards and 7 unique Ledger quotations** bind to their matching source snapshots/candidates; synthesis references resolve to those cards. No confirmed citation, relationship, release-hash or numerical accounting defect was found.

All **61 physical starts have completions**: 54 succeeded, 7 failed; 31 extractor, 21 Analyst and 9 discovery/planning calls. Input, output, cache-read, cache-write and cost fields are known for every call, including failed attempts. Recorded usage is **232,658 input / 73,309 output**, including **21,858 cached input** and **210,617 cache-write tokens**. Cache-write tokens describe the write basis within input; they are not additional unique input tokens.

The exact recorded estimate reconciles to **$0.063218505**, displayed as **$0.0632**:

| Component | USD |
| --- | ---: |
| Ordinary input/output at user-supplied $0.10/$0.50 per million | 0.059920300 |
| Catalog cache-read discount | −0.001967220 |
| Catalog cache-write premium | +0.005265425 |
| Recorded total | **0.063218505** |

Remaining global ceilings were 99 calls, 194,033 tokens and approximately $0.4368; the search stop was not forced by global exhaustion. Source-local caps remain intentional. The user's cumulative 700,000 input / 215,000 output would be $0.1775 at ordinary supplied rates. A conditional account-delta estimate of 170,000 / 50,000 ($0.0420), using the earlier supplied totals, does not match this run's complete recorded usage. Account aggregation, rounding, cache treatment and scope were not verified; the discrepancy alone does not establish an app accounting bug or invoice amount.

## Checks and next boundary

Existing focused evidence-display, post-analysis, admission, Analyst and lineage tests passed: **72 tests**, warnings treated as errors. Ruff lint passed; format check passed for **178 files**. Whitespace checking passed. The preceding 1,346-pass / 2-skip full suite is historical evidence for unchanged source, not a new full-suite run during this documentation-only review.

No repairs were implemented. Stop at the reviewed proposals pending the user's next direction. Existing source commit `4a1d1cc` and the installed app remain the preceding delivery; this review's documentation is uncommitted. Preserve immutable history, caps and existing paid/data/publication boundaries.
