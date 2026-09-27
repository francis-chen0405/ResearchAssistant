# Audit maintenance verification — 2026-09-26

## Changes reviewed

- Centralized legacy route policy in `V2RoutingConfig.preflight()`, including fixed alias expectations and physical-model checks. Seven agents no longer implement separate mode checks. Empty discovery/Analyst batches still validate before processing.
- Fresh extraction artifacts retain selected model/effort IDs (`gpt-6-luna-high` versus `gpt-6-luna-xhigh`). Persisted readback is tested. Historical no-selection metadata and the private extraction helper's existing physical-model keyword remain compatible; no schema or historical data changed.
- Aligned package/CLI branding to ResearchAssistant and version 0.1.0 to the existing desktop manifest. Streamlit is optional through `requirements-legacy.txt`, with corrected legacy launch guidance.
- Added root pytest import configuration and test-only `httpx2`, as required by installed Starlette's TestClient. Constraints pin httpx2/httpcore2 2.13.1 and truststore 0.10.4. Runtime provider adapters continue using httpx. No warning filter was added.
- Removed generated TypeScript cache from Git, added all three browser smokes to desktop CI, and removed an unused browser-test helper.
- Replaced the seven root documents with concise current instructions, preserved exact previous documents in the maintenance archive, and retained detailed current research rules in `docs/research-invariants.md`. Obsolete generated-artifact download directions are marked historical.
- Kept the GPT-5.6 Luna pricing branch: historical Standard routes still reach it. Added a comment explaining that compatibility use.

## Upgrade harness diagnosis and changes

The previous harness announced readiness from the backend's first stdout line, even though that line precedes server startup. It also left stderr undrained and read startup without an output-size bound or useful timeout diagnostics. Regression tests reproduce connection refusal before health readiness, pipe pressure, early exit, stalled credential phases, oversized startup output, and orderly shutdown.

The harness now drains both pipes, bounds startup output, waits for authenticated health, joins readers, and requests graceful backend shutdown before a forced stop so owned acquisition processes can be cleaned up. New frozen self-tests emit fixed startup phase labels. Failures report launch index, elapsed time, exit state, phase, and stderr size without raw child output or bootstrap secrets. Startup remains 45 seconds, shutdown remains 100 seconds, and every credential/history/preference assertion remains required.

These defects are confirmed independently. The two historical startup timeouts did not reproduce during this run, so their exact original cause remains unknown. Three consecutive final-build upgrade passes provide local regression evidence, not a guarantee across every machine or unsigned Keychain permission state. An OS permission prompt must still be answered normally; the test does not bypass vault protection or silently skip it.

## Final checks

| Check | Result |
| --- | --- |
| Bare pytest entry point, no PYTHONPATH override, warnings as errors | 1,163 passed, 2 existing skips, no warnings (76.98 seconds) |
| Ruff lint and format | Passed; 158 Python files formatted |
| Deterministic offline evaluation | Passed |
| TypeScript and ESLint | Passed |
| Offline interaction, polling, configuration-race browser smokes | All passed against the existing fresh webpack desktop export |
| PyInstaller backend rebuild on macOS arm64 | Passed |
| Packaged root/agent/provider/frontend/prompt identity input comparison | All 100 files match current source bytes |
| Final frozen native smoke | Passed: authenticated API/UI, native vault roundtrip/restart, settings and owned acquisition lifecycle |
| Final old-to-new upgrade smoke | Three consecutive passes with all original assertions |
| Diff whitespace and current documentation links | Passed |

The earlier post-commit review exported the unchanged web source with webpack; Turbopack's worktree symlink restriction remains a build-environment limitation. The local pytest launcher had an obsolete checkout shebang, which was repaired locally; the committed `pythonpath = ["."]` fixes import discovery. PyInstaller used a cache under ignored `desktop/build/` because the sandbox disallowed its default user cache. These environment fixes did not relax tests.

Authenticated-health times for the three final upgrade attempts:

| Attempt | Previous backend | Current backend |
| --- | --- | --- |
| 1 | 0.82 s | 6.74 s |
| 2 | 0.74 s | 5.97 s |
| 3 | 0.68 s | 3.96 s |

The previous resources came from the preserved pre-GPT-6-Luna app; current resources are the rebuilt ignored `desktop/build/resources`. Executable SHA-256 values:

- Previous: `ec8f4d465f027db6fd5f9e1391c5a4e2d3fd344072152a36970db5926e245905`
- Current: `54a7845ed904ece6568c73d12c45dac6742fd46280b099246f7bbad0a046636f`

## Git and release boundary

Verified remote `codex/phase-2-cleanup` at `ecf43150d3e84ad2c397899aff39a3ffdb0e3a66` was already an ancestor of master, then deleted it with a lease protecting against a concurrent remote change. The maintenance changes are recorded in the local commit containing this document; source commits were not pushed.

No provider calls, paid research, user-data migration, installed-app replacement, installer publication, or Windows execution occurred. The locally rebuilt backend is a verification artifact. Live-quality acceptance, clean-machine/minimum-OS checks, signing/notarization, and current Windows verification remain outside this maintenance result. The prior paid-test allowance is still exhausted.
