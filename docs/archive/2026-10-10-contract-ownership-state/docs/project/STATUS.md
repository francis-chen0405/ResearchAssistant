# Current status

[Prompt 11 renderer feature split](../verification/renderer-split-2026-10-10.md)
is implemented locally. Root `frontend/` owns the renderer. Its page composes
research, history, preferences/configuration and result/trail hooks and feature
views in **182 lines**, down from 784. Visible settings, support/challenge controls,
cost/provenance disclosures, modal accessibility and reduced motion are preserved.
Source leads remain separate from admitted evidence; research policy is unchanged.

The renderer API types are generated from backend OpenAPI and existing typed
serializer/catalog models. Byte parity and representative offline HTTP payloads
are checked mechanically. The successful JSON decoder still trusts the local API;
these static checks do not add runtime validation. All **21 routes**, saved OpenAPI
and **24 offline responses** match the immutable Prompt 10 fixture.

## Verified current source

- Frontend lint, TypeScript, generated contract check and static export pass.
  All **3** contract tests and all **5** offline browser/API smokes pass.
- Stale configuration/history selections are ignored; sequential polling reaches
  terminal state with at most one same-run request in flight. Result/trail requests
  abort on navigation; late responses cannot reopen stale UI. Ordered preference
  saves, bounded service readiness, dialog keyboard/focus and reduced motion pass.
- **90** focused API/credential/read/poll/evidence tests and **36** CLI/API subprocess
  tests pass (the subprocess selection has one existing skip).
- macOS 26.6.2 arm64 / Python 3.12.14: **2,390 Python tests pass, 5 existing skips**
  (2,395 collected) in the fresh full run.
- Ruff lint/format (**405 Python files**), repository/type boundaries and staged/
  unstaged whitespace pass. **20** desktop handler tests and all **9** local native
  process shutdown modes pass.
- Current documentation navigation has zero broken links; nine immutable archive
  references retain their preceding meaning.
- Frontend CI independently checks contracts, lint/types, export and the shared
  five-smoke runner before native packaging is needed. Desktop CI retains its frozen
  backend, native window/shutdown and unsigned installer paths. Local static export
  does not verify an installed app or a signed installer.

[Prompt 10](../verification/api-module-split-2026-10-10.md) owns the preceding backend
route split, frozen backend and fresh wheel/editable install evidence. No backend
source, executable identity inputs, prompt/font bytes or dependency locks changed
in Prompt 11. Historical inspection/export, release hashes, reservations and exact
resume compatibility remain preserved. [The test map](../../tests/README.md) and
[architecture](ARCHITECTURE.md) locate current owners and commands.

## Git and installed delivery

Local `master` HEAD remains `94a241b`; no branch switch, staging, commit, fetch or push
occurred. The pre-existing staged diff is byte-identical. Earlier dirty repairs,
migration, API split and stable historical records are preserved for review. Tests
used fake providers and isolated data, with no paid calls or real database changes.

The installed Mac app remains the [October 9 build from `27aeb95`](../verification/current-app-install-2026-10-09.md)
at `/Applications/ResearchAssistant.app`, including schema 17 and source discovery/
review changes through `15b8281`. The preceding Prompt 09 read-only recheck recorded
backend SHA-256 `12e1705b6790b2532e8284ce5baa32e25f09b83de701dd15ce6d0415945c03f5`
matching that installation record. This is an unsigned local Apple Silicon build
that predates the owning-folder migration and current renderer refactor. It was
not replaced, and no installer or public release was created by this task.

The preceding release record describes the
[September 28 unsigned test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928).
Its assets predate the October installed build and current source; public release
state was not rechecked in this frontend task. Signing/notarization and signed public
distribution remain unverified. Prior verification records remain in
[grouped history](../history.md); replaced documents are in [the archive index](../archive/INDEX.md).

## Open boundaries

Next is source review/commit, or separately authorized native delivery. Python 3.11,
Linux execution, native Windows/Jobs, fresh installers, clean-machine/minimum-OS
acceptance and signing/notarization were not tested locally. Workflow definitions
are not platform execution evidence. Installed-app replacement/publication and
live research-quality acceptance remain separate actions; the prior paid allowance
remains exhausted. [HANDOFF](HANDOFF.md) records this next boundary.
