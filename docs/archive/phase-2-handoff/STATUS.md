# Current status

**Phase 2 — Codebase and Documentation Cleanup is complete** on
`codex/phase-2-cleanup`. Phase 3 frontend redesign has not started or been authorized.

Stable imports now delegate to coherent domain-contract, fixture, schema, shared
application identity, progress and history modules. Current documentation is consolidated;
original narratives are linked from the archive. No dependency, prompt, UI, research-policy
or database semantic change was introduced. Start a new run after updating; exact resume
checks remain intact and historical inspection/export remains supported.

Verification: **923 passed, 2 existing skips**; Ruff lint/format, full branch diff,
frontend lint/types/static build, and desktop checks pass. Both native macOS and Windows
CI jobs rebuilt, smoke-tested and packaged the final source revision. The local final DMG
also passed runtime/window smokes and archive validation. All 160 model schemas and
complete SQLite SQL/migration rows match the baseline. See the
[verification record](docs/verification/phase-2.md) for CI links and artifact checksums.

Signing/notarization, minimum-OS and clean-machine installation remain separate
Phase 1 public-release gates; these unsigned test artifacts do not close those gates.

[Completed plan](.agent/plans/phase-2-cleanup.md) · [Handoff](HANDOFF.md) ·
[Architecture](ARCHITECTURE.md). The full former status history is preserved in
[the archive](docs/archive/pre-phase-2/STATUS.md); this concise state replaces it.
