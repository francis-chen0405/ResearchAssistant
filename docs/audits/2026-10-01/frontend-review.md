# Frontend race review

Date: 2026-10-01

## Review coverage

Read the live web UI and supporting files: `web/app/page.tsx`,
`web/app/layout.tsx`, `web/app/globals.css`, `web/lib/api.ts`,
`web/lib/preview.ts`, `web/components/dialog.tsx`,
`web/components/provider-setup.tsx`, and `web/components/workspace.tsx`.
Read the nested `web/AGENTS.md` and the installed Next.js Client Component
guidance before making changes. Reviewed `desktop/frontend-smoke.cjs`,
`desktop/frontend-poll-smoke.cjs`, and `desktop/configuration-race-smoke.cjs`.
The codebase graph was not used as a source of truth for this UI review; all
reported paths and outcomes were checked against the live source and browser
smokes.

## Confirmed race and repair

The history view allowed a history request from an older SQLite path to commit
after the user had switched to a different path. Opening a saved run had the
same stale-response problem: a delayed snapshot could replace a later
selection, and a late response could navigate back to Research after the user
had moved elsewhere. A terminal result could also remain selected after
changing its database, and two databases can contain the same run ID.

`web/app/page.tsx` now uses generation IDs for history loads and selected-run
opens, invalidates pending work when the database or navigation changes, and
keeps the history list visible while a run is opening. Switching databases
clears history and a terminal result from the previous database; the database
field is locked during an active run so its polling association stays stable.
The result component key includes database path as well as run ID and status.

Added `desktop/history-race-smoke.cjs`. Its mocked routes hold an old database
history response and an older run snapshot while delivering the newer results
first. It asserts that the old database cannot replace the new list, the latest
clicked run remains selected, changing databases clears the prior terminal
selection, and navigating home during a pending run open stays on home.

Before the repair, I temporarily disabled the new stale-history generation
checks and ran the same offline regression. It failed as expected: the delayed
old-database response put one stale row back into the list (actual count 1,
expected 0). I restored the source exactly and rebuilt before post-change
verification.

## Verification

- Dedicated history race smoke after repair: **passed**, including overlapping
  run opens, database changes, and navigation during run loading.
- Existing `desktop/frontend-smoke.cjs`: **passed** against the rebuilt desktop
  static export.
- Existing `desktop/frontend-poll-smoke.cjs`: **passed** (5 snapshots; one
  in-flight snapshot maximum; stop, replacement, and unmount behavior).
- Existing `desktop/configuration-race-smoke.cjs`: **passed**.
- `web/node_modules/.bin/tsc -p web/tsconfig.json --noEmit`: **passed**.
- `web/node_modules/.bin/eslint app/page.tsx`: **passed**.
- Desktop export build with `RESEARCHASSISTANT_DESKTOP=1`: **passed**.

All browser checks used local mock responses. No provider calls or real
application data were used.
