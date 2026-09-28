# Current status

## Database integrity fixes — 2026-09-28

The [database integrity plan](.agent/plans/database-integrity-fixes.md) implements all ten review findings. Writable initialization rejects newer schemas before mutation; schema validation checks complete known table/trigger/index definitions and foreign keys. Schema 14 adds nullable cached/uncached input-token fields without inventing historical usage; compatible schema 7–13 inspection remains read-only.

Fresh-v2 terminal artifacts and run manifests commit together, and explicit compatible resume repairs previously interrupted current-policy completion metadata from the saved result. Read-only history also projects older terminal results correctly without requiring resume or changing database bytes. Legacy portfolio writes use correct snapshot provenance, atomic batches, conflict-checked replay, and a narrow recovery path for earlier missing-provenance projections; historical rows remain unchanged. Imports return typed input errors, preserve pre-existing destination files, and close backup connections.

Final verification passed **1,204 tests with 2 existing skips**, with warnings treated as errors; Ruff, formatting, and whitespace checks passed. The 41 new regression cases and exact boundaries are recorded in [verification](docs/verification/database-integrity-fixes.md). This record accompanies the local database-fix commit; no push is included. The earlier packaged/native evidence below applies to the preceding maintenance commit, not these source changes. The installed app has not been replaced, and these changes require a fresh build before distribution.

## Prior audit maintenance — 2026-09-26

The 2026-09-26 [audit maintenance](.agent/plans/audit-maintenance.md) is implemented and reviewed. Extraction records preserve selected effort; legacy routing policy is centralized; the upgrade harness handles startup readiness and output pipes with safe diagnostics. Package/CLI branding, optional Streamlit installation, pytest imports, the Starlette test dependency, generated-cache tracking, and current documentation are corrected. The already-merged remote cleanup branch was deleted.

The preceding commit `5c66287` fixes selected-provider endpoint validation, model-aware connection checks, saved-selection API checks, TypeError fallbacks, and stale frontend responses. Fresh v2 retains seven model choices by stage: Luna High defaults for Scout/extraction and XHigh for the other five. Historical Standard routes and stored runs remain compatible. The historical Luna pricing branch is required and retained.

## Prior maintenance verification — 2026-09-26

**1,163 Python tests passed, 2 existing skips, with warnings treated as errors.** Ruff, TypeScript, ESLint, offline evaluation, and all three browser smokes passed. The final frozen backend matches all 100 source identity inputs and passed its native smoke. Three consecutive old-to-new upgrade checks passed every credential, preference, historical-report, executable-identity, and database-integrity assertion.

The original intermittent timeout did not recur; its exact historical cause remains unknown. Confirmed readiness and pipe-handling defects are fixed and regression-tested. This establishes successful local upgrade checks, not universal unsigned-vault or platform acceptance. See [the verification record](docs/verification/audit-maintenance.md) for artifacts, timings, commands, and limitations.

Test-only `httpx2` and its constrained dependencies were installed. Streamlit is available through `requirements-legacy.txt`; runtime adapters still use httpx. The changes are recorded in the local maintenance commit containing this document; source commits have not been pushed and the installed app has not been replaced.

## Release gates

Live provider effectiveness and dependable live research completion remain unverified. The five-submission allowance is exhausted ($0.178617536 recorded exposure, no released final report); further paid research needs a new allowance. The Mac candidate remains unsigned, with clean-machine, minimum-OS, signing, and notarization checks open. Windows release work remains deferred.

Dated implementation and prior failed checks are preserved in [the archive](docs/archive/INDEX.md). They are historical evidence, not current download instructions.
