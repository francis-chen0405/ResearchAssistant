# Current status

[Prompt 13 backend responsibility splits](../verification/backend-hotspot-split-2026-10-11.md)
is complete locally. Adaptive planning/novelty, execution/checkpoints and summaries
have single owners; budget-aware continuation remains in its compatibility module.
Round-4 authorization, planning, scheduling and admitted-evidence reconciliation
retain the hard four-round ceiling. Storage owns complete transaction aggregates;
research contracts have stage owners with unchanged public objects/serialized shapes.
Historical execution is isolated behind compatible module aliases after Prompt 12
removed inspection dependencies. Its inactive state machine remains intact.

## Verified current source

Checks completed October 11, 2026 on macOS arm64 / Python 3.12.14:

- Five sequential focused suites pass: **308, 257, 519, 474 and 419 tests**. Each owner
  passed the full Python suite, Ruff lint/format and staged/unstaged whitespace before
  the next move. Final result: **2,565 passed, 5 existing skips** (2,570 collected).
- **116 public class expectations** match: 102 schemas/configurations, 12 enums and
  2 historical exception identities. Old imports/pickle identities remain compatible.
  **360 original class/function bodies** have exactly one owner, preserving original
  logic apart from explicit dependency forwarding. All other original backend source
  bytes match; exactly five old owners changed and 27 extracted owners were added.
- Aggregate rollback/replay, concurrent reservations/finishes, cancellation, retry and
  unknown exposure, schema 7–17 reads, backups/recovery and historical exports pass.
  BEGIN/SQL/commit/rollback/close sequences and migration owners remain unchanged.
- Fresh processes resolve nine stage schema groups with execution imports blocked;
  historical inspection/export blocks all old/new executor names. Recorded release
  hashes and database bytes/mtime remain unchanged. Pre-split source identity cannot
  resume under current source: rejection precedes provider calls or database rewrites.
- All 18 prompts, 3 font/license/README resources and the prompt marker retain hashes.
  Exact **293-file** wheel and fresh wheel/editable installs from unrelated directories
  pass with identical identity/resources, all aliases, API and fixture/PDF/replay checks.
- Both offline evaluations pass: **38 integrity cases**, **6 synthetic discovery
  scenarios**. No live research-quality improvement is claimed.
- Ruff lint/format (**449 Python files**), root/dependency/type boundaries, generated
  renderer API parity and staged/unstaged whitespace pass. The graph is refreshed;
  live source and semantic tests verify its advisory findings.

Desktop **20 unit checks**, native POSIX shutdown/manager handoff cases and real
Electron startup-failure cleanup pass. The rebuilt macOS arm64 frozen backend passes
API authentication/origin protection, settings/restart persistence, native test-vault
cleanup and owned Wigolo lifecycle. Real desktop window, browser/Node isolation,
seven empty credential fields, duplicate exclusion and normal shutdown pass.
The build used `--backend-only`, retaining existing frontend/Node/acquisition/browser
resources. Its executable SHA-256 is
`94c047460129204e8bd3d1ffa6f2479ed3f545f6d4254090b340fee95840209d`.
No current installer or signed delivery was produced.

## Git and installed delivery

Local `master` HEAD remains `94a241b`; no staging, commit, fetch, push or branch switch
occurred. Earlier staged/unstaged repairs and consolidation remain intact; the original
staged binary diff is byte-identical. Tests used isolated data/fake providers, with
no paid call or real history change. Current source identity is
`source-sha256:4a9ce91342ff8933f7942d83dced1cd70b56f77ac80eac017e6a632aab5b2dc4`.
Stored fingerprints were not converted; changed identity requires fresh runs.

The installed Mac app remains the [October 9 build from `27aeb95`](../verification/current-app-install-2026-10-09.md)
at `/Applications/ResearchAssistant.app`, including schema 17 and discovery/review work
through `15b8281`. Prompt 09 recorded its backend SHA-256
`12e1705b6790b2532e8284ce5baa32e25f09b83de701dd15ce6d0415945c03f5`.
This unsigned Apple Silicon installation predates the current ownership work. It was
not replaced or rechecked here. The prior public artifact remains the
[September 28 unsigned test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928),
whose availability was not rechecked. Signing/notarization remains unverified.

## Open boundaries

Next is source review/commit, or separately authorized platform/delivery work.
Remaining large owners and reasons to defer are in the Prompt 13 record: historical
execution, schema/discovery persistence, shared base/evidence contracts, the v2
coordinator, acquisition, query execution and final release. Large store/adaptive
facades retain signatures/exports and defined connection/continuation responsibilities.
Python 3.11/Linux, native Windows/Jobs, current installers, clean-machine/minimum-OS
acceptance and signing remain separate gates. Paid quality allowance remains exhausted.
[HANDOFF](HANDOFF.md) records the next boundary; [history](../history.md) and
[archive index](../archive/INDEX.md) retain prior evidence and exact guidance.
