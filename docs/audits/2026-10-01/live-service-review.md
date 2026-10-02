# Live service audit — 2026-10-01

## Scope and result

Reviewed the live service, persisted progress projection, contracts, and history reader for usage accounting, route/direction state, polling identity, and historical physical-call artifacts. No provider calls, network requests, real app data, credentials, schema changes, or dependency changes were used.

Three defects were reproduced with isolated SQLite fixtures and corrected:

1. **Reserved exposure was presented as actual usage.** Running snapshots used the conservative budget exposure as the known subtotal, while terminal snapshots also marked exposure complete and reported it as an exact total. A terminal artifact can be incomplete or contain nullable usage, and its embedded budget can disagree with the physical-call audit. The snapshot now derives known per-metric subtotals, completeness, exact totals, physical call count, and conservative exposure from `read_v2_physical_call_audit`. Exact totals are set only for terminal runs whose audit has a completion and non-null usage for every call in that metric. Exposure still uses known usage where available and the original reservation otherwise. The same accounting is used for terminal-result and persisted-progress snapshots.

2. **A completed pre-persistence worker result could disappear.** `_evict_completed_run` cached the Future result only when the database file did not exist. If initialization created a database but the worker failed before persisting the requested run, the early result was evicted and a subsequent poll returned 404. Completed Future results are now retained in the existing bounded early-result cache; snapshot reads still prefer authoritative persisted run state.

3. **Failed terminal v2 snapshots lost persisted route directions and overstated progress.** A result without final output defaulted to support-only directions, and enabled sides were shown as completed. The terminal projection now recovers immutable directions from the persisted fingerprint, uses persisted directional artifact counts, and reports the terminal classification for enabled directions. The manifest-only terminal path applies the same status and accounting behavior.

The one-shot early-result response remains intact when no database file was created. When initialization did create a database but no requested run was persisted, the bounded early result remains available on repeated polls; a persisted run supersedes and clears that cached result. A test covers repeated polling with an existing database.

Fresh-v2 `inspect-run` was also confirmed to use the legacy inspector: an isolated v2 SQLite fixture with two physical-call starts printed zero calls and legacy usage. The CLI now dispatches from persisted v2 identity, reuses pure typed snapshot builders shared with the live controller, and reports audit-backed counts, independently complete token/cost subtotals and conservative exposure. Legacy inspection remains the fallback for runs without a compatible v2 identity. The CLI has dedicated running and terminal accounting regressions.

## Regression evidence

Before implementation, `tests/test_audit_live_service.py` produced failures for (a) running snapshots reporting 512 reserved tokens instead of no exact total, (b) terminal snapshots declaring incomplete usage complete, (c) a cached worker failure becoming `KeyError` when the database file existed, and (d) fresh-v2 CLI inspection reporting zero physical calls. The live-service suite has eight isolated cases covering terminal/running snapshots, direction state, complete and independently incomplete metric usage, existing-database repeat polls, and legacy no-database one-shot behavior. The CLI suite adds two v2 cases, including a terminal diagnostics fixture with three acquisition attempts but one acquired source.

Focused verification passed:

```text
.venv/bin/python -m pytest -q tests/test_audit_live_service.py tests/test_audit_cli_inspection.py tests/test_audit_legacy_retrieval.py tests/test_phase7.py tests/test_mvp4_cli.py tests/test_mvp5_live_web.py tests/test_mvp6_5_read_only_inspection.py tests/test_status_polling_compatibility.py tests/test_v2_phase12_production.py tests/test_v2_phase14_round_four.py
200 passed, 1 skipped
.venv/bin/ruff check cli.py frontend/live_service.py frontend/live_progress.py frontend/live_contracts.py tests/test_audit_live_service.py tests/test_audit_cli_inspection.py
All checks passed
.venv/bin/ruff format --check cli.py frontend/live_service.py frontend/live_progress.py frontend/live_contracts.py tests/test_audit_live_service.py tests/test_audit_cli_inspection.py
All files formatted
```

The broader repository test/lint gates were not run as part of this focused ownership pass.

## Files reviewed

- `frontend/live_service.py` — worker lifecycle, polling, persisted and terminal snapshots.
- `frontend/live_progress.py` — v2 directions, persisted artifacts, budget projection, and directional progress.
- `frontend/live_contracts.py` — stable snapshot accounting and presentation fields; no contract field changes were needed.
- `frontend/live_history.py` — read-only review of run history and research-trail projection.
- `providers/v2_budget.py` — authoritative physical-call audit reader and per-metric nullable completion semantics.
- `tests/test_audit_live_service.py` — new isolated regressions.
- `tests/test_mvp5_live_web.py`, `tests/test_mvp6_5_read_only_inspection.py`, `tests/test_status_polling_compatibility.py`, `tests/test_v2_phase12_production.py`, and `tests/test_v2_phase14_round_four.py` — focused compatibility coverage.

## Remaining coverage gaps

- Blocked and cancelled terminal direction labels now have dedicated parameterized cases; released rendering remains covered by existing v2 production tests.
- New fixtures cover complete terminal totals and token-complete/cost-incomplete accounting independently.
- The new live-service fixtures use phase-13 artifact names. Historical phase-12 selection remains dependent on existing audit-reader coverage; an existing one-session test verifies snapshot projections reuse their validated read-only SQLite connection.
- The controller continues to raise `DatabaseCompatibilityError` for incompatible inspection databases, as required by existing compatibility tests. The separate API boundary pass maps that exception to generic HTTP 400 and verifies inspection does not change the file; see [API/native review](api-native-review.md).
- Full `pytest`, repository-wide Ruff, app smoke, and packaged-app checks remain outside this focused verification result and belong to the root integration gate.
