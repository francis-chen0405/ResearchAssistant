# Handoff

Continue from the [database-review shared four-phase record](.agent/plans/database-review-2026-10-03.md). Use [STATUS](STATUS.md) for source, installed-app and public-download state. Prompts 1–3 are reviewed and committed. The installed app remains the preceding build.

## Next actions

1. Apply Prompt 4 for full-suite, cross-phase and measured performance/consistency work. Schema remains 16 and read-only support remains 7–16. Prompt 3's conditional-commit run passed 661 focused tests; no full suite was run for this phase. Retain its historical catalog and original values/hashes, strict current admission/resume rules, schema preflight, backup/lock boundaries, immutable artifacts and exact costs.
2. Before a separate release decision, build and verify the final artifact with ReportLab 4.4.9 and the bundled Unifont/license assets. Current packaging includes the complete backend data tree, but no new packaged executable was built or verified. Native Windows owner/SYSTEM ACL, NTFS publication and power-loss durability checks remain open; earlier live-quality, clean-machine, minimum-OS, signing and notarization gates remain in [STATUS](STATUS.md).

## Boundaries and remaining acceptance

The user authorized reviewing Prompts 1–3 and committing each successful implementation. Installed-app replacement, paid research, real-user database migration/restore/deletion, push and publication remain outside this task. Verification writes stay disposable. Historical decoding preserves recorded policies and does not authorize incompatible resume or fresh admission. PDF coverage limits are explicit; Markdown/DOCX retain the text when glyphs or shaping are unsupported. The exhausted paid-test allowance, release gates and separate OneDrive build-directory cleanup boundary remain unchanged.

Keep completed details in the task record and use [grouped history](docs/history.md) for prior records. Replace these next actions when they change; do not append another phase narrative.
