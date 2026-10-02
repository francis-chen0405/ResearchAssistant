# Fresh-v2 pipeline audit — 2026-10-01

## Scope and result

Read-only audit of `v2_orchestrator.py`, `research_governor.py`, every `agents/v2_*.py`
runtime module, and the fresh-v2 test modules. The current adaptive-budget/UI fixes were
present in the working tree and were preserved. No implementation or test files were
changed. No new correctness bug was confirmed, so there is no isolated reproduction or
regression fix to propose from this pass.

The current authority plan was
`.agent/plans/reviewer-route-testing-fix-2026-10-01.md`. No separate comprehensive-audit
plan was present in `.agent/plans` or `docs/audits` at review start. This is the initial
area-pass context; the completed comprehensive plan and integration results are
recorded in the [final audit report](README.md). Also read the current
architecture, conventions, decisions, status, handoff, plan index, and desktop operations
guide; relevant detail came from the model-choice, deterministic-concurrency, Round-14,
and research-invariants documents.

## Runtime files reviewed

- `v2_orchestrator.py`
- `research_governor.py`
- `agents/v2_acquisition.py`
- `agents/v2_adaptive_search.py`
- `agents/v2_coverage.py`
- `agents/v2_deep_analysis.py`
- `agents/v2_discovery.py`
- `agents/v2_evidence_admission.py`
- `agents/v2_evidence_analyst.py`
- `agents/v2_extraction.py`
- `agents/v2_final_output.py`
- `agents/v2_gap_analysis.py`
- `agents/v2_initial_planner.py`
- `agents/v2_reviewer_ledger.py`
- `agents/v2_round_four.py`
- `agents/v2_source_selection.py`

## Audit evidence

### Route integration and historical Reviewer compatibility

The fresh call path in `run_v2_production_pipeline` invokes Planner, Scout, Gap Analysis,
Search Agent, Source Selection, Extractor, and Analyst. It does not invoke the historical
Reviewer ledger or the model Synthesizer. The model selectors and `V2RoutingPreflight`
cover exactly those seven active stages. Fresh-stage request builders resolve the stage's
selected alias through the preflight; budget reservations use that same stage route. The
adaptive downstream reserve now iterates configured preflight entries, avoiding the
historical `REVIEWER` enum member that caused the reported failure.

The only fresh-runtime `for_stage(LLMStage.REVIEWER)` consumers are in
`agents/v2_reviewer_ledger.py`, the historical Phase-10 compatibility bridge. That module
uses the legacy all-routes configuration and is absent from the fresh orchestrator path.
The remaining Reviewer references in `v2_orchestrator.py` read old persisted result fields
or infer the stage of an old artifact; they do not request a Reviewer route. This is
consistent with the documented deterministic fresh synthesis and preserved historical
inspection contract.

### Orchestration, identity, budget, retry, and cancellation

Reviewed the four-round orchestration sequence, immutable production fingerprint and
provider contract checks, terminal artifact reuse, stage persistence, and the transitions
from Round 1 through selection, per-source deep analysis, admission, and deterministic
rendering. New runs freeze directions, enabled providers, model routes, ceilings, prompt
hashes, schemas, and semantic policy in identity. Existing terminal artifacts retain their
historical handling. Failed physical calls remain conservatively charged by the budgeted
provider.

Round-2/3 planning has bounded repair attempts, deterministic query novelty and lane caps,
persisted plans/results, Governor authorization, and fail-closed budget checks. Cancellation
is checked around orchestration/provider boundaries. The deep-analysis worker pool dispatches
a budget-safe priority prefix, caps waves at four, returns results in priority order, drains
in-flight work after cancellation, and avoids the aggregate completion artifact on a
cancelled stage. These paths have focused regression coverage listed below; no contradictory
transition or budget behavior was reproduced.

### Source selection, admission, final rendering, coverage, and Round 4

Source selection retains all survivors, validates persisted gap history, and builds a
deterministic queue from configured Extractor/Analyst reservations. Exact extraction verifies
quotes against stored snapshots; Analyst output is bounded and typed; admission independently
rechecks the exact candidate, scope qualification, score, and provenance before creating an
immutable record. Fresh synthesis consumes only admitted records. Final release validation
checks run/survivor identities, direction, recommendation, statement provenance, unresolved
gaps, and coverage disclosure before creating the rendered-output hash.

Round 4 requires a completed, non-degraded Round 3. It binds cumulative round context and
claim coverage, persists a typed Governor decision and reservation before Search-Agent
execution, limits lanes and queries, uses a fresh post-Gap budget snapshot, and reconciles
coverage only through the exact targeted query and admitted evidence chain. No path to a
fifth round was found. Governor precedence is explicit and fail-closed for cancellation,
terminal failure, degraded Gap Analysis, duplicate-heavy output, unproductive opportunity,
lack of novelty, and insufficient reservation.

### Historical Reviewer-ledger behavior

Read the Phase-10 bridge and its tests. It validates the persisted source and provenance chain,
uses the historical MiMo-v2.5-Pro Reviewer route, consumes/reconciles its bounded model attempt,
and admits only exact validated Reviewer-approved records. Its artifacts remain a separate
compatibility format from fresh analyzer admission. The historical bridge is not covered by
the new seven-stage selected-route configuration, by design of the active-stage model set;
the fresh path does not call it.

## Test coverage reviewed

Reviewed the test inventory and relevant assertions in:

- `tests/test_v2_phase12_production.py` — full pipeline/restart, selected-route downstream
  reservation, no fresh Reviewer request, Round-4 authorization and completion/failure,
  budget, cancellation, identity, diagnostics, and terminal behavior.
- `tests/test_v2_phase14_round_four.py` — Governor decisions, reservations, query caps,
  semantic gap identity, coverage linkage, cumulative context, and reconciliation.
- `tests/test_v2_deep_analysis_concurrency.py` — worker bounds, completion ordering,
  safe-prefix reservation, restart checkpoints, cancellation drain, and source failures.
- `tests/test_v2_phase1_contracts.py` through `tests/test_v2_phase11_final_output.py` —
  typed contracts, routing compatibility, initial plan, discovery, acquisition, Gap Analysis,
  adaptive continuation, queue planning, evidence analysis, historical Reviewer, and output.
- `tests/test_v2_phase13_analyzer_admission.py` — no fresh Reviewer metadata, deterministic
  synthesis, failed/rejected admission, and source artifact resume.
- `tests/test_v2_problem2_budget_reconciliation.py` — physical-call audit reconciliation,
  dense sequence and conservative unknown usage.
- `tests/test_v2_discovery_provider_adapters.py` and `tests/test_mvp11_research_governor.py`.
- `tests/test_stage_model_choices.py` — all 42 stage/choice payload, route, and mock-transport
  combinations, route identity, pricing, credentials, and budget bounds.

## Coverage gaps to keep visible

- The 42 model-choice tests exercise each stage's route and transport directly. They do not
  drive one full production run for every stage/choice combination. Current production-path
  integration coverage is representative and checks selected downstream routes and the
  no-Reviewer invariant. This is a test-scope observation, not evidence of a route defect.
- Historical Reviewer-ledger unit coverage uses the historical complete-route configuration;
  there is no compatibility test that invokes that old model-backed bridge with a seven-stage
  selected configuration. Fresh code should continue to avoid that call path, and historical
  resume/inspection must continue to rely on saved artifacts.
- This audit did not run the repository test suite. It made no provider/network calls and did
  not access real application data or credentials. The report records source and test review,
  not fresh execution evidence.

## Missed coverage

None identified within the assigned runtime modules and fresh-v2 test inventory. The separate
legacy orchestrator, non-v2 agents, and CLI were outside this audit wave by instruction.
