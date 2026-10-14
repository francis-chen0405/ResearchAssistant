# Current status

[Prompt 08 owning-folder consolidation](../verification/folder-consolidation-2026-10-10.md)
is implemented and locally verified. Python runtime/API/agents/providers live in the
installable `backend/src/researchassistant/` distribution; root `frontend/` owns Next.js.
Current project records live in `docs/project/`. Installed historical namespaces remain
thin canonical aliases. Root contains only agreed tracked owners, configuration and
transition launchers, with the historical `.agents/PLANS/` path retained.

## Verified current source

- macOS 26.6.2 arm64 / Python 3.12.14: **2,373 Python tests passed, 5 existing skips**;
  Ruff/format/type/ownership/whitespace checks and current documentation links pass.
- Exact **231-file wheel**, self-contained source-distribution rebuild, fresh wheel/editable
  installs from unrelated directories, CLI/API health, 63 namespace module aliases,
  prompt/font parity, binding replay and Unicode PDF pass.
- **38 offline adversarial cases**, six synthetic discovery scenarios, renderer lint/types/
  static export and five offline browser smokes pass.
- Fresh frozen source-data/executable checks, 20 shutdown handler tests, nine native Mac
  ownership scenarios, desktop window/deadline checks and isolated old→new history/vault/
  preference continuity pass. Historical database and released brief bytes remain unchanged.

Source/editable/wheel/frozen source data agree on
`source-sha256:da36d190283ef68a2fcf8a82c47bcb4c19147c0275ed6919cd262fc3c4a6a5d6`.
The frozen executable has its own additional identity, recorded in the verification record.
The new source rejects Prompt 07's predecessor identity under the unchanged resume gate;
use a fresh research run. Historical inspection/export, immutable hashes, reservations
and historical prompt/policy meanings remain preserved.

## Git and installed delivery

Local `master` HEAD remains `94a241b`; no branch switch, staging, commit, fetch or push
occurred. The pre-existing staged diff is byte-identical. Earlier dirty repairs and archive
records are preserved; the migration remains unstaged for review. Tests used fake providers
and isolated data. No paid calls or real research databases were modified.

The installed Mac app remains the [October 9 build recorded from `27aeb95`](../verification/current-app-install-2026-10-09.md).
It was used read-only as the preceding executable in the isolated upgrade smoke. This
migration built local resources but did not replace the installed application or create
installers/public releases. Prior implementation and verification records remain in
[grouped history](../history.md); exact replaced documents are in [the archive index](../archive/INDEX.md).

## Open boundaries

Python 3.11, Linux execution, native Windows/Jobs, fresh installers, clean-machine/minimum-OS
acceptance and signing/notarization were not tested locally. CI definitions are not executed
platform evidence. Installed-app replacement/publication and live research-quality acceptance
remain separate actions. The prior paid acceptance allowance remains exhausted.
