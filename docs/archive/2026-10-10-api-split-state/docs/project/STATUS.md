# Current status

[Prompt 09 guidance and test navigation](../verification/docs-test-navigation-2026-10-10.md)
reconciles current entry points and groups tests by subsystem/owner. Root README and
AGENTS point here for current state; [the test map](../../tests/README.md) keeps
focused checks and the full suite discoverable. Historical snapshots and completed
task records retain their bytes and dated meaning.

[Prompt 08 owning-folder consolidation](../verification/folder-consolidation-2026-10-10.md)
is implemented and locally verified. Python runtime/API/agents/providers live in the
installable `backend/src/researchassistant/` distribution; root `frontend/` owns Next.js.
Current project records live in `docs/project/`. Installed historical namespaces remain
thin canonical aliases. Root contains only agreed tracked owners, configuration and
transition launchers, with the historical `.agents/PLANS/` path retained.
The [review fixes](../verification/folder-consolidation-2026-10-10.md#review-fixes)
restore the optional evidence-viewer launcher and correct both Streamlit dependency messages.

## Verified current source

- macOS 26.6.2 arm64 / Python 3.12.14: Prompt 09 reran the full suite,
  **2,377 Python tests passed, 5 existing skips** (2,382 collected);
  Ruff/format/type/ownership/whitespace checks pass. Current navigation links resolve;
  nine preserved historical references to former root guidance remain, mapped in the
  Prompt 09 record. No archive bytes or stable completed task records changed.
- Prompt 09 reconfirms the exact **231-file wheel** and fresh wheel/editable installs
  from unrelated directories. CLI/API health, 63 module aliases, both installed
  evidence-viewer entry points using a fake Streamlit UI, prompt/font parity,
  binding replay and Unicode PDF pass.
- Prompt 08's rebuilt frozen source data matches all **226** current payload files. The isolated
  native backend smoke passes authentication, dummy-vault cleanup, durable temporary
  preferences and owned acquisition lifecycle.
- Prompt 09 also passes 69 focused seed-owner tests, 20 desktop handler tests and
  renderer lint/types with pinned pnpm and implicit reinstall disabled.
- The migration record retains the preceding source-distribution, offline evaluation,
  renderer/browser, native ownership/window/deadline and isolated upgrade verification.
  Those checks were not rerun for the optional Streamlit corrections. Historical
  databases and released brief bytes remain unchanged.

Source/editable/wheel/frozen source data agree on
`source-sha256:1824130e2c18fc260ca0b88c7113e3f33600d72ddea5434982844dae92bccbe3`.
The frozen executable has its own additional identity, recorded in the verification record.
The new source requires its exact identity under the unchanged resume gate;
use a fresh research run. Historical inspection/export, immutable hashes, reservations
and historical prompt/policy meanings remain preserved.

## Git and installed delivery

Local `master` HEAD remains `94a241b`; no branch switch, staging, commit, fetch or push
occurred. The pre-existing staged diff is byte-identical. Earlier dirty repairs and archive
records are preserved; the migration remains unstaged for review. Tests used fake providers
and isolated data. No paid calls or real research databases were modified.

The installed Mac app is the [October 9 build from `27aeb95`](../verification/current-app-install-2026-10-09.md)
at `/Applications/ResearchAssistant.app`, including schema 17 and source-discovery/review
changes through `15b8281`. Prompt 09's read-only recheck confirms the backend SHA-256
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
