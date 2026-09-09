# Current status

Phase 3 frontend and provider/model settings were developed on
`codex/phase-3-frontend-settings` and delivered to local `master` at the user’s request. Verification and release limits are recorded in
[Phase 3 verification](docs/verification/phase-3.md). The authorized 2026-09-08 macOS
upgrade test passed for native credentials, preferences and research history. Windows
rebuilding remains outstanding; Phase 3 is not fully verified.

The redesigned welcome, interactive fictional preview, research workspace, evidence,
history and settings share one visual system. Provider credentials stay in the native
vault; non-secret preferences and the supported Standard model profile are separate
from frozen per-run configuration. Existing research behavior and database schema remain.
No new dependencies, paid calls, public publishing or next-phase work were introduced.

macOS unsigned test artifacts and screenshots are listed in the verification record.
Signing/notarization, clean-machine installation and minimum-OS checks remain release gates.
The Keychain upgrade prompt expects a Mac login/keychain password, not a provider API key;
its cancellation does not establish that the provider rejected a key.

[Active plan](.agent/plans/phase-3-frontend-settings.md) · [Handoff](HANDOFF.md) ·
[Architecture](ARCHITECTURE.md). This replaces the previous current-state summary;
the exact [Phase 2 status](docs/archive/phase-2-handoff/STATUS.md) and
[earlier history](docs/archive/pre-phase-2/STATUS.md) are preserved.

## 2026-09-08 visual refinement

The user requested warmer, more varied colors, automatic preview playback, a smaller
side-by-side desktop home layout and removal of repetitive explanatory/footer copy.
The initial viewport of https://nomu.store/ was inspected without scrolling or exploring
lower sections. Coral, apricot, green and plum now distinguish actions, workspace,
supporting and challenging evidence. The hero and preview share the desktop viewport;
narrow windows retain readable stacking and scrolling.

The isolated example automatically advances through preparation, evidence, completion,
interruption and recovery. Hover and keyboard inspection pause it; hidden documents do
not advance. Reduced-motion mode shows a static completed example. A compact Example
badge and fictional source labels preserve its distinction from actual research. No
provider calls, engine changes, new dependencies or storage changes were introduced.
This supersedes the earlier manual example controls and dark workspace styling.

Verification: 942 tests passed, 2 existing skips; Ruff, frontend lint/types/build,
offline browser acceptance, archive validation and packaged Mac window test passed.
Updated installer and screenshots: `desktop/dist/phase3-colors/`. Replace the installed
app to see this refinement. See the Phase 3 verification record for retry details
and unchanged Windows/public-release gates.
