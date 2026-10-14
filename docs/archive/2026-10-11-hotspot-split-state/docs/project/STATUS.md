# Current status

[Prompt 12 neutral contracts and historical inspection](../verification/contract-ownership-2026-10-10.md)
is implemented locally. Stable search/neighborhood, retrieval, extraction and historical
result data now have neutral contract owners with compatible public re-exports. Pure
query validation and metadata identity no longer load research execution. Historical
inspection, trail, evidence browsing, CLI inspection and exports use validated readers
without importing the old executable orchestrator. Explicit `legacy_runner` execution
and all historical artifacts remain supported.

All six reviewed import exceptions migrated and the baseline is empty. Contracts reject
provider/agent/research imports; storage rejects agent/research imports, including local
and `TYPE_CHECKING` forms. Storage retains two documented pure provider helpers: URL
canonicalization and saved OpenAlex response parsing. Current v2 still uses the shared
evidence renderer/synthesizer; Researcher/Analyst remain compatibility facades.

## Verified current source

Checks completed October 11, 2026 on macOS arm64 / Python 3.12.14:

- **2,439 Python tests pass, 5 existing skips** (2,444 collected).
- Four focused steps pass: **139**, **185**, **202** and **139** tests, covering public
  schemas/aliases, exact serialization, query/seed replay, historical release hashes,
  read-only access, exports, incompatible resume, types and import boundaries.
- **36** pre-change schema/config/enum fingerprints match; **32** moved class/function
  bodies retain their original AST apart from the deliberate compiler import change.
  Fresh processes block both old orchestrator names while inspecting/exporting both
  historical August fixtures. Database bytes and mtime remain unchanged.
- All **18** prompt resources and **3** font/license/README resources retain their
  SHA-256 values. Released text, historical fixtures and stored fingerprints were not
  rewritten. Exact resume checks require new runs for this changed source identity.
- Exact **266-file** wheel audit and fresh wheel/editable installs from unrelated
  directories pass: matching source identity/resources, credential-free API assembly,
  released/blocked fixtures, three-page PDF and fresh/replayed discovery bindings.
- Ruff lint/format (**421 Python files**), root/dependency/type boundaries and staged/
  unstaged whitespace pass. The refreshed graph maps the new owners; live source and
  runtime checks establish compatibility. No startup-cycle failure was claimed.

The renderer retains the [Prompt 11 feature split](../verification/renderer-split-2026-10-10.md)
and prior frontend/browser evidence. No frontend source or dependency lock changed in
Prompt 12. Full Python coverage includes saved API/renderer contracts; current route,
OpenAPI and offline response parity remains checked. Native installers/window delivery
and frontend static/browser builds were not repeated in this backend ownership task.
[The test map](../../tests/README.md) and [architecture](ARCHITECTURE.md) locate owners.

## Git and installed delivery

Local `master` HEAD remains `94a241b`. No branch switch, staging, commit, fetch or push
occurred. The pre-existing staged binary diff is byte-identical. Earlier dirty repairs,
consolidation, API and renderer work and stable historical records remain for review.
Tests used fake providers and isolated data; no paid calls or real history changes.
Current source identity is
`source-sha256:3768f41771f0fe210ceda310b7867b7963df52c9c8ec1a549b5aec63dc2a577f`.

The installed Mac app remains the [October 9 build from `27aeb95`](../verification/current-app-install-2026-10-09.md)
at `/Applications/ResearchAssistant.app`, including schema 17 and source discovery/
review changes through `15b8281`. Prompt 09's read-only recheck recorded backend SHA-256
`12e1705b6790b2532e8284ce5baa32e25f09b83de701dd15ce6d0415945c03f5` matching that record.
That unsigned Apple Silicon app predates the owning-folder and subsequent source work.
Its installation was not replaced or rechecked by this task; no installer/public release
was created. The preceding public artifact remains the
[September 28 unsigned test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928),
whose state was not rechecked. Signing/notarization and signed distribution remain
unverified. Prior evidence is retained in [grouped history](../history.md); exact replaced
guidance is in [the archive index](../archive/INDEX.md).

## Open boundaries

Next is source review/commit, or separately authorized native delivery. Python 3.11,
Linux execution, native Windows/Jobs, current installers, clean-machine/minimum-OS
acceptance and signing/notarization remain separate gates. The existing paid quality
allowance remains exhausted. [HANDOFF](HANDOFF.md) records the next boundary.
