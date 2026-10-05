# Database review implementation — 2026-10-03

Authorized scope: the four sequential prompts accompanying [the audit](../../docs/audits/2026-10-03/database-review.md). Source, tests, documentation and disposable-database checks are authorized. The user's subsequent instructions authorize reviewing Prompts 1–4 and committing each successful implementation. Paid calls, real-user database writes, push, publication, installed-app replacement and release remain outside this task.

## Shared implementation phases

1. **Lifecycle, privacy and recovery (complete):** F7, I2, I3 and retained legacy lock ownership. Validate recognized recorded versions without initialization; publish a private, verified SQLite backup before upgrade writes; retain recoverable copies; restore only into new paths; keep worker locks through cancellation; preserve writable historical support and read-only schema 7+ boundaries. Provide supported CLI recovery and import flows. Use only temporary databases for verification.
2. **Schema and accounting (complete):** Prompt 2 owns stronger shared schema preflight, provenance guards, complete usage persistence and concurrent accounting integrity. Preserve exact historical amounts and immutable artifacts.
3. **Historical reads and exports (complete):** Prompt 3 owns historical decoding, noncreating point readers, progress/filter corrections and export layout. Preserve recorded policy and resume identity gates. Its initial review-ready handoff and subsequent conditional-commit review are recorded below.
4. **Performance and integration (complete at source boundary):** Prompt 4 delivers measured query batching/indexes, coherent requests and complete offline integration verification. Current evidence and the single finding-to-test matrix are in [the final acceptance record](../../docs/verification/database-phase4.md). Its successful conditional-commit review is recorded below; release and real-data writes were not authorized.

## Phase 1 design and boundaries

- Sol owns storage policy, backup/restore atomicity, historical preflight and final lock review. Luna helpers discover callers/fixtures and implement bounded privacy/CLI/test work.
- SQLite backup uses a read-only source transaction under the shared `.mvp5.lock`; no main-file-only WAL copying. Private temporary recovery files are verified before no-overwrite hard-link publication; the verification marker is published last. Metadata contains file identity and schema/recovery information, not research contents or credentials.
- A current-schema open validates without DDL, backup or source mutation. A successful later upgrade may prune bounded verified copies; cleanup errors cannot invalidate the upgrade or delete the final backup.
- Restore verifies a recovery copy and publishes a new private database without overwriting any occupied path. Import keeps exclusive creation and only removes files it created.
- App-owned folders receive POSIX owner-only permissions. Caller-selected folders retain their existing modes. Windows applies protected owner/SYSTEM ACLs using native security APIs; native platform and NTFS durability verification remain release gates.
- Fingerprint compatibility and immutable artifact/cost semantics remain unchanged.

## Discovery and verification record

Required root conventions, architecture, status, handoff, prior database verification, audit and both JSON evidence files inspected before editing. Initial checkout had the preceding audit/prompt documents and a `docs/history.md` change. Preserve those records and include them with the reviewed implementation so its documentation links remain complete; Prompts 2–4 remain proposals, not implemented source.

The advisory graph still names pre-organization root implementations. Live source and caller searches are authoritative; the tool surface does not expose `index_status`. Automatic approval review rejected an index-refresh attempt because the prompt expressly prohibits it; no refresh occurred and live-source verification continued. No branch switch occurred.

## Phase 1 implementation and caller map

| Boundary | Verified behavior |
| --- | --- |
| `store.init_db` → `store_schema.initialize_database` | Shared lock, read-only recorded-version recheck, backup before opening for writes, current complete schema returns without DDL. Baseline migrations 1–4 now install in one transaction; migrations 5–14 retain their transactions. |
| `v2_orchestrator.run_v2_production_pipeline` | Default CLI/live run and resume entry; shared lock creates selected missing parents. Live caller declares its retained physical lock. |
| `_run_v2_production_pipeline`, `_prepare_identity`, `agents.v2_initial_planner.run_v2_initial_planner` | Initialization stays compatible for direct stage/helper callers; production calls reuse the synchronous retained ownership scope, avoiding nested acquisition. |
| `orchestrator.run_provider_pipeline`, `run_mvp3b_pipeline` | Supported historical public/compatibility paths share the process lock. Injected legacy CLI runners are covered by an outer lock; injected desktop runners inherit the controller's retained lock scope. |
| `request_run_cancellation` (CLI, API, live shutdown) | Validates an existing read-only-compatible source and writes only the cancellation request. Never initializes or migrates. Controller releases its lock only after the worker exits its write/snapshot path, including timed-out shutdown. |
| `fixture_pipeline.run_fixture_pipeline` | Offline fixture-only execution, not a supported live writer; initialization uses the shared initializer. |
| `history_import.import_history` and `/api/history/import` | Source-side shared lock; exclusive private copy; default import folder secured even when pre-existing; cleanup only touches the import's created inode. Existing Advanced-settings action selects the returned usable copy. |
| `DEFAULT_LIVE_DB`, `prepare_default_database` | Per-user application directory from `application_data_dir`; app-owned parent secured. Caller-selected directories keep their existing permissions. |
| CLI maintenance | `list-backups`, `restore-backup` and `import-history` report usable paths. README documents retention, new-path restore, desktop path selection and exact resume gates. |

Recovery publication uses two private files: the complete verified SQLite copy is hard-linked under its stable UUID name, flushed, then its private verification marker is published with the same no-overwrite operation and flushed. Discovery accepts only matching marked copies and rechecks file/content hashes, integrity, recorded-version schema structure and FKs. SQLite source snapshots include committed WAL state. POSIX files are `0600`, owned folders `0700`; macOS flushes files with `fsync` and `F_FULLFSYNC`, and directory entries with `fsync`. No unsupported filesystem publication falls back to overwriting rename. Windows uses protected owner/SYSTEM DACLs, guarded ctypes calls and file flushing; native ACL, NTFS and power-loss durability remain unverified release gates. API choices were checked against Microsoft's [SID documentation](https://learn.microsoft.com/en-us/windows/win32/secauthz/sid-strings), [file flushing requirements](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers), and [SetFileSecurityW](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setfilesecurityw).

The default retention count is three (`RESEARCHASSISTANT_BACKUP_COUNT`, positive integer); an explicit typed policy can select another directory/count. Creation and discovery resolve custom directories consistently, including user-directory expansion. Cleanup runs only after successful upgrades, verifies candidates first and keeps at least one copy. Restore holds the backup-path lock through publication; cleanup takes that same lock without waiting and defers busy copies until a later cleanup, avoiding a verification-to-copy deletion race or lock-order deadlock. Cleanup failures cannot undo an upgrade. Failed/interrupted migrations retain the verified copy, report its path and permit retry; restore always verifies and atomically publishes into a new path. Orphan/unmarked files are ignored and retained for explicit review, never treated as recovery points or automatically deleted. No WAL/SHM sidecars are blindly deleted.

## Exact supported schemas and remaining phases

- Writable upgrade cases **1–13 → 14**, and current **14** without backup or byte/mtime changes, passed. Lower cases are generated from checked-in baseline DDL and executable migration functions, not claimed archival snapshots or invented historical schemas. Versions 1–4 use the established baseline DDL; 5–14 use their explicit migrators. Existing older-version fixtures and exact-cost migration assertions remain intact.
- Public read-only cases **7–14** pass without source mutation; **1–6** remain rejected. Backup/restore use explicit recorded-version checks so recognized lower writable schemas remain recoverable without weakening this boundary.
- Preserve the exact pre-v5 migration-4 description recognized by the existing fixture and sparse migration-6 accounting fixtures. Prompt 2 owns complete shared ledger/preflight tightening and must resolve that compatibility distinction. Unrelated history, exports, evidence queries, accounting and query performance are outside this phase.
- Source/package fingerprint gate code was not relaxed. Restoration preserves history; incompatible active research still requires a fresh run. Immutable artifacts and exact historical costs are not rewritten by recovery.
- Parent handling preserves the supported boundaries: CLI/direct writable initialization creates missing selected parents before acquiring the sidecar lock; desktop `LiveRunRequest` rejects missing/non-writable parents before a worker starts. README now documents that desktop requirement. The existing API boundary tests and assertions remain unchanged.

## Verification — local macOS, disposable databases only

- Broad focused Python run with `-q -W error`: **344 passed, 2 skipped**, 50.63 s. Selected files cover recovery/privacy/locks, schema/transactions/import/accounting regressions, read-only inspection, CLI, live/API, pipeline selection, v2 production/planner/concurrency, desktop Python and annotations. One skip is the new native Windows ACL check; the other is the existing opt-in CLI integration skip.
- Final atomicity review added an interrupted baseline-1 upgrade test: real prefix DDL/ledger writes roll back, the verified copy survives, and retry upgrades successfully. Post-change migration/schema/transaction/read-only/accounting/lock/type checks: **143 passed**, 4.71 s (including **47 recovery cases**).
- Actual disposable CLI chain: schema-13 source → verified pre-upgrade backup → CLI listing → restore to a new schema-13 path → history import into temporary application storage. All three commands passed, with paths/counts reported.
- Repository `ruff check .`, `ruff format --check .` (**199 files**) and `git diff --check`: passed. No renderer/Electron code or dependencies changed; no desktop rebuild or installed-artifact claim is made.
- Coverage includes WAL data, source/copy identity, current-schema immutability, disk-full/permission/verification failures before source writes, backup/restore collisions and publication races, orphan files, source-parent backup placement, failed retention, migration interruption/retry, POSIX permissive-umask privacy, mocked Windows ACL success/failure/signatures/replacement race, cross-process lock contention, retained ownership, selected missing parents and active/cancelling legacy workers versus import.
- Initial broader checks exposed a direct-helper initialization regression (restored the existing supported behavior), two asynchronous legacy-runner test races (added bounded worker-entry synchronization while retaining all assertions), test default-directory sandbox failures (subsequent tests explicitly isolate `RESEARCHASSISTANT_DATA_DIR`), and subprocess stream warnings (closed streams deterministically). These were resolved without weaker assertions or acceptance.
- Implementation verification did not migrate, restore or delete an actual user database or make provider/network research calls, replace the installed app or publish. Only public Microsoft API documentation was consulted. The later user review authorizes a verified source commit.

## Conditional-commit review — 2026-10-04

- Live-source review with Luna discovery/test helpers checked Prompt 1's lifecycle, privacy, CLI, schema-boundary and lock requirements. Confirmed and fixed two recovery defects: pruning could delete a backup between restore verification and copying, and custom `~/...` policy directories were resolved during creation but not discovery. Two new regressions cover these exact cases, including successful restore and later cleanup after a busy copy is released.
- A proposed desktop missing-parent change was unnecessary: the existing request validator and API boundary test already reject that path before the controller runs. Preserve that contract and its original assertions; document the required existing writable desktop folder in README. CLI/direct initialization still creates selected missing parents before sidecar locking.
- Final full suite, with `RESEARCHASSISTANT_DATA_DIR` set before import to a new temporary directory: **1,475 passed, 3 skipped**, 73.02 s, using `pytest -q -rs -W error`. Skips are the two existing opt-in provider/CLI integrations and native Windows ACL verification. The first unisolated run encountered seven sandbox denials while API tests tried to secure the real app directory; the isolated final run passes without actual user-database operations. Intermediate desktop-contract exploration was reverted after the existing boundary regression identified the mismatch; no acceptance assertion was weakened.
- Final `ruff check .`, `ruff format --check .` (**199 files**) and `git diff --check` passed. Prior architecture, status, handoff and plan-index snapshots were checked byte-for-byte against the preceding commit. No dependency, renderer/Electron or installed-artifact change is included.

At the phase-1 completion, Prompt 2 was the next implementation boundary. The phase-2 record below supersedes that handoff. Cross-phase and performance verification still belong to Prompt 4; the full-suite phase-1 result supported its conditional commit. A fresh build, artifact/platform verification, app replacement and publication require separate later decisions/authorization.

## Phase 2 implementation — schema, accounting and provenance

Prompt 2 authorizes F2–F5 source, regressions and documentation. The user's later conditional approval additionally authorizes review and commit if successful; push, publication, rebuilding the installed app and real-data migration remain outside scope. Sol implemented the shared schema calculation and persistence transactions and integrates final compatibility decisions. Luna helpers handled caller discovery, fixture preparation, regression construction, bounded tests and independent source review. The advisory graph still points at pre-organization root files; its freshness tool is unavailable. No graph refresh or attempt to bypass the earlier rejection occurred.

- **F4:** Read-only inspection and writable initialization use the same non-mutating recorded-schema validator, retaining their separate upgrade permissions. Required object presence for migrations 5–16 is derived by executing the migrators in an isolated memory database; baseline 1–4 retains its established introduction boundaries and column rules. Preflight rejects missing committed objects, altered descriptions, gaps, unknown/non-integer/future versions, unexpected constraints/table options, inert triggers, FK corruption and inconsistent same-run ownership. Only pristine empty SQLite layouts may bootstrap: no user objects, at most one page, no free pages, and zero schema/user/application markers. A previously used file with all objects dropped fails even after VACUUM; nonempty databases without recognized records fail. A current valid database returns before opening for writes or creating a backup. Existing recognized upgrades reuse Prompt 1's retained sidecar lock and verified backup before mutation, with another preflight before DDL.
- **Historical compatibility:** Public read-only support is schemas 7–16; 1–6 still require an intentional writable upgrade. Early writable paths 1–16 remain supported. The exact pre-v5 migration-4 description remains a recognized historical alias and is converted only during that recognized upgrade. Sparse migration-6 accounting fixtures are recognized only when migration 6 alone is missing and both exact-cost columns and all four migration-6 immutable triggers are absent; dropping just a committed migration record is corruption. Public read-only inspection does not accept this pending upgrade. Valid objects from a pending migration can remain present, but their full definitions must match before reuse.
- **F2:** Migration **15**, `persist model cache-write tokens and usage cost basis`, adds nullable INTEGER/TEXT fields only. Old rows retain null write counts/bases. Insert, finish, reconstruction and full replay preserve all fields, token partitions and canonical Decimal cost text. An empty usage record and no usage share the existing all-null persistence representation. Columns and the migration ledger record commit atomically. No completed charges, physical-call artifacts, saved briefs or release hashes are recomputed. V2 physical-call completion artifacts continue to own its overall budget; this projection fix is not a correction of understated v2 ceilings.
- **F3:** Stable reservation identity comprises attempt/run/operation IDs, stage/output type, logical/pinned model, route index/attempt number, input IDs, original start time, token/cost reservations and original retry/escalation metadata. Reservation replay checks that identity before returning and never adds another call. Persistence reconstructs fresh raw dictionaries for both model levels so constructed/copied instances run every validator again, with finite latency and serialized-output checks. Completion locks with `BEGIN IMMEDIATE` before re-reading the row, binds identity, and commits exactly one terminal transition. Matching terminal finishes succeed; conflicting finishes cannot overwrite. Both reservation and finish roll back even on interruption and close owned connections. Still-running usage claims are retained as data but do not reduce budget exposure or count as final actual usage. Truthful terminal usage and exact costs retain their authority.
- **Caller replay:** The retained routed caller and direct v2 Analyst/Reviewer callers validate the requested slot's full stable identity and recalculated reservation/retry metadata before returning saved output. Intentional replay retains the persisted start instead of comparing it to a new clock reading. A completion returned by reservation is reused without another provider call; failed attempts keep existing retry/escalation behavior. Analyst interruption recovery clears unconfirmed usage, and both direct callers use reservations for running attempts and reject unprovable exposure. Known terminal input/output counts remain usable when total tokens are absent. Conservative price calculations now remain Decimal through persistence/comparison. Exact source/executable/provider/policy gate code is unchanged.
- **F5:** Migration **16**, `protect same-run provenance ownership and keys on update`, derives targeted immutable ownership/reference/key guards from the inventory of all 17 relationships covered by nine original insert guards. Mutable scores, run status, checkpoints and completion fields retain their permissions. Existing snapshot/Ledger/final-artifact immutability and insert rejection remain. Semantic same-run checks run without changing evidence, at migration 4+ where all inventoried core relationships exist; required-table validation precedes those queries. Imported copies and recovery verification inherit the same validator. Migration 16 installs guards and its ledger record atomically. Canonical pending guards are validated and reused; damaged committed guards fail before repair. Repeated-validation cost remains for Prompt 4 to measure.

### Phase 2 reproduction and verification

Corrected disposable regressions against an isolated HEAD source copy reproduce the migration-4 gap repair, child/parent provenance update bypass and semantic ownership-open bypass: **4 failed, 19 passed**. The first provenance test fixture accidentally closed uncommitted DML; it was corrected to commit and close explicitly before this reproduction, and its initial result is not treated as defect evidence. Accounting regressions initially reproduce lost write counts/bases, unchecked reservation/completion identity, bypassed instance validation and both conflicting concurrent finishes succeeding: **36 failed, 15 passed**. An initially mislabeled missing-write test and an invalid start-time drift fixture were corrected to exercise their intended invariants; assertions were not weakened. Concurrent test entry uses bounded external synchronization, with no barrier inside the serialized state read.

- Final combined focused local macOS run, with `RESEARCHASSISTANT_DATA_DIR` isolated to a new temporary folder and `pytest -q -rs -W error --tb=short`: **790 passed, 2 skipped**, **68.59 s**. Selection covers every `test_database*.py` file, private imports, read-only inspection, runtime/exact accounting, acquisition and quote-selection schema checks, phase-9 routing, MVP-10/11 evidence/governor, CLI inspection, live/API boundaries, v2 foundation/planner/Analyst/Reviewer/analyzer-admission/production/concurrency, v2 budget reconciliation/backfill/cache pricing, pipeline selection, desktop Python/smoke support and type contracts. Skips are the existing explicit-approval CLI integration and native Windows ACL verification. No warnings were suppressed.
- The preceding broader run had **1 failed, 633 passed, 2 skipped**, 64.22 s: an existing v2 Planner fixture still asserted schema 14. Its exact expected version was updated to 16; the v2 foundation ledger assertion was also extended to 1–16. The final run includes both. Earlier focused iteration exposed stale downgraded fixtures retaining later ledger records/guards and one missing helper return annotation; these were corrected without removing assertions. One attempted selection did not start because a shell glob named nonexistent phase-9 files; it was replaced by the actual test paths.
- The first passing combined run had **714 passed, 2 skipped**, 67.30 s. Subsequent independent caller inventory identified direct Analyst/Reviewer replay paths that lacked full identity checks and trusted running usage in their ceilings. Those were repaired and covered by **23 additional direct-caller regressions**, included in the final combined run. A forged terminal-return fixture was then strengthened to be shape-valid and assert an identity-specific cause; the stable direct-caller file passed again with warnings as errors: **23 passed**, **0.98 s**. Pre-fix live source confirms both missing identity checks; no isolated pre-fix runtime reproduction was claimed for these later cases. Luna also traced the production pipeline/desktop retained database lock, confirming supported workers serialize restart recovery. Final schema review found no blocking issue in version boundaries, strict preflight or migration/backup atomicity.
- Additional focused verification of the two new persistence/schema suites: **156 passed**, 4.01 s. Source-derived recovery fixtures cover upgrades 1–15 → 16, current schema 16 without mutation/backup, public readers 7–16 without mutation, and rejected readers 1–6. New regressions cover all usage cost bases and null/zero/nonzero writes, exact Decimal preservation, all stable reservation identity fields, constructed/copied invalid completions, missing rows, sequential/concurrent matching and conflicting finishes, real interrupted-update rollback, cross-operation call/token/cost races, unknown usage, all 17 child/parent relationship guards, semantic FK-valid ownership corruption at open/import/writable boundaries, new migration rollback, verified backup retention and retry.
- Repository `ruff check .`, `ruff format --check .` (**203 files**) and `git diff --check`: passed. No dependency, renderer/Electron, provider transport, installed build or fingerprint-gate change. Luna independently reviewed reservation/completion serialization, caller replay and migration atomicity; Sol reviewed the integrated live source and compatibility decisions. Graph refresh remains prohibited and was not retried.

At the initial phase-2 implementation handoff, this was uncommitted source work. The conditional-commit review below supersedes that delivery state. Prompts 3–4, cross-phase/performance acceptance, native Windows ACL/durability, fresh build and distribution gates remain pending.

### Conditional-commit review — 2026-10-04

- Sol reviewed live persistence transactions, exact costs, identity binding and usage reconstruction; Luna independently reviewed schema/provenance and the three reservation callers. The advisory graph returned pre-organization root paths, so live files and current diffs remained authoritative. No index refresh was attempted.
- Independent review reproduced a fully erased schema being accepted as a new database. Added a read-only bootstrap-state check and regressions for dropped objects before/after VACUUM, genuine zero-byte/header-only files and nonzero user/application markers. Refused cases retain source bytes/mtime and publish no backup. Schema/provenance focused checks passed **105 tests** before the later table-option cases.
- STRICT and WITHOUT ROWID changes also reproduced acceptance despite physical/FK validity. Canonical validation now compares normalized options following the table body as well as its declarations. Both new refusal cases preserve source bytes/mtime and produce no backup. The final focused schema/provenance suites passed **107 tests** with warnings as errors.
- The first complete suite had **1 failed, 1,673 passed, 3 skipped** (94.01 s): its older-schema status fixture deleted all migration records from a current database, which is now correctly classified as corruption. Rebuilt that case from executable schema-6 DDL while retaining every assertion, and added separate missing-ledger/table corruption cases. The intermediate full suite passed **1,682 tests, 3 skipped** (84.77 s), before the suffix-option and upgrade-fixture changes.
- Updated the isolated old-build upgrade fixture for generated schemas 14–16. Conversion to schema 13 removes only recognized post-13 guards, null usage columns and later records in one write transaction; any reported usage, including zero, blocks conversion. Refusal or interruption rolls back all DDL/ledger work. Offline fixture tests check historical read-only compatibility, preserved data and exact replay state; no native executable or credential smoke was run.
- Current README, architecture, decisions, research invariants and desktop compatibility notes now agree on schema 16 and read-only support for 7–16. Historical audit/verification/archive records retain their recorded version claims. Caller-level restart replay intentionally uses the persisted original start; storage reservation/completion enforce original-start identity rather than comparing it with a new clock reading.
- Only disposable databases were used. Actual user databases, credentials, providers and the installed application were untouched. The authorized delivery is a local source commit; push, publication, app replacement and real-data migration remain outside scope.
- Final complete local macOS run after all review fixes, with isolated `RESEARCHASSISTANT_DATA_DIR` and `pytest -q -rs -W error`: **1,693 passed, 3 skipped**, **85.20 s**. Skips are the existing explicit-approval CLI/provider checks and native Windows ACL verification. `ruff check .`, `ruff format --check .` (**204 files**) and `git diff --check` passed. Prompt 2 meets its source acceptance requirements and is delivered in the user's authorized conditional commit; Prompts 3–4 and native/artifact release gates remain open.

## Phase 3 implementation — historical reads, progress, filters and PDF exports

Prompt 3 authorizes only **F1, F6, F8, F9 and X1**. The integrated committed
Prompt 1/2 baseline (`2bd3a86`, schema 16) was inspected before changes. Its
schema, accounting, identity and provenance protections are retained. Sol owns
the historical trust decisions and final integration; user-authorized Luna
helpers prepared fixtures, focused reader/filter/progress tests and independent
progress review. The graph still returns pre-organization paths, has no exposed
freshness tool, and remains advisory. Live source, current diffs and tests were
used; the previously denied index/export refresh was not retried.

### Compatibility and implementation choices

- **F1 native Ledger:** Current validation runs first. The exact August
  schema/prompt/policy identity triple in `historical_decode.py`, a validated
  canonical provider fingerprint and same-run ownership select the narrow
  phase8 read contract. It preserves EQ/CF/score 4, secondary placement and
  original `Strong`, restricted to the recorded Analyst-v1/Reviewer-v2 versions.
  Stored snapshot identity, retrieval relationship and actual content hash are
  checked. Both verified August releases reconstruct with their original hash.
- **F1 native trails:** The explicit two schema/prompt pairs and recorded policy
  catalog select old web academic-study intent and the earlier discard floor 20
  (floor 5 for the recorded relaxed policy). Other run, stance, score, rank,
  exclusion and provenance validators remain in force. Embedded snapshot hashes
  are checked. Native stage envelopes have no separate payload-hash column;
  none is invented. Old release-v1 connective text/no-coverage-paragraph rendering
  was verified against retained `1fc21a8:agents/renderer.py` and is accepted only
  for the August identity plus recorded validator-v1, with exact final-hash equality.
- **F1 v2 catalog:** Explicit typed read subclasses support source-selection-v1
  queues with caps 12/7 and synthesis allowance 2; extraction phase-12 v1/v2;
  phase-9 Analyst v1/v2; phase-10 Reviewer v1/v2; phase-12 backfill-v1 with nested
  historical queue/Analyst/Reviewer. Phase-13/current wrappers continue through
  their existing contracts. Absent old cap/result-policy fields stay unknown;
  early Analyst policy comes from its recorded input. Extraction/backfill string
  identities are checked against an explicit supported catalog before decoding.
  V2 original payload SHA-256, run identity and nested snapshot hashes are verified.
  The [fixture guide](../../tests/fixtures/historical_reads/README.md) maps all cases.
- **Trust boundary:** No global validator is loosened and no `model_construct`
  fallback is used. Historical objects carry an inspection-only marker. Native
  and v2 Ledger writes revalidate raw data under the current contract; v2 artifact
  persistence and final-release validation reject historical read objects.
  Execution/resume retains strict decoding and the unchanged exact identity gates.
  Unknown types/policies, malformed shapes or unsafe hashes have typed per-record
  results in browser, trail and provider-inspection views, leaving unrelated
  records available. A corrupted released brief still raises the existing hash
  error. Historical round merging retains its read type without changing values.
- **F6:** Every path-based low-level reader uses one percent-encoded `mode=ro`
  connection helper. Owned connections enable foreign keys/query-only and close
  on exceptions. Caller-owned connections retain their row factory, pragmas,
  open state and transaction: cursors supply named rows independently. Public
  `ReadOnlyStore` retains its strict schema checks and typed open errors; point
  reads do not repeat full validation. No polling/snapshot policy is changed.
- **F8:** Persisted attempt entries, including failed and fallback calls, are
  counted across acquisition rounds 1–4. Complete singleton discovery-cluster
  direction mapping is authoritative; persisted acquisition direction is a
  fallback when the cluster mapping is absent. Conflicting/incomplete/missing
  mapping remains in `unassigned_retrieval_attempts_used`. Acquired sources and
  usable survivors remain separate. Running/terminal totals use the same actual
  persisted attempts, including disabled directions and repeat inspection.
- **F9:** Approval/rejection means an explicit persisted outcome at either
  Analyst or Reviewer stage; the stage results remain separate. Missing decisions
  are pending and match neither filter. Existing “Rejected” labeling is accurate
  after this change, so no label/layout change was needed.
- **X1:** ReportLab wraps by glyph width, breaks arbitrarily long words/URLs and
  paginates at fixed margins. GNU Unifont 15.0.01 is bundled unmodified with its
  license (OFL option); SHA-256 is
  `299459bc34e915b1c18dd38677739f41d0b2a6d79b93f480cd157ef24da675ab`.
  Supported text includes Latin accents/punctuation, Greek/math, Cyrillic and
  representative Chinese/Japanese/Korean. Unsupported code points, private/control
  characters and unsupported complex shaping raise a specific error naming code
  points and Markdown/DOCX alternatives. There is no silent replacement. Original
  released text/hash and export metadata remain authoritative, not regenerated
  PDF bytes. Inspection connections close before slow layout/embedding.

ReportLab is the necessary new PDF-generation runtime dependency:
`>=4.4.9,<5.0`, pinned to **4.4.9** in desktop constraints. The bundled font is
12,273,948 bytes; ReportLab embeds subsets. Existing `desktop/build.py` already
copies the entire `researchassistant` data tree, including the font/license.
No build-script change or new installed-artifact claim is needed. A later build
must verify the pinned dependency and packaged font on each target platform.
Only official font downloads and the dependency install used network access;
no research provider or credentials were accessed.

### Verification — final source, local macOS

- Final focused run: **614 passed, no skips**, **40.36 s**, using
  `pytest -q -rs -W error --tb=short` with `RESEARCHASSISTANT_DATA_DIR` set before
  import to a new temporary folder. The full suite was deliberately left to
  Prompt 4. An earlier focused run passed **565 tests**, 31.61 s, before the final
  hash/shape guards and adjacent legacy inspection checks.
- The final selection is the five new phase3 suites plus
  `test_mvp8_exports.py`, `test_mvp8_2_evidence_browser.py`,
  `test_mvp6_5_read_only_inspection.py`, `test_mvp6_6_runtime_integrity.py`,
  `test_status_polling_compatibility.py`, `test_database_schema_integrity.py`,
  `test_database_schema_provenance_phase2.py`,
  `test_database_attempt_integrity_phase2.py`,
  `test_database_attempt_caller_phase2.py`, `test_database_v2_replay_phase2.py`,
  `test_database_cache_accounting.py`, `test_database_transactions.py`,
  `test_database_recovery.py`, `test_database_lifecycle_locks.py`,
  `test_type_contracts.py`, `test_phase5.py`, `test_phase6.py`, `test_phase9.py`,
  `test_v2_phase10_reviewer_ledger.py`, `test_v2_phase12_production.py`,
  `test_v2_research_status_display.py` and `test_v2_evidence_display.py`.
- Tests cover missing/direct/URI-sensitive path readers, default/named caller
  rows, transaction/pragma ownership, exception closure, permission/open/malformed
  and version errors; all known historical families/nested wrappers; current
  rejection and forged identity/hash guards; unknown later trail rounds and
  Ledger records; unchanged public inspection/export identity; failed/fallback,
  round/direction/unassigned progress; and public pending/explicit decision filters.
  Prompt 2's schema suite retains readers 7–16 and rejected readers 1–6.
- PDF parsing checks include empty/short output, escaped characters, Unicode,
  a 70-line report, very long URLs and exact 49/50/98/99-line page boundaries.
  Latest QA PDF was rendered with Poppler and **both pages visually inspected**:
  accents, punctuation, Greek/math and CJK/Cyrillic glyphs are present; all 70
  lines and the full wrapped URL parse; margins are clear, with no clipping,
  overlap or replacement boxes. A public export regression checks that every
  inspection connection is closed before drawing and retains the release hash.
- Strictly read-only verification of the original repository schema-13 database
  lists **all 47 entries**. All **526** artifacts in the five affected families
  decode (36 queue, 199 extraction, 199 Analyst, 81 Reviewer, 11 backfill),
  including all **188** direct-current failures (14/7/81/81/5). Browser/trail
  reads across 28 entries with recorded provider contracts report no compatibility
  issue. Both affected completed August provider views reconstruct and match
  original released hashes. Source bytes and mtime are unchanged. Payload JSON,
  original hashes, provenance and accounting are never updated. These results
  classify the observed failures as supported drift, not SQLite corruption.
- `ruff check .`, `ruff format --check .` (**213 Python files**) and
  `git diff --check` pass. Renderer `tsc --noEmit` and ESLint on changed
  `web/lib/api.ts` pass. No UI layout or Electron code changed. Exact prior
  status/handoff/architecture/plan-index snapshots match committed HEAD bytes in
  [the Prompt 3 archive](../../docs/archive/2026-10-04-phase3-state/).
- Iteration corrected synthetic fixture snapshot/hash references, a missing
  timestamp-format comparison and empty historical candidate selection. A test
  initially assumed a saved Round-2 trail was the initial-round result; it now
  checks the actual persisted retrieval count while retaining the unrelated-round
  assertion. A final adjacent legacy hash-corruption check also preserved its
  established error behavior. No existing assertion or acceptance was weakened.

### Exact changed-file inventory

All paths below are relative to the repository. This inventory includes source,
dependencies/assets, tests/fixtures and documentation; temporary QA/preparation
files outside the repository are not delivery artifacts.

| File | Change |
| --- | --- |
| `agents/renderer.py` | Reject inspection-only objects for new release validation. |
| `researchassistant/contracts/historical.py` | New narrow August read type, marker and typed per-record compatibility result/error. |
| `researchassistant/storage/historical_decode.py` | New explicit native/v2 historical dispatch and hash/provenance verification. |
| `researchassistant/storage/store.py` | Shared read-only point-reader boundary, caller row-factory preservation, historical Ledger read and strict write guards. |
| `researchassistant/research/orchestrator.py` | Historical provider inspection, compatibility results, original release reconstruction and typed round merging. |
| `researchassistant/evidence/evidence_browser.py` | Historical Ledger inspection and explicit-decision filtering. |
| `researchassistant/evidence/historical_render.py` | New exact released-v1 text reconstruction/hash check. |
| `researchassistant/evidence/brief_export.py` | Use the materialized Unicode PDF renderer after read sessions close. |
| `researchassistant/evidence/pdf_render.py` | New embedded-font wrapping/pagination and explicit coverage errors. |
| `researchassistant/evidence/fonts/unifont-15.0.01.ttf` | New unmodified licensed bundled font. |
| `researchassistant/evidence/fonts/UNIFONT-LICENSE.txt` | New upstream license text. |
| `researchassistant/evidence/fonts/README.md` | New source, coverage, license and packaging notes. |
| `frontend/live_contracts.py` | Typed trail/history compatibility, acquired-source and unassigned-attempt fields. |
| `frontend/live_history.py` | Historical native/v2 trail dispatch and per-record/per-run compatibility results. |
| `frontend/live_progress.py` | Actual attempt counts from persisted rounds and safe direction mapping. |
| `web/lib/api.ts` | Compatible optional renderer API fields. |
| `requirements.txt` | ReportLab runtime dependency. |
| `pyproject.toml` | Matching ReportLab dependency. |
| `desktop/constraints.txt` | ReportLab 4.4.9 pin. |
| `tests/test_database_read_paths_phase3.py` | New noncreating path/caller ownership regressions. |
| `tests/test_historical_reads_phase3.py` | New catalog, public reconstruction, strict-current/hash/trust/export regressions. |
| `tests/test_v2_retrieval_progress_phase3.py` | New no-provider persisted-attempt regressions. |
| `tests/test_browser_decisions_phase3.py` | New public pending/Analyst/Reviewer filter regressions. |
| `tests/test_pdf_exports_phase3.py` | New PDF completeness, page geometry, Unicode and unsupported-text regressions. |
| `tests/fixtures/historical_reads/native-ledger-august2.json` | New two-case redacted Ledger fixtures. |
| `tests/fixtures/historical_reads/legacy-researcher-trails.json` | New two-case redacted native trail fixtures. |
| `tests/fixtures/historical_reads/v2-prior-policy-artifacts.json` | New ten-case redacted v2 family/nested-wrapper fixtures. |
| `tests/fixtures/historical_reads/README.md` | New fixture provenance, redaction and recognized-version guide. |
| `.agent/plans/database-review-2026-10-03.md` | Shared Phase 3 decisions, results and exact inventory. |
| `.agent/PLANS.md` | Current review/Prompt 4 navigation. |
| `STATUS.md` | Current verified source/dependency/delivery state. |
| `HANDOFF.md` | Review boundary and Prompt 4/future-build actions. |
| `ARCHITECTURE.md` | Current read/contract/progress/export ownership and invariants. |
| `docs/archive/INDEX.md` | Links the exact prior current-state set. |
| `docs/archive/2026-10-04-phase3-state/STATUS.md` | New byte-for-byte prior snapshot. |
| `docs/archive/2026-10-04-phase3-state/HANDOFF.md` | New byte-for-byte prior snapshot. |
| `docs/archive/2026-10-04-phase3-state/ARCHITECTURE.md` | New byte-for-byte prior snapshot. |
| `docs/archive/2026-10-04-phase3-state/.agent/PLANS.md` | New byte-for-byte prior snapshot. |

**Initial implementation handoff:** Phase 3 was implemented and ready for review, uncommitted.
No reviewed historical format remains unresolved; unknown/unsafe formats produce
explicit results and unsupported PDF text produces an explicit export error.
No real database was migrated, rewritten, restored or otherwise modified; no
research provider was contacted, credentials accessed, installed app replaced,
commit made, push performed or release published. Prompt 4 still owns full-suite,
cross-phase, query/index and consistency design, and measured performance work.
Windows native and packaged-artifact acceptance remain separate later gates.

### Conditional-commit review — 2026-10-04

- The user's subsequent instruction authorizes this successful source review and local commit. Sol checked historical dispatch, strict admission/release boundaries, original release reconstruction and caller ownership; Luna independently reviewed historical trust, all point readers, directional progress, browser filtering and PDF rendering. The advisory graph remains stale and was not refreshed. No execution/resume gate or historical row/hash was changed.
- Review reproduced a blocker: direct v2 discovery/acquisition decoding could abort the whole trail for an unsupported record. Both now use the versioned hash/type/run-aware inspection decoder and collect per-record results. Unsupported discovery omits only that round; unsupported acquisition retains its discovery with unknown acquisition state rather than inventing an outcome. Invalid stored envelopes/hashes receive typed results without weakening storage integrity checks.
- Related history listing now preserves other runs when a production envelope is unreadable and reports compatibility on that history item. If an older terminal result needs stage inference and a child artifact is unsafe, its verified terminal status and recorded stage remain available with a reconstruction issue. Missing artifacts retain the established manifest fallback. Eleven new public regressions cover unknown fields, wrong types/runs, envelope/snapshot hashes, unaffected rounds/runs and unchanged bytes/mtime/payloads/hashes.
- Independent reader/progress/browser verification passed **27 tests**; PDF/export/connection-close verification passed **21 tests**, all with warnings as errors and isolated application storage. Sol and Luna inspected both Poppler-rendered pages of a 70-line report with a long unbroken URL and Latin/Greek/math/Cyrillic/CJK text: complete wrapping, margins and glyphs, with no clipping or overlap. The font/license/dependency and desktop data inclusion agree; native packaged-build verification remains open.
- The first review selection passed **614 tests**, **44.13 s**, before the compatibility repair. The expanded adjacent legacy-trail/production/export check then passed **140 tests**, **18.93 s**. The reviewed historical module with the eleven new cases passed **34 tests**. These are source checks using disposable databases, not an installed-artifact or full-suite claim.
- Final combined selection after the source repair and eleven additional cases: **661 passed, no skips**, **40.96 s**, with warnings as errors and isolated `RESEARCHASSISTANT_DATA_DIR`. It repeats the implementation's full focused selection and adds `test_mlp4_research_quality.py`. The history hash fixture was then strengthened to start from valid typed production results and prove clean history before hash-only mutation; the complete historical module passed again (**34 tests**). Repository Ruff lint/format (**213 files**), diff checks, renderer TypeScript and changed-file ESLint pass. Prompt 4 retains full-suite, cross-phase and measured performance/consistency acceptance. The successful review is delivered in the user's authorized local source commit; user databases, providers, credentials, installed artifacts, push and publication were untouched.
- Staging brought new files into the diff check and exposed two trailing spaces and an extra final blank line in the upstream license text. Normalized only that whitespace, verified identical words and retained the unmodified font bytes; the complete staged diff check then passed.

## Phase 4 initial completion — verified source, uncommitted

Prompt 4 authorizes necessary source/tests/docs work and explicitly excludes commits, provider calls, credentials, real-user database writes, automation, installed replacement, push and publication. Those boundaries were retained. Sol owns snapshot/reader-writer policy, trust and final acceptance; GPT-6-Luna helpers completed query/fixture discovery, focused tests, independent cross-phase/cache review and isolated packaging proof. No denied graph refresh was retried.

The [final acceptance record](../../docs/verification/database-phase4.md) is the single final traceability checklist for F1–F9, I1–I4, X1 and the supported legacy-lock follow-up. It records the query inventory, migration 17/index definitions, one-second contention and rollback-journal decision, recovery/import/restore behavior, all exact verification commands, benchmark methods/results and external/platform limits. Linked JSON/Markdown benchmark artifacts preserve operation counts, query plans, typed output equality, first/warm timing and memory. The [supplemental review](../../docs/verification/database-phase4-review.md) records distinct auxiliary-cache checks and packaged-artifact provenance.

Cross-phase review retained strict validation, original values/hashes and incompatible-resume rejection. Integration fixes preserve aggregate-only historical retrieval counts, propagate V2 projection failures, recognize migration 17 throughout exact fixtures/recovery/upgrade smoke, retain released export mock assertions using valid disposable databases, and ensure historical Ledger records with a distinct same-run snapshot are verified in the bounded union. Tests now cover caller-owned/nested transaction success/failure, validation-before-query coherence, DELETE/WAL concurrency, replacement, contention without replay and interruption cleanup. Original current-state documents are archived byte-for-byte at [the phase-4 snapshot](../../docs/archive/2026-10-04-phase4-state/).

The complete source suite, quality checks, offline evaluations, renderer lint/type/build and isolated mocked polling/race plus actual CLI recovery/import/three-format export checks passed. Three explicitly gated Python skips retain live-provider and native Windows boundaries. PDF pages were visually inspected, and the frozen backend verifies bundled dependencies/font/schema/identity without starting a credential-backed application. Exact final counts and timings live in the acceptance record rather than duplicated here.

Installed/public builds and all original real-data bytes remain unchanged. Installed Wigolo cache access, native Windows ACL/NTFS durability, credential-backed launch, minimum-OS/clean-machine acceptance, signing/notarization and live research quality remain explicitly unverified. The source task ends at a reviewable result; these external/release boundaries require separate authorization or platform access.

### Phase 4 conditional-commit review — 2026-10-04

The user's subsequent instruction authorizes review and a local commit on success. Sol independently reviewed coherent public reads, historical trust, snapshot ownership, migration 17 and deterministic batch ordering; GPT-6-Luna helpers checked schema/recovery, query scaling, source/package identity and cross-phase evidence. Review reproduced a Python 3.12 `autocommit=True` snapshot leak on both success and failure. Explicit SQL transaction completion now releases only locally owned snapshots, preserving existing caller transactions. Four new regressions cover both outcomes and nested caller rollback; the complete snapshot module passes fourteen cases.

The review also corrected the polling JSON's first-sample label without changing any sample and updated current compatibility/upgrade/identity documentation. All five archived prior-state files match committed HEAD exactly. Final full-suite, lint/format/diff, offline evaluations, renderer and repeated corrected-source package proof are recorded in the [conditional acceptance section](../../docs/verification/database-phase4.md#conditional-commit-review--2026-10-04). The source implementation passes review and is delivered in the authorized local commit. Historical phase counts and original packaging records remain as-of evidence; the corrected-source package record supersedes their final-source claim. No providers, credentials, user-database mutation, installed replacement, push or release occurred. The external/native acceptance gates remain open.
