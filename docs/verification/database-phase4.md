# Database implementation — final source verification

Local macOS verification on October 4, 2026. This record completes the shared four-phase [implementation plan](../../.agent/plans/database-review-2026-10-03.md); the original [audit and evidence](../audits/2026-10-03/database-review.md) remain historical. All write/build fixtures and outputs were isolated. No provider calls, research submissions, credential access, real-data upgrades, installed-app replacement, pushes or publication were performed. The initial implementation was uncommitted; the subsequent user instruction authorizes a local commit after successful review, recorded below.

## Request consistency and contention

`ReadOnlyStore` begins a read transaction **before** physical/schema/FK/ownership validation and retains that committed view through the request. History, trail, native browsing, default legacy/v2 status, CLI inspection and export share it. Default legacy status, inspection and export no longer open separate validated sessions for dispatch/result/provider controls. Export closes the connection before PDF/DOCX layout and filesystem publication. Point readers close their cursors and establish a locally owned snapshot for multi-query reconstruction. A borrowed connection's existing transaction, row factory and pragmas remain its caller's property: no nested BEGIN, commit or rollback of that transaction occurs. Owned snapshots and connections are released on failures and interruption.

Each new request opens and validates anew. There is no path/mtime validation cache, connection pool or stale result reuse; replacement at the same pathname is revalidated. The full physical, FK, schema and semantic checks remain enabled at request/import/recovery/upgrade boundaries. The polling benchmark measures their cost, rather than weakening trust to meet an assumed latency target.

The selected main-database policy retains SQLite rollback journaling by default. Existing WAL files stay supported and their committed WAL contents are read through SQLite; inspection never changes journal mode or requires migration. All policy connections have a **1,000 ms** SQLite busy timeout. BUSY and LOCKED result codes, including extended codes, produce retryable contention errors. Inspection API errors use HTTP 503, `Retry-After: 1`, and `{issue: "busy", retryable: true, message: ...}`. Unsupported schema and genuine corruption retain distinct nonretryable compatibility issue codes; the renderer displays their typed message. Neither provider work nor reservations/completions are automatically replayed. Worker/import locks, cancellation draining and shutdown ownership remain intact.

At 20,000 synthetic runs with 4 KiB claims (90.75 MiB main database), validation plus a point status read had warm medians of **32.44 ms quiet / 53.42 ms with writes** in DELETE mode. WAL measured **30.67 / 31.51 ms**, but retained roughly **95.3 MiB of WAL** plus shared-memory data in that workload. No polling errors or writer busy retries occurred. These are application-first/warm measurements with a shared OS page cache and traced Python allocation, **not** full-controller/UI timings or installed-app benchmarks. Full samples, writer wait measurements, sizes and method are in the [polling report](../benchmarks/database-read-polling-2026-10-04.md) and [JSON](../benchmarks/database-read-polling-2026-10-04.json). WAL checkpoint starvation, disk/sidecar/crash/readonly/platform lifecycle adoption was not implemented or claimed; its isolated timing benefit alone does not justify a persisted mode switch.

## Query inventory and migration

| Consumer | Queries / scope | Change and measurement boundary |
| --- | --- | --- |
| History | Ordered limited run manifests; terminal artifact keys and stage projection for those runs | History index removes temporary ordering; per-record historical decoding retained. |
| Progress/status | Run identity, manifest, artifact/physical-call accounting, per-round acquisition/discovery and per-source outcomes | One validated snapshot; existing exact usage/budget and directional projection retained. Historical terminal aggregate attempts without detailed acquisition artifacts remain recorded as unassigned, without invented direction/round attribution. |
| Research trail | Selected run, round 1–4 discovery/acquisition or recognized legacy researcher artifacts | One snapshot; per-record compatibility handling retained. |
| Native evidence browsing | Candidates and selected snapshots, Analyst decisions, drafts, reviews, Ledger; validation/trail/governor metadata | Related reads batch in 500-key chunks, skip empty sets, deduplicate the candidate/selected-Ledger snapshot union and decode each snapshot once. No unrelated-run rows or joined duplicate products are materialized. |
| Provider/CLI inspection | Manifest, checkpoints, usage, planner/researcher/analysis/synthesis/validation/release and provider controls | One coherent connection, including legacy result and controls. |
| Export | Released final output or legacy inspection, original hash, provider controls | One validated snapshot; formatting starts after closure. |

The next available migration is **17**, following usage migration 15 and provenance migration 16. It adds these measured indexes:

- `runs_updated_history`: `(updated_at DESC, run_id ASC)`.
- `candidates_run_extracted_quote`: `(run_id, extracted_at, quote_block_id)`.
- `statement_drafts_run_quote_drafted`: `(run_id, quote_block_id, drafted_at)`.
- `statement_reviews_run_quote_reviewed`: `(run_id, quote_block_id, reviewed_at, statement_draft_id)`, preserving the prior equal-timestamp draft-ID order.
- `ledger_records_run_quote_claim`: `(run_id, quote_block_id, ledger_claim_id)`.

Analyst and snapshot lookups reuse existing primary/unique indexes. Canonical executable migration boundaries include all five definitions and their introduction version. Current committed missing/altered objects are rejected before source writes; matching additive pending indexes can be reused. Index DDL and the migration record commit together; injected record failure rolls both back. Read-only inspection supports **7–17** without upgrade; writable historical **1–16 → 17** fixtures retain the verified-backup boundary. Version advancement updates precise migration assertions and source-derived fixtures, without removing historical assertions.

Before/after native browsing at 2/10/40 candidates improves related-table queries from **11/51/201 to 6/6/6**. A 1,000-candidate workload crosses the chunk boundary with **10** related queries. Full typed output equality and robust operation-count/empty-set/chunk regressions accompany measured plans and timings. Complete counts, plans, output comparisons and timings are in the [native query benchmark](../benchmarks/database-query-scale-2026-10-04.md) and [JSON](../benchmarks/database-query-scale-2026-10-04.json). Counts include historical snapshot verification where present; distinguish those workloads in that record. At 1,000 candidates, the measured warm median fell from **1,410.57 ms to 416.32 ms**, and peak traced Python allocation from **82.27 MiB to 20.92 MiB**. These include validation/reconstruction and uncontrolled OS-cache effects. Timing is diagnostic, never a pass threshold or an assertion that the installed v2 UI is slow. V2 uses its separate artifact tables.

## Finding-to-test acceptance matrix

Each row refers to current source and executed regressions, except the explicitly named platform/external limitations. The complete suite includes these files.

| ID | Implementation / invariant | Regression evidence / limit |
| --- | --- | --- |
| F1 | Version-aware native Ledger/researcher/v2 reads, original contracts/hashes, per-record errors; strict fresh admissions and incompatible resume | `test_historical_reads_phase3.py`, `test_database_read_paths_phase3.py`; phase-3 read-only evidence retains all 47 repository history entries, both August release hashes and 188 prior-policy artifacts without changing bytes. |
| F2 | Cache-write tokens/cost basis round-trip; historical unknowns and exact costs unchanged | `test_database_cache_accounting.py`, `test_database_attempt_integrity_phase2.py`, `test_database_v2_replay_phase2.py`. |
| F3 | Immutable identity-bound reservation/completion, serialized terminal comparison, conservative atomic budgets | `test_database_attempt_integrity_phase2.py`, `test_database_attempt_caller_phase2.py`, `test_database_v2_replay_phase2.py`. |
| F4 | Shared strict nonmutating recorded-version/schema/ledger preflight; valid bootstrap/pending/historical migration | `test_database_schema_integrity.py`, `test_database_schema_provenance_phase2.py`, `test_database_recovery.py`; migration-17 missing/index/atomicity regressions. |
| F5 | Same-run child and referenced-parent ownership/key changes guarded; semantic preflight catches old violations | `test_database_schema_provenance_phase2.py`. |
| F6 | Noncreating URI read-only paths, encoded special characters, borrowed-connection ownership | `test_database_read_paths_phase3.py`, `test_mvp6_5_read_only_inspection.py`, `test_database_read_snapshots.py`. |
| F7 | Selected CLI parent prepared before sidecar lock | `test_database_lifecycle_locks.py`, `test_database_recovery_cli.py`. Desktop's existing-parent boundary retained. |
| F8 | Persisted failed/fallback attempts, round/direction isolation, unassigned ambiguous/history aggregates | `test_v2_retrieval_progress_phase3.py`, `test_audit_cli_inspection.py`; aggregate terminal-history assertion retained. |
| F9 | Pending evidence excluded from explicit rejection; Analyst/Reviewer outcomes distinguished | `test_database_read_paths_phase3.py`, `test_mvp8_2_evidence_browser.py`. |
| I1 | Bounded batching, exact typed equality/order, measured versioned indexes | `test_evidence_browser_batching.py`, migration-17 regressions, native query benchmark. |
| I2 | Private exclusive creation, default-owned folder policy, collision cleanup | `test_private_import_files.py`, `test_database_import_failures.py`, `test_database_recovery.py`. Native Windows ACL verification remains skipped on macOS. |
| I3 | Locked verified pre-upgrade recovery, bounded safe retention, interruption/disk-full/verification failure and nonoverwriting new-path restore | `test_database_recovery.py`, `test_database_recovery_cli.py`, `test_database_upgrade_fixture_phase2.py`. Native Windows/NTFS power-loss durability remains unverified. |
| I4 | Explicit request snapshots, local/borrowed/nested ownership, deterministic release, replacement and bounded transient contention | `test_database_read_snapshots.py`, `test_database_request_consistency.py`, `test_status_polling_compatibility.py`, export validation/close-before-layout regression; DELETE and WAL tested. |
| X1 | Unicode embedded-font wrapping/pagination and original released-content metadata | `test_pdf_exports_phase3.py`, `test_mvp8_exports.py`, historical release/export regressions; three rendered QA pages visually inspected: no clipping or overlap. Unsupported glyph/shaping coverage fails explicitly with text-preserving alternatives. |
| Legacy-lock follow-up | Supported legacy/direct/injected workers share retained sidecar ownership; import does not race active/cancelling worker | `test_database_lifecycle_locks.py`, CLI/controller regressions and recovery/import suites. |

## Backup, restore and packaging boundaries

Before intentional writable upgrades, the shared sidecar lock covers nonmutating preflight, SQLite backup, verification, private no-overwrite publication, then migration. SQLite backup includes committed WAL data. Default retention is three verified copies; pruning occurs only after successful upgrades and respects restore ownership. Failed verification/disk exhaustion prevents source writes; migration failure retains the recovery path. Restore verifies and publishes into a **new** path, never overwriting an occupied destination. Current-schema initialization validates without DDL or a backup. User databases were not upgraded/restored during this work.

Source identity includes organized Python sources (including `sqlite_policy.py`) and now bundled PDF font bytes. Font/policy changes invalidate resume identity; historical reading/export remains available. The final packaging record verifies exact packaged source/font inclusion, the pinned ReportLab dependency, frozen read-only schema-17 initialization and PDF rendering using only temporary inputs. Credential-backed native desktop smokes remain outside authorization and are not counted as passed.

## Verification and unresolved external gates

The exact command results and packaging provenance are recorded below. Final review also repaired the valid historical Ledger/candidate distinct-snapshot case and preserved equal-timestamp review ordering. Intermediate integration failures exposed stale version fixtures, a missing ReportLab dependency assertion from phase 3, aggregate-only historical attempt display and error-projection handling; they were investigated without weaker validators or suppressed errors. Existing export mocks now use real isolated valid databases, preserving all original release/hash/content assertions. Graph freshness could not be confirmed (`index_status` unavailable and stale locations); no denied refresh/export was retried. Source and tests are authoritative.

The [independent cross-phase/cache review](database-phase4-review.md) verifies the repository build Wigolo cache via read-only SQLite backup and the exact bundled `sqlite-vec` extension: physical integrity, nine migrations, FKs, vector/map/metadata consistency and FTS checks passed on a disposable copy. Installed Wigolo cache access remains unavailable and unverified, with an explicit completion path in that record. Repository-owned acquisition lifecycle was inspected; no newly reproduced recovery defect was found. Partial cache coverage is not proof that all external caches are healthy.

Native Windows ACL/NTFS checks, credential-backed Electron/backend launch, installed-app verification, minimum-OS/clean-machine checks, signing/notarization and live research quality remain separate gates. No current source result claims an installation or release.

## Initial implementation verification

All commands used the local macOS arm64 checkout and existing installed dependencies. Python checks used disposable `RESEARCHASSISTANT_DATA_DIR` directories. Native provider checks were not enabled.

| Check | Exact command / executed boundary | Result |
| --- | --- | --- |
| Complete Python suite | `.venv/bin/pytest -q -rs -W error` | **1,793 passed, 3 skipped, 93.79 s**, after the final historical-snapshot regression. |
| Repository lint | `.venv/bin/python -m ruff check .` | Passed. |
| Repository format | `.venv/bin/python -m ruff format --check .` | 220 files already formatted. |
| Whitespace | `git diff --check` | Passed. |
| Offline evaluations | `.venv/bin/python evaluations/run_evaluations.py --json-output /private/tmp/ra-phase4-evaluations/results.json --summary-output /private/tmp/ra-phase4-evaluations/summary.md` | 38 cases passed, no failures; frozen corpus SHA-256 `86611a646450995ba51fa2e8d047924d174e1bd62c3e4f320cc1d8f576bdbedc`. Optional live suite skipped. |
| Renderer quality/build | `./node_modules/.bin/eslint .`, `./node_modules/.bin/tsc --noEmit`, `RESEARCHASSISTANT_DESKTOP=1 NEXT_TELEMETRY_DISABLED=1 ./node_modules/.bin/next build` in the isolated copied `web/` tree | ESLint and types passed; Next build compiled and prerendered two routes. |
| Renderer smoke | `node frontend-smoke.cjs`, `node frontend-poll-smoke.cjs`, `node configuration-race-smoke.cjs`, `node history-race-smoke.cjs` in the isolated `desktop/` copy, with mocked APIs | Passed; five polling snapshots, maximum one same-run request in flight. |
| CLI recovery/export | `cli.py inspect-run`; `list-backups --db-path`; `restore-backup --backup-path --output-path`; `import-history --source-path --destination-dir`; `export-brief ... --format markdown/pdf/docx` | All seven commands exited 0. Released FakeLLM/FakeSearch/FakeScraper fixture, verified schema-16 backup, schema-17 upgrade, logical-content-preserving restore and import, three exports. Scratch path `/private/tmp/ra-phase4-cli-provider.St8iyF`. |
| PDF visual QA | Poppler-rendered 110-line Unicode/long-URL report using the production exporter | All three pages inspected: complete text, readable margins, no clipping or overlap. |
| Frozen backend/font/schema | Isolated PyInstaller backend and offline verifier described in the [packaging record](database-phase4-review.md#final-source-offline-packaging-check) | Embedded-font PDF, schema-17 initialization/read-only validation and packaged source identity passed; no application/vault/service start. |

The three full-suite skips are precise: `test_mvp4_cli.py` requires explicit live enable and execution-time approval; `test_phase8.py` requires `RUN_LLM_INTEGRATION_TESTS=1`; `test_private_import_files.py` requires native Windows ACL verification. The first two are outside this offline scope, and the third remains a platform gate. The source suite increased from the audit's 1,400-test baseline as the four phases added regression coverage; that baseline is not an expected count.

Credential-backed `desktop/smoke.py` and Electron `ui-smoke` were not run because their backend launch opens the native credential vault. Frontend mock smoke and frozen offline verification are narrower, explicitly identified checks. All installed/public artifact provenance remains unchanged.

Initial implementation full-suite log: `/private/tmp/ra-phase4-final-source-pytest.log`, SHA-256 `35043df1db5613a335a6f849fd245862706e96b9e27ff27de34038c43abd4337`. The last source change before the conditional-commit review added historical snapshot-union verification; the complete suite and package proof were repeated afterward. Exact prior-state archive byte comparisons passed for all five replaced documents.

## Conditional-commit review — 2026-10-04

The user's subsequent request authorizes checking Prompt 4 and committing a successful implementation. Sol reviewed live snapshot ownership, public request/export boundaries, historical trust, strict migration definitions and query ordering. GPT-6-Luna independently checked schema/recovery fixtures, batching/counts, auxiliary-cache evidence, renderer inputs, source identity and isolated packaging. The stale advisory graph was checked against live source; the previously rejected refresh was not retried.

The review reproduced an uncovered Python 3.12 failure: `Connection.commit()` and `rollback()` do nothing for `autocommit=True`, leaving a locally started read snapshot open after either success or failure. The helper now uses cursor-closed explicit SQL `COMMIT`/`ROLLBACK` only for its locally owned transaction. Two regressions failed before the fix; four success/failure and nested-caller cases now pass. Existing caller-owned transactions and their rollback behavior remain intact; the complete snapshot module passed **14 tests**. No validators or historical data were weakened or rewritten.

Polling metadata now calls its first sample `first_poll_ms`, matching the existing report's application-first measurement; all twelve captured numeric samples are unchanged. Current README, desktop upgrade instructions and research invariants now state schema **17**, read-only **7–17**, one-second contention policy and font-inclusive source identity. The five prior-state archive files were independently compared byte-for-byte with committed HEAD and match.

Final checks after the source repair:

| Check | Result / executed boundary |
| --- | --- |
| Complete Python suite | `.venv/bin/pytest -q -rs -W error` with fresh disposable application storage: **1,797 passed, 3 existing skips, 100.41 s**. Log `/private/tmp/ra-prompt4-final-tests.txt`, SHA-256 `b0dcd29dbc108c04dd8679d5e8cb3a0c4f7d4c6d88966dd4512814dc5cb63a41`. |
| Repository quality | Ruff lint, format (**220 files**) and diff checks passed. Staged whitespace is checked before the local commit. |
| Offline evaluations | **38 cases passed**, no failures; optional live comparison remains disabled. Fresh results `/private/tmp/ra-phase4-final-eval.jk9N86/results.json` and `summary.md`; frozen corpus SHA-256 remains `86611a646450995ba51fa2e8d047924d174e1bd62c3e4f320cc1d8f576bdbedc`. |
| Renderer | ESLint and TypeScript passed again in the isolated copied tree. All **16** renderer source files match the current checkout exactly, substantiating the initial build and mocked-smoke results without a redundant build. |
| Final corrected-source packaging | The repeated isolated backend/font/schema proof and exact executable/source hashes are recorded in the [conditional packaging review](database-phase4-review.md#conditional-commit-corrected-source-packaging-check). |

Final checkout identity is `source-sha256:489f3b513aa3ecd68546d76a7579cff4d6dc4724ad0bfc9a6fe7d2095e51c7b3`. The successful review is delivered in the user's authorized local source commit. Installed Wigolo health and the native/platform/release gates above remain explicitly unverified. No provider calls, credentials, real-user database writes, installed replacement, push or publication were performed.
