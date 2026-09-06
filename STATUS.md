# Current status

Active: **Phase 2 — Codebase and Documentation Cleanup**, on
`codex/phase-2-cleanup`. Implementation and documentation consolidation are in place;
final native-target verification is in progress. Phase 3 redesign has not started.

The Phase 1 desktop and completed v2 Phase 14 research behavior are preserved. Stable
imports now delegate to separate contract, fixture, schema, application identity,
progress and history modules. No dependency, prompt, research-policy or database
semantic change was introduced. Source fingerprints change: start a new run;
historical inspection/export remains supported.

Verification: baseline 909 passed / 2 existing skips; the refactored existing suite
also passes (923 passed including 14 new regressions, 2 existing skips). All 160 model schemas and complete SQLite SQL/migration rows match the
baseline. New import-order and fingerprint regressions pass. macOS runtime rebuild and
native-vault/backend/acquisition smoke pass. Installer/window and native Windows checks
are being completed; see [verification record](docs/verification/phase-2.md).

Phase 1 signing/notarization, minimum-OS and clean-machine installation remain public
release gates. Native Windows success is not assumed from macOS results.

[Active plan](.agent/plans/phase-2-cleanup.md) · [Handoff](HANDOFF.md) ·
[Architecture](ARCHITECTURE.md). The complete former status history is preserved in
[the archive](docs/archive/pre-phase-2/STATUS.md); this concise state replaces it.
