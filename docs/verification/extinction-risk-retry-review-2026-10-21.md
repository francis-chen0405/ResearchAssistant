# Completed extinction-risk retry — October 21, 2026

Read-only review of `4fa0dcb5-b7f2-4167-b627-2a9eae710ff3`, “Biodiversity loss
increases the risk of species extinction”. Completed in 5m55s, with released output
and explicitly incomplete evidence coverage. No paid research or application-source
change was performed by this review. All 251 artifact hashes, 13 captured snapshot
content hashes and six admitted snapshot/segment ownership links verify.

## Pipeline outcomes

| Stage | Saved outcome |
| --- | --- |
| Discovery | 20 raw SERP hits, 18 distinct retained metadata records |
| Acquisition | 21 capture attempts, 13 fetched, 11 usable; five unavailable works and two fetched/unusable works |
| Recommendation | All 11 sources included, zero input-cap omissions; 14,729 / 24,000 conservative input tokens |
| Recommendations | Three provisional recommendations; two admitted, one subsequently rejected |
| Extraction | 11 successful sources, zero final extraction failures; one source required two extraction attempts |
| Admission | Six admitted, five rejected, zero analysis/admission failures |
| Claim fit | Four Partial / two Weak admitted findings; none Full or Claim Fit 5 |
| Final relationship | Two supporting / four qualifying admitted findings; claim not established |

Recommendations were the Nature extinction-risk-footprints paper, the Bangor drylands
paper and the IPBES summary. The IPBES candidate was subsequently rejected on the
selected passage. Admitted sources also include UN Goal 15, UN News, an economic-
complexity paper and a Carbon Brief progress page. Two sources classified as supporting
still have only Partial fit; this is not direct causal confirmation.

Four early source assessments were supplied to Gap Analysis. It distinguished concurrent
trends and broad multi-pressure statements from evidence connecting separately measured
biodiversity loss to subsequent species-level extinction risk. It requested continuation
and a targeted search. This confirms the assessment-to-gap decision step worked; no
follow-up query could run under the request safeguard described below.

Eight previous-run leads were offered. None of their exact URLs appears in the retained
pool, so this case does not demonstrate fresh reassessment of a prior lead. Paper-identity
audit groups were empty; the mirror-collapse path was not exercised here.

## Why search coverage was small

Only the first SERP logical query dispatched. Its first two pages completed with ten
raw hits each, retaining 18 distinct records. Page three started and ended 15 seconds
later as `interrupted_unknown`, with no response hash or known actual provider cost.
The saved artifacts do not establish the underlying transport cause or whether the
provider accepted/charged the request.

The configured global unknown-request safeguard then blocked six remaining initial
queries before dispatch: one SERP, three Exa, one OpenAlex and one arXiv. Those providers
were configured, but Exa/OpenAlex/arXiv supplied no discovery results in this run. This
was not exhaustion of the source target or request budgets. The model budget retained
382,703 tokens, 133 calls and $0.473833920; recorded model use was 117,297 tokens and
$0.026166080. Search costs remain incompletely reported and reserved separately.

Code inspection confirms `fair_query_order` rotates logical provider queries, but a
single `execute_query` runs its pagination before the next logical query. Consequently
SERP reached a third-page unknown outcome before any other provider's first page. Keep
unknown reservations and the stop guard; consider bounded first-page scheduling across
providers before optional deeper pagination in a later implementation.

## Reporting gaps exposed

The stop text says no provider remains within its search ceiling. In fact, an unknown
request froze eligibility; ceilings remained unused. The new blocked counters correctly
show six blocked queries. However, `record_search` increments `unknown_queries` only
when a logical query failed. This partially successful SERP query kept its results,
so the unknown third page disappears from that summary count. Report partial results
and their unknown page together without double-counting logical query outcomes.

## Captured PDF context still lost

The recommended IPBES summary snapshot is explicitly truncated: 20,389 characters,
3,054 words, pages 1–8, ending in acknowledgements. Only one extinction-related word
occurrence exists in that captured text, in front matter. The extracted passage
(characters 11,690–12,132) concerns biodiversity loss but not the claimed extinction-risk
relationship, so the Analyst rejected it. This does not establish that the full IPBES
report is irrelevant: its main findings were not available to the assessment.

Live acquisition passes the configured 100-page limit into `normalize_pdf`. The owned
worker extracts text from every permitted page, then `_document_from_text` keeps only
the first 3,000 normalizer-counted words. Thus eight captured pages reflect a word-
prefix cutoff, not an eight-page parser setting. No later-page recovery path exists
in the inspected acquisition/normalization code. The worker already encounters later
page text before normalization discards it; capture coverage and model input bounds
should be treated separately in the proposed repair.

Treat a front-matter-only truncated capture as a capture-coverage limitation and consider
a bounded relevant later-page window/new immutable snapshot, preserving page/time/byte
limits and original quotes. Source token-cap recovery cannot recover text never captured.

## Conclusion and next boundary

The live recommendation-coverage fix worked (11/11 considered rather than one), and all
retained sources were successfully extracted/assessed. Four early assessments caused a
precise missing-evidence search request. Practical follow-up benefit remains unmeasured
because search stopped; strong evidence for the exact causal claim remains absent.

Before another controlled broad/specific comparison, prioritize provider/page scheduling,
truthful partial-unknown/stop reporting and bounded substantive PDF capture. The separate
initial-planner invalid-response failure from `7a38a9c4…` remains unfixed despite this
retry succeeding. Do not rewrite either saved run, bypass unknown-call accounting or
interpret higher admission counts alone as improved research quality.
