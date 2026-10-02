# ALPR saved-run review — 2026-10-01

Subsequent authority: the user approved A–G, now implemented and verified in the [fixes record](alpr-run-fixes-2026-10-01.md). The findings and approval boundary below describe the original read-only review.


Read-only review requested by the user. Findings and proposed fixes are recorded for
their decision; no runtime, installed-app, test, setting, credential, or saved-run
changes were made. No new provider request was issued. Three Luna High helpers
reviewed accounting, pipeline outcomes, and evidence presentation, with primary-agent
cross-checks against current source and typed saved artifacts.

## Cost calculation

Using the user's supplied rates **per million tokens**, assuming all input tokens
are uncached:

| Usage | Rate | Cost |
| --- | --- | --- |
| 250,000 input tokens | $0.10 / million | $0.0250 |
| 70,000 output tokens | $0.50 / million | $0.0350 |
| Total: 320,000 tokens | | **$0.0600 (6 cents)** |

These are the user's corrected counts; they supersede the initial 50,000/15,000
example ($0.0125). The corrected estimate is $0.002047540 higher than the app's
recorded $0.057952460, about 3.4% of the corrected estimate.

These are supplied assumptions, not a new external pricing verification. The current
Luna High/XHigh model presets already use $0.10 input and $0.50 output, with $0.01
cached input. Their higher $0.25/$0.75 reservation caps protect budgets and are
separate from ordinary usage rates. No rate setting was changed.

## Run identity and result

- Claim: `Automated License Plate Cameras reduce crime`.
- Run: `daf3e186-eb9c-42ec-b9ec-d992334a5428`.
- Database inspected with SQLite URI `mode=ro`:
  `~/Library/Application Support/ResearchAssistant/live-runs.sqlite3`.
- Started 2026-10-02 00:39:37 UTC; completed 00:47:58 UTC, about **8 minutes 20 seconds**
  (2026-10-01 local date). Released with no final validation errors.
- Supporting research enabled; challenge research disabled. The latter's absence
  is an explicit run control, not evidence of balanced review.
- **48 physical model calls**, all Luna 6, each with a completion: 45 succeeded and
  3 failed. Failed attempts retain cost and token usage.
- **268,135 recorded total tokens**, usage-estimated model cost **$0.057952460**,
  correctly displayed as **$0.0580**. Remaining model budget $0.442047540 of $0.50;
  remaining tokens 231,865 of 500,000; remaining physical calls 112 of 160.
- **13 discovery queries**, 65 results, **39 acquisition attempts**, 21 successful
  acquisitions and 18 failed attempts (16 unique failed source identities).
- Of 21 source-analysis outcomes: **12 admitted, 2 rejected, 7 failed**. The brief
  uses 12 admitted records, divided into 6 supporting and 6 qualification items.
- All **233 stored artifact payload hashes match**. Typed production/admission
  parsing passed. The deterministic final validator rechecked the stored admissions,
  synthesis, continuation, and reconciliation with the same valid rendered hash:
  `74b9c1da7bb4386c931a108c96898b1da417bad4c2554a387860af1645c4a600`.

### Accounting checks and limits

| Stage | Physical calls | Combined tokens | Recorded usage-estimated USD |
| --- | --- | --- | --- |
| Planner | 1 | 2,688 | 0.000774300 |
| Scout | 4 | 24,773 | 0.006053950 |
| Gap Analysis | 3 | 57,985 | 0.012007400 |
| Search Agent | 2 | 8,155 | 0.002826350 |
| Source Selection | 1 | 20,112 | 0.004434675 |
| Extractor | 20 | 96,981 | 0.016640685 |
| Analyst | 17 | 57,441 | 0.015215100 |
| Total | **48** | **268,135** | **0.057952460** |

Summing physical completions matches the final budget and UI. This establishes
internal accounting consistency, not an independently checked provider invoice.
The full run's input/output/cache splits are not retained. Only 15 completed Analyst
route rows retain that split: 32,021 input, 20,587 output, zero cached input, and
$0.014295000. Two semantically rejected Analyst responses have another $0.000920100
retained in physical accounting but omitted from their failed per-route usage rows.
The other 31 calls have combined tokens/cost only. The user's revised input/output
counts total 320,000 tokens, **51,865 more** than the physical audit's 268,135.
The full provider usage breakdown/account scope is unavailable here, so these values
cannot be exactly reconciled or attributed to a confirmed billing bug. Cached-input
pricing can alter cost but does not itself explain a different combined token count.

The initial reservations across attempts sum to $0.607281000. This is not cumulative
spend: known usage reconciles prior reservations before later dispatch. No global
budget overshoot or omitted failed-call cost was found.

## How the research did

Execution completed and preserved exact internal provenance while excluding failed
or rejected records from the released synthesis. The brief appropriately qualifies
the reported 11% motor-vehicle-theft association and distinguishes investigative
case value, clearance, anecdotes, respondent beliefs, and vendor claims from a
general crime-rate effect. It does not establish that ALPRs causally reduce all crime.

The evidence is mixed and the final coverage assessment remains **partial** for
crime reduction, limitations, and replication/generalizability. Counterevidence
coverage is unavailable because challenge research was disabled. Several articles
discuss the same underlying working paper, so their number is not independent
replication. This assessment uses the captured passages and artifacts, not a new
independent external literature review.

There were real retrieval and model-output limitations: 18 acquisition failures
were classified as 16 authentication/HTTP-access failures and 2 unsupported-content
outcomes. These records do not establish that the user's provider credentials are
wrong. The seven failed source analyses include three per-source token-cap failures
before transport, one bounded extractor semantic failure, two Analyst outputs
missing the required factual statement, and one deterministic qualification failure.
The two unrelated items were rejected. These are fail-closed outcomes, and raising
limits or weakening validators is not an implied fix.

## Findings and proposals awaiting user approval

### A. Unadmitted records appear in the released Evidence panel — confirmed bug

Directly reproduced `_build_v2_evidence_display` against the saved typed artifacts:
**15 cards = 12 admitted + 2 rejected + 1 failed**. The unadmitted cards are the
Springer page-load error, unrelated arXiv crime-topic-modeling abstract, and failed
Denmark analysis. They are absent from the validated synthesis but shown under its
Evidence heading. Their rejected/failed status is visible only after expansion.

Cause: `frontend/api.py:410-446` tests for an Analyst candidate and assessment but
does not require a successful admission/evidence record. Proposal: show admitted
records in this panel and retain failed/rejected items explicitly in the research
trail/source outcomes. Bind the visible accepted statement to its admitted record.
Preserve all immutable history and source survivors.

### B. Search direction is presented as evidence relationship — confirmed ambiguity

All 12 admitted assessments in this run say `relationship_to_claim=qualifies`.
The API omits that field, while `web/app/page.tsx:543` displays “Supporting” from the
support search lane—even on the unrelated rejected cards. The same run direction
also becomes Ledger stance. The six supporting-section items retain their caveats,
but some include contrary/null results or attribution limits.

Proposal: present support-search origin separately from “supports,” “qualifies,”
or “challenges” evidence relationship. A heading/caption improvement is bounded UI
work; changing persisted stance, scoring/placement, or the direction constraint in
`agents/v2_evidence_analyst.py:549-562` is a separate research-policy decision. The
current six/six sectioning obeys the existing score/stance contract; this review
does not treat a policy disagreement as a proven validator corruption.

### C. Stop explanation and gap disclosure disagree with the actual decision — confirmed

The post-Round-3 model explicitly says another support search likely overlaps prior
families and that stopping is **not resolution**. It returns `continue_research=false`
and an empty material-gap list despite three partial coverage dimensions.
Round 4 was evaluated and declined; budgets were not exhausted.

`research_governor.py:152-155` maps either no gaps or no continuation to
`NO_MATERIAL_GAPS`; its explanation says no material coverage gap remains.
The final output instead retains the earlier phase-7 “fixed three-round maximum”/
`hard_round_limit` disclosure. The run fingerprint allows four rounds.
Thus the displayed reason is stale and the governor explanation overstates coverage.
“0 unresolved gaps” accurately counts an empty actionable-gap list but can be read
as complete evidence, contradicting the visible partial coverage assessment.

Proposal: retain the authoritative post-Round-3 stop explanation, distinguish no
useful new search from resolved coverage, and present coverage limits independently
of actionable-search gap count. Do not force Round 4 or invent a budget failure.
Any stricter model rule for retaining unresolved material gaps is a separate
contract/prompt decision; existing saved artifacts must remain unchanged.

### D. Findings lack visible links to their exact evidence — confirmed usability gap

All 12 synthesis Ledger IDs bind to listed sources internally. However, the brief
does not emit inline source/quote links, and `V2EvidenceDisplayItem` omits Ledger IDs
and approved factual statements. The reader must manually match slightly different
wording between the brief and detailed cards. Raw source-family UUIDs do not help.

Proposal: add deterministic citation links from each finding to its admitted quote
and human-readable source label. Keep machine IDs in the research trail/copy detail.
This repairs visible auditability; no broken underlying citation binding was found.

### E. Source outcomes are easy to miss — presentation improvement

“Recommended for deeper analysis” describes selection history, while source cards
ignore the final `source.status`. Among seven recommended sources, one was rejected
and three failed analysis. The result sidebar likewise shows successful acquisition
and provider discovery counts but no compact acquisition/analysis failure summary.

Proposal: show final analyzed/admitted/rejected/failed states alongside selection
status and summarize 21/39 successful acquisition attempts and 12/21 admitted sources.
Keep retries distinct from unique sources. Provider outcomes currently describe
discovery accurately; absence of failure summaries is a visibility gap, not a false
search-error count.

### F. Full token breakdown is unavailable — accounting telemetry improvement

`V2PhysicalCallCompletion` (`providers/v2_budget.py:85-92`) keeps only total tokens
and cost. Failed Analyst route records also lose successfully returned usage when
subsequent objective output validation fails (`agents/v2_evidence_analyst.py:520-543`).
Physical accounting still includes that usage; final cost is not undercounted.

Proposal: preserve input/output/cache splits for future physical calls and retain
returned usage on failed semantic validations. Keep old missing fields unknown and
immutable; do not retroactively estimate the full run's token split. This would allow
the user to check bills against rates rather than only sum opaque cost records.
The corrected user-supplied 320,000-token total versus 268,135 persisted tokens is
an additional reconciliation concern to investigate if those counts are exact and
cover precisely this run, rather than a rounded or wider account usage interval.

### G. Mirrors can count as separate source families — quality limitation

The Exa library working-paper page and PubPub PDF report the same 11.0% effect and
confidence interval under near-identical titles, but receive distinct family IDs
`bad54a23-...` and `27ef7fb9-...`. Only the PDF is recommended. Family identity in
`evidence_portfolio.py:20-34` intentionally keys on canonical/resolved URL, so this
is a limitation of the current identity rule, not a failed invariant.

Proposal for separate approval: identify mirrors/underlying works using trustworthy
DOI or equivalent metadata and disclose shared-study lineage. Do not merge distinct
studies solely because titles or domains look similar, or rewrite historical IDs.

## Verification and boundary

Reviewed using `mode=ro` queries, typed parsing, hash comparison, deterministic
validator replay, pure evidence projection reproduction, and live source checks.
The advisory code graph was last refreshed after the audit source changes; no branch
switch or subsequent runtime edit occurred. Findings were checked against live files.
No new test files or source fixes were made, so no full source-suite rerun was needed
for this inspection. Documentation links and whitespace are checked separately.

The user decides which proposals to authorize. A–G are review identifiers, not
an approved implementation plan. The installed app and saved run remain as inspected.
