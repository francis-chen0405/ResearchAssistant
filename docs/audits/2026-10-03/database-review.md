# Database review — proposals for approval

Reviewed October 3, 2026, on macOS. This is an audit and proposal record. No application code, schema, or user database was changed. GPT-6-Luna helpers reviewed schema/migrations, reads, evidence consumers, and lifecycle paths; the primary agent reproduced and integrated the cross-cutting findings.

The strongest finding is an existing historical-read compatibility failure. The installed database passes the checks performed, but two completed runs in the repository's older research database cannot be inspected through the current evidence browser. The next priorities are complete accounting persistence, safe attempt completion, and consistent schema validation.

## Approval menu

Approve by ID; each row is a separately selectable scope. Sizes are relative implementation effort, not time estimates. All scopes are also grouped into [four comprehensive implementation prompts](implementation-prompts/all-four-prompts.md), ready to run sequentially.

| ID | Priority | Proposed change | Size |
| --- | --- | --- | --- |
| F1 | High | Preserve inspection/export access to historical records whose original contracts differ from current research rules. | Large |
| F2 | Medium | Persist cache-write token counts and the basis used to calculate model cost; restore identical-completion replay. | Medium |
| F3 | Medium | Make model-attempt reservation/completion check identity and reject concurrent conflicting completions. | Medium |
| F4 | Medium | Reject missing committed schema objects and inconsistent migration records before writable initialization. | Medium |
| F5 | Medium | Protect same-run provenance against updates, including changes to referenced parent ownership. | Medium |
| F6 | Medium | Make every path-based storage reader non-creating and read-only. | Small–medium |
| F7 | Low | Handle a new CLI database path whose parent directory does not exist. | Small |
| F8 | Medium | Count failed and fallback retrieval attempts in persisted v2 progress. | Small–medium |
| F9 | Low | Keep unreviewed evidence out of the legacy browser's “Rejected” filter. | Small |
| I1 | Optional | Add measured history/evidence indexes and batch related evidence queries. | Medium |
| I2 | Optional | Create imported database copies with owner-only permissions. | Small–medium |
| I3 | Optional | Provide verified backups before upgrades and an explicit restore workflow. | Medium |
| I4 | Optional | Design coherent read snapshots and a measured polling/reader-writer policy. | Large |
| X1 | Adjacent defect | Wrap and paginate exported PDFs, and preserve Unicode. | Medium |

Recommended first approval: **F1–F6**, then **F8**. F7 and F9 are smaller usability repairs. I1–I4 have different benefits and tradeoffs; they are not required to fix the confirmed defects. X1 concerns an export consumer, rather than SQLite persistence itself.

## What was checked

Source coverage included the full storage implementation and schema, all 14 migrations, all 37 current tables, every reader/writer, structural and foreign-key validation, transaction boundaries, exact-cost storage, immutable artifacts, provenance guards, import/backup cleanup, process locks, database path handling, and history/progress/evidence/export consumers. Database-related runtime and API entry points and the relevant contracts/tests were traced. Previously repaired issues in `docs/verification/database-integrity-fixes.md` were used as a baseline, rather than reported again.

The codebase graph was an advisory map. Its old module locations showed it was stale; no `index_status` tool was exposed. Automatic approval review rejected `index_repository` because a full refresh might transmit sensitive source to an unspecified MCP destination. The audit therefore relied on current local source, live query plans, isolated reproductions, existing tests, and read-only data checks. No workaround for the rejected refresh was attempted.

### Actual database checks

| Database | Size | Schema | Runs | V2 artifacts | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Installed `Application Support/ResearchAssistant/live-runs.sqlite3` | 36.3 MiB | 14 | 8 | 1,374 | Physical/FK/schema checks pass; all v2 artifact classes decode; history lists all 8 runs. |
| Repository `.researchassistant/live-runs.sqlite3` | 67.9 MiB | 13 | 47 | 2,509 | Physical/FK/schema checks pass; historical semantic incompatibilities detailed in F1. |
| Build acceptance `acceptance.sqlite3` | 11.4 MiB | 13 | 4 | 346 | Physical/FK/schema checks pass; all v2 artifact classes decode. |

Every table in those three databases was counted. Checks covered `integrity_check`, `foreign_key_check`, migration/schema compatibility, validity of JSON columns, payload/run identity where represented, every v2 artifact's stored SHA-256, lifecycle timestamps, and cross-run joins corresponding to provenance relationships. Native model readers were exercised across persisted rows, and every v2 payload was tested against its corresponding currently available class. No main-database physical corruption, broken foreign keys, invalid JSON, hash mismatch, or cross-run ownership mismatch was found. Read sessions used SQLite read-only mode; main-file size and modification time stayed unchanged.

There are also older generated fixture databases at schemas 1 and 3. They pass physical/FK checks and are correctly rejected by today's supported read-only schema boundary; they were not upgraded. The small performance-observer database passes physical/FK checks. Third-party acquisition caches were inventoried but could not be fully checked: the installed Wigolo cache failed read-only opening in this environment, and the build cache's table traversal requires the unavailable `vec0` extension. The latter's physical/FK checks passed before that limitation. Development package caches are outside the ResearchAssistant database scope. These limits prevent claiming that every auxiliary database is fully audited.

## Confirmed fixes

### F1 — Historical records need version-aware readers

**Evidence:** Two completed August 2 runs in the repository database contain native Ledger rows with Claim Fit 4, Evidence Quality 4, secondary placement, and historical entailment `Strong`. Today's `LedgerRecord.validate_score_contract` rejects them. Public evidence browsing fails for those two runs, and provider-run inspection raises validation errors. Across the 16 repository runs with native candidates, browsing succeeds for 14 and fails for 2. Research-trail reads also fail for 2 runs because historical researcher payloads conflict with today's query-intent or ranking validators. The history list itself still returns all 47 runs.

Separately, **188 of 2,509** repository v2 artifacts fail direct decoding under current classes: 14 queue results, 7 extraction results, 81 Analyst batches, 81 Reviewer batches, and 5 backfill results. The differences include earlier physical-call caps and Analyst/Reviewer policy identities. This is contract drift, not corrupt SQLite bytes. These v2 differences did not block the tested history listing or the 18 tested v2 research trails, whose readers consume different payloads. Installed and build-acceptance v2 payloads all decode.

**Locations:** `researchassistant/contracts/model_contracts.py:847`, `researchassistant/storage/store.py:1785`, `researchassistant/research/orchestrator.py:959`, `researchassistant/evidence/evidence_browser.py:181`, `frontend/live_history.py:114`; historical v2 contracts in `model_research.py` and `model_evidence.py`.

**Proposal:** Dispatch read-only historical decoding using recorded artifact/prompt/provider-policy identity, preserving the original evidence and validated output. Add real historical-format regression fixtures. Keep current research admission rules strict. Do not relabel old evidence as newly approved, rewrite immutable rows, recompute costs, or enable incompatible resume. If a historical version cannot be interpreted safely, show a per-record compatibility explanation while preserving access to unaffected history.

**Verification after approval:** Both affected historical browser/inspection paths and the trail failures must become readable under their historical interpretation; fresh admissions must retain all current validation failures, and database/output bytes must stay unchanged during inspection.

### F2 — Two usage fields disappear in route-attempt storage

**Evidence:** A valid completion with `cache_write_tokens=10` and cost basis `published_cache_prices_reported_writes` round-trips with both fields set to null. Repeating the exact original completion then raises “already finished differently” because the reconstructed stored model lacks those fields. Token totals and exact cost survive; this is missing explanation/detail, not a demonstrated change to the amount.

**Locations:** `researchassistant/contracts/model_contracts.py:1364`, `researchassistant/storage/store.py:2921`, `researchassistant/storage/store.py:2970`, `researchassistant/storage/store.py:3019`.

**Proposal:** Add nullable fields in a new migration, or persist complete validated usage metadata, and include them in insert/update/read/replay comparison. Leave historical unknowns null and existing exact amounts untouched. Test round trips and identical/conflicting replay for each supported cost basis.

**Scope:** Legacy accounting and current v2 Analyst/Reviewer route rows are affected. Current v2's separate physical-call completion artifacts already preserve both fields and drive overall budget snapshots; this finding does **not** establish understated v2 budget ceilings.

### F3 — Completion is neither identity-bound nor concurrency-safe

**Evidence:** Reserving an existing attempt ID with a different run/model/operation returns the original row without checking the supplied identity. Completing that ID with the mismatched model attaches the incoming cost/output to the original stored identity. In a deterministic two-thread reproduction, both workers read `running`, both submit different completions successfully, and the later write replaces the first cost/output. Sequential conflicting replay is rejected, but this race bypasses that check.

**Locations:** `researchassistant/storage/store.py:2787`, `researchassistant/storage/store.py:2901`.

**Proposal:** Validate the immutable reservation identity on replay and completion, then serialize completion with a write transaction and re-read under the transaction, or use a conditional running-to-terminal update plus checked row count. Matching completed replay succeeds; mismatched identity or conflicting terminal data fails. Preserve valid reservation reuse and conservative unknown-usage accounting. This is a storage-boundary defect; the audit did not observe wrong charges or conflicting writers in a real run.

**Verification:** Wrong run/operation/model/input/reservation tests, two simultaneous conflicting completions with exactly one accepted result, matching concurrent replay, and existing retry/resume accounting tests.

### F4 — Writable initialization can conceal schema damage

**Evidence:** After dropping `model_invocations` in a committed schema-14 database, read-only opening correctly rejects the missing table. Writable `init_db` skips its absence, recreates it empty, and subsequent inspection accepts the database. The lost rows were already removed by the drop; initialization conceals the missing-history condition instead of recovering them.

Writable initialization also accepts an incorrect migration-1 description and leaves it unchanged, while silently overwriting an incorrect migration-4 description. Read-only validation rejects inconsistent migration records. The two paths therefore disagree about what is safe to open.

**Locations:** `researchassistant/storage/store_schema.py:1427`, `researchassistant/storage/store_schema.py:1460`, `researchassistant/storage/store_schema.py:639`; comparison read-only checks at `researchassistant/storage/store.py:364`.

**Proposal:** Before any writable DDL, validate the complete committed migration ledger and the required objects for that recorded version. Allow bootstrap and objects introduced by genuinely pending migrations. Reject missing committed objects and changed descriptions without modifying the file. Reuse a common compatibility calculation across read-only and writable entry points.

**Compatibility:** Preserve recognized older upgrade paths, including schemas 7–13. Do not require current objects before their migration or remove established legacy upgrade handling without explicit compatibility evidence.

### F5 — Same-run guards cover inserts but permit provenance-changing updates

**Evidence:** A retrieval for run A with a query belonging to A can be updated to run B. Both foreign keys remain valid, `foreign_key_check` reports no violation, and read-only schema validation accepts it. Current same-run triggers fire only on insert. No such mismatch was found in the actual databases.

**Location:** `researchassistant/storage/store_schema.py:566`.

**Proposal:** Make provenance identity fields immutable, or enforce equivalent update guards. Cover referenced parents too: guarding only a child's update will not prevent changing ownership on its query/candidate parent. Add a read/import semantic check for same-run relationships so earlier violations are reported without rewriting history. Preserve intentional mutable run status/checkpoint/completion fields.

### F6 — Low-level reads can create an empty database

**Evidence:** On absent temporary paths, `read_run`, `list_runs`, and `read_snapshot` each raise a missing-table error after leaving a zero-byte database file. Both the shared path-based `_read_connection` and ten older direct readers use ordinary writable-capable `_connect`.

**Locations:** `researchassistant/storage/store.py:262`, `researchassistant/storage/store.py:271`, and the direct readers at `1275`, `1344`, `1419`, `1497`, `1570`, `1630`, `1686`, `1771`, `2015`, `2147`.

**Proposal:** Use a non-creating read-only URI connection for every path-based read; preserve caller-owned connection reuse and closure rules. Move direct readers onto that shared helper. Keep full compatibility validation at public inspection boundaries rather than repeating it for every point query.

**Scope:** Public history/browser/import opening already uses `ReadOnlyStore` and does not create missing files. This repair concerns lower-level storage APIs and their direct callers.

### F7 — A new CLI path fails before database initialization

**Evidence:** `_v2_database_lock` raises `FileNotFoundError` for its sidecar when the selected database's parent does not exist. The fresh-v2 CLI resolves the path and enters this lock without creating its parent. The legacy runner creates parents; desktop request validation requires an existing parent.

**Locations:** `researchassistant/research/v2_orchestrator.py:617`, `researchassistant/runtime/cli.py:264`.

**Proposal:** Create the explicitly selected database parent before locking, or give a direct CLI validation error. Prefer creation to match existing legacy CLI behavior, with sensible permissions. Test a temporary nested path and concurrent startup.

### F8 — Retrieval-attempt progress counts successful acquisitions

**Evidence:** Persisted failure-only acquisition output with one attempt and zero acquired sources displays zero retrieval attempts. A failed provider followed by successful fallback records two attempts but displays one. Current v2 progress increments the field from `output.acquisitions` instead of `output.attempts`.

**Location:** `frontend/live_progress.py:382`.

**Proposal:** Count attempts by discovery cluster/direction, including failed calls and fallback calls, while keeping acquired/usable snapshot counts separate. Add failure-only, fallback, multiple-round, and direction-isolation regressions. If the intended product metric is acquired sources, change its field/label consistently instead.

### F9 — Pending candidates match “Rejected”

**Evidence:** A temporary offline candidate with no Analyst or Reviewer decision is returned by public browsing with `approved=False`. `_matches` substitutes false for an absent Analyst decision; the legacy Streamlit UI labels that choice “Rejected.”

**Locations:** `researchassistant/evidence/evidence_browser.py:274`, `frontend/evidence_browser_app.py:41`.

**Proposal:** Match explicit stored decisions only, and optionally add a pending state. Preserve the distinction between Analyst and Reviewer decisions. This consumer serves legacy/native candidate rows; the installed v2 database has no rows in that native candidates table.

## Optional improvements

### I1 — Measured indexes and batched evidence reads

Actual schema-13/schema-14 files and a fresh temporary database use `SCAN runs` plus a temporary ordering B-tree for history, and scan/sort candidate/draft/ledger predicates that lack suitable indexes. A temporary native evidence browser performs 11 related-table queries for 2 candidates, 51 for 10, and 201 for 40: one candidate query plus five per candidate.

Add a history index on `(updated_at DESC, run_id ASC)`, and indexes matched to evidence predicates/orderings. Fetch related rows in batches and reconstruct the same typed result. Verify query plans, output equality, and representative timing before deciding the final index set. This mainly improves large histories and legacy/native evidence browsing; it is not proof that the present installed v2 UI is slow. Indexes add storage/write cost and require a migration.

### I2 — Private import copies

In a temporary reproduction, a pre-existing imports directory at mode 0755 stays 0755 and a copied database becomes 0644 under umask 022. Create new copies owner-only and enforce private modes for the application-owned default import folder; use an appropriate ACL policy on Windows. Do not unexpectedly change arbitrary caller-supplied folders. The actual installed app directory is already 0700 and the home directory 0750, so this audit did not establish current cross-user exposure of that database.

### I3 — Verified backup and restore

Current history import uses SQLite backup safely but is not an automatic pre-upgrade backup/restore facility. Add a bounded, verified backup before a writable upgrade, private storage, retention controls, and an explicit restore path. Use the shared worker lock and SQLite backup API. Do not rewrite completed artifacts or schedule a new automation as part of this proposal. Verification should cover interruptions, failed verification, space exhaustion, and restoration into a new path.

### I4 — Read consistency and polling scale

A `ReadOnlyStore` reuses one connection but does not begin an explicit read transaction; consecutive queries can observe successive commits. Main databases currently use rollback journaling. Any coherent request snapshot or WAL policy must address reader duration, writer contention, busy-timeout behavior, checkpointing, sidecars, backup/import, and shutdown together.

Opening/validating/closing the installed 36.3-MiB database measured 12.0 ms median over five local warm runs; the 67.9-MiB repository database measured 34.0 ms median. First samples were 198.3 and 339.6 ms. These are local validation measurements, not UI benchmarks. Full integrity/FK checks remain proportional to accumulated data. Benchmark growth, then consider lightweight polling checks with explicit full health checks at appropriate boundaries. Do not weaken corruption detection or cache compatibility merely by path/mtime. This is a separately designed optimization, not a blind WAL switch.

## Adjacent export defect

**X1:** `researchassistant/evidence/brief_export.py:201` emits one PDF page with no wrapping or pagination. Seventy lines produce one page; the content instructions place the last text baseline at `760 - 69×12 = -68`, below the page. Non-Latin-1 text is also replaced during encoding. Add wrapping, pagination, and suitable Unicode font handling; verify page content and layout. This does not require changing persisted evidence.

## Conditional finding and boundaries

Default desktop workers, fresh-v2 CLI/direct runs, and imports share the same database sidecar lock. The compatibility `run_provider_pipeline` entry point does not acquire that lock itself. If direct/injected legacy execution remains supported, extend the shared ownership protocol without double-locking controller-owned runs. SQLite backup remains transactionally consistent; the demonstrated gap is the importer's ability to recognize an active legacy worker, not a proven corrupt backup. No default v2 import/run race was found.

An exhaustive audit cannot prove absence of every future bug. In particular, Windows lock/ACL behavior and bundled third-party cache extensions were not exercised on Windows, and no provider calls or desktop rebuild were performed. Implementation, migrations, backups, installed-app updates, commits, and publication all await the user's selected scope.

## Verification and evidence

- Full existing Python suite: **1,400 passed, 2 skipped** in 79.94 seconds on macOS. No test assertions were changed. Passing baseline tests do not cover the newly reproduced cases.
- Repository lint and format checks pass; 192 files already formatted. `git diff --check` passes.
- Fresh temporary SQLite reproductions confirm schema masking, migration-ledger inconsistency, cross-run update acceptance, usage-field loss, replay failure, attempt identity mismatch, and conflicting concurrent completions. A Luna helper independently repeated the root attempt-write reproductions.
- Offline temporary fixtures confirm progress and filter errors and related-query growth. Actual database checks were read-only, and report outputs contain no claims, source text, credentials, or model outputs.
- [Database health and semantic-check counts](database-health.json) and [temporary reproduction outcomes](database-repro-results.json) accompany this record.

Only this audit record, its evidence files, and a history-index link were added to the repository. The proposed fixes have not been implemented.
