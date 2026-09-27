# Handoff

The [audit maintenance](.agent/plans/audit-maintenance.md) is implemented and reviewed. Its local commit includes the remaining code fixes, test harness corrections, documentation rewrite, dependency changes, and generated-cache cleanup. The prior CLI/setup correction remains in `5c66287`. See [STATUS](STATUS.md) and the [verification record](docs/verification/audit-maintenance.md) for exact results.

## Preserve these changes

- Resolve legacy stage policy in routing preflight. Agents should not regain their own selection-mode branches. Preserve early validation for empty batches.
- Fresh extraction artifacts record the selected model/effort ID; historical no-selection records keep their physical-model meaning. Do not rewrite stored artifacts. The historical GPT-5.6 Luna pricing branch remains reachable and necessary.
- Keep Streamlit optional via `requirements-legacy.txt`. Starlette tests use the test-only httpx2 dependency; production provider adapters retain httpx. Use constrained requirements installs from README, since editable package discovery is not configured for this flat repository.
- Run all three offline browser smokes after a fresh desktop export. Generated TypeScript cache stays ignored. Current rules are in [architecture](ARCHITECTURE.md), [research invariants](docs/research-invariants.md), and [conventions](CONVENTIONS.md); exact previous documents remain in [the archive](docs/archive/INDEX.md).

## Verification and next boundary

The final suite passed 1,163 tests with 2 existing skips and warnings as errors. Ruff, frontend checks, offline evaluation, browser smokes, the rebuilt native smoke, and three consecutive final-build upgrades passed. All 100 packaged source identity inputs match the working source. Source changes require new runs under the existing resume gate.

The old upgrade timeout's original cause was not reproduced. Readiness waiting, pipe draining, bounded output, reader cleanup, graceful shutdown, and fixed startup-phase diagnostics now make failures easier to diagnose without exposing secrets. Keep the 45-second startup and 100-second shutdown limits and all native credential/history assertions. Unsigned Keychain permission prompts still need normal OS approval.

No installed app was replaced or installer published. Source commits were not pushed; only the verified merged remote cleanup branch was deleted. Further distribution work requires fresh artifact-specific checks. Live-quality acceptance, clean-machine/minimum-OS verification, signing/notarization, and current Windows testing remain open. The original paid-test allowance is exhausted and has not been renewed.
