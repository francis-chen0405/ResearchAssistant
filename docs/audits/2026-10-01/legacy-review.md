# Legacy, CLI, and evaluation audit — 2026-10-01

## Scope

Reviewed the legacy pipeline, retrieval deduplication, run inspection CLI, offline evaluation entry points, and secondary Python frontends. All reproductions used isolated local fixtures and fake providers. The live MiMo smoke script was read only; it was not executed. No provider, paid, or network calls were made.

Two integration defects were reproduced and corrected:

1. **Concurrent legacy retrieval could scrape the same original URL twice across stances.** Existing coverage proved that sequential duplicate original or resolved URLs are skipped, but it did not overlap support and challenge retrieval. A controlled two-thread fake-scraper reproduction entered the scraper twice for the same URL and returned one duplicate outcome. Retrieval now claims each original URL in-flight under the deduplication lock, lets waiters observe cancellation and retry the dedup lookup, and releases the claim in `finally`; the lock is not held during network acquisition. The regression suite verifies one physical scrape across two stances, claim release and retry after a failed scrape, and continued parallelism for different URLs.

2. **`inspect-run` misclassified fresh-v2 runs as legacy provider runs.** An isolated v2 SQLite fixture had two persisted physical-call starts; the CLI printed zero calls and attempted legacy result validation, returning an invalid-input code for a valid failed v2 result. The CLI now dispatches from persisted v2 pipeline identity and builds its read-only view with the typed snapshot helpers shared with the live controller. It reports physical-call counts, per-metric actual subtotals/completeness, and conservative exposure; legacy format and fallback remain in place when no compatible v2 identity exists. No executor, controller, or provider factory is constructed during inspection.

## Verification

The new regression files are `tests/test_audit_legacy_retrieval.py` and `tests/test_audit_cli_inspection.py`. The legacy race was failing before its fix (`second_entered=True` for the competing same-URL scrape). The CLI regressions were failing before dispatch because v2 calls were shown as zero and the terminal fixture was fed to the legacy validator.

Focused verification after the fixes:

```text
.venv/bin/python -m pytest -q tests/test_audit_legacy_retrieval.py tests/test_phase7.py
28 passed

.venv/bin/python -m pytest -q tests/test_audit_cli_inspection.py
2 passed
```

Combined verification after the final edits:

```text
.venv/bin/python -m pytest -q tests/test_audit_live_service.py tests/test_audit_cli_inspection.py tests/test_audit_legacy_retrieval.py tests/test_phase7.py tests/test_mvp4_cli.py tests/test_mvp5_live_web.py tests/test_mvp6_5_read_only_inspection.py tests/test_status_polling_compatibility.py tests/test_v2_phase12_production.py tests/test_v2_phase14_round_four.py
200 passed, 1 skipped

.venv/bin/ruff check cli.py frontend/live_progress.py frontend/live_service.py agents/supportingresearcher.py tests/test_audit_cli_inspection.py tests/test_audit_live_service.py tests/test_audit_legacy_retrieval.py tests/test_v2_phase12_production.py
All checks passed
.venv/bin/ruff format --check cli.py frontend/live_progress.py frontend/live_service.py agents/supportingresearcher.py tests/test_audit_cli_inspection.py tests/test_audit_live_service.py tests/test_audit_legacy_retrieval.py tests/test_v2_phase12_production.py
All files formatted
```

The one-session read-only connection regression now instruments `frontend.live_progress.read_run`, the location used by the extracted pure builder. Its original same-connection, one-open, and schema-validation assertions are preserved. Repository-wide gates belong to the root integration pass.

## Files reviewed

- `orchestrator.py`
- `agents/planner.py`
- `agents/supportingresearcher.py` (edited for the confirmed concurrent dedup race)
- `agents/opposingresearcher.py`
- `agents/researcher.py`
- `agents/analyst.py`
- `agents/reviewer.py`
- `agents/synthesizer.py`
- `agents/renderer.py`
- `research_governor.py`
- `evidence_core.py`
- `evidence_browser.py`
- `brief_export.py`
- `cli.py` (edited for persisted-v2 inspect dispatch)
- `evaluations/schema.py`
- `evaluations/evaluator.py`
- `evaluations/run_evaluations.py`
- `evaluations/__init__.py`
- `evaluations/README.md`
- `frontend/evidence_browser_app.py`
- `frontend/streamlit_app.py`
- `frontend/live_history.py` (read only)
- `frontend/live_progress.py` (pure shared v2 snapshot builders added)
- `frontend/live_service.py` (compatibility wrapper delegation and early-result polling fix)
- `scripts/mimo_live_smoke.py` (static review only)
- `tests/test_phase7.py`, `tests/test_mvp4_cli.py`, and new audit regressions listed above

The repository has no standalone `researcher_support` package or frontend files named `reader`, `fixture_gateway`, `research_trail`, `export`, `style`, or `view_models`; related persisted evidence and export logic resides in the reviewed `evidence_browser.py`, `brief_export.py`, and current live history/service modules. Next.js UI files and `frontend/api.py` / `frontend/service_manager.py` are assigned to the separate UI and root ownership passes and were not modified here.

## Findings not confirmed

No additional actionable defect was confirmed in the inspected legacy orchestrator, reviewer/synthesis/render paths, research governor, evaluation schema/runner, or secondary Python frontends. The offline evaluation runner only enables live comparison with an explicitly injected provider; no such provider was supplied or invoked.

An inspection boundary issue was independently confirmed for corrupt or non-SQLite files: `LiveResearchController.snapshot` preserves its established `DatabaseCompatibilityError` behavior, while the API originally caught only `KeyError`. The primary integration pass fixed the API mapping to generic HTTP 400 and added an immutable read-only regression; see [API/native review](api-native-review.md). The controller contract is preserved.

## Coverage gaps

- Legacy retrieval deduplication covers identical original URLs across stances. Distinct original URLs that resolve to the same final canonical URL can only be compared after acquisition, so this regression does not prove one scrape for that alias case.
- CLI v2 regressions cover running exposure with incomplete calls and terminal token-complete/cost-incomplete accounting. The pure snapshot builder's complete-both-metrics boundary is separately covered in `tests/test_audit_live_service.py`.
- The live smoke script was reviewed but deliberately not run; live integrations, credentials, app data, full repository tests, packaging, and platform-specific frontend behavior are outside this offline audit evidence.
