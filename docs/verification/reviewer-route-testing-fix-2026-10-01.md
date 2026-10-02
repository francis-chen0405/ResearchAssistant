# Adaptive budget route failure verification — 2026-10-01

Source: `master` at `0c49338` plus the uncommitted changes for this fix. The initial
working tree was clean. The handoff's earlier `4d88266` is followed by the
documentation-only `0c49338`. Target: Apple Silicon macOS 26.6.2, Python 3.12.14,
Node 24.18.0. No paid provider calls or real app-data/credential changes occurred.

## Report and reproduction

The installed app screenshot shows `ValueError: no v2 route is configured for
reviewer`, Adaptive Search, four model calls, seven search attempts, twelve acquired
sources, estimated cost $0.0071, and no released brief. Its banner incorrectly says
a validated brief remains available. No real research run was repeated.

The installed bundle's `v2_orchestrator.py` contains the same failing loop as source:
`_adaptive_budget` reserves every historical `LLMStage`, although fresh selected
routes contain only the seven active model stages. It fails while calculating
budget protection, before an adaptive model request; it is not a missing required
Reviewer model call.

Before the fix, the initial selected-route unit/integration regressions produced
three failures with the exact Reviewer-route error; the historical integration
passed. After the route fix, the integration fixture's original 100,000-token
ceiling correctly prevented adaptive search because the selected models have larger
completion allowances. The assertion requiring actual adaptive requests was kept;
the fixture now explicitly supplies 500,000 tokens, 80 calls, and $5, and exercises
round four. Production ceilings and budget policy were unchanged.

The browser regression against the old static export failed with one unexpected
`/v2-result` request for a failed run. The corrected renderer requests detailed
results only for released runs, then evidence only after a valid result. It retains
historical brief fallback and shows a details warning only when a validated result
is actually present. Result state is remounted across run/classification changes.

## Verified results

| Check | Result |
| --- | --- |
| Seven new backend regression cases | Passed: default/expensive mixed-route protection, 16/17 call threshold, historical/default/mixed completion through round four without Reviewer calls |
| Full pytest with warnings as errors | **1,211 passed, 2 unchanged skips**, 102.50 seconds |
| Ruff lint, format, and diff whitespace | Passed; 162 Python files formatted |
| Full frontend ESLint and TypeScript | Passed using installed local binaries |
| Deterministic offline evaluation | Passed |
| Fresh static export and frozen backend | Passed |
| Interaction browser smoke | Passed, including failed run, evidence-fetch failure, invalid v2 result, and successful evidence reload |
| Polling and configuration-race browser smokes | Passed |
| Frozen backend native smoke | Passed with isolated data and temporary test-vault namespace |
| Packaged backend native smoke | Passed: authentication, native-vault cleanup, durable settings, owned acquisition lifecycle |
| Actual packaged Electron window smoke | Passed: local page, authenticated requests, empty password fields, renderer isolation, duplicate exclusion, normal shutdown |
| Packaged source and frontend parity | All **100** source identity inputs and every exported frontend file match |

PyInstaller's first attempt could not clean its default cache outside the workspace.
The unchanged builder passed with `PYINSTALLER_CONFIG_DIR` in the ignored build
directory. A first packager attempt could not resolve GitHub inside the sandbox;
the successful package used the already installed unpacked Electron distribution.
No dependency or Electron version changed. Browser/native checks used approved
local execution with isolated data and mocked or offline application requests.

Logs and offline-evaluation artifacts are under `desktop/build/` with the prefix
`reviewer-route-` and date suffix `20261001`. The previous final resource bundle,
browser screenshots, and native-window screenshot are preserved under the
corresponding `*-before-reviewer-route-20261001` names. The original published
DMG/ZIP remain untouched under `desktop/dist/mac-current-20260928/`.

## Rebuilt app and next boundary

The verified local unsigned app is:

`desktop/dist/reviewer-route-20261001/mac-arm64/ResearchAssistant.app`

Its backend SHA-256 is
`b9c691de57120e6ee12d22f02b0d6974518c0981d9b6820c7ab087a7a1259da0`.
The tested source-only identity is
`source-sha256:14f477d6d850f15669973bf5f664d5dbbebd78e24ea04d2b6597ac5efc37327e`.
The preserved preceding backend SHA-256 is
`945a80542a95cbbb6a02659c3cf9cc1fe4d8c8b13324aa9e8e43b6dee4c39b7f`.

The installed `/Applications/ResearchAssistant.app` still contains the old loop.
It was not replaced, and no new installer or release was published. Install the
verified replacement as the next separately authorized step; a fresh research run
is required by exact source/executable identity. Preserve the failed run and its
recorded costs. These offline checks verify this defect, not live answer quality.
Paid-call allowance, signing/notarization, actual macOS 14/clean-machine checks, and
Windows release boundaries are unchanged.
