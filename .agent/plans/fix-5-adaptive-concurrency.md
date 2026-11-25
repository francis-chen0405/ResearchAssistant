# Fix 5: adaptive stage concurrency

Implementation and the combined offline review cover all five scheduling/search fixes.
The current user request authorizes verification, packaging, commit and push. No paid
provider calls or changes to user research databases are part of this review.

## Integration

`providers/run_scheduler.py` owns one typed policy and transient run control state.
`BudgetedV2LLMProvider` creates the run owner; initial and follow-up capture coordinators
receive that same owner. There is no scheduling model call or Settings surface.

| Stage | Initial / maximum | Expansion interval | Block expansion at downstream waiting count |
| --- | --- | --- | --- |
| Scout | 4 / 6 batches | 25 seconds | 8 captures |
| Capture | 4 / 6 source tasks | 5 seconds | 8 extractions |
| Extraction | 4 / 6 admitted sources | 7 seconds | 10 analyses |
| Analysis | 5 / 8 extracted sources | 13 seconds | None |

Demand is running plus ready work, with capacity waiters counted as waiting. Expansion
requires every condition continuously, including two waiting tasks and a reservable
allowance; timers reset on loss of any condition. Shrink after 30 seconds of demand
below the control limit never raises a limit or cancels work. Source and capture
eligibility, early half-allowance, family/mirror ownership and dispatch order remain
under their existing owners. Coordinator events and a two-second fallback tick drive
recalculation. Control time uses `monotonic`, independently of persisted wall time.

Final Extraction and Analysis have separate pools and ready queues. An immutable
source dispatch plus its persisted extraction result is the durable dependent-stage
queue; resume recovers the same artifact before attempting pending Analysis. The
`owned` source-envelope ledger includes extraction, waiting Analysis and active
Analysis, and releases only after durable terminal source result persistence. It does
not reserve the whole source a second time at the transition. Failed extraction is
terminal bookkeeping rather than ready Analysis. Early assessment uses the same stage
functions with separate queues, including the non-overlap checkpoint path, retaining its original four-source ceiling and each
source's cost ceiling across both stages. Frozen assignment/dispatch order owns history,
not completion order.

One run owner admits at most ten model requests across all routes and attempts.
Planner/Gap Analysis waiters precede other eligible requests; other model stages rotate
with FIFO order within a stage. Waiting admission owns no physical reservation or
fresh attempt journal. `dispatch_intent.py` carries a transient context-local callback
from existing attempt owners to admission, excluded from all saved request identities.
Actual request usage, admitted capacity and waiting demand are separately inspectable
through `scheduler.snapshot()`. Slots are released before physical accounting completion
writes, with idempotent cleanup on all exits. Atomic physical reservations remain at
the original locked budget boundary; unknown usage is never refunded.

Explicit model HTTP rate limits / overload signals halve the provider limit to at
least one. Provider labels group routes without exposing credentials. New dispatch
waits at least 30 seconds and honors a longer delta-seconds or HTTP-date Retry-After.
Recovery adds at most one slot after each 30 seconds of successful operation;
non-overload failures reset recovery observation without halving capacity. This adds
no retry. Generic network, schema and inaccessible-source failures are not overload.
Capture task admission is separate from a shared six-transport semaphore. Primary and
fallback acquisition services use their own effective capacities and the same overload
control. Service waits park the transport and precede fresh capture-attempt journals;
ordinary source-host errors do not prove service overload. Browser
parking releases the actual transport; the single browser and existing host constraints
remain. Fallback retrieval stays inside the same capture lease. Transports and parked
tasks have separate counts. Exceptional coordinator exit wakes blocked model dispatchers
before executor draining. All worker persistence uses existing independent connections
and short transactions.

New Scout plans contain at most six candidates. Recorded sizes 8, 15 and 20 remain
accepted, including the original fallback for plans predating stored size. Frozen
plans are never repartitioned. Actual rendered batch reservations still cover both
attempts; early pending-Scout protection, follow-up/Round-4 estimates and live source
projection consume the saved/current batch size. Completion ceilings are not derived
from batch count and remain unchanged. The affordability helper defaults to six and
allows explicit historical sizes.

## Starting working tree (recorded before edits)

```
 M backend/src/researchassistant/agents/adaptive_planning.py
 M backend/src/researchassistant/agents/capture_overlap.py
 M backend/src/researchassistant/agents/evidence_checkpoint.py
 M backend/src/researchassistant/agents/post_analysis_round.py
 M backend/src/researchassistant/agents/round_four_planning.py
 M backend/src/researchassistant/agents/v2_deep_analysis.py
 M backend/src/researchassistant/agents/v2_source_selection.py
 M backend/src/researchassistant/contracts/research_planning.py
 M backend/src/researchassistant/contracts/research_selection.py
 M backend/src/researchassistant/contracts/source_recovery.py
 M backend/src/researchassistant/research/v2_orchestrator.py
 M docs/project/ARCHITECTURE.md
 M docs/project/DECISIONS.md
 M docs/project/STATUS.md
 M tests/README.md
 M tests/test_v2_phase8_source_selection.py
?? backend/src/researchassistant/agents/followup_context.py
?? backend/src/researchassistant/agents/pending_source_priority.py
?? backend/src/researchassistant/contracts/followup_context.py
?? docs/run-reviews/2026-11-23-artificial-turf-injuries.md
?? docs/run-reviews/2026-11-23-grass-turf.md
?? tests/test_pending_source_priority.py
```

The pre-existing source-selection shortcut, gap priority, rolling dispatch and follow-up
context changes remain in place. The list above records files that predated Fix 5;
the combined review additionally supplies scheduler and replay regressions.

## Fix-5 files

New: `providers/run_scheduler.py`, `providers/dispatch_intent.py`, this plan.

Additional edits to pre-existing dirty files: `agents/adaptive_planning.py`,
`agents/capture_overlap.py`, `agents/evidence_checkpoint.py`,
`agents/round_four_planning.py`, `agents/v2_deep_analysis.py`,
`agents/v2_source_selection.py`, `research/v2_orchestrator.py`,
`docs/project/{ARCHITECTURE,DECISIONS,STATUS}.md`, `tests/README.md`.

Previously clean implementation files changed: `agents/adaptive_execution.py`,
`agents/v2_discovery.py`, `agents/v2_evidence_analyst.py`, `agents/v2_extraction.py`,
`agents/v2_gap_analysis.py`, `agents/v2_initial_planner.py`,
`agents/v2_stage_checkpoint.py`, `agents/v2_acquisition.py`,
`providers/{llm,mimo,v2_budget,acquisition,firecrawl,scraper}.py`,
`research/discovery_policy.py`. Guidance also updates `docs/project/CONVENTIONS.md`
and `.agent/PLANS.md`. All implementation paths above are under
`backend/src/researchassistant/`.

## Review checklist and existing owners

Focused tests cover the checks below; the complete suite is the final integration
gate. Fixtures explicitly choose either all-fit or constrained model-selection work
while retaining historical schemas, replay checks and conservative unknown usage.

- [x] One/two ready tasks start only one/two tasks; zero demand starts none.
- [x] Continuous expansion at 25/5/7/13 seconds, reset on any condition loss;
      downstream waiting thresholds 8/8/10 exclude active and unauthorized work.
- [x] Thirty-second shrinking preserves the initial control floor and active work.
- [x] Ten admitted requests across stages and provider routes;
      pending Planner/Gap priority and rotation among other stages.
- [x] Explicit model/acquisition-service overload halves the correct shared provider, honors Retry-After,
      freezes growth, and recovers at most one slot per successful 30 seconds;
      invalid output/network/access failure does not halve it.
- [x] Extraction-to-Analysis retains one source envelope while dependent work waits;
      early allowances and final all-fit / normal selection remain unchanged.
- [x] Cancel while waiting for model, browser or transport capacity: no fresh attempt
      consumed, no slot leak/deadlock, active writes drained, no aggregate completion.
- [x] Fresh six-source layouts, final partial batch, both attempt estimates,
      follow-up/Round-4 affordability and live cards; 8/15/20 saved plans replay intact.
- [x] Interrupted extraction, pending Analysis, source dispatch/result and physical
      attempt recovery preserve identities, order and unknown reservations.

Start with `test_v2_deep_analysis_concurrency.py`, `test_source_loss_recovery.py`,
`test_ranked_acquisition_integration.py`, `test_pending_source_priority.py`,
`test_v2_phase8_source_selection.py`, `test_bounded_stage_checkpoint_resume.py`,
`test_selection_planner_checkpoint_resume.py`, `test_stage_pair_checkpoint_resume.py`,
`test_v2_checkpoint_resume.py`, `test_v2_resume_integrity.py`,
`test_provider_absolute_deadlines.py`, `test_audit_provider_budget.py`,
`test_v2_problem2_budget_reconciliation.py`, `test_discovery_*.py`,
`test_selection_recovery_repairs.py`, `test_type_contracts.py` and identity/boundary owners.

Self-check: focused Ruff lint/format, repository dependency-boundary guard and
`git diff --check` / `git diff --cached --check`. Final results are reported in chat.
Runtime regressions use controlled clocks, actual independent SQLite workers and
offline provider fixtures. The combined review preserves follow-up input variants,
reuses a terminal Analyst reservation without dispatch, and retains query/gap links
when source selection is skipped. Live throughput, native app startup, clean-machine
installation and human research-quality acceptance remain separate checks.
