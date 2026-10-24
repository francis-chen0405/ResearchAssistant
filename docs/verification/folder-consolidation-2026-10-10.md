# Owning-folder consolidation — Prompt 08

Verified October 10, 2026 on macOS 26.6.2 arm64 / Python 3.12.14. This is a
repository/source migration; the installed native application was not replaced,
and no installer or public release was produced. [DebateAI](https://github.com/justinwen4/DebateAI)
was used only as a clarity reference for recognizable folder owners.

The original migration's results and fingerprints below are retained. The
[review fixes](#review-fixes) supersede them for the repaired current source.

## Starting state and preservation

Started on `master`, HEAD `94a241b`, with substantial earlier staged/unstaged changes.
The [Prompt 07 record](backend-installability-2026-10-10.md), actual build hook,
explicit manifests, resource helpers, CLI/API construction and exact source identity
were inspected before relocation. The live predecessor identity matched that record:
`source-sha256:3db588793ffa3fd023a39172b798eec5682202a53c433dbb2b056a4d46945e5b`.
No missing installability implementation was found. The outside-checkout verifier
was carried through the migration and expanded to test every module facade and an
actual API health request. All 18 historical prompt hashes, font/license bytes,
policy/schema history, release reconstruction and immutable resume gates remain intact.

The pre-existing staged binary diff is byte-identical to its starting snapshot.
Earlier runtime/test/frontend repairs were moved with their owners; no branch switch,
staging, commit, fetch, push, paid call or real research-database mutation occurred.
Current documents replaced during cleanup have exact snapshots under
[the starting-state archive](https://github.com/francis-chen0405/ResearchAssistant/tree/archive-2026-10-23-docs-baseline/docs/archive/2026-10-10-folder-consolidation-state).
Earlier archives were not rewritten. Obsolete ignored flat-layout build/metadata/cache
files were preserved under `backend/build/pre-migration-local-cache/`.

## Review steps and intermediate checks

1. **Backend distribution/runtime.** Move the installable project to `backend/`,
   preserving explicit source/data discovery and exact installed configuration bytes.
   Move canonical implementation to `backend/src/researchassistant/`, Python API/services
   to `researchassistant.api`, agents to `researchassistant.agents`, and providers to
   `researchassistant.providers`. Shared renderer and synthesizer have a single canonical
   owner in `researchassistant.evidence`; historical and current consumers use it.
   Install historical namespaces as thin module aliases under `backend/src/`.
   Intermediate CLI/API imports, console help, wheel/editable outside-cwd installation,
   18 prompts/font, release/blocked fixtures, fresh binding/replay and Unicode PDF passed.
   Scoped history/CLI/resume/lifecycle/fallback checks passed: **108 passed, 1 existing skip**.
2. **Renderer rename.** Rename the existing Next.js tree from `web/` to root `frontend/`,
   preserving its earlier local changes. Update static export, desktop mount/build/smoke
   paths and the native command launcher. The installed historical Python `frontend`
   package remains importable beside the renderer directory. ESLint, TypeScript and a
   fresh webpack static export passed. No renderer feature behavior was changed.
3. **Tooling, CI and records.** Root `pyproject.toml` now owns workspace checks;
   `backend/pyproject.toml` owns distribution metadata. CI installs `./backend[dev]`,
   runs isolated install verification, both offline evaluations and independent frontend
   checks, with native integration retained in desktop CI. Root ownership permits only
   the agreed files/folders, and the six dependency exceptions retain exact symbols,
   counts and reasons with updated paths. Project records move to `docs/project/`;
   current links, fixtures and source-reading tests follow their owners. The frozen
   builder stages an explicit clean source/resource manifest under `backend/` and
   includes installed compatibility imports. Final checks below passed.

The intermediate stages were scoped source/install/renderer checks. Native source data,
resources and the frozen executable were regenerated and verified after all three steps;
the earlier generated bundle was not represented as a current intermediate build.
The changes remain unstaged for review alongside the untouched earlier staged work.

## Final owners and transition exceptions

```text
backend/                 Python distribution, requirements and build support
  src/researchassistant/ canonical runtime, API, agents, providers and resources
  src/{agents,providers,frontend}/  installed historical namespace facades
  src/{cli,models,orchestrator,store}.py  installed module facades
frontend/                Next.js renderer
desktop/                Electron/native shell and packaging
tests/                  regressions
evaluations/            offline integrity/research benchmarks
docs/project/           current architecture/conventions/decisions/status/handoff
docs/{proposals,verification,archive}/
scripts/                workspace tools and build-hook facade
.github/                CI
.agent/                 plan index and historical plans
```

Root retains README, AGENTS, normal Git configuration, workspace `pyproject.toml`,
`cli.py` and `Launch ResearchAssistant.command`. The two root launchers require the
backend installation and are explicit transition exceptions. The historical
`.agents/PLANS/phase-00-foundation.md` keeps its stable path. Ignored developer
configuration, environment/data folders and hidden caches remain outside the tracked
root allowlist. The root guard respects pending working-tree deletions so review can
preserve the original index; staged additions and committed/live illegal owners still fail.

`scripts/build_distribution.py` remains a workspace facade for the self-contained
backend build hook in `backend/_build/build_distribution.py`; the source distribution
includes that implementation. It is excluded from the installed runtime. The optional
Streamlit fixture UI remains backend-owned and outside the base dependency set.

## Exact packaged surface and identity

The final wheel has **231 files**. [The exact inventory](folder-consolidation-2026-10-10-wheel-files.txt)
is audited against every current source/resource byte:

| Contents | Count |
| --- | ---: |
| Canonical `researchassistant/**/*.py` | 134 |
| Installed `agents`, `providers`, Python `frontend` facades, including namespace initializers | 66 |
| Installed `cli.py`, `models.py`, `orchestrator.py`, `store.py` | 4 |
| Executable prompt Markdown | 18 |
| Font, license and font README | 3 |
| Exact installed backend build configuration | 1 |
| The five allowed distribution metadata files | 5 |

The wheel contains no tests, archives, fixture inputs, caches, secrets, SQLite data,
Electron/Node or Next.js output. Its archive SHA-256 for this build is
`242f5f8c4d8d7f058a121915af7b3007ffe08fb5e6b63f3d5787c7381bbd976f`;
timestamps can change the archive hash on a subsequent build. A self-contained
source-distribution rebuild produced the same exact wheel payload.

The source, editable, wheel and actual frozen source-data identities agree:
`source-sha256:da36d190283ef68a2fcf8a82c47bcb4c19147c0275ed6919cd262fc3c4a6a5d6`.
The current executable additionally binds executable bytes:
`source-sha256:bae4706595ebaa036291f96822c50104e3aa826b116af5643e0f4e66c9e5b7e9`.
All 226 frozen source/resource/configuration files match the wheel/source bytes exactly.
The configuration hashes as `backend/pyproject.toml`; installed/frozen sources hash as
current `backend/src/...` paths. These are the new distribution's install mapping,
not a conversion or normalization of any stored predecessor fingerprint.

The migration regression freezes the actual Prompt 07 source identity in an isolated
fake-provider interrupted run, then attempts resume with the current source. The
existing binding conflict rejects it, makes zero model/search/acquisition calls,
and leaves the database bytes and physical-call audit unchanged. Its existing rejection
classification is retained. Read-only history still succeeds after rejection. Existing
historical export/reconstruction and incompatible-resume tests pass; no old database,
hash, prompt bytes or policy meaning was rewritten.

## Final verification

- **2373 passed, 5 skipped in 220.51s (0:03:40)**. The five prior platform/opt-in skips remain.
  The first full run exposed five stale source/metadata/launcher test paths; they were
  corrected. The added source-identity regression was adjusted to poll the established
  status projection rather than the raw worker outcome. The final full suite is clean.
- Ruff lint/format, repository ownership/dependency guard, type contracts and staged/
  unstaged whitespace passed. Current relative documentation links resolve. The graph
  was checked/refreshed before discovery, after relocation and after implementation;
  consequential conclusions were verified against live source and tests.
- Two fresh environments, with no inherited system/user packages, verified wheel and
  editable installs from distinct unrelated working directories using isolated Python,
  no custom import path and no user provider credentials. Isolated builds and installs
  used cached declared dependency wheels; both `pip check` results passed. All **63**
  historical module facades alias canonical module objects, and four module facades
  preserve CLI/contracts/store/orchestrator identity. Console/module help, console fixture
  execution, API construction/OpenAPI and HTTP health, all prompt/font hashes, fresh
  binding/replay, released/blocked fixtures and a three-page Unicode PDF passed.
- **38 offline adversarial cases** and **six synthetic discovery scenarios** passed.
  This is regression evidence, not a live research-quality claim.
- Renderer ESLint, TypeScript and fresh webpack static export passed. All five offline
  browser smokes passed: research interface, bounded polling/rejected resume/interrupted
  restart, stale configuration/service readiness, TypeScript API/audit wiring and history races.
- **20 shutdown handler tests**, **nine native Mac ownership/process scenarios**, a freshly
  rebuilt frozen backend smoke from an unrelated cwd with an empty developer-tool PATH,
  the real desktop window and Electron deadline smoke passed. They covered authentication,
  namespaced dummy-vault cleanup, temporary durable settings, acquisition ownership,
  duplicate-launch exclusion, renderer isolation and shutdown.
- The native upgrade smoke read the existing installed executable and the new one using
  an isolated fake-provider historical database and dummy credential namespace. Credential/
  preference continuity, identical validated historical brief, unchanged database bytes and
  distinct executable identity passed. It did not replace the application or touch real runs.

Sandbox attempts initially could not open loopback ports/use native vault/process access.
The applicable native/browser checks were rerun with authorized host access and passed.
No platform acceptance was inferred from workflow definitions or earlier artifacts.

## Untested delivery boundaries

Local Python 3.11, Linux runtime, native Windows/Windows Jobs, fresh installers,
clean-machine/minimum-OS acceptance, signing/notarization and public release were not
executed here. The current-source Mac installed-app replacement remains a separate
user-authorized delivery action. Current live research-quality acceptance is also separate.
Full logs and isolated build/install artifacts are retained under
`/private/tmp/researchassistant-prompt08/` for local review.

## Review fixes

The authorized review corrections restore `__main__` dispatch in the installed
`frontend.evidence_browser_app` facade while preserving ordinary canonical import
identity. Both optional Streamlit tools now name the existing
`backend/requirements-legacy.txt` in missing-dependency errors.

Four regression cases exercise module/script launch through a fake Streamlit UI
and both missing-dependency messages. The isolated installation verifier now checks
the real installed viewer module and script in fresh processes, requiring rendered
read-only controls without starting Streamlit or reading a database. All 31 focused
frontend/resource/type checks passed. The full suite passed: **2,377 passed, 5 existing
skips in 253.15 seconds**, on macOS arm64 / Python 3.12.14. Ruff lint/format, ownership
guard and staged/unstaged whitespace checks passed. Current archive-index links were
also corrected to the moved `docs/project/` owners.

Fresh outside-checkout wheel and editable installs passed the enhanced verifier;
the wheel still has exactly 231 files. Its SHA-256 is
`d5d676b210c7563c465baa0f5a8bfaf3a58e0444534d55fecfcd069f77a8c476`.
All 226 rebuilt frozen source/configuration/resource files match the current payload.
Source/editable/wheel/frozen source data agree on
`source-sha256:1824130e2c18fc260ca0b88c7113e3f33600d72ddea5434982844dae92bccbe3`.
The rebuilt frozen executable additionally binds executable bytes:
`source-sha256:155aa5982a81ddcf57d840c80a793954b34b67743a536dbb51d2f0ebf95cb883`.
The isolated frozen backend smoke passed authentication, native dummy-vault cleanup,
durable temporary preferences and owned acquisition lifecycle with an empty developer
PATH and unrelated working directory.

The review correction changes executable identity under the existing exact gate;
use a fresh research run. It does not modify historical databases, released bytes,
prompt/font resources, installed applications or publication. The earlier renderer,
offline evaluation, native ownership/window/deadline and upgrade results above were
not rerun for these optional-UI corrections. Platform/delivery boundaries remain.
Review-fix logs and artifacts are under
`/private/tmp/researchassistant-prompt08-review-fixes/`. Exact preceding current records
are preserved in [the review-state archive](https://github.com/francis-chen0405/ResearchAssistant/tree/archive-2026-10-23-docs-baseline/docs/archive/2026-10-10-folder-consolidation-state/before-review-fixes).
