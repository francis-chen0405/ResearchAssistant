# Database integrity fixes — verification

Verified 2026-09-28 on local macOS using the repository `.venv`. The user authorized all ten findings in the database review; scope is recorded in [the plan](../../.agent/plans/database-integrity-fixes.md).

## Implemented fixes

| Finding | Resolution | Regression coverage |
| --- | --- | --- |
| Newer schemas accepted for writes | Inspect recorded version before initialization DDL or updates; reject newer databases without changing bytes. | `test_database_schema_integrity.py` |
| Terminal result and manifest split across commits | Commit both in one transaction; explicit compatible resume repairs interrupted manifests using the saved completion time. Read-only history projects saved terminal status for current and older result keys without requiring resume or mutating the database. | `test_database_transactions.py` |
| Legacy portfolio loses snapshot provenance | Look up the snapshot by retrieval-attempt identity when constructing source-family and trail rows. | `test_database_transactions.py` |
| Partial portfolio writes cannot replay | Commit family/trail/portfolio rows as a batch. Preserve prior timestamps and accept matching replays; reject conflicting content. Recognize the narrow earlier missing-provenance projection without rewriting it. | `test_database_transactions.py` |
| Cached-token usage disappears | Schema 14 adds nullable cached/uncached input-token fields. Insert, completion, and read preserve values and exact cost. Missing historical values remain unknown. Identical completion replay succeeds; conflicting completion fails. | `test_database_cache_accounting.py` |
| Invalid imports return HTTP 500 | Catch typed compatibility failures and return the sanitized 422 response; retain active-run 409 handling. | `test_database_import_failures.py` |
| Import collision deletes another file | Remove a failed destination only after this operation created it. Close the SQLite backup target explicitly. | `test_database_import_failures.py` |
| Broken references accepted | Validate foreign keys as well as physical/schema integrity. | `test_database_schema_integrity.py` |
| Inert triggers accepted | Compare full normalized known trigger definitions, including conditions and bodies. | `test_database_schema_integrity.py` |
| Malformed table shapes accepted | Compare canonical declarations, required version-specific columns, and constraints before writable migration and during read-only validation. Reject unexpected constraints too. Malformed migration versions produce typed compatibility errors. | `test_database_schema_integrity.py` |

The canonical schema is built in an isolated in-memory database from executable migration definitions. Only those static definitions and pure SQL tokenization are cached; live database validation results and connections are not cached. Inspection rechecks each requested database.

## Verification results

- `.venv/bin/pytest -q -W error`: **1,204 passed, 2 skipped**, 63.21 seconds. The skips are unchanged from the baseline. There are 41 new regression cases across the four database test files.
- `.venv/bin/ruff check .`: passed.
- `.venv/bin/ruff format --check .`: passed; 162 files already formatted.
- `git diff --check`: passed.
- Focused checks cover actual transaction rollback, no-provider terminal resume, unchanged read-only history bytes, imports and source-file preservation, schema-14 migration rollback, all supported historical schemas 7–13, exact-cost preservation, and semantic replay conflict rejection.
- New schema-validation and historical-status regressions were observed failing before their corresponding fixes. Existing migration tests retain their assertions and now include the schema-14 record; the historical schema-10 fixture removes later migration records when constructing that older database.
- Sol reviewed transaction/recovery work and independently reviewed schema validation. Luna implemented and verified import and accounting fixes. The primary agent reviewed the integrated diff and completed the schema and history changes. The advisory code graph was refreshed after the repository changes.

## Compatibility and remaining release boundary

Only temporary test databases were used. No real user database was migrated or modified, and no paid provider calls or new dependencies were introduced. Completed immutable artifacts and historical accounting amounts are not rewritten. Earlier portfolio rows with missing provenance stay unchanged; replay can finish a partial batch but does not retroactively fill their unknown fields or recompute already completed coverage.

The installed app and packaged executables were not rebuilt or replaced. Earlier native/upgrade results apply to the preceding maintenance commit. These source changes require a fresh build and artifact-specific checks before distribution. Existing source/policy fingerprint checks still reject incompatible research resume; read-only inspection remains available. Mac-first delivery, the exhausted paid-test allowance, and open public-release gates are unchanged.

This record accompanies the local database-fix commit; no push or release publication is included.
