# Test map

Run commands from the repository root with the backend development environment:
`python -m pip install -c desktop/constraints.txt -e "./backend[dev]"`.
Use `.venv/bin/python` (Windows: `.venv\Scripts\python.exe`) if the environment is
not activated. Tests use offline fixtures/fake providers by default; existing
platform and explicitly opted-in checks retain their skips.

## Full collection and focused checks

```sh
python -m pytest tests --collect-only -q
python -m pytest tests
rg --files tests -g 'test_*.py'
```

`tests/pyproject.toml` discovers every `tests/test_*.py`, including milestone and
review suites. The table is a starting map, not an exclusive suite list. Older
`phase`, `mvp`, `mlp`, `v2_phase` and `audit` names describe when regressions were
introduced; many span multiple current owners. Keep them in full collection.
Assertions, fixture bytes and cross-test helpers retain their existing meanings.

| Subsystem / current owner | Focused starting files in this directory |
| --- | --- |
| Contracts, types, repository boundaries, distribution/resources | [neutral ownership/serialization](test_contract_ownership.py), [type contracts](test_type_contracts.py), [boundaries](test_repository_boundaries.py), [distribution](test_distribution_resources.py), [standalone source](test_source_archive.py), `test_cleanup_boundaries.py`, `test_repository_build_review.py` |
| Discovery policies, normalization, metadata ranking and product integration | `test_discovery_*.py`, `test_metadata_*.py`, `test_product_discovery_pipeline.py`, `test_v2_discovery_provider_adapters.py` |
| Query compilation/execution, durable pages, retention and provider bounds | `test_query_*.py`, `test_v2_*provider*.py`, `test_v2_metadata_pages.py` |
| Seed expansion / OpenAlex neighborhoods | [runtime/evidence chain](test_seed_expansion_runtime.py), [identity/replay review](test_seed_expansion_review.py), [shared limits](test_seed_expansion_limits.py), `test_openalex_neighborhood.py`, `test_neighborhood_planning.py`, `test_graph_neighbor_adaptive_handoffs.py` |
| Acquisition, Probe and exact source previews | `test_acquisition_*.py`, `test_preview_*.py`, `test_claim_source_previews.py`, `test_ranked_acquisition_integration.py`, `test_v2_phase5_acquisition_probe.py` |
| Research orchestration, stages, concurrency, Governor and admission | `test_v2_phase*.py`, `test_v2_deep_analysis_concurrency.py`, `test_v2_post_analysis.py`, `test_pipeline_selection.py`, `test_mvp11_research_governor.py`, `test_repository_agents_review.py` |
| Evidence, historical reads, brief/PDF exports and lineage | `test_historical_reads_phase3.py`, `test_pdf_exports_phase3.py`, `test_docx_exports.py`, `test_v2_evidence_display.py`, `test_study_lineage.py`, `test_source_display.py`, `test_mvp8_exports.py`, `test_audit_evidence_provenance.py` |
| Storage, recovery, locks, accounting and compatibility | `test_database_*.py`, `test_metadata_cost_reservations.py`, `test_status_polling_compatibility.py`, `test_private_import_files.py`, `test_native_storage_durability.py`, `test_native_windows_security.py`, `test_mvp6_8_persistence_accounting.py`, `test_repository_storage_review.py` |
| Renderer wire schemas and offline HTTP payload compilation | [frontend contracts](test_frontend_api_contracts.py), `test_api_module_split.py` (unchanged route/OpenAPI/offline fixture) |
| API/live lifecycle, resume and credentials | `test_api_module_split.py` (saved OpenAPI/offline contract, route uniqueness, import and snapshot ownership), `test_service_lifecycle_atomicity.py`, `test_live_resume_status.py`, `test_mlp3_api.py`, `test_mlp2_credentials.py`, `test_audit_api_boundaries.py`, `test_audit_live_service.py` |
| Desktop process ownership, settings, UI and renderer | `test_desktop*.py`, `test_frontend_discovery_diagnostics.py`, `test_phase7_frontend.py`; native/browser commands below |
| Model routing, pricing and reservations | `test_stage_model_choices.py`, `test_model_cache_pricing.py`, `test_v2_phase2_routing.py`, `test_audit_provider_budget.py`, `test_v2_problem2_budget_reconciliation.py` |
| Source-lead read-only access, stopped runs, artifact ownership and visibility | `test_source_leads.py`, `test_source_leads_review_fixes.py`, `test_source_leads_evaluation.py`, `test_provider_adapter_conformance.py`; `python -m evaluations.source_leads --output-dir /private/tmp/source-leads` |
| Research-quality observation benchmark, provenance and unknown denominators | `test_research_quality_benchmark.py`, `test_research_quality_metrics_review.py`, `test_research_quality_reference_replay.py`, `test_observation_safety.py`, `test_saved_research_import.py`, `test_research_quality_preflight.py`, `test_source_discovery_evaluation.py`, `test_discovery_evaluation_transport.py`; [bounded quality protocol](../evaluations/cases/research_quality/PROTOCOL.md) |
| Broader historical pipeline/CLI/release coverage | `test_phase*.py`, `test_mvp*.py`, `test_mlp*.py`, `test_repository_runtime_review.py`, `test_v2_phase12_production.py` |

Patterns in the table are discovery hints. Use concrete files from `rg --files`
with `python -m pytest tests`; quoted wildcards are not pytest file arguments.

`test_contract_ownership.py` compares the pre-Prompt-12 schema/config/enum fixture
and old/new object aliases, validates exact search serialization and exercises
compiled-request validation with providers/agents/research imports blocked.
`test_historical_reads_phase3.py` exercises recognized recorded formats and released
hashes; its fresh-process checks block historical orchestration during API/CLI
inspection, trails and export, while checking unchanged database bytes/mtime.

`test_backend_hotspot_compatibility.py` retains pre-Prompt-13 schema/configuration/
enum fingerprints, class/pickle and public alias identity, and resolves stage schemas
with execution imports blocked. Its resume check rejects the recorded pre-split source
identity before calls or database rewrites. The storage reader-boundary regression in
`test_database_read_paths_phase3.py` invokes every public reader against a never-created
path and proves each reaches the shared boundary without creating the database.

The R37–R52 regressions include `test_stage_pair_checkpoint_resume.py`,
`test_retained_reviewer_checkpoint_resume.py`, `test_fresh_quote_occurrences.py`,
`test_discovery_provenance_and_metadata_review.py`, `test_admission_render_wording.py`,
`test_native_evidence_browser_integrity.py`, `test_retained_retrieval_review_fixes.py`,
`test_query_scale_benchmark_fixture.py`, `test_older_evaluation_output.py` and methods
cases in `test_preview_structure_review.py`. Historical schema fixtures remain
unchanged; compatibility tests verify exactly the approved versioned additions before
comparing all preceding schema bytes. The query-scaling benchmark generates validated
schema-16 fixtures, refuses Round-4 data and compares current schema without weakening
runtime validation.

## Find tests for an owner

For `researchassistant.research.seed_expansion`, start with the module's
`select_seeds`, `offer_expansions` and `execute_expansion` functions. A fresh graph
`search_graph` followed by inbound `trace_path(include_tests=true)` exposes callers
and integration tests. Verify those paths/imports against live files. Text search
also finds shared fixtures and policy use that a call trace may miss:

```sh
rg -l '\bseed_expansion\b|\bexecute_expansion\b|\boffer_expansions\b' tests -g 'test_*.py'
python -m pytest tests/test_seed_expansion_runtime.py tests/test_seed_expansion_review.py tests/test_seed_expansion_limits.py
python -m pytest tests/test_product_discovery_pipeline.py tests/test_graph_neighbor_adaptive_handoffs.py tests/test_openalex_neighborhood.py tests/test_neighborhood_planning.py
# Narrow a collected file to named behaviors:
python -m pytest tests/test_seed_expansion_runtime.py -k 'graph_neighbor or resume or budget'
```

The three owner files cover owned seeds, full evidence propagation, cancellation,
identity aliases, replay/forgery rejection and shared request/cost/retention limits.
Product integration checks disabled expansion; adapter/planning tests cover the
neighbor transport and authorized handoff. For another owner, replace the module
and function terms, then inspect the matching tests before selecting them. Neither
text search nor a graph trace proves exhaustive coverage; run the full suite too.

## Desktop and renderer checks

Approved full-review regressions are in `test_saved_result_integrity.py`,
`test_public_source_transport.py`, `test_discovery_transport_bounds.py`,
`test_pdf_worker_deadline.py`, `test_api_shutdown_owner.py`,
`test_database_schema_integrity.py`, `test_research_quality_output.py`, the
research-quality lineage/metrics tests, and metadata-ranking tests.
`test_bounded_resolver.py` exercises killed DNS helpers, bounded slots/output,
unrelated-directory startup and real transport timeout/cleanup. Source/model
header/trickle/redirect budgets, concurrent request isolation and unknown-usage
accounting are in `test_provider_absolute_deadlines.py`. IPv6 normalization,
historical identity dispatch and numeric source acquisition are covered by
`test_ipv6_discovery_identity.py` and `test_public_source_transport.py`.
Source shutdown
also exercises an active interrupted resume without refunding its unknown attempt.
`frontend/scripts/hook-regressions.test.cjs` compiles the actual hooks for retry and
active-run reconnection, preference hydration/retry, import ownership, pending key
actions and current-selection configuration refresh (17 checks). `desktop/acquisition/network-policy.test.cjs` checks pinned
upstream integration. `network-proxy.test.cjs` checks HTTP/CONNECT/upgrade rejection,
pinned peers and owned shutdown. `network-policy-smoke.cjs` uses real Chromium with
generated public worker content and an owned private HTTP/WebSocket sentinel.
Dedicated/shared workers remain enabled; no upstream source requests occur.
These checks do not establish Windows or
packaged installer acceptance. See the [review fixes](../docs/verification/full-review-fixes-2026-10-15.md).

```sh
npm --prefix desktop test
npm --prefix desktop run smoke:shutdown
node --test desktop/acquisition/cache-policy.test.cjs desktop/acquisition/network-policy.test.cjs desktop/acquisition/network-proxy.test.cjs
python frontend/scripts/generate_api_contracts.py --check
python -m pytest tests/test_frontend_api_contracts.py
pnpm --dir frontend lint
pnpm --dir frontend exec tsc --noEmit
RESEARCHASSISTANT_DESKTOP=1 NEXT_PUBLIC_RESEARCH_API_URL= NEXT_TELEMETRY_DISABLED=1 pnpm --dir frontend exec next build --webpack
```

With already installed dependencies in an offline workspace, pass
`--config.verify-deps-before-run=false` to pnpm to suppress its implicit dependency
reinstall. Normal setup still uses the frozen-lockfile install above. Use the declared
pnpm 11.19.0; a different global version may attempt a package-manager download.

The independent frontend job and reusable runner exercise the real static UI
against mocked APIs. Install only the existing locked browser runtime (without
lifecycle scripts or bundled acquisition/native builds) when it is not present:

```sh
npm ci --prefix desktop/acquisition --ignore-scripts --no-audit --no-fund
node desktop/acquisition/node_modules/playwright/cli.js install chromium
pnpm --dir frontend smoke:offline
```

Linux CI uses `install --with-deps chromium`. The runner reuses
`desktop/frontend-smoke.cjs`, `desktop/frontend-poll-smoke.cjs`,
`desktop/configuration-race-smoke.cjs`, `desktop/preferences-race-smoke.cjs`,
`desktop/audit-api-smoke.cjs` and
`desktop/history-race-smoke.cjs`. These cover workflow/directions/cost/provenance,
keyboard/reduced motion, stale configuration, pending key inputs and late-save model
refresh, delayed/failed/retried preference loading, edit-preserving owned imports,
sequential polling/recovery,
ordered preference commits and database/run/result/trail ordering. They can also
be invoked individually. The contract tests compile real offline successful
responses against generated renderer types; Python-only environments without
frontend dependencies skip the Node compilation, while frontend CI installs them.

Native/frozen checks (`desktop/smoke.py`, `desktop/ui-smoke.cjs`,
`desktop/shutdown-electron-smoke.cjs`, `desktop/upgrade-smoke.py`) require the actual
resources/platform described there; source checks do not establish installer acceptance.

On a disposable Windows NTFS environment, run:

```powershell
python -m pytest tests/test_native_storage_durability.py tests/test_native_windows_security.py tests/test_desktop_shutdown.py -v
python desktop/windows-shutdown-electron-smoke.py
```

The first command uses real files, hard links, protected DACLs, a restricted-token
access denial, unique Credential Manager test targets, child processes and native
Jobs. The five upgrade interruption hooks inject timing around actual operations;
they do not simulate physical power loss. Existing API-mocked ordering tests remain
separate from the native checks. The second command needs installed desktop Electron
dependencies; it uses the production main with an accelerated test clock and disposable
backend stubs, checking exact owned handles and an unrelated sentinel.
`desktop/windows-installer-smoke.py` additionally requires a disposable GitHub Windows
runner, an actual built NSIS candidate and a read-only Actions token to retrieve its
SHA-bound previous test artifact. It does not use a user's installed app or data.
[Prompt 17 verification](../docs/verification/windows-ci-durability-2026-10-13.md)
owns the exact runner/revision/results and physical power-loss limits; added commands
alone do not establish that a packaged smoke passed.

`test_wigolo_cache_policy.py` checks exact pinned acquisition staging and rejects
unreviewed upstream bytes. The native cache test requires the locked standalone
Node/Wigolo dependencies; it reproduces replacement-write FTS drift, verifies
derived-index repair without changing content/vectors/migrations, and tests
healthy/repeated initialization and refusal on core corruption or unrelated errors.

For packaging changes run `python scripts/verify_distribution.py --constraints desktop/constraints.txt`.
For offline quality/integrity fixtures see [evaluations](../evaluations/README.md).
Required lint/format/whitespace checks are in [conventions](../docs/project/CONVENTIONS.md#packaging-and-verification);
[STATUS](../docs/project/STATUS.md) owns actual results and untested platforms.

R27–R29 regressions cover actual redacted HTTP error envelopes and generated types,
DOCX XML representability with unchanged released text/hashes, and active/interrupted
discovery diagnostics. `desktop/frontend-poll-smoke.cjs` verifies rendered saved counts
and warnings during the running state.

`test_provider_attempt_integrity.py` rejects checksum-valid completion/operation
contradictions through audits, counters, status, page/lead inspection and replay,
with unchanged database bytes/mtime and existing unknown-cost behavior.

`test_v2_resume_integrity.py` covers cached production/final release hashes, recognized
historical keys, six completed-stage interruptions, immutable input checks and
preservation of original budget snapshots and unknown physical reservations.

`test_v2_checkpoint_resume.py` interrupts nine selection/adaptive checkpoint prefixes
with an advancing clock, verifies unchanged original artifact bytes/timestamps and
physical audit prefixes, and requires successful bounded resume.

`test_admission_checkpoint_resume.py` covers atomic source admission, legacy
relational-only interruption recovery, contradictory records and transaction rollback.
`test_four_round_survivor_capacity.py` covers actual >75-source balanced production,
100-source current/75-source historical contracts, exact old-policy resume and
read-only shortlist fallback/integrity. `test_cli_configuration_redaction.py` checks
secret-bearing input/context/extra-key redaction before database/provider setup.

`test_bounded_stage_checkpoint_resume.py` cuts real Scout/Gap Analysis intent,
outcome and aggregate commits with an advancing clock; it verifies cumulative
attempt limits, input drift, zero-budget completed replay and conservative unknown
physical reservations. `test_relationship_rendering_review.py` covers both search
directions, all three admitted relationships, existing indirect warnings, source
ownership, historical v2/v3 rendering/hashes and Analyzer-only template admission.

`test_selection_planner_checkpoint_resume.py` covers Source Selection and initial
Planner intent/outcome/publication interruptions, exact request ownership, original
selection estimates/budgets, exhausted-attempt replay and conservative unknown usage.
It includes actual generated production and validated historical projection recovery.
`test_checkout_launcher_readiness.py` executes the actual checkout launcher against
isolated process/transport doubles: stalled API/web checks, refused listeners,
successful opening and owned-child cleanup with an unrelated surviving process.
The compatible-resume status test now pauses before execution: an unknown initial
Planner intent must never be dispatched again, even under matching controls.
