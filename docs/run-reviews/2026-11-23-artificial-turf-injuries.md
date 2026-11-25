# Review: Artificial turf increases the risk of sports injuries.

Run `ec118a36-6664-442e-893e-11823ac2197d`. Local time: November 23, 2026, 4:26:49.091–4:31:55.159 PM PST. Whole-run elapsed: **306.067 seconds (5:06.07)**. Reviewed saved artifacts only: 392 v2 artifacts, 26 paired physical-model call receipts, nine Analyst mirror rows, nine ledger admissions, saved source captures and current read-only inspection output. Released output/hash revalidation passed. No new searches or model calls were made.

## Assessment

Execution completed and the report correctly stops short of establishing the broad claim. All ten metadata search requests succeeded, so this particular run did not exercise the new provider-isolation failure path. The major new mechanical findings are a false source-family merge caused by reCAPTCHA canonical-URL metadata, two failed Source Selection validations followed by fallback, and a phase-insensitive protected-budget reserve that prevented another round. Source excerpt representativeness and overlapping evidence remain limitations of the unchanged extraction process.

The final assessment records **7 supporting, 1 challenging, and 1 qualifying finding**, support-only searches, partial coverage, an unresolved material gap, and unresolved data overlap. These are classifications of retained passages, not nine independent studies or a vote establishing the claim. Internal synthesis stance fields say supporting because all sources came from the support-directed lane; the current evidence display correctly labels the football meta-analysis as challenging. That internal lane label is not a separate relationship-labeling bug.

## Run configuration and comparison

| Metric | Previous grass-safer run | New artificial-turf run |
|---|---:|---:|
| Wall time | 240.23 s | 306.07 s (+27.4%) |
| Physical model calls | 25 | 26 |
| Input tokens | 81,052 | 94,356 |
| Output tokens | 37,641 | 51,194 |
| Total tokens | 118,693 | 145,550 (+22.6%) |
| Recorded model cost | $0.028950125 | $0.036979690 (+27.7%) |
| Metadata search requests | 6 (one failed/unknown) | 10 (all successful) |
| Raw hits / deduplicated works | 54 / 50 | 137 / 84 |
| Scouted candidates | 50 | 60 |
| Capture-shortlisted clusters | 23 | 26 |
| Usable snapshots / unique final sources | 10 / 9 | 10 / 9 |
| Search rounds | 1 | 1 |

Both used Standard depth, metadata depth 30, support-only/focused mode, target 10 sources per enabled side per round, five enabled providers with four-request caps, $0.20 model cap, 1,000,000 token cap and 160 model-call cap. PubMed and OpenAlex were not enabled. This is not a controlled benchmark: the claim, returned documents, model outputs and provider health differed. More hits did not produce more retained unique sources in this run.

## Providers and request accounting

| Provider | Physical requests | Raw results | Final source credits | Recorded provider charge |
|---|---:|---:|---:|---|
| SERP Search | 2 | 18 | 4 | Unknown |
| Exa | 3 | 75 | 4 | $0.066 reported |
| arXiv | 1 | 5 | 0 | $0 documented free |
| Serper | 2 | 19 | 2 | Unknown |
| Brave | 2 | 20 | 2 | Unknown |

All ten starts have completed receipts; no query retry, unknown reservation or blocked query is recorded. Provider source credits overlap and must not be summed as unique sources. The successful ten-query execution is healthy behavior, but it does not demonstrate recovery from an actual failed search in this run. The changed code was present in checkout commit `29ee9dd`; the earlier offline provider-failure regression is the direct test of isolation.

arXiv returned five hits this time rather than zero, but none became final retained evidence. Exa received three 25-result operations, versus two roughly ten-result operations for each web provider, so its larger raw count is not a fair standalone provider-quality comparison.

The recorded model estimate is $0.036979690 and Exa separately reported $0.066, giving a known recorded subtotal of **$0.102979690 (about 10.3 cents)** before unrecorded SERP Search/Serper/Brave/Firecrawl charges. The model cap and model-spend display do not include those external-service charges.

## Candidate flow and capture outcomes

137 raw hits → 84 deduplicated works → 60 scouted → 26 capture-shortlisted → 18 with captured content → 10 usable snapshots → 9 unique retained sources. The duplicate usable snapshot is another capture of the 2013 soccer meta-analysis and was merged by publication/location identity.

The 84-work disposition audit records 24 not-scouted, 13 scout-skipped, 21 cap-prevented, 8 unavailable, 8 fetched-but-unusable and 10 usable clusters. The current v3 binding allows 60 acquisition candidates, so 26 is not an overrun of the older v1 25-candidate default. The operation stopped after reaching the usable-source target.

Capture transport made 38 attempts: 26 Wigolo plus 12 Firecrawl. Six Wigolo captures and four Firecrawl captures were readable. Eight access/authentication failures and eight unusable captured results account for the acquisition losses. These capture failures are separate from the ten successful metadata searches.

## Source Selection: verified failure and its cause

The two Source Selection calls ran from 00:29:44.058Z to 00:30:55.150Z: **71.092 seconds**, 15,460 model tokens and $0.004644740. Both model answers returned but were rejected with the same validation error: `Final Source Selection repeated a family before using available diversity`. The stored outcomes have no usable candidate. A deterministic fallback then ranked/recommended all nine sources; all recommendation rationales explicitly identify fallback.

The family error has a concrete source: three different captured PMC articles have `canonical_url=https://www.google.com/recaptcha/challengepage`:

- 2013 soccer meta-analysis, PMC4590909 (`23c0880b`).
- 2020 concussion review, PMC7254119 (`c1b8aa4a`).
- 2026 Brazilian football study, PMC13412916 (`d955898a`).

Their actual source URLs and article text are different. `identify_source_family()` in `evidence/evidence_portfolio.py` prioritizes that canonical URL, and `source_family_key(..., track_shared_data=True)` consequently reproduces the exact same `unverified-data:823ecf5a-889b-59be-b76f-ffa027ff20c1` for all three. This is a metadata identity collision, not evidence that the papers use the same dataset or merely share a PMC host. The selector’s hard diversity rule then demands other families before another of these papers.

This explains the family constraint the model failed and why fallback became decisive. It does not establish which exact proposed order caused each error because invalid rankings were not saved. The fallback prioritized PSU’s bibliography-only page first and ActGlobal’s secondary summary second. The first queue reserved five sources ($0.1605225 / 300,000 tokens), and backfill later assessed all nine. None of the nine final sources was left unanalyzed for lack of queue capacity.

## All nine retained sources

| Recommendation | Source | Saved relationship | Audit |
|---|---|---|---|
| 1 | [Penn State injury-study reading list](https://plantscience.psu.edu/research/centers/ssrc/research/synthetic-turf-injuries) | supports | Selected passage is a bibliography entry/title for Mack et al. 2018, not the study’s methods/results or an effect estimate. The Analyst gave Evidence Quality 2 / Claim Fit 4, yet it was admitted and is recommendation #1. |
| 2 | [ActGlobal MLS study summary](https://www.actglobal.com/mls-injury-surveillance-calloway-2019/) | supports | Secondary summary of the 2019 MLS surveillance study. Ankle injury rates differed; no other subgroup differed significantly. The quoted surrounding text says the studied turf was a viable alternative. Narrow ankle support should not become a general all-injury conclusion. |
| 3 | [2013 soccer meta-analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC4590909/) | supports | Again quotes introductory background about first-generation turf. The saved paper’s own third-generation-turf synthesis reports AT/grass IRR 0.86, with heterogeneity and caution. This is an unrepresentative study-level summary even though the historical quotation is genuine. |
| 4 | [Washington University publication profile](https://profiles.wustl.edu/en/publications/injury-incidence-is-higher-on-artificial-turf-compared-with-natur/) | supports | Institutional publication record containing an abstract: 953 injuries, 585 turf vs 368 grass, reported RR 1.5897 (58% higher). Direct numerical association in high-school athletics, not proof of causation; overlaps the UH report. |
| 5 | [ACFAS review synopsis](https://www.acfas.org/lower-extremity-injury-rates-on-artificial-turf-versus-natural-grass-playing-surfaces-a-systematic) | supports | Professional-society synopsis: higher foot/ankle injury rates on turf, with limits across injury categories. It is a summary of a systematic review, not the captured original full review. |
| 6 | [University Hospitals report](https://www.uhhospitals.org/for-clinicians/articles-and-news/articles/2019/08/artificial-turf-versus-natural-grass) | supports | Reports the same 953 injuries, 585 turf/368 grass, collected through 26 high-school trainers in 2017–18. This and the Washington University record are accounts of the same underlying dataset, not independent corroboration. |
| 7 | [2023 football meta-analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC10139885/) | challenges | Correctly retained as challenging: pooled overall injury incidence 14% lower on artificial turf, with no subgroup/category increase found. Relevant counterevidence, limited to the review’s football setting. |
| 8 | [2020 concussion meta-analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC7254119/) | qualifies | Selected introduction text saying a clear turf/concussion link had not been established, rather than the review’s own pooled findings. The saved article reports concussion-only RR 0.72 favoring turf, with combined head injury/concussion RR 0.89 including no difference. It is weaker and less representative than the results passage retained in the prior run. |
| 9 | [2026 Brazilian football retrospective study](https://pmc.ncbi.nlm.nih.gov/articles/PMC13412916/) | supports | Reports 88 injuries and rates of 9.5/1,000 player-hours on artificial vs 6.6 on natural turf in the 2024 Brazilian First Division. Narrow, retrospective single-competition comparison; confounding and generalization remain concerns. |

The two high-school reports are demonstrably overlapping: both contain 953 total injuries, 585 on turf and 368 on grass, the same reported 58% difference, and the associated 26-school/trainer context. The paper-identity audit and UI study-lineage list contain no group linking them. Counting both as separate reading locations is understandable, but they must not be presented as two independent corroborating studies.

The 2013 introduction-versus-result problem recurred. The concussion review now also contributes background rather than its actual pooled comparison. The 2023 football review was faithfully retained as counterevidence. The Brazil cohort and foot/ankle review synopsis provide context-specific support; neither alone establishes a general risk increase across all sports and injury categories.

## Source-specific model usage

Each row combines one extraction and one Analyst call; shared planning, Scout, Gap and selection work and search/scraping fees are excluded. Per-source seconds below sum its two model call durations; rows ran concurrently.

| Source | Input | Output | Total tokens | Extraction / Analyst seconds | Model cost |
|---|---:|---:|---:|---:|---:|
| 2013 soccer meta-analysis | 5,843 | 2,179 | 8,022 | 8.15 / 15.06 | $0.001819725 |
| 2023 football meta-analysis | 5,661 | 1,921 | 7,582 | 2.98 / 15.71 | $0.001667975 |
| Washington University publication profile | 4,831 | 1,587 | 6,418 | 5.50 / 13.44 | $0.001397225 |
| ACFAS review synopsis | 4,801 | 3,384 | 8,185 | 3.44 / 30.28 | $0.002291975 |
| 2020 concussion meta-analysis | 5,872 | 2,318 | 8,190 | 7.44 / 15.62 | $0.001892850 |
| 2026 Brazilian football retrospective study | 5,732 | 1,648 | 7,380 | 6.53 / 10.27 | $0.001540350 |
| ActGlobal MLS study summary | 5,301 | 2,320 | 7,621 | 5.64 / 16.95 | $0.001822475 |
| University Hospitals report | 5,432 | 1,628 | 7,060 | 3.46 / 13.07 | $0.001492850 |
| Penn State injury-study reading list | 6,149 | 3,011 | 9,160 | 15.13 / 17.70 | $0.002273975 |

The title-only PSU recommendation consumed 9,160 source-specific model tokens, more than the 7,582 spent extracting and assessing the substantial 2023 football meta-analysis. This is a low evidence-yield allocation, although the exact title quotation and its stated limitations remained transparent.

## Timing and model roles

| Stage | Calls | Input | Output | Total tokens | Model cost | Sum of call seconds |
|---|---:|---:|---:|---:|---:|---:|
| planner | 1 | 2,852 | 6,173 | 9,025 | $0.003442925 | 48.39 |
| scout | 4 | 18,421 | 13,158 | 31,579 | $0.008881325 | 112.51 |
| extractor | 9 | 26,978 | 4,727 | 31,705 | $0.005735075 | 58.28 |
| analyst | 9 | 22,644 | 15,269 | 37,913 | $0.010464325 | 148.10 |
| gap_analysis | 1 | 16,327 | 3,541 | 19,868 | $0.003811300 | 30.70 |
| source_selection | 2 | 7,134 | 8,326 | 15,460 | $0.004644740 | 71.07 |
| **Total** | **26** | **94,356** | **51,194** | **145,550** | **$0.036979690** | **469.05** |

All 26 physical model calls returned successfully, but the two Source Selection stage validations failed. There are nine additional model-route-attempt rows mirroring Analyst calls; adding them again would double count those calls and their usage. No separate Reviewer or Synthesizer model calls occurred: admission used the Analyst policy, and final assembly/validation were deterministic, as configured.

Planner took 48.386 seconds; four Scout calls spanned 55.651 seconds; the initial Gap call took 30.701 seconds; two selector calls spanned 71.092 seconds. The remaining eight sources ran from approximately 00:30:55.378Z to 00:31:52.543Z (57.165 seconds), with up to four concurrent model calls. The first source was analyzed earlier to feed Gap. Last model completion to run completion took 2.615 seconds.

The union of intervals with at least one active model call is **285.985 seconds**, about 93.4% of whole-run wall time. Sum of individual call durations is 469.052 seconds because calls overlap; it is not run duration. Total time with no active model call was 20.083 seconds. This run was mostly waiting on model work, not idle frontend time. The extra failed selection attempt was a visible contributor to the longer run, alongside longer Planner/Scout work.

Scouting/extraction used `gpt-6-luna-high` (13 calls, 63,284 tokens, $0.014616400). Planning/Gap/selection/Analyst used `gpt-6-luna-xhigh` (13 calls, 82,266 tokens, $0.022363290). The cache metadata records 3,564 cached input tokens and 90,714 cache-write tokens; cache writes are already included in input usage. One selector retry had the cache hit, but it still incurred output-token cost and failed validation. The recorded cost basis uses published cache prices with reported write counts, not an independently verified invoice.

## Why another round did not happen

The early Gap call used only one completed source assessment—the 2013 background quotation—plus pending-source excerpts and 28 outstanding-capture IDs. It asked for contemporary, exposure-adjusted comparisons by sport/injury/surface generation. All nine sources were later analyzed, but the post-analysis cost precheck stopped before a refreshed Gap call or another search plan. Consequently the final coverage explanation still says other supplied sources were not assessed, although nine Analyst assessments had finished. That explanation is stale; the overall incomplete-coverage conclusion may still be warranted.

At completion, $0.163020310, 854,450 tokens and 134 model calls remained. The stop was a protected-reservation check, not that actual spend reached 20 cents. `_adaptive_budget()` still protects **eight downstream model calls** at this late phase; with matching current stage routes, that reserves **$0.098306** before any follow-up work. The post-analysis guard then adds its own complete follow-up envelope.

| Reconstructed protected follow-up component | USD |
|---|---:|
| Two extractor allowances | $0.013788000 |
| One Analyst allowance | $0.013038000 |
| Two Scout allowances | $0.006144500 |
| Search Agent allowance | $0.007144000 |
| Two Gap allowances using the original saved Gap input | $0.054411000 |
| Fixed eight-call downstream protection | $0.098306000 |
| **Total using original Gap input** | **$0.192831500** |
| Available model allowance | $0.163020310 |

This reconstruction is pure local calculation with the matching saved model aliases; no API requests were made. The actual refreshed-Gap input/reservation was not saved, so $0.1928315 is an illustrative original-input comparison, not a claim to recover the exact transient gate value. It already exceeds the remaining allowance. Source code confirms the fixed eight-call tail is reused after initial source analysis, while the guard separately adds new-source work and final synthesis has no model call. This is a phase-insensitive, overconservative reservation policy worth revisiting; there is no evidence of an arithmetic overspend. Cumulative reservations over all 26 calls ($0.3036465 / 657,530 tokens) are also not simultaneous exposure and do not mean the $0.20 cap was violated.

## All 26 capture-shortlisted clusters

| Cluster | Source | Saved disposition | Saved Probe failure, if any |
|---|---|---|---|
| `d0b69561` | [Risk of injury in elite football played on artificial turf versus natural grass: a prospective ](https://bjsm.bmj.com/content/40/12/975) | unavailable | — |
| `b18ae15a` | [Injury incidence is higher on artificial turf compared with natural grass in high school athlet](https://journals.lww.com/c-orthopaedicpractice/Fulltext/2021/07000/Injury_incidence_is_higher_on_artificial_turf.6.aspx?generateEpub=Article%7Cc-orthopaedicpractice%3A2021%3A07000%3A00006%7C10.1097%2Fbco.0000000000001012%7C) | unavailable | — |
| `2defaf58` | [Incidence, Causes, and Severity of High School Football Injuries on FieldTurf versus Natural Gr](https://journals.sagepub.com/doi/10.1177/0363546504266978) | unavailable | — |
| `53bb5f47` | [Incidence, Mechanisms, and Severity of Game-Related College Football Injuries on FieldTurf vers](https://journals.sagepub.com/doi/10.1177/0363546509352464) | unavailable | — |
| `acf8f4ca` | [Lower Extremity Injury Rates on Artificial Turf Versus Natural Grass Playing Surfaces: A System](https://journals.sagepub.com/doi/abs/10.1177/03635465211069562) | unavailable | — |
| `d05b359b` | [Incidence of football injuries sustained on artificial turf compared to grass and other playing](https://pmc.ncbi.nlm.nih.gov/articles/PMC10139885/) | usable | — |
| `15980681` | [Examining the Prevalence of Anterior Cruciate Ligament Injuries on Artificial Turf Surfaces Com](https://pmc.ncbi.nlm.nih.gov/articles/PMC11296738/) | fetched_unusable | abstract_only |
| `b4435b8b` | [Lower Extremity Injury Rates on Artificial Turf Versus Natural Grass Surfaces in the National F](https://pmc.ncbi.nlm.nih.gov/articles/PMC11363235/) | fetched_unusable | abstract_only |
| `d955898a` | [Incidence of Musculoskeletal Injuries in Natural and Artificial Turfs during the 2024 First Div](https://pmc.ncbi.nlm.nih.gov/articles/PMC13412916/) | usable | — |
| `dce76d0d` | [Risk of injury in elite football played on artificial turf versus natural grass: a prospective ](https://pmc.ncbi.nlm.nih.gov/articles/PMC2577464/) | fetched_unusable | abstract_only |
| `763934b9` | [A Meta-Analysis of Soccer Injuries on Artificial Turf and Natural Grass](https://pmc.ncbi.nlm.nih.gov/articles/PMC4590909/) | usable | — |
| `c1b8aa4a` | [Association of artificial turf and concussion in competitive contact sports: a systematic revie](https://pmc.ncbi.nlm.nih.gov/articles/PMC7254119/) | usable | — |
| `0d9f5bb3` | [Epidemiology of Anterior Cruciate Ligament Injury on Natural Grass Versus Artificial Turf in So](https://pmc.ncbi.nlm.nih.gov/articles/PMC7376298/) | fetched_unusable | acquired snapshot cannot meet the minimum quote length |
| `198ddf27` | [Lower Extremity Injury Rates on Artificial Turf and Natural Grass Playing Surfaces: A Systemati](https://pmc.ncbi.nlm.nih.gov/articles/PMC8794856/) | fetched_unusable | abstract_only |
| `a13fc8f8` | [Injury incidence is higher on artificial turf compared with natural grass in high school athlet](https://profiles.wustl.edu/en/publications/injury-incidence-is-higher-on-artificial-turf-compared-with-natur/) | usable | — |
| `ee1a112d` | [Lower Extremity Injury Rates on Artificial Turf Versus Natural Grass ...](https://pubmed.ncbi.nlm.nih.gov/35593739/) | fetched_unusable | no_substantive_source_text |
| `a526b85f` | [Examining the Prevalence of Anterior Cruciate Ligament Injuries on Artificial Turf Surfaces Com](https://www.cureus.com/articles/243887-examining-the-prevalence-of-anterior-cruciate-ligament-injuries-on-artificial-turf-surfaces-compared-to-natural-grass-surfaces-in-athletes-a-scoping-review) | unavailable | — |
| `23c0880b` | [A Meta-Analysis of Soccer Injuries on Artificial Turf and Natural Grass - PMC](https://www.google.com/goto?url=CAESbgHEIkXXXNH51UMM49PCslMSkZQz9Y6W_Mz7vpQTCKpTPhpaDq7jLZbmMbKlv_OCUVjIEiPAZXASUOuRZ2Jx6TLjCHU69kHjAl0tT_p9i1oQFv3kuoePFiK8a7erEK5BeU_L9X8jNFwQ4X0QspvI&gsessionid=4Jrtg7URQA9nDgWm7z80C7Zt1MUoLeSk5yu1r56mb5LpdOl5Ja_qNg) | usable | — |
| `231aef52` | [MLS 4-Year Injury Study: Turf vs. Grass](https://www.google.com/goto?url=CAESfQHEIkXXjbmTVroVwpdjQq8YYEjHz6HlN7mNRsgoLI2u-xAdqLbx1DiPGiR9_H8xUTjIDJVIzujAukcx6ahMBApHHd4Eo5l1ayW8IQFWXWsNI-r_ldD1RTKEZOBo6oZRrvZhQXzOvx4viuEdNBsyscyFRSam5guhefvYYBJP&gsessionid=4Jrtg7URQA9nDgWm7z80C7Zt1MUoLeSk5yu1r56mb5LpdOl5Ja_qNg) | usable | — |
| `ceecebea` | [Lower Extremity Injury Rates on Artificial Turf Versus Natural Grass ...](https://www.google.com/goto?url=CAESZgHEIkXXVX94UEFq81oGfLK9mp75rFlTL-zfXZREZ7Z0-0rwidS2PciPT79av_EkyR6YtkDKe76270fwqBQMSCEdnxjjTvCFgt4giSUP4rG6tTCpWcZOT4xTAD94HT-xggRbJ833lw&gsessionid=i77M8NOnSGrYKuzTgaFhKAEEMXJZ5Pif57teO11yXYmKCtf6CZmuvQ) | fetched_unusable | no_substantive_source_text |
| `4a7414c1` | [Lower Extremity Injury Rates on Artificial Turf Versus Natural Grass ...](https://www.google.com/goto?url=CAESZgHEIkXX_OaKDHtM0xs2BrlM8X0kmerdU9tOedgkkGfay6ccBa2lmTH7Bap_xB7hpBFisovPMOkDx42FyXdkzl-4j_tbbfbhYMjbeNQ5HNxxiR8-3n9lsilmpZcjMxUpWONs_vROxQ&gsessionid=i77M8NOnSGrYKuzTgaFhKAEEMXJZ5Pif57teO11yXYmKCtf6CZmuvQ) | fetched_unusable | preview_windows_selected |
| `22028b3b` | [Synthetic Turf Injury Studies - Department of Plant Science](https://www.google.com/goto?url=CAESkAEBxCJF1-oUa_7HbXBa4fGBGRobZNPscHH-aiQTucDYWpKYkHaqtUJomjZGmolg4wBB7btpUvzzY8_1_7m6qe77Y8Y42sDPDd3YGeFrI32ovchB2xBrrWQXeYqfGNQtrTWN7KUgVE5pv986HQgTADtDGZRiQSYxZdMHr2Xv9WuNen68wA7YFICRNVscTuIpfbM&gsessionid=i77M8NOnSGrYKuzTgaFhKAEEMXJZ5Pif57teO11yXYmKCtf6CZmuvQ) | usable | — |
| `a51ef4be` | [Lower Extremity Injury Rates on Artificial Turf Versus Natural Grass ...](https://www.google.com/goto?url=CAEStQEBxCJF10mQEJM5UYZ3twFQ_8emuokw2T4HdP9DsrOlIrWXkj4hBB-nQTq9mtuFu6XPngNDuNdP11osWZoImUypCt7K49-30YVxbiTxlWARwgn7oZmQWi6fFOehLc2rcG3ljn7UElAgdPirFr97TX714bvRQahN5XiiBfSkiCsDYZdOWoK3O1O0LVF2ZdLp314jhhop-zPXPiqpCtUI6H8x7UMItuza1UcaE5XXOeWXyW4cEbeW&gsessionid=i77M8NOnSGrYKuzTgaFhKAEEMXJZ5Pif57teO11yXYmKCtf6CZmuvQ) | usable | — |
| `f96526f2` | [(PDF) Higher shoe-surface interaction is associated with doubling of lower extremity injury ris](https://www.researchgate.net/publication/277722031_Higher_shoe-surface_interaction_is_associated_with_doubling_of_lower_extremity_injury_risk_in_football_codes_A_systematic_review_and_meta-analysis) | unavailable | — |
| `b438b6ba` | [INJURY RESEARCH REVIEW – NATURAL GRASS AND SYNTHETIC TURF PLAYING SURFACES](https://www.sportsfieldmanagement.org/wp-content/uploads/2019/11/Injury-Research-Review-FINAL.pdf) | unavailable | — |
| `be3dfdb5` | [Artificial Turf vs. Natural Grass: Study on Which is Better for High School Sports / University](https://www.uhhospitals.org/for-clinicians/articles-and-news/articles/2019/08/artificial-turf-versus-natural-grass) | usable | — |

These are saved dispositions under the existing classifier. Access walls, abstract-only policy, toolbar/error classification and quote-length gates still affected yield. The capture-classification and source-context changes previously declined by the user were not introduced.

## Priorities suggested by this review

1. **Canonical URL / family identity guard:** prevent challenge-page URLs from becoming scientific publication identities; use the verified article URL or keep identity uncertain instead of merging unrelated studies. This is a local metadata fix, with no extra model calls needed.
2. **Phase-aware budget protection:** retain the hard cap while reserving only work still needed at post-analysis. Log the component reservation amounts so a budget stop is explainable. This is deterministic accounting, not an additional source-verification model stage.
3. **Selection failure handling:** preserve useful rank information or repair mechanical family-order violations before paying for an unchanged retry/falling back to raw Probe priority. Keep the low-value bibliography-only recommendation visible as such.
4. **Final coverage freshness and independence disclosure:** distinguish an early Gap summary from completed source assessments, and link secondary accounts of the same dataset.

This was a read-only review of the run and existing code. No pipeline changes, model calls, new captures, or edits to historical evidence were performed. Only this review document was added.
