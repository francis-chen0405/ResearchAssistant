# Current research-quality acceptance protocol

Prepared October 11, 2026; approval/preflight recorded October 12, 2026
(America/Los_Angeles). The human explicitly approved the **$2.48 cap**, then chose
**“Collect now; human scores pending.”** [Allowance](allowance.json) freezes the
baseline, queries and assistant nominations. [Result](LIVE_RESULT.md) and
[preflight](preflight.json) record a stop before transport: all four required native
keys were missing, account terms unverified and bounded private collection unavailable.
**Zero paid calls; $0.00 exposure consumed.** The old five-submission allowance is
exhausted; the prior eight-run/$6.48 proposal conveys no permission or price guarantee.

## Frozen baseline and topic allocation

`prepared.json` records exact current controls, discovery policy, model catalog,
reasoning effort, completion limits, provider origins, reservation ceilings and
source identity. These were obtained from current source, not an installed app.
HEAD is `94a241b52f9525cab3aff52d1f85026f081b3e85`, on dirty local `master`.
Source identity is `source-sha256:4a9ce91342ff8933f7942d83dced1cd70b56f77ac80eac017e6a632aab5b2dc4`.
The installed October 9 app is a different artifact. No production files change.

Baseline: standard depth, both research directions; SERP Search, Exa and OpenAlex;
source target 10 per direction/round; metadata depth 20; lexical scholarly search;
expansion enabled. Planner, Gap Analysis, Search Agent, Source Selection and Analyst
use GPT-6 Luna xhigh; Scout and Extractor use Luna high. Reviewer/final rendering
are deterministic. Model exposure is $0.20/run, at most 160 physical calls and
500,000 tokens. All current protection, admission and Round-4 gates still apply.
Provider exposure is separately capped at SERP $0.12/12 requests, Exa $0.18/18
requests, OpenAlex $0.01/10 requests including lookup/expansion. Exa depth-20
reservations normally restrict it to nine requests. Lower remaining budgets bind.

Six development topics: ALPR vehicle theft, ALPR deployment equity, adult CBT and
depression, primary-school homework, cold-climate heat-pump costs, congestion
pricing. Two held-out topics: adolescent sleep/start times and green-roof cooling
energy. Each has an exact claim, short neutral query, concepts and reason for
inclusion. Biomedical coverage uses the same product providers initially; this
does not evaluate PubMed. Economic claims require tariffs/climate/time qualifiers;
equity exposure cannot substitute for causally demonstrated discrimination.

Held-out outcomes must not inform query, ranker, prompt or routing tuning. A later
policy must be specified before their outputs are unblinded. A four-topic pilot
uses development `alpr-crime`, `congestion`, then held-out `school-start`,
`green-roofs`; the remaining topics are unexecuted scope, not hidden successes.

## Reference sets and human rubric

No genuine frozen provider-response bundle was found under repository evaluations,
fixtures or documented verification artifacts. Read-only inspection subsequently
found eight historical native-app runs (September 6–October 2, schema 14). Their
exact saved search/acquisition/plan JSON and model reservation/completion receipts
were exported privately; the database's bytes and mtime remained unchanged.
Derived typed handoffs replay through current normalization/ranking with historical
query dispatch preserved. These are **replayed observations**, outside the
representative/held-out pilot, with transport authenticity unverified. Original
HTTP bodies, complete search/acquisition counts, exact rendered model inputs and
human usefulness/entailment judgments are unavailable in this export. No discovery
recall, model-value or current live-quality claim follows. Known model token/cost
subtotals and recorded reservations stay separate from unknown total/invoice costs.
Historical 38-case integrity and six-scenario discovery corpora remain fixtures.

Every real topic currently has a **pending, non-exhaustive reference set**. Its
useful denominator is unknown. Do not publish numeric live recall from this
prepared manifest. `reference_nominations.json` supplies eight provisional sources
identified through zero-cost public browsing; their contribution and scope need
human review. These are assistant nominations, not application provider observations
or human-confirmed usefulness. The human authorized freezing these candidates
and collecting observations before human scoring. Their byte hashes are frozen in
`allowance.json`; useful-source denominators remain unknown and no numeric useful
recall may be reported until an appropriate human reference set exists. This revision
changes only the reference-before-collection gate; all budget/rate/capture stops remain.
To establish a human reference set, a topic reviewer builds and signs the artifact:
first ten organic URLs from the frozen short ordinary Google query, plus up to five independently nominated primary works.
Record query, time, browser/account state, country/language/location, rank, URL,
title, snippet, public readable source snapshot, work aliases and rationales.
Only human-confirmed useful works enter the locked useful reference list. Save
irrelevant nominations too in the reference artifact. Reference collection uses
public pages without the application's paid API credentials; no subscriptions,
top-ups or metered scrape services. If a reviewer cannot inspect content, abstain.

Ordinary Google is a documented reference sample, not exhaustive ground truth or
a claim of identical data center/personalization. The product sends **no** explicit
SERP country, language or location. Record these as unknown upstream defaults;
match browser settings where possible and disclose residual mismatch. Do not add
unsupported parameters to production adapters to manufacture parity.

Reviewers see randomized source/statement IDs with arm/model/provider rank hidden.
Preserve original independent judgments in hashed judgment artifacts. Two human
reviewers score usefulness, relevance, capture and final statements independently;
disagreements remain unknown until a named adjudicator explains the resolution.
The manifest stores the resolved judgment and links both originals. Assistant
screening is allowed as triage but never counts as a human usefulness judgment.

- Relevance: does the inspected content address the claim's population, intervention,
  outcome and setting? Support/challenge/mixed/negative findings count equally.
- Usefulness: does it add direct evidence, a credible synthesis, methods/limitations,
  authoritative policy facts, or a material counterexample? Record its contribution.
  A snippet alone cannot establish content usefulness.
- Capture: distinguish readable full text, abstract only, partial text, shell,
  blocked and unknown. Exact quotation is a separate check. PDF length/word count
  cannot alone establish usable coverage; inspect tables and necessary context.
- Independence: DOI/publication aliases identify works, not independent studies.
  Give study-group IDs only after checking samples/data/cohorts and cite that basis.
  Distinct articles about one trial remain one study. Otherwise abstain.
- Entailment: split every substantive final assertion, including numeric and causal
  qualifiers. Inspect cited snapshot text and context; score supported, unsupported,
  mixed or unknown. Count unsupported/uncited assertions and contradictions even
  when deterministic admission accepted an item. Admission is not human truth.

Lock/hash human references **before** scored observations. Collection may precede
human scoring under the explicit revision above. A human reference created after
outputs must be labeled post-observation and scored as a sensitivity analysis; it
cannot acquire a preregistered denominator by backdating. Additional useful finds count
separately. An expanded pooled set can be reported only as a separately versioned
post-observation sensitivity analysis; never rewrite the preregistered denominator.
All-web useful-source and true independent-study denominators remain unknown.

The locked scoring artifact follows [reference-schema.json](reference-schema.json).
It contains exact topic/claim identity, work IDs/URLs/rationales, scope, sampling
method, lock time, reviewer and supporting human evidence hashes. The manifest's
scored list/metadata must match these frozen bytes; unrelated notes do not lock a
denominator. Pending reference sets remain unscored. The updated arithmetic fixture
uses this canonical lock; the earlier report is retained in the
[pre-repair archive](../../../docs/archive/2026-10-12-quality-review-state/README.md).

## Isolate discovery, selection, interpretation and admission

`queries.json` freezes five SERP arms per topic, each one page/top ten: current
quoted concepts/verbatim; quoted concepts/ordinary; unquoted concepts/verbatim;
unquoted concepts/ordinary; short human-style ordinary query. The first four form
the quote × verbatim factorial. Endpoint, date window, page and unspecified locale
stay equal. Five queries' union has five times the search exposure of one query;
report per-query and union coverage separately. Use alternate predetermined arm
order by topic; collect all five within 30 minutes or mark the comparison incomplete.
These are standalone experimental requests, not a successor production compiler.
The existing adapter does not support a compiled ordinary-mode action. Collect
the direct ordinary arms via a separately audited experiment transport, with
sanitized exact payload and no automatic retry, never by bypassing production gates.

Four fresh current-pipeline submissions provide the baseline. Capture actual
Planner queries and every original physical request/response, including failures,
pages, retries, expansion, model repair/fallback and acquisition. Keep complete
candidate dispositions through returned, normalized, retained, ranked, Scout,
acquisition, capture, selection, extraction, Analyst, admission and visibility.
Record missing stages as not observed; explain loss by normalization, alias,
shortlist, budget, model skip, capture failure, selection omission or evidence
rejection. A work surviving at a different URL is distinct from exact URL loss.

Freeze production `V2DiscoveryResponse` handoffs with raw provider bytes alongside
them. `--replay` runs current production normalization and rank/allocation locally.
It does not parse raw HTTP anew, run Scout/models, or reconstruct missing transport
receipts. Raw bytes and original handoff lineage are inspected separately. Model
outputs already observed can be replayed as stage artifacts; never generate a fake
model output and label its disposition as an observed model decision.

For complete replay, `discovery_handoff_attempts` maps each exact logical response
file to its successful physical search attempts. `search_attempt_result_paths` maps
each attempt to a frozen typed page-result projection with the exact logical query.
Attempt settings include `query_id`; provider identity and each page's URL/rank
multiplicities must agree with its candidates. Complete canonical result values
(including titles, snippets and metadata) in the aggregate must originate in those
pages, allowing deduplication and dropped results. Later stage retention
dispositions remain separate from provider aggregation. Repeated URLs
from another query/page still need separate returned candidates/dispositions.
Historical handoffs without physical receipts remain replayable with inventory and
lineage explicitly incomplete. Raw HTTP is retained separately and not reparsed.

Model value experiment: on each completed topic, reuse the first Source Selection
input and first Analyst input/output at baseline xhigh. Submit the identical bytes,
schema, snapshot set, completion ceiling and endpoint once at Luna high, at most
eight extra calls total, one call per stage/topic, **$0.03 each**, no repair/retry.
Use hash-equal inputs and blind human scoring to compare useful selected works and
interpretation correctness; report output variability and failures. No new model
family is tested. If a baseline stage did not run or the exact prompt reservation
exceeds $0.03, skip with a reason; do not replace it with an easier input. Reuse
baseline xhigh exposure separately and disclose that only high consumes extra
calls. Discovery rankings stay fixed. This small effort comparison cannot establish
general model superiority or justify routing changes.

For a later policy, retain this baseline bundle and execute new arms only with
fresh authorization. Freeze source/prompt/settings identities for both, use the
same topic/reference/snapshot sets and K=10 per acquisition comparison, disclose
all changes and compare within equal physical/model/token/dollar ceilings. Report
effective budget reductions, incomplete pairs, neutral and negative results; never
replace failures. Same recorded dollars alone do not imply equal search exposure.

## Approved live allowance and enforceable stops

The human approved **at most $2.48 of new aggregate conservative exposure** after
offline validation. This cap is not a guaranteed invoice estimate:

| Component | Scheduled work | Physical ceiling | Exposure ceiling |
| --- | --- | --- | --- |
| Current pipeline | Four fresh submissions | 160 search requests; 640 model calls; 2,000,000 model tokens | 4 × ($0.20 model + $0.31 discovery) = $2.04 |
| SERP factorial/short query | Five arms × four topics | 20 search requests, no retries | $0.20 |
| Frozen-stage effort comparison | Up to eight high calls | 8 model calls; 480,000 reserved tokens in total | $0.24 |
| Acquisition | Public URLs/local capture only | 2,400 acquisition operations across four runs | $0 paid-service exposure |
| Total | Four submissions + comparisons | 180 search requests; 648 model calls; 2,480,000 model tokens | **$2.48** |

Acquisition bound is four rounds × 25 clusters × at most six method/location
operations × four runs. It is deliberately conservative; source target, deadlines,
model protection and cluster/location budgets reduce it. Browser subresources and
redirect hops are not separately enumerated by that operation counter: total HTTP
wire requests are unknown and must not be reported as 2,400. No Firecrawl, paid
OCR, contents/highlights, Crossref extra calls, semantic/deep mode or fifth round.
Expected scheduled work is 20 direct search requests, four submissions and up to
eight additional model calls; adaptive requests/completion are unknown beforehand.
No minimum completion or quality score is promised at the default $0.20 budget.

Public pricing was read October 11, 2026, without application provider credentials:
[Exa](https://exa.ai/docs/admin/pricing) lists auto search at $0.007 up to ten
results plus $0.001 per additional result; 20 results gives $0.017 before extras,
below the repository's $0.02 reservation. [SERP pricing](https://serpsearch.com/pricing)
was rechecked October 12: published top-up rates are at most $0.001/request.
[OpenAlex operation costs](https://help.openalex.org/access/example-costs/) list
keyword search at $0.001/request, single-entity lookup free, and filter lists at
$0.0001/request. Account-specific terms, balances and automatic purchase settings
remain unverified; no account API or dashboard was accessed. The published rates
fit the reservations but do not waive account preflight.
[Luna pricing](https://developers.openai.com/api/docs/models/gpt-6-luna) lists
$0.10 input/$0.01 cached input/$0.125 cache writes/$0.50 output per million standard
short-context tokens, with processing/context premiums. Production reservations
use $0.25 input/$0.75 output and assume no cache discount. These are rate observations,
not invoice reconciliation. Unknown usage/cost must remain unknown in reports.

After approval, verify account rates and official endpoints without metered test
calls; no key/health request may quietly consume the allowance. Require standard
nonregional OpenAI processing, Exa auto/no contents, SERP at no more than $0.01 per
request and OpenAlex at no more than $0.001 per request. If an account, tier,
endpoint, cache-write or other premium can exceed the existing conservative
reservation, **stop before transport**. Do not change production pricing/defaults
to make this pilot fit. No automatic top-up/purchase. Taxes and standing plan fees
are excluded from incremental API exposure and not newly authorized; if incremental
charges cannot be bounded within $2.48, do not start. Invoice total remains unknown.

Maintain a separate durable global allowance ledger: reserve each physical start
before send, retain full reservation for missing/unknown completion, sum exposure
with Decimal, reject a start exceeding either component or aggregate cap. The
production per-run audit remains authoritative inside each run. Every retry or
fallback consumes the cap. Global unknown outcome stops the pilot; do not silently
refund, retry, reset the ledger, replace a failed pair or spend remaining funds on
follow-ups. Known authentication/rate-limit failure also stops the pilot. Stop on
credential leakage, provenance mismatch, source/settings drift, cancellation,
unsupported terms/rates or an uncollectable audit. Hard wall deadline: 45 minutes
per submission including drain, three hours aggregate; reserve two minutes for
shutdown. Report budget/time stops as incomplete observations.

## Credential and data handling

Use existing native credential storage only after explicit allowance approval.
Never read `.env`, dump Keychain contents or copy credentials into reports,
request URLs, shell arguments, prompts, SQLite or exports. Remove API-key query
values and authorization/cookie headers from capture; retain exact non-secret
request bytes and a documented redaction map. Hash content before/after redaction;
an unredacted digest is optional, unredacted secret bytes are never persisted.
Provider bodies and source text are untrusted data. Store isolated run databases
and raw bundles in a local private directory (directories 0700/files 0600), outside
synced repository/OneDrive; do not modify real history. No external upload or
publication. Public repo artifacts contain schemas, fixture data and aggregate
metadata only. Preserve licensed full text privately with URL/time/hash; share
only permitted excerpts/metadata. Record acquisition truncation, inaccessible
content, browser state and source revision dates. If safe redaction changes parser
meaning, abstain and explain instead of asserting exact raw replay.

## Reproduction and acceptance

From the repository root, using the existing backend development environment:

```sh
.venv/bin/python -m evaluations.research_quality --output-dir /private/tmp/prompt14/prepared --replay
.venv/bin/python -m evaluations.research_quality --manifest evaluations/cases/research_quality/fixture_bundle/manifest.json --output-dir /private/tmp/prompt14/fixture --replay
.venv/bin/python -m pytest tests/test_research_quality_benchmark.py
```

For an explicitly identified existing application database, the read-only importer
requires the operator to declare fixture versus replayed-observation origin and a
fresh private directory. It never resumes research or migrates/writes the database:

```sh
.venv/bin/python -m evaluations.import_saved_research --database /absolute/path/to/existing.sqlite3 --origin replayed_observation --output-dir /private/tmp/quality-history-new
```

The October 11 private sample is `/private/tmp/prompt14/history-replay-final/`.
Its metadata/projection lineage, missing audits and unchanged database hash are
recorded in the manifest. Fixtures cannot be imported with a real-observation label.

`schema.json` comes from strict Pydantic contracts; unknown fields, invalid
ownership, changed file/settings/claim hashes, post-observation reference locking,
unowned quotations, non-finite costs and fixture-to-real relabeling fail. Hashes
detect changes, not truth: collector/allowance/human signatures and raw-to-handoff
lineage still need review. The scoring runner has no live adapter, credential integration
or enable-live switch. Its paid-call count is always zero. Separate
`evaluations.research_quality_preflight` checks the approved hashes/current source
first and optionally reads only four named native keys into memory. It saves status
states, never keys or provider exception text, and sends no requests. It always
stops before transport; it does not claim to implement the durable live collector.
Reproduce the failed gate with a fresh private receipt path:

```sh
.venv/bin/python -m evaluations.research_quality_preflight --check-native-credentials --output /private/tmp/quality-preflight-new/receipt.json
```

Exit 1 records a deliberate stop; exit 2 means approval/hash/source validation failed.
Existing receipts cannot be overwritten. Use application Provider setup to supply
missing keys; never paste credentials in chat or substitute plaintext files.

Report per topic/arm/origin, never merge fixture scores into real outcomes.
Reference recall counts unique useful works over the locked non-exhaustive useful
reference set. Precision counts useful unique works over returned/surviving unique
works, with judged precision, coverage and lower/upper bounds for abstentions.
Per-page top-K metrics also give the actual number of returned slots and aliases;
work precision is not slot precision. Extra useful works, exact-URL duplicates,
publication aliases and manually resolved study groups remain separate.
Readable-full-text yield, relevant captures and stage recall are separate from
selection/admission and human final-statement support. Stage metrics apply to the
recorded inventory; incomplete inventory invalidates recall. Time, physical counts,
tokens, known cost subtotal, unknown attempts and reservation exposure are explicit.
Missing total costs/denominators are null, never inferred from displayed totals.

Whole-output statement bounds are null when assertions are missing; explicitly
named `recorded_subset_*` bounds cover recorded assertions only. Work usefulness/
relevance disagreements remain unknown after aliases are filtered. Admission
behavior can be observed while human utility remains untested or partial.
Publication aliases count distinct URLs per work separately from repeated hits.
Saved exports reject bad stage checksums/types/ownership and recognized credential
content before writes. SQLite provenance identifies the pinned committed snapshot,
including WAL, separately from main-file measurements, without source checkpointing.

Acceptance here is a reproducible offline harness and bounded reviewable protocol,
not a live quality pass. The new allowance is approved but credential/account/collector
preflight stopped before any live collection. Live rankings, full-text yield, current
model-selection value, interpretation quality and admission utility remain untested.
No default or model routing may be changed on this evidence.
