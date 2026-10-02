# Comprehensive code audit and confirmed-defect fixes — 2026-10-01

Status: complete; reviewed source, confirmed fixes, and final local Mac artifact
verified 2026-10-01. Installation and release remain separate boundaries.

The user explicitly requested a comprehensive codebase review using Luna subagents
and fixes for all code issues found. This supersedes the preceding single-bug scope,
while retaining existing data, evidence, provider-call, and release boundaries.

## Scope and method

- Inventory repository-owned runtime, test, build, and configuration code; exclude
  generated bundles, vendor dependencies, fixtures as executable code, and archived
  documentation from runtime coverage claims.
- Use Luna helpers for parallel area reviews, independent verification, and bounded
  implementations. The primary agent reviews consequential findings and integration.
- Review storage/contracts/evidence, fresh orchestration, providers/accounting,
  API/controller/security, renderer, native desktop/settings/credentials, historical
  compatibility/CLI, evaluation tooling, and build/test automation in distinct passes.
- Verify graph freshness and use its structural map; important conclusions require
  live source and reproducible evidence. `index_status` is not exposed, so refresh the
  graph before the audit and after consequential repository changes.
- Maintain a reviewed-file coverage ledger and distinguish confirmed bugs, rejected
  suspicions, unchanged intended behavior, and areas requiring unavailable platforms
  or live services. Do not claim an audit proves absence of all possible bugs.
- Reproduce confirmed validator/integrity defects with failing regressions, fix causes,
  preserve invariants and immutable history, then review the integration again.
- Run focused tests and the full pytest/Ruff/whitespace gates. Run relevant frontend,
  offline evaluation/browser and rebuilt Mac/native checks on final affected artifacts.

## Boundaries

No paid live calls, real app-data/Keychain changes, installed-app replacement,
publication, destructive Git operations, or unrelated new features. Dependency,
schema/policy redesign, prompt changes, and provider/framework integrations are not
assumed necessary: diagnose first and prefer existing contracts and dependencies.
Windows source may be audited, but native Windows release work and unsupported
platform verification remain deferred. Do not lower criteria or remove assertions.

The verified, uncommitted Reviewer-route/UI fix is the starting state. Preserve it,
the preceding verified local Mac app, published installers, and immutable evidence.
Baseline patch: `desktop/build/comprehensive-audit-baseline-20261001.patch`.
Baseline checks from the immediately preceding task: 1,211 passed / 2 unchanged skips,
Ruff, frontend lint/types, offline evaluation, all three browser smokes, and rebuilt
frozen/packaged backend/window checks passed.

## Coverage and evidence

Area reports and the final coverage/finding ledger live under
`docs/audits/2026-10-01/`. Record actual reproduction and test results, including
rejected hypotheses. Update STATUS.md and HANDOFF.md with final changes, remaining
limits, and the next installation/release boundary.

## Completion criteria

Complete assigned audit passes, verify and resolve every confirmed in-scope defect,
review changed integration points, and pass required checks on the resulting source
and affected rebuilt app. Record any unresolved externally blocked issue explicitly
instead of treating it as fixed or claiming all software is now bug-free.

## Completed result

Three Luna High helpers reviewed separate areas and bounded follow-ups; the primary
agent checked findings and integration. The [final report](../../docs/audits/2026-10-01/README.md)
records all confirmed repairs, nine area reports, a 206-input coverage ledger, and
explicit exclusions. All confirmed in-scope defects are resolved. The preceding
Reviewer-route/UI fix and historical evidence are preserved.

Final verification: **1,256 passed / 2 unchanged skips**, warnings as errors, 81%
combined line/branch coverage; repository Ruff and formatting (170 files); frontend
lint/types and static export; offline evaluation; API/config smoke and four browser
smokes; frozen and packaged backend checks and the actual Electron window. Source
parity matches all 100 source-identity inputs and all 22 exported frontend files.
The first window candidate failed due to a baked fixed API origin; the guard and
origin regression were added, the app rebuilt, and the final window check passed.
Strict tests also exposed output-stream/reaping leaks, which were fixed without
suppressing warnings or weakening checks.

Verified unsigned local app:
`desktop/dist/comprehensive-audit-20261001/mac-arm64/ResearchAssistant.app`.
The installed app, prior local Reviewer-route app, and published installers are
unchanged. Changes remain uncommitted; no paid/live provider calls, real app-data
changes, dependency/schema changes, installation, publication, or push occurred.
The final report records exact hashes and remaining live/platform release limits.
