# Corrective plan: Gap Analysis → Adaptive Search reliability

Status: implementation explicitly authorized after the 2026-09-12 planning request.
The user's “implement” instruction activates this narrowly scoped corrective work.
Implementation and offline verification are complete; Mac delivery checks are recorded below.
No paid research or changes to historical run contents are part of this correction.

## Outcome

Supporting-only research must receive a valid gap assessment after each applicable
round. A repairable search-planning mistake gets one bounded opportunity to recover.
If research stops, the report preserves known evidence gaps and explains the stop.
Successful execution must never be confused with proof of the user's claim.

Keep supporting-only as a first-class setting. There is no evidence that enabling
challenging research would fix these failures. Additional supporting searches can
explore definitions, mechanisms, populations, independent sources, and evidence
boundaries without changing the requested direction.

## Evidence and confidence

Analysis used the two persisted runs previously inspected in the local history and
the live source at master `a2ede2a`. The graph was consulted as an advisory map; its
freshness could not be established through the exposed tools, so source inspection
is authoritative. Neither run has been replayed with paid providers.

| Observation | Diagnosis | Confidence / limit |
| --- | --- | --- |
| `7ec1d8bc-8dcb-453a-a3af-f388f2cd25a9`: supporting-only; initial coverage focus empty; Gap Analysis stopped after Round 1 citing missing focus and absent later rounds | The initial-planner prompt promises an application default that the initial handoff does not supply. Early gap analysis also loads a prompt written around post-Round-3 context. | Observed output and live source agree. We cannot prove a corrected prompt would necessarily choose continuation. |
| `bc08bee8-0021-4751-b0d5-523488769977`: supporting-only; Gap Analysis requested continuation for `gap-effect-direct-association`; Search Agent response rejected as a repeated/trivial query; no Round 2 search ran | Semantic validation is fail-closed, but the caller provides no feedback-and-repair opportunity. | Confirmed rejection category. The rejected proposal was not persisted, so the exact query and collision partner are unknown. |
| Latest report has no unresolved gaps despite that material gap | Early final-output logic treats an admitted source's relevant Gap IDs as resolved Gap IDs. Coverage map is also absent without post-Round-3 reconciliation. | Source confirms the unsafe closure rule. Regression fixtures must isolate the exact path; relevance does not establish resolution. |

These are separate failures in one handoff, not simply a provider outage or an
insufficient API balance. In the latest run the model call returned; the application
then rejected its plan. A valid final release establishes integrity under existing
checks, not that the claim received strong or complete support.

## Source map

- `prompts/v2_initial_planner.md` and `agents/v2_initial_planner.py`,
  `_assemble_initial_plan`: promised default versus forwarded empty focus.
- `prompts/gap_analysis.md` and `agents/v2_gap_analysis.py`,
  `build_v2_gap_analysis_input` / `run_v2_gap_analysis`: early-round context and prompt.
- `agents/v2_adaptive_search.py`, `_plan_round`, `_run_round`,
  `_validate_and_assemble_plan`, `queries_are_materially_new`: single proposal,
  validation, persistence, and terminal stop.
- `agents/v2_round_four.py`, `_claim_coverage_specification`, `_plan_round_four`:
  existing application default and separately governed Round 4.
- `v2_orchestrator.py` and `agents/v2_final_output.py`, `_unresolved_gaps`:
  gap transport, reconciliation, and misleading early closure.
- `model_research.py`, typed persistence modules, live progress projections, and
  `tests/test_v2_phase7_adaptive_search.py`: contracts, audit, UI, and regressions.

## Decisions

1. Preserve strict validation. Do not accept duplicate queries, invent Gap IDs,
   silently switch directions/providers, or manufacture evidence.
2. Repair the whole proposal once with actionable feedback. Do not add an automatic
   deterministic fallback query: lexical novelty does not establish research value.
3. Keep current global call, token, cost, provider, and round ceilings. Recovery can
   consume remaining allowance; it cannot increase it or spend the downstream reserve.
4. Keep older runs immutable and readable. New prompts/source/policy require new
   runs under existing fingerprint rules. Do not reopen a completed failure in place.
5. Keep Round 4's existing Governor authority unchanged. Initial recovery scope is
   Round 2 and Round 3; shared validation diagnostics must not add Round 4 calls.
6. No new dependencies or database migration are planned. Use strict, typed,
   immutable artifacts in existing storage where compatible; verify this before coding.

## Work package 1 — Establish regressions and correct gap inputs

First add offline reproductions of both observed paths. The repeated-query fixture
must be labeled synthetic because the historical rejected proposal is unavailable.
Retain sanitized input/output facts sufficient to reproduce the control flow; do
not copy credentials, whole private databases, or unrelated source content.

Extract the application-owned claim-component default into a small shared helper,
or an existing appropriate contracts module. Fresh initial plans with no
effect/association focus receive the exact claim as the default component. Preserve
validated optional components without duplicates. Do not import the entire Round 4
specification into early rounds: its evidence-audit dimensions have separate rules.
Do not infer a mechanism, population, or ethical conclusion from claim wording.
Do not retrofit defaults during historical deserialization.

Make gap instructions explicitly respect `completed_round`. Round 1 evaluates only
Round 1; Round 2 evaluates available cumulative context; post-Round-3 retains its
cross-round requirements. Use an explicitly versioned round-aware prompt/renderer
with conditional sections and tests of each rendered request. Ensure early inputs
carry the intended focus and applicable prior gaps; do not merely change prose.
Validate supplied dimensions and enabled directions at the appropriate boundaries.

Separate stopping search from resolving uncertainty. A lack of a useful new query,
budget, or provider does not prove a gap is closed. Preserve prior assessments when
continuation ends. Audit the current prompt instruction to return no gaps on stop:
it must not erase known gaps; typed stop/searchability state must distinguish these.

Acceptance: an empty optional model focus cannot leave a fresh Round-1 assessment
without its application default; early prompts never demand nonexistent rounds;
support-only fixtures never enable challenge. Legitimate early stopping remains valid.

## Work package 2 — Make rejection explainable before adding retries

Persist a typed planning-attempt record before the physical call and a typed outcome
after it. Include round, attempt number, request/prompt identity, relevant artifact
IDs, physical-call linkage, candidate if schema-valid, and validation findings.
Reuse the existing physical-call accounting rather than creating another ledger.
Schema failures receive bounded diagnostics; never persist raw secrets or an
unbounded provider response solely for debugging.

Give validation failures stable codes: repeated query, disabled direction/provider,
unknown or mismatched Gap ID, empty executable plan, and schema failure. For novelty
failures include candidate index, matched query reference, history versus same-batch
origin, and the lexical rule that matched. Preserve the existing novelty threshold;
do not present it as a semantic similarity measurement.

Explicitly document capacity handling. Initially retain whole-proposal validation
and existing overflow behavior, including duplicate checks, to avoid silently changing
acceptance. Test overflow and same-batch collisions. Explain this to the repair model
and request a proposal within the actual caps. A future pruning policy is separate.

Acceptance: a future failure identifies exactly what was rejected and why, without
executing any part of the rejected plan or exposing credentials in the UI.

## Work package 3 — One budgeted repair for Round 2/3

The state sequence is: request → persist attempt → call → validate → persist accepted
plan → execute searches. On a repairable schema or semantic rejection, persist its
outcome, refresh budget/cancellation state, and permit one repair call. The repair
request contains the original bounded context, rejected candidate when available,
structured errors, previous queries, exact Gap IDs, enabled lanes, and remaining caps.
Every repaired plan passes the same complete validation before execution.

Maximum: two physical Search Agent attempts per affected round, including the first.
Count any lower-level retry against that same allowance; audit wrappers to prevent
multiplicative retries. Do not retry authentication/configuration failures, cancelled
work, exhausted budgets, absent gaps, or exhausted providers. Transport/unknown-outcome
handling stays within existing conservative accounting and recovery rules.

Recompute the full repair reservation from its rendered request and a fresh shared
budget snapshot. Preserve mandatory downstream allowance in calls, tokens, and cost
as required by current policy. Keep the deep-analysis per-source allowance separate.
If repair cannot be afforded or fails, retain completed work, stop adaptation with a
precise typed reason, and continue downstream only if existing gates permit it.

Crash safety is part of this work, not a later enhancement: consumed attempt slots
survive restart; unknown outcomes retain reservations; stored valid plans are reused;
no provider search runs before accepted-plan persistence. Use existing idempotent
search checkpoints to prevent replay of completed work. Resume requires compatible
fingerprints and explicit existing controls. Exhausted repair cannot restart a loop.

Acceptance: a duplicate-first/valid-second fixture reaches Round 2 exactly once;
duplicate-first/duplicate-second stops honestly; no invalid plan produces searches;
budget and restart fixtures demonstrate the physical-attempt bound.

## Work package 4 — Preserve uncertainty through final output

Remove relevance-as-resolution from the fresh early-round path. Transport the latest
available coverage assessment and identified material gaps through selection,
admission, synthesis, validation, UI, and export, including stopped/failed adaptation.
Retain Gap identity and assessment round. Do not erase a prior gap because a later
step failed or returned no new directions.

Use a conservative early-round policy: without explicit validated resolution proof,
a known gap remains unresolved/unverified. Admission of a source or inclusion of a
Gap ID in provenance is insufficient. Distinguish an early strategy assessment from
a verified final coverage finding in names and presentation. Preserve the existing
stronger Round 4 reconciliation contract, including targeted-query and admitted
analysis requirements; do not generalize its proof rules by implication.

Audit final-output validators alongside construction. They must catch a disappearing
known gap, rather than recomputing and approving the same flawed closure rule.
Historical stored reports remain byte-stable; introduce a fresh policy/version path
where necessary instead of reinterpreting old results during read/export.

User-facing examples: “Refining follow-up searches” during repair; “Follow-up search
stopped after two invalid plans. Results use the sources already collected” on final
failure. Display the unresolved evidence requirement next to results. Do not add
technical rejection payloads to normal UI or imply an automatic rerun will succeed.

## Verification matrix

| Area | Required cases |
| --- | --- |
| Gap context | Empty focus; preserved explicit focus; Round 1/2/3 prompts; support-only, challenge-only, both; valid early stop; stop with unresolved prior gap |
| Validation | Exact/reordered/one-token duplicate; cross-provider history duplicate under current policy; same-batch duplicate; cap overflow; invalid provider/direction/Gap ID; empty plan |
| Repair | Valid first attempt; invalid then valid; two invalid; malformed schema; no provider; unaffordable repair; cancellation; underlying retry accounting |
| Recovery | Crash before/after call outcome; unknown usage; accepted-plan persistence; resume after rejection; completed search reuse; no extra attempt after exhaustion |
| Reporting | Relevant admitted source does not close gap; missing gap assessment disclosed; early-stop gap survives UI/export; valid Round 4 closure still works; historical read/export unchanged |
| End-to-end | Offline support-only production orchestration with both failure fixtures; successful repaired Round 2; honest partial result after failed repair; release integrity unchanged |

Run targeted regressions after each work package, then `pytest`, `ruff check .`,
`ruff format --check .`, and `git diff --check`. Run frontend lint/types/build and
offline browser acceptance for progress/results changes. Do not lower assertions
or acceptance criteria. Report current results, not the prior 942-test baseline as
if rerun. Confirm applicable nested instructions before frontend edits.

## Delivery sequence and completion criteria

Implement in four reviewable increments: gap contracts/prompts with regressions;
typed diagnostics; bounded recovery with accounting/restart tests; honest reporting
with UI/export tests. The user supplied explicit corrective-phase authority with
“implement”, extending the Phase 3 boundary for this correction. Record approved decisions and
actual checks in the plan index, STATUS, HANDOFF, and relevant architecture/decisions.
If committing, use the user's requested master branch; do not push without authority.

Rebuild the packaged backend and frontend, verify packaged identity and offline smoke
checks, and produce a new Mac installer. Verify the installed application contains
that build before asking the user to evaluate it. Changing source alone does not
update the installed app. Preserve the history database and credentials.

Only after offline acceptance, an optional newly authorized, explicitly budgeted live
support-only run can assess real query usefulness. It must be a new run, with the
repair audit and unresolved-gap reporting inspected afterward. It is not necessary
to spend credits to establish the control-flow fix. Do not infer permission for paid
research from earlier isolated credential-test authorization.

Completion means the reproduced defects are prevented, failure remains bounded and
visible, old data remains unchanged, and the shipped build is verified. It does not
promise every claim has strong supporting evidence or every run needs another round.

## Separate follow-ups

The latest workflow also warrants separate investigations into acquisition accepting
browser/error pages, model-specific cache pricing/accounting, and the long extraction
timeout. They affect quality, cost, and duration, but did not cause the observed
Search Agent semantic rejection. Do not bundle speculative fixes into this change.
In particular, elapsed time alone cannot distinguish an inactivity timeout, streaming,
or Mac sleep; capture appropriate timing evidence before changing timeout policy.

## Implementation and verification, 2026-09-14

Implemented the four work packages. Fresh initial plans receive the exact-claim default;
the complete typed plan is now persisted atomically with its relational projection, and
readback cross-checks both. This fixes the additional restart loss of coverage discovered
during implementation, without adding database columns or changing old stored payloads.

Fresh early gap inputs carry a versioned strict coverage policy. The round-aware prompt
and Round-2 handoff preserve that policy and prior Gap identity. Stop outputs retain the
existing no-new-search-directions contract; historical gap records and coverage assessments
remain available separately, so stopping does not erase previously identified gaps.

Round 2/3 planning stores immutable attempt starts and typed outcomes, with request hashes,
rejected candidates and diagnostic codes. Attempt IDs link to physical-call records. One
schema/semantic repair is allowed; actual adapter schema/JSON/truncation failures are
classified separately from authentication and transport failures. Restart never reissues
an unknown-outcome call or resets the allowance. Stored accepted outcomes recover without
another model call. Round 4 retains its one governed planning call and original limits.

Budget checks use fresh snapshots for repairs and Round-3 entry, protecting calls, tokens,
and cost. The production fixture formerly labeled as protecting Round-3 budget actually
expected entry using stale capacity; its assertions now require the correct earlier stop
and no Round-3 planner call. Other fixture changes supply both rejected attempts and reuse
stable semantic Gap IDs. No validator, assertion, or acceptance criterion was weakened.

Fresh selection handoffs opt into conservative gap reporting and carry the latest strategy
coverage assessment. Relevance no longer resolves a gap; absent coverage is disclosed as
unavailable. Final validation rejects disappearing gaps and altered coverage. Historical
selection handoffs default to legacy reporting. Persisted-final comparison now projects
gap types correctly, preserving restart with nonempty unresolved gaps.

Verified: 959 Python tests passed, 2 existing skips; Ruff lint/format and diff checks;
frontend lint/types/static build; offline browser acceptance including repair limitations
and coverage; visual review of the result; rebuilt frozen backend/native smoke including
isolated credentials, settings, authenticated local services and shutdown. No paid calls.
Native Windows and public-release signing/notarization remain outside this local delivery.
See `docs/verification/adaptive-search-reliability.md` for packaged delivery evidence.

Mac delivery completed: DMG and ZIP integrity checks passed; packaged and installed window
smokes passed. `/Applications/ResearchAssistant.app` contains the new backend/frontend/prompt,
with the prior bundle retained as a temporary backup. History/preferences were not replaced.
Installers are in `desktop/dist/adaptive-reliability/`. Stop at this corrective boundary.
