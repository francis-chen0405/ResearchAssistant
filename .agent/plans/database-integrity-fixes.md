# Database integrity fixes

Status: authorized 2026-09-27 by the user’s request to fix all ten database review findings; implemented, reviewed, and verified 2026-09-28 for the local fix commit.

## Scope

Reject newer database schemas before writes; atomically persist fresh-v2 terminal results and repair interrupted terminal manifests; correct legacy portfolio snapshot lookup and make partial portfolio replay safe; preserve cached/uncached token usage; return typed import validation failures; clean up only import files created by the operation; validate foreign keys, complete trigger definitions, and required table shapes.

Schema 14 adds nullable cached/uncached input-token columns to model attempts. Historical values stay unknown, exact costs and immutable artifacts remain unchanged, and read-only inspection continues to support schemas 7–14 without migration. This explicit authorization supersedes the completed audit-maintenance plan’s no-schema-change boundary for these fixes only.

## Verification and boundaries

Add regression tests before integrity fixes where practical. Use temporary databases and offline provider fixtures only. Run the full pytest suite, Ruff checks and formatting, and git diff checks; retain existing skips and assertions. Test upgrade from schema 13, older read-only compatibility, rejected future schemas without mutation, rollback/replay, and malformed database rejection. Record actual results in STATUS.md and HANDOFF.md.

No new dependencies, paid calls, research-policy changes, native installer publication, or replacement of the installed app. Prior release evidence remains historical; modified source requires a rebuilt artifact for future distribution checks.

## Completion

All ten findings are addressed. Verification passed 1,204 tests with 2 unchanged skips (warnings as errors), Ruff, formatting, and whitespace checks. Read-only terminal-history projection also handles older results that cannot resume under current fingerprints. Historical source rows and artifacts remain unchanged. See [verification](../../docs/verification/database-integrity-fixes.md) for the checks and unchanged release boundary.
