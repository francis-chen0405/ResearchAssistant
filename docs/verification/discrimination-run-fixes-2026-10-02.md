# Approved discrimination-run fixes — 2026-10-02

The user approved the preceding [findings](discrimination-run-review-2026-10-01.md) with “fix” and resumed the work with “go on.” The [implementation plan](../../.agent/plans/discrimination-run-fixes-2026-10-01.md) bounds A–G. Three Luna helpers implemented admission/qualification, source presentation/lineage, and cache telemetry; the primary agent handled full-source extraction input, integration and Mac replacement verification.

Status: A–G implementation, offline verification and installed Mac replacement complete. The replacement is open for manual testing.

## Changes

| Finding | Repair |
| --- | --- |
| A: incomplete totals | Separate recommendation and survivor summaries include analyzer-admitted evidence. Reviewer-approved counts use exact statuses and exclude sources not analyzed. |
| B: missed mirror | Corroborated matching article dates/slugs and headlines disclose the Louisville publisher mirror despite differing date URL formats and a publisher suffix. Records remain separate; the warning does not establish independence or verified identity. |
| C: unrelated admission | New versioned Analyst/admission policies reject unrelated material before claim-evidence drafting/admission. Historical records retain their policy, display, export and hash. |
| D: qualification failures | Ordinary attributed/scoped statements pass the existing lexical gate. Missing canonical qualifications are checked within the bounded combined Analyst loop; transport/malformed/direction failures retain their prior nonretryable behavior. |
| E: oversized source handling | Extractor input renders the complete numbered source once, with the explicit untrusted-source boundary. Exact quote assembly uses the original snapshot. Source cap rejection is typed, avoids a futile retry and permits other sources to continue; global exhaustion still stops work. No context truncation or larger cap is introduced. |
| F: ambiguous status | Saved-brief wording, unresolved evidence gaps and productive-search stopping are distinguished from claim resolution. Frozen historical exports remain unchanged. |
| G: incomplete cost explanation | Future physical-call JSON retains optional cache-write counts and typed reported-write, conservative-assumption or configured-cap estimate basis. Read-only views show complete or partial/unknown input/output/cache details. Historical unknowns remain unknown, and the existing verified tariff is preserved. |

No dependencies, prompt bytes, SQL migrations, paid/provider requests or real-data/credential edits are included. These changes do not establish the discrimination claim or remove the research limitations.

## Source verification

- Full Python suite with warnings as errors: **1,320 passed, 2 unchanged skips**, 92.17 seconds.
- Ruff lint, format and whitespace: passed; **176 Python files** formatted.
- Default offline evaluation and API/configuration smoke: passed, without provider calls.
- Browser polling, configuration and history races: passed with mocked APIs and temporary browser data.
- Frontend ESLint, TypeScript, desktop static export and final interaction smoke: passed. Assertions cover source counts, not-analyzed status, budget blocks, lineage, unresolved gaps and reported/assumed/unknown usage details. The final result screenshot was visually inspected.
- Frozen, packaged and installed native/window checks: passed with temporary data and separate test credential namespaces; actual window isolation, empty password controls, authenticated requests, duplicate-launch exclusion and normal shutdown passed.
- Advisory graph refreshed after implementation: **5,300 nodes / 35,670 edges**; source and tests remain authoritative.

Logs and generated diagnostics use the `discrimination-fixes-` prefix under ignored `desktop/build/`. The frozen native smoke initially failed under filesystem/OS sandbox restrictions. Automatic approval review rejected its first escalation as a credential-boundary concern. Source inspection confirmed the test uses only fabricated secrets under `ResearchAssistant.Smoke.<random namespace>` and temporary app data, separate from user credential services. The unchanged test was then approved and passed native vault cleanup, restart persistence, authentication and owned acquisition-service lifecycle. No product gate was skipped or weakened.

## Historical result and usage

Read-only inspection of run `44b8cc42-0a18-4c31-9c6f-5f23fe68260a` verifies all **280 artifact hashes**, ten unique Ledger-bound evidence cards and the unchanged release hash `00aa01fe399464692d84d22e50707b09dc7a52373c5687045fb5b180c3383424`. The derived view adds **one possible mirror warning and six token-cap blocks**, preserving the original final artifact and its eight qualifying/two unrelated findings. The new relevance policy applies to new runs.

Recorded usage remains **209,356 input / 62,618 output / 2,747 cached-input tokens**, 57 physical calls and **$0.057158320**. Historical cache-write counts and the newly introduced pricing-basis metadata remain unknown. At the user's supplied ordinary rates, their cumulative account-total difference is 160,000 input plus 60,000 output, or $0.046; those account totals do not match the saved run's recorded token scope. No invoice verification is inferred.

## Delivery and remaining boundary

The verified installed app is `/Applications/ResearchAssistant.app` on macOS 26.6.2 arm64. Staging, installed checks and cleanup preserved exact parity across **30,929 payload files/symlinks**, all **101 source inputs** and **22 exported frontend files / 27 entries**.

- Backend SHA-256: `03e88ac86dac18258e108ff1b94cc02f77c6b7909464dfc24f28661fd461b28f`.
- Source-only identity: `source-sha256:3ac75722e2dfdb43cc23e5a9e260bd69d802ad0e714b810d3c58e3abb5d7d207`.
- Computed runtime identity, including the installed executable: `source-sha256:cae6f975bd16786a55182b0fe18e2db7ad87b171b7700248b6f2d1fa2b619ff1`.

After installed checks passed, the verified superseded Applications rollback, redundant `mac-arm64` candidate and three backend/cache directories were removed. Package text records were archived under `desktop/build/retired-package-records-20261002/discrimination-fixes`. Source, current development resources, saved research and real credentials remain. A Luna name-only scan of Applications, user Applications/Downloads/Desktop, repository candidates and Codex worktrees found no additional obsolete app bundles or named installers; vendor Chromium directories and source worktrees were preserved. The two known obsolete targets are absent after cleanup. This bounded scan is not a claim about every possible location on the machine.

Normal LaunchServices opening was verified from Applications with its owned backend and unauthenticated health returning 401. The initial 40-second observer missed readiness; the app/backend remained running, and a later observer passed. A one-second call-stack sample showed an active event loop; the startup delay's cause remains unconfirmed. No product changes or weaker gate were introduced for that diagnostic timeout. The app remains open. Read-only saved-run revalidation and source/export parity passed again after normal opening.

The first packaging command used a config path relative to the repository rather than the configured desktop project and failed before packaging. Correcting that invocation produced the verified candidate; no product source changed. Empty generated export directories were removed before copying resources so strict packaging parity includes the same directory inventory.

No automatic commit/push or public release is included in this phase. Local checks do not establish live-provider quality, clean-machine/macOS 14, Developer ID signing or notarization acceptance. New research must obey the existing executable/source identity gate; historical artifacts are inspected/exported without regeneration. The next boundary is user manual testing.
