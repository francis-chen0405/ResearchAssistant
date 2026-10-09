# Improve website discovery before evidence analysis

Research and proposed experiment design, 2026-10-09. This is a proposal, not a completed implementation or a live quality result. No paid provider calls were made. The user's approximate 60% coverage relative to decent Google results is an experience report, not a measured recall score.

## Objective and scope

Find at least the useful websites available from a straightforward Google search, then improve discovery through the existing v2 rounds. Preserve current models and research rounds initially. Defer a general tool-using controller and post-admission search loop until discovery weaknesses are understood. More expensive models are not the first intervention.

The first deliverable is a comparison of actual websites returned and where they disappear. It does not require the user to supply known missed sources or a large evaluation corpus. Search-result usefulness and evidence admission are separate measurements: a useful website can be worth showing even if an exact quotation has not been admitted.

## Verified implementation facts

- `researchassistant/research/query_compiler.py` quotes every term/phrase in SERP concept groups and sets `exact_match=True`. OpenAlex lexical queries also quote concept alternatives and AND the groups. These are implemented behaviors, not evidence that either setting causes the observed quality gap.
- `providers/serpsearch.py` accepts compiled `exact_match` only when true. It normalizes organic results but does not retain query-correction notices, related searches, sitelinks, or AI Overview citation URLs as separate discovery candidates. The documentation's optional/omitted organic-result field also needs comparison against the adapter's mandatory-list check for genuine empty pages.
- Exa compilation uses `type=auto` and semicolon-separated concepts with parenthetical aliases. `providers/exa.py` returns title, URL and selected metadata; it does not request or retain content highlights in this path. Missing descriptive text may affect triage, but its effect has not been measured. The default excluded-domain list applies to the legacy uncompiled path, not ordinary compiled requests; do not diagnose fresh discovery from that list alone.
- Metadata ranking uses lexical overlap and other deterministic signals. `agents/v2_discovery.py` applies a lane-fair shortlist under both a 60-item round cap and a budget-derived Scout capacity. Acquisition has its own shortlist/caps, followed by source selection and analysis. A provider hit can therefore disappear at multiple distinct points.
- Adaptive novelty compares concepts and search mode, as well as normalized query text. A future deliberate broadening operation using the same concepts needs an explicit identity/novelty rule; changing punctuation must not authorize repeated requests.
- V2 already performs multiple discovery/acquisition/preview/gap-analysis rounds. The narrower missing loop is a new search after final extraction/Analyst/admission outcomes. That is a separate proposal and is not needed to start this work.

Verify these owners against live source when implementing. The advisory graph was ready at source HEAD `27aeb95`; no executable source was changed for this proposal.

## What current provider documentation establishes

1. [SERP Search documentation](https://serpsearch.com/docs) says `exact_match=true` requests Google verbatim search and suppresses automatic spelling correction; its default is false. Query quotes and operators are preserved independently. It also exposes correction notices and several result modules. This establishes a real difference from ordinary search behavior, not a demonstrated recall improvement from changing it.
2. [Google search help](https://support.google.com/websearch/answer/2466433?hl=en) describes quotation marks as exact-match narrowing and documents `site:` and `filetype:`. Use these deliberately for a known phrase, domain, or document, rather than automatically quoting all broad concepts.
3. [OpenAlex search help](https://help.openalex.org/api/searching/) distinguishes exact phrases from unquoted words, supports Boolean expressions, and uses stemming in ordinary `search`. Dropping quotes does not make concept groups optional: unseparated words are ANDed. Broadening needs fewer mandatory concepts or alternative query formulations as well as selective phrase matching.
4. [Exa's official query guidance](https://github.com/exa-labs/agent-skills/blob/main/skills/build-with-exa/references/prompting-and-patterns.md) recommends explicit natural-language intent and query-anchored highlights. [Its API reference](https://exa.ai/docs/reference/search) documents contents options and additional search modes. Neither establishes that paid deep mode beats ordinary Google for these claims; test auto wording first and price any contents/deep experiment separately.

Checked 2026-10-09. Public documentation browsing does not execute the project's configured search providers.

## First experiment: isolate query restrictions

Use six to eight representative claim topics, including ALPR/crime, discrimination and a non-academic policy claim from existing project examples. Add a biomedical topic if PubMed is part of the user's ordinary usage. Write one short, neutral Google query for each. Avoid stuffing every qualification in the claim into that first query.

First compare the same short wording in ordinary Google and the existing SERP provider, without the app's ranker or Scout. Match language/country where possible, record date and settings, and acknowledge personalization/data-center differences. Save the first ten organic URLs, titles and snippets. This distinguishes provider coverage from application behavior.

For the app's concept formulation, run this controlled comparison through the same SERP endpoint, page and location settings:

| Query wording | Ordinary mode | Verbatim mode |
| --- | --- | --- |
| Current concept groups with quoted phrases | Isolates removing verbatim | Current behavior |
| Same groups with unquoted terms | Tests combined relaxation | Isolates removing quotes |

Then compare the best variant with a short human-style query, and with separate concise terminology variants rather than one large alias expression. Keep request/result allowances comparable. Do not compare one new query against a union of many baseline queries without reporting the extra exposure.

Illustrative broad formulations: `license plate readers crime reduction study`; `automatic number plate recognition crime evaluation`. They are proposed wording, not live-verified successful queries. For Exa, separately compare the current concept rendering with a concise intent such as `Studies evaluating whether automatic license plate recognition reduces crime`. Do not assume this wording is superior before observing results.

For each response, identify useful unique pages and group multiple articles about one underlying study. Record relevance and potential directness without requiring completed evidence admission. Do not infer source content from snippets alone; manual inspection of promising pages determines usefulness. Record useful coverage of the Google reference set and additional useful sources separately so different good results are not treated as failures.

## Second experiment: find losses inside the app

Replay captured provider results through current normalization, metadata ranking and shortlist logic. Use frozen Scout outputs from actual pilot observations if comparing model behavior; synthetic decisions cannot establish live Scout quality. Follow each useful URL/work through these stages:

`provider returned → retained/normalized → ranked/shortlisted → Scout decision → acquisition attempted → readable capture → selected → analyzed/admitted → visible`

Use explicit reasons: not returned, normalization exclusion, duplicate alias, shortlist cap, budget reservation, Scout skip, acquisition failure, unusable capture, selection omission, analysis rejection, or display omission. Distinguish exact URL loss from the same work surviving through a different valid publication location.

If most losses happen before provider return, change query formulation/provider behavior. If the provider already returns the websites, fix the relevant filter, allocation, capture or display boundary. Increasing raw result depth alone is not evidence of a fix.

## Candidate changes, selected from observed losses

- SERP: use ordinary mode for broad discovery; retain selective phrase/verbatim searches for known titles or exact terms. Preserve Google's interpretation/correction notice as discovery metadata. A corrected query is visible upstream behavior, not a change to the submitted research claim.
- Query diversity: allocate existing initial/adaptive slots to a short broad query, a concise terminology variant and a precise follow-up where useful. Relax nonessential method/outcome restrictions when they suppress useful results. Keep disabled providers disabled and do not narrow by desired answer sign.
- Native wording: choose phrase matching deliberately for OpenAlex and retain explicit natural-language intent for Exa. Avoid an automatic switch to semantic/deep modes before a separate comparison.
- Retention: if useful top organic results are being dropped, test a protected allocation for the provider's leading results alongside the current ranker. Missing metadata remains uncertainty; provider rank is a discovery signal, not proof. Compare at equal downstream capacity.
- Exa previews: test bounded query-relevant highlights if missing descriptive text causes useful candidates to be skipped. They remain discovery context and cannot bypass source snapshots or quotation checks; include contents charges and failures in accounting.
- Supplemental leads: consider documented related-search suggestions, sitelinks or AI Overview citation URLs only if useful coverage remains missing. Record module origin, deduplicate, bound any extra requests and independently acquire each page. Generated answer text does not become evidence.
- Visibility: if useful websites are already found, surface their discovery/readability status clearly even when they have no admitted quote. Keep them distinguishable from admitted evidence.

## Acquisition clarification: a separate bounded repair

Today `_acquire_cluster` returns after the first successful scrape. The caller subsequently checks usability; it does not resume the location loop after rejecting that capture. Thus a landing page or page-load notice may prevent a known alternate PDF from being attempted. The proposed repair is to try another allowed location/method after a successful-but-unusable capture, within existing exposure limits, preserving every attempt and immutable snapshot. This is different from discovering a URL Google finds and does not justify starting a broad OCR project.

## Implementation and acceptance boundary

Prepare comparisons and fake-transport regressions before changing defaults. Any executable change must version compiler/policy/prompt identity where applicable, retain historical dispatch, preserve incompatible-resume rejection and count every physical request. Intentional broadening must be distinguishable from repetition. Current hard-coded compiler/ranking identity dispatch also needs successor handling; changing an identity string alone is insufficient.

Begin with the SERP ordinary/phrase/verbatim comparison and URL-loss tracing. Expand to other engines and supplemental leads only where the findings justify it. A small pilot is a decision aid, not a parity claim; use additional held-out topics before declaring general improvement. Judge useful top results, reference-source coverage, extra useful sources, readability, cost and time. Do not optimize raw hit count, report length or admitted-source count alone.

No live experiment is authorized or executed by this document. A future pilot needs an explicit bounded provider-call/total-cost allowance; the exhausted historical allowance and existing production per-run ceilings remain intact. This proposal makes no model, app-installation, database, commit or publication change.
