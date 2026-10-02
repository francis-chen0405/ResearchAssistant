# Discrimination run review — 2026-10-01

Status: read-only review complete. No product fixes have been made.

The user requests results and bugs for “Automated license plate cameras cause
discrimination.” This follows their cumulative 410,000 input / 130,000 output token
report. The [read-only plan](../../.agent/plans/discrimination-run-review-2026-10-01.md)
bounds this review. Three Luna helpers review accounting, pipeline and presentation;
the primary agent verifies the immutable release and integration. Repository
baseline is pushed commit `fdc9dc63a32b0b2ec1336949e1aeb7485e925bf3`.

## Result assessment

The run produced a cautious, usable summary of disparities and concerns. It did
**not establish that ALPR cameras caused discrimination**. The brief correctly
distinguishes deployment geography, reported enforcement disparities, broader
surveillance-AI research and misuse anecdotes from ALPR-specific causal evidence.

The acquired material includes a 614-camera deployment study, Louisville reporting
about 177 citations, and an Oak Park report comparing Flock-stop demographics with
a broader traffic-stop benchmark. These are narrow source-supported observations,
not controlled attribution to cameras. A surveillance-AI study does not isolate
ALPR effects; civil-rights concerns and misuse reports do not by themselves prove
the causal claim. These judgments concern the stored passages, not a new external
fact-check of the complete publications.

Only support-directed research was enabled. The latest decision stopped after two
rounds because more searches were expected to overlap the existing pool. One
material gap and one partial coverage dimension remain. The latest Gap Analysis
returned no further actionable search gaps, while final output conservatively
retained the unresolved causal evidence gap. That stopping state is
internally consistent; it does not mean the claim is established. The correct
conclusion is that the run found potentially relevant disparities while leaving
camera-specific causal attribution unresolved.

| Recorded result | Value |
| --- | --- |
| Run | `44b8cc42-0a18-4c31-9c6f-5f23fe68260a` |
| Rounds / search attempts | 2 / 14 |
| Acquired surviving sources | 30 |
| Admitted / analysis failed / Analyst-rejected | 10 / 12 / 8 |
| Admitted relationships | 8 qualifies / 2 unrelated / 0 supports / 0 challenges |
| Recommended sources | 5; all analyzer-admitted |
| Material gaps / partial coverage dimensions | 1 / 1 |
| Physical model calls | 57 |

Ten admitted items are not ten independent studies: two repeat the same Louisville
report, and two are explicitly unrelated to the claim. The useful findings are
qualified and the analysis yield/relevance could improve.

## Integrity and checks

All **280 artifact payload hashes match**. Strict typed loading and pure
deterministic final reconstruction reproduce release hash
`00aa01fe399464692d84d22e50707b09dc7a52373c5687045fb5b180c3383424`.
All ten displayed quotes validate against their immutable snapshots and offsets;
ten unique Ledger IDs match the synthesis IDs. No corrupted release, substituted
source, or unadmitted Evidence card was found. Release validation establishes the
application's integrity checks, not the truth of the causal claim or independent
Reviewer approval.

The installed web export matches current `web/out`. The advisory graph was
refreshed (5,216 nodes / 34,934 edges); consequential conclusions were checked
against source and persisted artifacts. Existing evidence-display, status,
lineage and budget regressions passed **23 tests with warnings as errors**. This
is a focused check, not a repeated full 1,283-test gate or new packaged release.
Local logs and helper reports use the `discrimination-` prefix under
`desktop/build/`.

## Findings and proposed repairs

| ID | Finding and classification | Proposed bounded repair |
| --- | --- | --- |
| A | **Confirmed UI summary defect.** The aggregate shows 0 Reviewer-approved, 12 failed and 8 rejected, omitting 10 analyzer-admitted sources. It counts all 30 survivors while appearing under Recommended Sources; the five actual recommendations all succeeded. | Include analyzer-admitted totals and label the aggregate's survivor-pool scope; preserve separate recommendation outcomes and explain that fresh synthesis does not use a Reviewer. |
| B | **Confirmed lineage-warning false negative.** Louisville LPM and Afro-Conscious versions have the same dated slug/base headline and nearly identical stored text (similarity 0.9971), but a publisher suffix defeats exact title matching. Separate family/Ledger IDs are valid; there is no warning against treating them as replication. | Add conservative mirrored-report notices using corroborating metadata/text identity; preserve both immutable records and do not merge by title alone. |
| C | **Relevance/policy concern.** Two unrelated items are admitted as qualified-only facts: an article's bibliographic title and an ALPR deployment description. Claim Fit 2 / Evidence Quality 3 is deliberately admitted by existing policy; this is not a broken quote validator. | If approved, exclude unrelated records from new claim-evidence admission or clearly separate them as background. Keep historical records intact and version any changed admission policy. |
| D | **Confirmed qualification false rejections cause avoidable yield loss.** Three completed drafts reached ready-for-admission and then failed the mandatory qualification check. They use “In this study” or “The paper/article reports,” while the lexical matcher recognizes “reported” but not these formulations. | Validate canonical qualification before accepting the combined Analyst result and provide bounded repair consistent with the strict scope requirement; add regressions for the observed formulations without weakening provenance or scoring. |
| E | **Budget/input-size failure mode.** Six sources were blocked by the existing per-source token cap. This is protective enforcement, not evidence that the cap should be raised. It reduces yield and is grouped with executed analysis failures. | Improve preflight fit checks, distinguish budget-blocked sources in diagnostics, and evaluate bounded passage input preparation under the unchanged caps and quotation rules. |
| F | **Minor copy issues.** A fresh run is called a “historical brief.” “1 actionable gap” is derived from the conservatively retained unresolved gap even though latest Gap Analysis returned no actionable searches; “Sufficient Source Pool” can sound stronger than its careful explanation. | Use “saved brief” and “unresolved evidence gap”; use a clear stopping label that explains expected search overlap. |
| G | **Cost telemetry/display limitation.** Input/output/cache-read splits are complete, but cache-write counts and whether cost uses known writes or a conservative fallback are not retained. | Retain optional write counts and estimate provenance on future calls; show model-token totals and the pricing basis without inventing past counts or rewriting historical costs. |

A and B are directly reproduced presentation defects. C changes intended policy
and needs an explicit product decision. D and E warrant bounded regression-driven
improvements, retaining strict gates. F and G are clarity/telemetry improvements.

## Analysis yield and failure details

The 12 failed source outcomes break down as follows:

| Cause | Sources | Interpretation |
| --- | --- | --- |
| Per-source token cap could not cover the request | 6 | Protected budget enforcement; improve input preparation/preflight and report separately from executed semantic failures |
| Qualification false rejection | 3 | Completed drafts rejected by lexical formulation rather than actual lack of attribution/scope |
| One-word quote below the 30-word minimum | 1 | Exact extraction failed closed; do not remove the minimum to improve yield |
| Missing final factual statement after bounded Analyst retries | 1 | Semantic output/retry exhaustion; incurred usage remains recorded |
| Empty/short selected sentence ranges | 1 | Provider structured output failed the schema; failed-call usage/cost remain recorded |

One qualification-rejected draft was itself classified unrelated; repairing its
wording should not override a separate relevance decision. The eight Analyst
rejections are screening outcomes, not eight extra runtime crashes. These source
outcomes also are not twelve failed physical transports: 56 of 57 physical calls
succeeded, with one schema-failed Extractor call. Local budget-preflight and
deterministic-admission failures happen outside physical-call completion success.

## Cost reconciliation

The user's cumulative subtraction gives 160,000 input and 60,000 output tokens,
costing **$0.046** at ordinary $0.10/$0.50 per-million rates. That arithmetic remains
correct for the supplied totals and excludes cache-write pricing.

The actual saved call audit retains **209,356 input / 62,618 output tokens**,
including 2,747 cache-read and 206,609 uncached input tokens: **271,974 combined**.
All 57 calls have completions and known input/output splits, including one failed
physical Extractor call (1,410 input / 415 output, $0.000221870). All calls use the
same OpenAI `gpt-6-luna` physical model: 30 High and 27 XHigh, with identical rates. Recorded computed cost is **$0.057158320**, correctly rounded to
the UI's **$0.0572**. The account-total subtraction differs by 49,356 input and
2,618 output tokens; its time/project/model scope and prior rounded baseline
cannot be established from saved artifacts alone.

Official [GPT-6 Luna pricing](https://developers.openai.com/api/docs/models/gpt-6-luna)
lists $0.10 ordinary input, $0.01 cache-read input, $0.125 cache-write input and
$0.50 output per million. The [prompt-caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)
confirms that cache writes have a distinct 1.25× rate; this tariff is legitimate.
The code treats missing write counts conservatively. It is a computed estimate,
not an imported invoice. Removing the write tariff is not an appropriate fix.

At the recorded input/output/read counts, ordinary-input-plus-cache-read cost
would be $0.051997370 before write uplift. Pricing all uncached input as writes
would give $0.057162595. The stored $0.057158320 lies within that range. Inverting each of the 57 exact
per-call estimates under the catalog formula produces 206,438 implied write
tokens in aggregate and matches every stored estimate. This is a mathematical
inference from estimates, not independently persisted raw write metadata or
invoice evidence.
The simple ordinary-rate estimate for recorded input/output without cache detail
would be $0.052244600. There is no confirmed sum/rounding defect. Lack of retained
write counts prevents independently reconstructing every call's pricing basis or
asserting an exact match to the account bill.

## Boundary

No app/runtime/prompt/test behavior, database, saved artifact, preference or
credential was changed; no provider/research call was made. Only documentation
and ignored diagnostic reports were added. The installed app remains the verified
build. This review reports proposals for the user's selection; it does not start
another implementation, installation, push or paid-run phase.
