# Installed Mac testing: adaptive budget route failure — 2026-10-01

Status: fix and local rebuilt-app verification complete; installation remains next.

The user reported a failed run in the installed unsigned Mac test app. The screen
records `ValueError: no v2 route is configured for reviewer`, final stage Adaptive
Search, four model calls, seven search attempts, twelve acquired sources, and no
released brief. It also incorrectly says a validated brief remains available.

## Authorized scope

- Reproduce and fix this route failure using isolated offline fixtures.
- Preserve conservative downstream budget protection and historical routing.
- Correct the related failed-run evidence message without changing release policy.
- Add regression coverage, run focused and full Python/Ruff checks, frontend checks
  and offline browser smokes, then rebuild and verify an affected Mac app locally.
- Record actual evidence and the source-versus-installed-app boundary.

Fresh per-stage routing covers seven active model stages. `_adaptive_budget`
currently reserves every historical `LLMStage`, including Reviewer, which fresh
per-stage routing does not configure. Fresh synthesis and validation remain
deterministic; adding a Reviewer model call is outside this fix.

No paid provider calls, real-data/Keychain changes, installed-app replacement,
remote publication, dependencies, schema changes, or Windows work are authorized.
Preserve the existing published installers and prior verified resource bundle.
The corrected executable requires a new run under the existing exact identity
gate; failed history must remain intact.

## Verification

Seven new regression cases pass. Full pytest passed 1,211 tests with two unchanged
skips; Ruff, frontend lint/types, offline evaluation, all three browser smokes, frozen
and packaged native smokes, and the actual packaged Electron window passed. All 100
source identity inputs and exported frontend files match. The failing regressions,
artifact hashes, preserved evidence, and limits are recorded in
[verification](../../docs/verification/reviewer-route-testing-fix-2026-10-01.md).

## Next boundary

After local verification, installing or publishing the corrected test app is a
separate next step. Existing signing, notarization, clean-machine, minimum-OS,
and live-quality limitations remain open.
