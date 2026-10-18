# Test map

Run commands from the repository root with the backend development environment:
`python -m pip install -c desktop/constraints.txt -e "./backend[dev]"`.
Use `.venv/bin/python` (Windows: `.venv\Scripts\python.exe`) if the environment is
not activated. Tests use offline fixtures/fake providers by default; existing
platform and explicitly opted-in checks retain their skips.

## Full collection and focused checks

```sh
python -m pytest --collect-only -q
python -m pytest
rg --files tests -g 'test_*.py'
```

Root `pyproject.toml` discovers every `tests/test_*.py`, including milestone and
review suites. The table is a starting map, not an exclusive suite list. Older
`phase`, `mvp`, `mlp`, `v2_phase` and `audit` names describe when regressions were
introduced; many span multiple current owners. Keep them in full collection.
Assertions, fixture bytes and cross-test helpers retain their existing meanings.

| Subsystem / current owner | Focused starting files in this directory |
| --- | --- |
| Contracts, types, repository boundaries, distribution/resources | [neutral ownership/serialization](test_contract_ownership.py), [type contracts](test_type_contracts.py), [boundaries](test_repository_boundaries.py), [distribution](test_distribution_resources.py), `test_cleanup_boundaries.py`, `test_repository_build_review.py` |
| Discovery policies, normalization, metadata ranking and product integration | `test_discovery_*.py`, `test_metadata_*.py`, `test_product_discovery_pipeline.py`, `test_v2_discovery_provider_adapters.py` |
| Query compilation/execution, durable pages, retention and provider bounds | `test_query_*.py`, `test_v2_*provider*.py`, `test_v2_metadata_pages.py` |
| Seed expansion / OpenAlex neighborhoods | [runtime/evidence chain](test_seed_expansion_runtime.py), [identity/replay review](test_seed_expansion_review.py), [shared limits](test_seed_expansion_limits.py), `test_openalex_neighborhood.py`, `test_neighborhood_planning.py`, `test_graph_neighbor_adaptive_handoffs.py` |
| Acquisition, Probe and exact source previews | `test_acquisition_*.py`, `test_preview_*.py`, `test_claim_source_previews.py`, `test_ranked_acquisition_integration.py`, `test_v2_phase5_acquisition_probe.py` |
| Research orchestration, stages, concurrency, Governor and admission | `test_v2_phase*.py`, `test_v2_deep_analysis_concurrency.py`, `test_v2_post_analysis.py`, `test_pipeline_selection.py`, `test_mvp11_research_governor.py`, `test_repository_agents_review.py` |
| Evidence, historical reads, brief/PDF exports and lineage | `test_historical_reads_phase3.py`, `test_pdf_exports_phase3.py`, `test_v2_evidence_display.py`, `test_study_lineage.py`, `test_source_display.py`, `test_mvp8_exports.py`, `test_audit_evidence_provenance.py` |
| Storage, recovery, locks, accounting and compatibility | `test_database_*.py`, `test_metadata_cost_reservations.py`, `test_status_polling_compatibility.py`, `test_private_import_files.py`, `test_mvp6_8_persistence_accounting.py`, `test_repository_storage_review.py` |
| Renderer wire schemas and offline HTTP payload compilation | [frontend contracts](test_frontend_api_contracts.py), `test_api_module_split.py` (unchanged route/OpenAPI/offline fixture) |
| API/live lifecycle, resume and credentials | `test_api_module_split.py` (saved OpenAPI/offline contract, route uniqueness, import and snapshot ownership), `test_service_lifecycle_atomicity.py`, `test_live_resume_status.py`, `test_mlp3_api.py`, `test_mlp2_credentials.py`, `test_audit_api_boundaries.py`, `test_audit_live_service.py` |
| Desktop process ownership, settings, UI and renderer | `test_desktop*.py`, `test_frontend_discovery_diagnostics.py`, `test_phase7_frontend.py`; native/browser commands below |
| Model routing, pricing and reservations | `test_stage_model_choices.py`, `test_model_cache_pricing.py`, `test_v2_phase2_routing.py`, `test_audit_provider_budget.py`, `test_v2_problem2_budget_reconciliation.py` |
| Source-lead read-only access, stopped runs, artifact ownership and visibility | `test_source_leads.py`, `test_source_leads_review_fixes.py`, `test_source_leads_evaluation.py`, `test_provider_adapter_conformance.py`; `python -m evaluations.source_leads --output-dir /private/tmp/source-leads` |
| Research-quality observation benchmark, provenance and unknown denominators | `test_research_quality_benchmark.py`, `test_research_quality_metrics_review.py`, `test_research_quality_reference_replay.py`, `test_observation_safety.py`, `test_saved_research_import.py`, `test_research_quality_preflight.py`, `test_source_discovery_evaluation.py`, `test_discovery_evaluation_transport.py`; [bounded quality protocol](../evaluations/cases/research_quality/PROTOCOL.md) |
| Broader historical pipeline/CLI/release coverage | `test_phase*.py`, `test_mvp*.py`, `test_mlp*.py`, `test_repository_runtime_review.py`, `test_v2_phase12_production.py` |

Patterns in the table are discovery hints. Use concrete files from `rg --files`
with `python -m pytest`; quoted wildcards are not pytest file arguments.

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

```sh
npm --prefix desktop test
npm --prefix desktop run smoke:shutdown
node --test desktop/acquisition/cache-policy.test.cjs
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
`desktop/configuration-race-smoke.cjs`, `desktop/audit-api-smoke.cjs` and
`desktop/history-race-smoke.cjs`. These cover workflow/directions/cost/provenance,
keyboard/reduced motion, stale configuration, sequential polling/recovery,
ordered preference commits and database/run/result/trail ordering. They can also
be invoked individually. The contract tests compile real offline successful
responses against generated renderer types; Python-only environments without
frontend dependencies skip the Node compilation, while frontend CI installs them.

Native/frozen checks (`desktop/smoke.py`, `desktop/ui-smoke.cjs`,
`desktop/shutdown-electron-smoke.cjs`, `desktop/upgrade-smoke.py`) require the actual
resources/platform described there; source checks do not establish installer acceptance.

`test_wigolo_cache_policy.py` checks exact pinned acquisition staging and rejects
unreviewed upstream bytes. The native cache test requires the locked standalone
Node/Wigolo dependencies; it reproduces replacement-write FTS drift, verifies
derived-index repair without changing content/vectors/migrations, and tests
healthy/repeated initialization and refusal on core corruption or unrelated errors.

For packaging changes run `python scripts/verify_distribution.py --constraints desktop/constraints.txt`.
For offline quality/integrity fixtures see [evaluations](../evaluations/README.md).
Required lint/format/whitespace checks are in [conventions](../docs/project/CONVENTIONS.md#packaging-and-verification);
[STATUS](../docs/project/STATUS.md) owns actual results and untested platforms.
