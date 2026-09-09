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
