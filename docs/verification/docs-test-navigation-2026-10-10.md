# Current guidance and test navigation — Prompt 09

October 10, 2026, macOS arm64 / Python 3.12.14. This task reconciles current
guidance after the owning-folder migration. Runtime, tests, fixtures, executable
prompts and packaged resources are unchanged. [STATUS](../project/STATUS.md) is
the sole current-state summary; this record owns this task's evidence.

## Starting state and provenance

Read root AGENTS/README, current conventions/architecture/decisions/status/handoff,
the plan index, the October 9 installation record, staged and unstaged Git diffs,
and the actual Prompt 01/07/08 verification and implementation files.

- Prompt 01's removed root copies and dependency guard remain in the local diff.
  The guard now permits only the root `cli.py` transition launcher, following Prompt 08.
- Prompt 07's supported distribution, console entry, package resources and verifier
  are present under their Prompt 08 backend owners. Its old flat-layout commands
  remain historical evidence, not current install instructions.
- Prompt 08 and its review corrections are implemented: `backend/src/researchassistant/`
  owns Python, `frontend/` owns Next.js, and `docs/project/` already owns current records.
  No second move was needed. Source/package/frozen checks remain in that task's record.
- Read-only recheck of `/Applications/ResearchAssistant.app` finds bundle ID
  `org.researchassistant.desktop` and backend SHA-256
  `12e1705b6790b2532e8284ce5baa32e25f09b83de701dd15ce6d0415945c03f5`,
  exactly matching the [October 9 installation from `27aeb95`](current-app-install-2026-10-09.md).
  It is an unsigned local build, distinct from the subsequently modified checkout.
- The public GitHub releases API lists one published prerelease,
  [v0.1.0-mac-test.20260928](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928),
  with target `ac494041c759f52980db82e29f5dda9ea68194fb`, published at
  `2026-09-29T05:35:00Z` (September 28 Pacific). Its body identifies an unsigned,
  unnotarized build; DMG, ZIP, checksum and readme assets remain listed. No assets
  were downloaded, app replaced or release published.

The graph index was checked/refreshed. Graph search and inbound tracing of
`execute_expansion` confirmed seed owner tests plus product-policy integration and
offline evaluation callers; live imports and assertions were checked before mapping.

## Current guidance and test navigation

Root README and AGENTS point to one [current STATUS owner](../project/STATUS.md).
The plan index identifies Prompt 09 and source review, not completed Prompt 08 as
active implementation. Handoff distinguishes the installed October 9 app from
the new source layout. Architecture defers provenance to STATUS; decisions no
longer claim the installed compatibility facades live at root.

[The test map](../../tests/README.md) groups owners/subsystems, gives full collection
and execution commands, and demonstrates seed-expansion file/function discovery,
focused owner checks and broader integration. Broad milestone/review suites remain
in full collection; no filenames, assertions, shared helper imports or fixtures changed.
Backend and renderer guides link to their actual owners. Desktop operations use
root-relative workspace commands and distinguish local unsigned packaging/installation
from signing, notarization, installer acceptance and public publication.

Exact replaced guidance is saved under
[the guidance snapshot](https://github.com/francis-chen0405/ResearchAssistant/tree/archive-2026-10-23-docs-baseline/docs/archive/2026-10-10-guidance-state).
Existing archive bytes and stable completed task records are preserved.

## Link audit and compatibility navigation

The audit covers local inline/reference links and Markdown heading fragments in
root, `docs/`, `.agent/`, `.agents/`, desktop/backend/frontend and test/evaluation
guidance. Executable prompts and generated/vendor/cache trees are excluded.
Archived paths are checked literally and, separately, at their original document
locations. The [archive index](https://github.com/francis-chen0405/ResearchAssistant/blob/archive-2026-10-23-docs-baseline/docs/archive/INDEX.md#old-guidance-paths) owns current
navigation for old root guidance and historical Python frontend documentation.

Current navigation and stable completed records have **zero** missing local targets
or heading fragments. **Nine** unresolved references remain in preserved archives:

The [machine-readable inventory](docs-test-navigation-2026-10-10-links.json) records
the complete counts and exact exception locations for **298 Markdown documents**.

| Preserved source | Line(s) | Former target |
| --- | --- | --- |
| `docs/archive/README.md` | 14–18 | `../../ARCHITECTURE.md`, `../../CONVENTIONS.md`, `../../DECISIONS.md`, `../../STATUS.md`, `../../HANDOFF.md` |
| `docs/archive/2026-10-07-source-preview-state/PLANS.md` | 10 | `../STATUS.md`, relative to original `.agent/PLANS.md` |
| `docs/archive/phase-2-handoff/HANDOFF.md` | 7 | `ARCHITECTURE.md`, `CONVENTIONS.md` |
| `docs/archive/phase-2-handoff/STATUS.md` | 23 | `ARCHITECTURE.md` |

These nine references map to the current owners through the archive index. Hundreds
of other literal archive-relative paths fail from their snapshot directory but resolve
from their original document location or within a preserved snapshot; they remain
intentional archival references. The old Python `frontend/README.md` references now
encounter a renderer guide at the same path, so the index explicitly points historical
service readers to the backend API guide and its original snapshot instead.

The published `master` README was read separately through GitHub's raw-content endpoint.
It establishes default-branch links to all five former root guidance files and the old
Python frontend guide. This working tree updates those links before publication; the
root README and archive index are compatible navigation entry points. Literal raw/file
URLs will still need consumers to update after the migration is committed/published;
Markdown cannot redirect those URLs. No external bookmarks or integrations were changed,
and the local audit cannot enumerate off-repository inbound consumers. Historical
commit-pinned links remain valid at their original revision.

## Verification and Git boundary

- Full Python suite: **2,377 passed, 5 existing skips in 231.60 seconds**;
  default collection discovers **2,382** tests. No test files moved or assertions changed.
- The exact test-map commands collect **69** seed-owner tests, **49** broader
  neighborhood/product integration tests and **4** selected runtime behaviors.
  The focused owner command also executes successfully: **69 passed**.
- Fresh **231-file wheel** and wheel/editable environments outside the checkout pass
  CLI/API health, **63** historical module aliases, prompt/font parity, fake fixture
  releases/blocks, binding replay and Unicode PDF. Console, module and root transition
  help plus recovery/import/export/run option checks pass. The documented example
  paths and flags agree with the installed CLI.
- Ruff lint and formatting (**381 Python files**), repository root/dependency guard,
  staged/unstaged whitespace and new-document whitespace checks pass. The original
  staged binary diff is byte-identical; all pre-existing archive snapshots and stable
  completed task records remain byte-identical. Only their mutable navigation index changes.
- Desktop shutdown handler command passes **20** tests. Renderer lint/types pass with
  pinned pnpm **11.19.0** and existing locked dependencies, disabling its implicit
  dependency reinstall using `--config.verify-deps-before-run=false`. Initial bundled
  pnpm/direct pinned invocations attempted that reinstall and failed at sandbox DNS/
  noninteractive module-purge checks. The pinned tool was downloaded to temporary
  storage; no project dependencies or lock files changed. Static/native builds and
  browser smokes retain the preceding Prompt 08 evidence; they were not rerun for docs.

Current source identity is unchanged:
`source-sha256:1824130e2c18fc260ca0b88c7113e3f33600d72ddea5434982844dae92bccbe3`.
No native app replacement or installer publication is required for this task.
An attempted `desktop/build.py --help` discovered that this script has no help parser;
it entered its checksum-fetch path and stopped at unavailable sandbox DNS before
staging/building resources. Build instructions were verified against live code and
existing Prompt 08 evidence instead of claiming a new native build.

Local HEAD remains `94a241b` on `master`. Earlier staged/unstaged migration and
repairs are retained. No branch switch, staging, commit, fetch or push is part of
this task. The starting staged binary diff is preserved separately for byte comparison.
No paid provider calls, real research database changes or credential operations occur.
