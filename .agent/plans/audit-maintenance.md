# Audit maintenance and follow-up checks

Status: authorized and implemented 2026-09-26; reviewed and verified for the local maintenance commit.

## Objective

Finish the remaining fixes from the current audit, review the combined changes, verify them, and prepare the authorized local commit. Preserve established contracts and report any check that remains unresolved.

## Authorized scope

- Diagnose the intermittent desktop upgrade-smoke startup failure and fix a confirmed cause without weakening its assertions, timeouts, or credential protections. If the cause cannot be established, retain the limitation as open.
- Complete the approved extraction work and centralize the route guard within the current architecture.
- Align package identity metadata (`researchassistant`, version `0.1.0`) and user-facing CLI/banner branding (`ResearchAssistant`). Keep Streamlit out of the base install and provide the legacy frontend through `requirements-legacy.txt`; a setuptools extra is not viable while package metadata generation rejects this repository's multiple top-level packages. Address pytest/httpx compatibility through the `dev` optional dependency set, including `httpx2`, and pin the required test/build environment in `desktop/constraints.txt`.
- Replace the long current-state root documents with concise current records after archiving their exact prior contents. Preserve history, established invariants, and release boundaries.
- Stop tracking generated TypeScript build cache and clean up merged branch state only after confirming that all work is accounted for.

## Boundaries

Do not add live provider calls, paid acceptance runs, new release claims, schema or research-policy changes, or unrelated dependencies. Preserve historical run/read/export behavior, current evidence and accounting rules, and the Mac-first release boundary. The spent five-submission allowance is not renewed by this work. Do not claim Windows current-version verification or public-release readiness from historical Phase 2 evidence.

## Completion record

Record exact code and documentation changes, commands and outcomes, remaining upgrade-smoke or platform limits, and local Git state in [STATUS.md](../../STATUS.md) and [HANDOFF.md](../../HANDOFF.md). Required repository checks remain `pytest`, `ruff check .`, and `ruff format --check .`; preserve the existing tests and skips. Do not mark this plan complete until the authorized review and commit work is finished.

## Verified outcome

The remaining code, harness, package, tooling, and documentation fixes are implemented. Final verification passed 1,163 Python tests (two existing skips, warnings as errors), Ruff, frontend checks, offline evaluation/browser smokes, the rebuilt native smoke, and three consecutive final-build upgrade checks. The original timeout did not reproduce, so its historical cause remains an explicit diagnostic limitation; confirmed readiness and pipe-handling defects are fixed without weakening the gate. Test-only httpx2/httpcore2 2.13.1 and truststore 0.10.4 are pinned; Streamlit is optional. The merged remote branch was verified and deleted. See [verification](../../docs/verification/audit-maintenance.md) for exact evidence and unchanged release gates. This plan and its outcome accompany the authorized local commit.
