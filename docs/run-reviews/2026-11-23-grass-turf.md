# Review of the grass-versus-turf research run

Run: `b206d484-b89e-40d7-a4a0-6edfbbe816bc`. Claim: **Grass is safer than turf**. Started November 23, 2026, 10:34:03.866 PST; completed 10:38:04.095 PST. Audit uses saved run data, 355 persisted artifacts, physical-call receipts, the nine admitted records, captured source text, current inspection output, and relevant pipeline code. No live searches or model calls were made. The saved release hash was revalidated successfully.

## Assessment

The run executed successfully and produced a properly caveated but incomplete research result. It does not establish the broad claim. Its major weaknesses are one consequential source-context error, four false-negative body-text classifications, inconsistent treatment of conference abstracts, and a run-wide search stop following one SERP Search HTTP 500. These matter more than raising the spend or token cap.

The final assessment records 3 supporting, 3 challenging, and 3 qualifying findings, all from support-directed searches. Search direction is not evidence relationship: retaining counterevidence was correct. The counts are publication/finding classifications, not votes or an estimate of the overall balance of literature. The 2013 soccer finding needs correction before those counts are relied upon.

## Configuration and completion

| Setting | Saved value |
|---|---|
| Depth / metadata depth | Standard / 30 |
| Source target | 10 per enabled side per round |
| Direction / tone | Support only / neutral |
| Enabled providers | SERP Search, Exa, arXiv, Serper, Brave |
| Provider request caps | 4 each |
| Model ceilings | $0.20; 1,000,000 tokens; 160 calls |
| Seed expansion | Enabled, but no graph/seed expansion artifacts were executed in this run |
| Search rounds completed | 1 |
| Technical result | Released; persisted release validation valid |
| Research outcome | Incomplete coverage, one unresolved material gap |

Only 14.48% of the model cost ceiling, 11.87% of the token ceiling, and 15.63% of the call ceiling were used. The run did not stop because these caps were exhausted. PubMed and OpenAlex were not enabled.

## Search and provider behavior

| Provider | Dispatched requests | Returned hits | Blocked planned queries | Final unique source credits |
|---|---:|---:|---:|---:|
| SERP Search | 2: one success, one HTTP 500 | 9 | 0 | 0 |
| Exa | 1 success | 25 | 2 | 7 |
| arXiv | 1 empty success | 0 | 0 | 0 |
| Serper | 1 success | 10 | 1 | 3 |
| Brave | 1 success | 10 | 1 | 1 |

Credits overlap when a source was found by multiple providers; they must not be summed as independent sources. The persisted diagnostics show two Brave probe survivors before final canonical deduplication; the final nine-source list credits Brave on one retained source.

The planner produced ten query lanes. Six were dispatched. SERP Search’s second request returned HTTP 500 and was persisted as a failed completion with neither a response hash nor known actual cost. `_unknown_request_outcome` treats that combination as an unresolved reservation. The `unknown_request_recovery="stop"` policy and run-wide reservation guard then blocked two Exa queries, one Serper query and one Brave query before dispatch. There was no second Exa request with an unknown transport outcome, and the six-request diagnostic total is correct.

This is an intentional conservative policy with an overly broad effect for this run: uncertainty about one provider prevented unaffected providers from continuing. The reservation can remain charged against SERP Search while recovery for independent providers is considered separately; retries of the uncertain request should still be prevented unless reconciled.

arXiv worked at the transport level and returned zero hits. Its query used exact natural-grass surface phrases in title/abstract fields, which is a narrow search for this topic. One empty query does not establish that the provider is broken. Exa yielded most retained sources, but it received 25 results and a descriptive query versus 10 results for the web providers; this run is not a controlled ranking-quality comparison.

## Candidate and acquisition flow

54 raw hits → 50 deduplicated/scouted works → 23 capture-shortlisted clusters → 21 clusters with saved content → 10 usable snapshots → 9 unique final sources. Of the other 27 clusters, 17 were cap-prevented and 10 scout-skipped. The nine-source final count is explained by merging two Mass General URLs with the same canonical article and identical snapshot hash.

There were 35 capture attempts: 23 Wigolo attempts and 12 Firecrawl fallbacks. Nine Wigolo captures and one Firecrawl capture were marked readable. The audit’s 21 fetched documents includes content later rejected; it is not 21 usable papers. Two SAGE-hosted sources were unavailable. All nine admitted sources had successful extraction and Analyst calls.

## All nine admitted sources

| Source | Recommended | Saved relationship | Review |
|---|---|---|---|
| [2023 football systematic review/meta-analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC10139885/) | Yes | challenges | Challenges the broad claim in pooled football injury incidence: turf 14% lower (7%–21%). Strong comparative evidence in this set; not all safety outcomes. |
| [2013 soccer meta-analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC4590909/) | No | supports | Material extraction/context error: counted as supports using introductory first-generation-turf background. Its own saved eight-study G3 soccer synthesis reports AT/NG IRR 0.86 (P<.05), with substantial heterogeneity. The study result should be represented as challenging/qualifying the claim. |
| [2020 concussion systematic review/meta-analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC7254119/) | Yes | challenges | Challenges for concussion-only outcomes: turf/grass RR 0.72 (0.58–0.89). Combined head injury/concussion RR 0.89 (0.77–1.04) includes no difference. |
| [ACFAS lower-extremity review synopsis](https://www.acfas.org/lower-extremity-injury-rates-on-artificial-turf-versus-natural-grass-playing-surfaces-a-systematic) | Yes | qualifies | Narrowly favors grass for foot/ankle outcomes; does not settle overall safety. This is a professional-society synopsis of a review, not the underlying full review. |
| [2022 professional rugby injury-burden cohort](https://pmc.ncbi.nlm.nih.gov/articles/PMC9825862/) | Yes | qualifies | Higher injury burden on artificial than natural/hybrid surfaces: 3,082 vs 2,364 days/1,000 hours; incidence did not differ. Natural/hybrid is not an isolated natural-grass comparator. |
| [2020 NCAA soccer ACL conference abstract](https://pmc.ncbi.nlm.nih.gov/articles/PMC7137113/) | Yes | challenges | Challenges for ACL incidence: grass 1.16 vs turf 0.92 per 10,000 athlete exposures; practice drives the difference; matches not significantly different. Abstract-level conference evidence, not a full cohort paper. |
| [2017 elite Italian rugby cohort](https://pmc.ncbi.nlm.nih.gov/articles/PMC5505587/) | Yes | supports | Narrow support: more overuse injuries on turf, but no significant traumatic-injury difference. Limited to elite Italian rugby players. |
| [National Center for Health Research injury explainer](https://www.center4research.org/injuries-related-to-artificial-turf/) | No | supports | Narrow support from a secondary account: NCAA football PCL tears reported roughly three times as common on turf. The primary study was not the admitted source. |
| [Mass General Brigham turf/grass explainer](https://www.massgeneralbrigham.org/en/health-wellness/turf-vs-grass-fields-sports-injury-prevention) | No | qualifies | Qualifies: discusses mechanism and risk factors but explicitly says evidence cannot confirm turf alone causes more non-contact injuries. Context, not an independent comparative outcome study. |

The 2013 source’s own abstract and results were present in the saved capture. The wrong overall impression therefore came from selecting background as the finding, not from lack of access to the study. The Analyst receives the selected quote and its local preceding/following context, rather than automatically receiving the paper’s abstract and conclusion. An exact quote can pass deterministic validation while still giving an unrepresentative account of the source.

The final report appropriately flags unresolved data overlap. Reviews may share underlying studies; six articles hosted on PMC are not necessarily either six independent datasets or duplicates. Canonical URL deduplication worked for the Mass General mirror, but it does not resolve study overlap across reviews.

## Per-source model usage

These figures combine one extraction and one Analyst call per source. Times are individual call durations; sources ran concurrently. They exclude shared planning/scouting/gap/selection costs and all search/scraping fees.

| Source | Input tokens | Output tokens | Total | Extract / Analyst seconds | Recorded model cost |
|---|---:|---:|---:|---:|---:|
| 2023 football systematic review/meta-analysis | 5,683 | 1,465 | 7,148 | 5.85 / 12.18 | $0.001442725 |
| 2013 soccer meta-analysis | 5,837 | 1,785 | 7,622 | 5.99 / 10.65 | $0.001621975 |
| 2020 concussion systematic review/meta-analysis | 5,602 | 2,189 | 7,791 | 6.12 / 16.25 | $0.001794600 |
| ACFAS lower-extremity review synopsis | 4,811 | 1,037 | 5,848 | 3.93 / 7.12 | $0.001119725 |
| 2022 professional rugby injury-burden cohort | 6,300 | 1,969 | 8,269 | 7.13 / 14.09 | $0.001771850 |
| 2020 NCAA soccer ACL conference abstract | 5,331 | 1,908 | 7,239 | 10.01 / 10.83 | $0.001620225 |
| 2017 elite Italian rugby cohort | 5,851 | 1,700 | 7,551 | 6.10 / 14.13 | $0.001581225 |
| National Center for Health Research injury explainer | 5,781 | 1,929 | 7,710 | 4.13 / 13.38 | $0.001686975 |
| Mass General Brigham turf/grass explainer | 6,029 | 2,194 | 8,223 | 8.84 / 12.86 | $0.001850475 |

The 18 source-specific calls cost $0.014489775, roughly half the total model cost. The other seven calls handled planning, four Scout batches, gap analysis and source selection.

## All 23 capture-shortlisted sources

“Rejected” below describes the saved pipeline disposition, not this audit’s judgment that the source lacks useful evidence.

| Source / cluster prefix | Saved disposition | Audit explanation |
|---|---|---|
| [Incidence, Mechanisms, and Severity of Match-Related Collegiate Men’s Soccer Injuries on FieldTurf a](https://journals.sagepub.com/doi/10.1177/0363546516671715) (`39cbe448`) | unavailable | SAGE access/authentication failure. |
| [Epidemiology of Anterior Cruciate Ligament Injury on Natural Grass Versus Artificial Turf in Soccer:](https://journals.sagepub.com/doi/10.1177/2325967120934434) (`7b2c4011`) | unavailable | SAGE access/authentication failure. |
| [Incidence of football injuries sustained on artificial turf compared to grass and other playing surf](https://pmc.ncbi.nlm.nih.gov/articles/PMC10139885/) (`91d7a703`) | usable | Usable; retained and analyzed. |
| [Examining the Prevalence of Anterior Cruciate Ligament Injuries on Artificial Turf Surfaces Compared](https://pmc.ncbi.nlm.nih.gov/articles/PMC11296738/) (`befe74c2`) | fetched_unusable | Confirmed body-classification false negative: saved text includes article body, Methods, Results and tables. |
| [Lower Extremity Injury Rates on Artificial Turf Versus Natural Grass ...](https://pmc.ncbi.nlm.nih.gov/articles/PMC11363235/) (`92d0cb00`) | fetched_unusable | 403/Forbidden body; fallback rate-limited. |
| [Association Between Playing Surface and Anterior Cruciate Ligament (ACL) Injury Risk in the National](https://pmc.ncbi.nlm.nih.gov/articles/PMC13543646/) (`79c3be2e`) | fetched_unusable | Confirmed body-classification false negative: substantial introduction/background, materials/methods and results present. |
| [Risk of injury in elite football played on artificial turf versus natural grass: a prospective two‐c](https://pmc.ncbi.nlm.nih.gov/articles/PMC2577464/) (`b85abede`) | fetched_unusable | Confirmed body-classification false negative: article methods and cohort results present after the structured abstract. |
| [A Meta-Analysis of Soccer Injuries on Artificial Turf and Natural Grass](https://pmc.ncbi.nlm.nih.gov/articles/PMC4590909/) (`c6c881ff`) | usable | Usable; retained and analyzed. |
| [The influence of playing surface on injury risk in italian elite rugby players](https://pmc.ncbi.nlm.nih.gov/articles/PMC5505587/) (`0ffb88e1`) | usable | Usable; retained and analyzed. |
| [The Effect Of Playing Surface On Anterior Cruciate Ligament Injury In NCAA Soccer](https://pmc.ncbi.nlm.nih.gov/articles/PMC7137113/) (`5bfaf6ef`) | usable | Usable; retained and analyzed. |
| [Association of artificial turf and concussion in competitive contact sports: a systematic review and](https://pmc.ncbi.nlm.nih.gov/articles/PMC7254119/) (`da1c9468`) | usable | Usable; retained and analyzed. |
| [Lower Extremity Injury Rates on Artificial Turf and Natural Grass Playing Surfaces: A Systematic Rev](https://pmc.ncbi.nlm.nih.gov/articles/PMC8794856/) (`b26a1d96`) | fetched_unusable | Genuine structured/conference abstract; excluding it under a body-text policy is reasonable. |
| [Epidemiological Comparison of ACL Injuries on Different Playing Surfaces in High School Football and](https://pmc.ncbi.nlm.nih.gov/articles/PMC9083053/) (`886f7bb3`) | fetched_unusable | 403/Forbidden body; not usable paper text. |
| [Increased Risk of ACL Injury for Female but Not Male Soccer Players on Artificial Turf Versus Natura](https://pmc.ncbi.nlm.nih.gov/articles/PMC9382072/) (`2c7a32c7`) | fetched_unusable | Confirmed body-classification false negative: methods and results body, study characteristics and IRRs present. |
| [Influence of playing surface on match injury risk in men's professional rugby union in England (2013](https://pmc.ncbi.nlm.nih.gov/articles/PMC9825862/) (`cbc79ef1`) | usable | Usable; retained and analyzed. |
| [Incidence, causes, and severity of high school football injuries on FieldTurf versus natural grass: ](https://pubmed.ncbi.nlm.nih.gov/15494326/) (`42092f53`) | fetched_unusable | Substantive PubMed abstract, not full paper. Wrong error label triggered by unrelated advanced-features-unavailable banner. |
| [Incidence, mechanisms, and severity of match-related collegiate women's soccer injuries on FieldTurf](https://pubmed.ncbi.nlm.nih.gov/23942283/) (`d2ead8f0`) | fetched_unusable | Cookie-enable landing page only. |
| [Lower Extremity Injury Rates on Artificial Turf Versus Natural Grass Playing Surfaces: A Systematic ](https://pubmed.ncbi.nlm.nih.gov/35593739/) (`e8d5bcf0`) | fetched_unusable | Substantive PubMed abstract, not full paper. Same unrelated banner triggers error label. |
| [Comparing Sports-Related Orthopedic Injury Trends on Artificial Turf and Natural Grass: A 20-Year Na](https://pubmed.ncbi.nlm.nih.gov/40561243/) (`c94253f2`) | fetched_unusable | Cookie-enable landing page only. |
| [Lower Extremity Injury Rates on Artificial Turf Versus Natural Grass ...](https://www.acfas.org/lower-extremity-injury-rates-on-artificial-turf-versus-natural-grass-playing-surfaces-a-systematic) (`822609a4`) | usable | Usable; retained and analyzed. |
| [Injuries Related to Artificial Turf](https://www.center4research.org/injuries-related-to-artificial-turf/) (`983fca5d`) | usable | Usable; retained and analyzed. |
| [Turf vs. Grass Injuries: Which Playing Surface Is Safer for Athletes? / Mass General Brigham](https://www.massgeneralbrigham.org/en/about/newsroom/articles/turf-vs-grass-fields-sports-injury-prevention) (`80a43348`) | usable | Usable duplicate Mass General URL; correctly merged into retained article. |
| [Turf vs. Grass Injuries: Which Playing Surface Is Safer for Athletes? / Mass General Brigham](https://www.massgeneralbrigham.org/en/health-wellness/turf-vs-grass-fields-sports-injury-prevention) (`a8ac88a4`) | usable | Usable; retained and analyzed. |

Four of the eleven fetched-but-unusable sources are confirmed body-parser false negatives. The segmenter deliberately holds Methods/Results headings inside a structured abstract until a recognized article-body boundary appears. It misses “Introduction and background” and full bodies that start directly with Methods, leaving substantial body text labeled abstract. This needs a boundary-detection fix, not blanket acceptance of every structured abstract.

The opposite inconsistency also occurred: the retained NCAA soccer ACL source is a conference abstract with Objectives/Methods/Results/Conclusion but no literal “Abstract” heading in the captured PMC text. The app’s 616-word count covers the whole snapshot, including metadata and navigation; the Objectives-to-Conclusion abstract itself contains about 437 whitespace-separated words. The publisher explicitly labels it Abstract: https://journals.sagepub.com/doi/10.1177/2325967120S00125. The same generic gate labeled it partial body text and accepted it. There is no document-type exception explaining the different treatment. It should be identified and assessed as abstract-level evidence.

Two PubMed abstract captures were incorrectly labeled error because a toolbar said advanced features were temporarily unavailable. The abstract-only body-policy rejection would still be appropriate; this is a diagnostic/content-classification error, not proof that these contain full papers.

## Timing and concurrency

| Interval or activity | Wall duration | Interpretation |
|---|---:|---|
| Whole run | 240.23 s | 4 min 0.23 s |
| Planner call | 29.81 s | Initial plan |
| Initial search dispatch window | 18.28 s | Six physical provider requests, sequentially dispatched |
| Four Scout calls | 33.67 s elapsed | Three concurrent calls initially; fourth overlaps their tails |
| Capture window | 62.30 s elapsed | Overlaps Scout tail, early analysis and gap analysis |
| Early source extraction + Analyst | 18.03 s active | One completed source assessment before gap analysis |
| Gap-analysis call | 46.75 s | Largest single model call |
| Source-selection call | 32.50 s | Sequential after gap analysis |
| Remaining eight sources | 44.43 s elapsed | Four source workers, extraction and analysis overlap across sources |
| Last model completion to run completion | 2.83 s | Admission/final assembly/validation and persistence |

The model-call union is 205.02 seconds, about 85.3% of total wall time. Summing every model call gives 369.58 seconds because concurrent calls overlap; it must not be reported as run duration. The largest model-free intervals were the search window (18.51 seconds between Planner completion and first Scout start) and an 11.10-second capture/selection wait before the first extraction. This was predominantly model-bound rather than idle UI time.

Gap analysis and source selection alone took 79.25 seconds, about one-third of the run. The gap call knew only one completed source assessment and some pending-source excerpts; after all nine analyses, no new model gap-analysis call occurred. The final deterministic assessment retained the earlier unresolved severity/time-loss gap. That is conservative, but the final research plan was not freshly reconsidered against all nine findings.

## Model calls, tokens and cost

| Stage | Calls | Input | Output | Total | Recorded model cost | Sum of call seconds |
|---|---:|---:|---:|---:|---:|---:|
| planner | 1 | 2,066 | 3,100 | 5,166 | $0.001808175 | 29.81 |
| scout | 4 | 13,212 | 9,595 | 22,807 | $0.006448700 | 90.92 |
| extractor | 9 | 28,194 | 4,798 | 32,992 | $0.005922575 | 58.11 |
| analyst | 9 | 23,031 | 11,378 | 34,409 | $0.008567200 | 111.49 |
| gap_analysis | 1 | 10,858 | 5,198 | 16,056 | $0.003956175 | 46.75 |
| source_selection | 1 | 3,691 | 3,572 | 7,263 | $0.002247300 | 32.50 |
| **Total** | **25** | **81,052** | **37,641** | **118,693** | **$0.028950125** | **369.58** |

All 25 model calls succeeded. Scouting and extraction used `gpt-6-luna-high`; planning, gap analysis, selection and evidence analysis used `gpt-6-luna-xhigh`. There were no separate Reviewer or Synthesizer model calls. The saved policy explicitly uses Analyst admission plus deterministic synthesis/validation, and the brief says evidence was not independently reviewed. “Released” means the deterministic release checks passed; it does not certify source representativeness or scientific truth.

There are also nine `model_route_attempts` rows mirroring the nine Analyst calls. Counting them again would inflate the call and token totals. Output token usage is provider-reported usage, not the length of the final visible brief.

The audit records 80,977 cache-write tokens and zero cached-input tokens. Cache writes are included in input usage and must not be added again. This run does not demonstrate input-cache hits. The recorded cost basis is published cache pricing with reported write counts; it is not a verified billing invoice.

The sum of individual call reservations is 599,012 tokens and $0.284921, versus actual usage of 118,693 and $0.028950125. These are cumulative per-call maximum reservations, not simultaneous exposure and not an overrun of the $0.20 ceiling. The final budget reconciles correctly. The source queue initially reserved conservatively for four sources and then used backfill to analyze all nine; no final source was left unanalyzed because of model budget.

The $0.02895 figure excludes paid search and scraping services. Exa reported another $0.022 for its request, so the known recorded model-plus-Exa subtotal is $0.050950125. SERP Search, Serper, Brave and Firecrawl actual charges are not completely recorded; total run cost is unknown.

## Fix priorities

1. **Source-level context verification.** Include the source abstract/conclusion and passage role in evidence analysis; require an explicit check that a quoted introduction/background sentence is not presented as the study result. Replay the saved 2013 soccer paper as a regression case.
2. **Body-boundary detection and document type.** Recover the four substantial body-text captures, recognize introduction/background and direct-to-methods body boundaries, and classify conference abstracts consistently. Keep genuine abstract-only and access-wall safeguards.
3. **Provider failure isolation.** Retain uncertain SERP reservations without automatically blocking independent providers. Separate known HTTP failure, uncertain billing, and interrupted transport; do not blindly retry the same uncertain request.
4. **Final gap reassessment.** Reconsider the earlier gap after all nine source analyses, especially when the remaining gap concerns severity/time-loss and a newly analyzed rugby source directly reports injury burden. Current final coverage remains conservatively incomplete.
5. **Performance tuning after correctness.** Profile the 46.7-second gap call and 32.5-second selector, trim duplicated source/navigation context and evaluate whether xhigh is needed for every role. Preserve factual scope and limitations while benchmarking any speed change.
6. **Cost observability and evidence metadata.** Show search/scrape costs separately from model spend, label conference/secondary sources, expose false rejection reasons, and retain uncertainty about overlap between meta-analyses.

No pipeline code or historical run data was changed during this review. This document records the audit findings; it does not silently relabel or replace the released result.
