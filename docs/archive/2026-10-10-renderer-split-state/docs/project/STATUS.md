# Current status

[Prompt 10 Python API responsibility split](../verification/api-module-split-2026-10-10.md)
assigns all 21 HTTP operations to seven small route owners under
`backend/src/researchassistant/api/`. Application assembly/authentication/lifespan and
shared lifecycle coordination remain central. Result/evidence reads and diagnostic
projection use application services. The 334-line public API facade preserves imports
and `create_app`; explicit legacy `app`/`runtime` access initializes one lazy pair.
Importing either canonical or historical facade creates no runtime or application.

Prompt 08's backend/renderer folder ownership and Prompt 09's guidance/test navigation
remain in place. [The test map](../../tests/README.md) includes the new contract regression;
[the ownership/compatibility record](../verification/api-module-split-2026-10-10.md)
contains exact route mapping and before/after evidence. Earlier repairs and immutable
history records are preserved.

## Verified current source

- macOS 26.6.2 arm64 / Python 3.12.14: **2,387 Python tests pass, 5 existing skips**
  (2,392 collected). **208 focused tests pass** for API/security,
  atomic lifecycle, rejected resume, credentials, read consistency/read-only inspection,
  polling and evidence display. The ten new split regressions pass, including closure
  checks on the request thread that owns each SQLite connection.
- All **21 routes** register exactly once. Saved OpenAPI/route metadata and **24 offline
  responses** match; every operation shares session/host/origin guards. HTTP contracts,
  redaction, lifecycle reservations and rejected-resume semantics remain unchanged.
- Ruff lint/format (**403 Python files**), repository/type boundaries and staged/unstaged
  whitespace pass. Current navigation has zero broken links; nine preserved archive
  references retain their preceding meaning.
- All five offline browser/API/race smokes pass, including rejected resume, interrupted
  restart, service readiness and preference/history ordering. Renderer lint/types,
  **20** desktop handler tests and native shutdown smoke pass.
- Current frozen backend rebuild and isolated native smoke pass authentication, UI,
  temporary vault cleanup/settings and owned acquisition start/stop. All **246** frozen
  source/configuration files match the checkout byte-for-byte.
- The exact **251-file wheel** and fresh wheel/editable installs from unrelated directories
  pass CLI/API health, **63** historical module aliases, prompt/font parity, offline fixture
  release/block, binding replay and Unicode PDF. No runtime dependencies changed.

Source, wheel/editable and frozen source payload identity:
`source-sha256:a524568b2932d8ab6e5058adfd6196899e4f7d7a71cd586549d7b84d8ccafc6d`.
The frozen executable additionally binds its bytes; the verification record owns its hash.
Changed executable source still requires a fresh run under the unchanged exact resume gate.
Historical inspection/export, immutable release hashes, reservations and prompt/policy
meanings remain preserved.

## Git and installed delivery

Local `master` HEAD remains `94a241b`; no branch switch, staging, commit, fetch or push
occurred. The pre-existing staged diff is byte-identical. Earlier dirty repairs and archive
records are preserved; the migration and API split remain unstaged for review. Tests used fake providers
and isolated data. No paid calls or real research databases were modified.

The installed Mac app is the [October 9 build from `27aeb95`](../verification/current-app-install-2026-10-09.md)
at `/Applications/ResearchAssistant.app`, including schema 17 and source-discovery/review
changes through `15b8281`. The preceding Prompt 09 read-only recheck confirms the backend SHA-256
`12e1705b6790b2532e8284ce5baa32e25f09b83de701dd15ce6d0415945c03f5`
matches that installation record. This is an unsigned local Apple Silicon build.
The later folder migration built local resources and requires a fresh source identity;
it did not replace the installed app or create new installers/public releases.

The public releases API still lists only
[the September 28 unsigned test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928)
from `ac49404` (published September 28 Pacific), with DMG/ZIP/checksum/readme assets.
It predates the October installed build and current source. Signing/notarization and
signed public distribution remain unverified. Prior implementation and verification records remain in
[grouped history](../history.md); exact replaced documents are in [the archive index](../archive/INDEX.md).

## Open boundaries

Python 3.11, Linux execution, native Windows/Jobs, fresh installers, clean-machine/minimum-OS
acceptance and signing/notarization were not tested locally. CI definitions are not executed
platform evidence. Installed-app replacement/publication and live research-quality acceptance
remain separate actions. The prior paid acceptance allowance remains exhausted.
