# Comprehensive code audit — 2026-10-01

Subsequent authorized [installation and cleanup](../../verification/audited-app-install-2026-10-01.md)
installed this verified build in `/Applications/ResearchAssistant.app` and removed
obsolete/redundant local bundles and installers, including the candidate path below.
This report records the preceding audit state; source and verification logs remain.

The authorized Luna-assisted audit is complete. All confirmed in-scope defects
were repaired and the resulting source and rebuilt unsigned Mac app passed the
available offline checks. This is evidence of a broad review and tested repairs;
it is not proof that every possible software defect has been eliminated.

Authority: [comprehensive audit plan](../../../.agent/plans/comprehensive-code-audit-2026-10-01.md).
The previously verified [Reviewer-route/UI repair](../../verification/reviewer-route-testing-fix-2026-10-01.md)
was the starting state and is retained. Work remains uncommitted. No paid/live
provider calls, real user-data changes, dependency or schema changes, installation,
publication, or push occurred. Native smoke tests used isolated temporary data and
test-specific vault entries and verified cleanup.

## Review coverage

Three GPT-6 Luna High helpers handled storage/evidence, fresh and historical
pipelines, providers, desktop lifecycle/build, live projection/CLI, and renderer
follow-ups. The primary agent reviewed API/native boundaries, checked consequential
findings against current source, reviewed integration, and ran final checks.

The [coverage ledger](coverage.csv) contains **206 repository-owned inputs**:
**133 runtime, build, and configuration inputs** reviewed in the area passes, and
**73 test/helper inputs** inventoried and checked through relevant assertions,
targeted reproductions, and the full suite. This does not claim every test file
received the same line-by-line review as runtime modules. Area reports distinguish
source review, focused execution, rejected suspicions, and coverage limits.

- [Storage, evidence, contracts, and money](storage-review.md)
- [Fresh-v2 orchestration and stage integration](pipeline-review.md)
- [Providers, routing, and budget accounting](providers-review.md)
- [Live service, usage, and progress projection](live-service-review.md)
- [Legacy retrieval, CLI inspection, and evaluation](legacy-review.md)
- [Renderer and saved-history races](frontend-review.md)
- [API, settings, native boundaries, and desktop export](api-native-review.md)
- [Owned service lifecycle and cleanup](service-manager-review.md)
- [Desktop packaging and CI source review](desktop-build-review.md)

Generated output, bundled runtimes, third-party dependencies, and archived documents
are excluded from repository-owned executable review claims. Static prompt and
evaluation fixtures were assessed through their callers, contracts, and tests;
they are not counted as executable inputs. The live MiMo script was reviewed but
not executed. The code graph was advisory and refreshed before and after changes;
`index_status` is unavailable. Final fast index: 6,074 nodes, 38,286 edges. Its
exclusions include scripts and generated/vendor directories, so the live-file
ledger, rather than graph coverage, supports the review scope.

## Confirmed repairs

| Defect | Resulting behavior and regression evidence |
| --- | --- |
| Nonterminal research rounds accepted completion timestamps and could be persisted after bypassing model validation. | Both the strict record and store boundary reject these states; model and `model_construct` regressions preserve terminal requirements. |
| Candidate quotes were not fully bound to captured-snapshot provenance. | Central verification and Analyst input validate run, retrieval, actual snapshot URL, retrieval time, and snapshot creation time; forged provenance and recomputed quote-ID regressions fail closed. |
| Decimal addition lost small amounts across wide exponent ranges. | Precision includes exponent alignment and carry room; accepted nonnegative USD inputs retain exact values independently of ambient precision. |
| Budget reservation omitted contract/instruction text added by the physical model adapter. | Routed and direct adapters estimate the actual transport prompt; aggregate token and cost limits reject before transport. Real-adapter mocked-HTTP regressions cover both ceilings and unknown usage. |
| Reserved exposure was displayed as exact model usage. | Running and terminal views derive known subtotals and independent token/cost completeness from physical-call audits; only complete terminal metrics expose exact totals. |
| Worker failure before persisting a run disappeared when initialization had already created the database. | Bounded early results remain pollable for that case; persisted results supersede them, and the established no-database one-shot behavior remains. |
| Failed, blocked, or cancelled results lost frozen directions and showed completed directional progress. | Terminal projection uses persisted directions/counts and the actual classification. |
| Terminal retrieval counts used acquired sources instead of attempts. | Diagnostics report acquisition attempts, including failures; a three-attempt/one-source fixture verifies the distinction. |
| Unicode authorization could raise HTTP 500. | Constant-time UTF-8 byte comparison returns the existing generic HTTP 401. |
| Stricter internal start-request validation escaped as HTTP 500. | Invalid claims and database paths return generic HTTP 422 before worker dispatch. |
| Corrupt or non-SQLite snapshot databases escaped as HTTP 500. | Specific compatibility failures map to generic HTTP 400; read-only file bytes and modification time remain unchanged. |
| A valid service `starting` response prevented research startup. | The client waits for health with a bounded deadline and per-request aborts; terminal launch failures stop immediately. |
| Older preference writes could finish last and overwrite newer choices. | Writes commit in submission order; failed saves do not poison subsequent writes. |
| Late history/run responses replaced newer database selections or forced navigation back to Research. | Generation guards invalidate obsolete work; database changes clear prior selections, active-run database association stays stable, and result identity includes the database. |
| Dead service leaders left descendants alive or lost ownership during restart. | Serialized lifecycle operations retire old ownership, terminate the owned POSIX group even after leader exit, escalate when needed, and close retired Windows jobs. Actual subprocess and mocked-Windows regressions verify cleanup/callback order. |
| Service output pipes and replacement test processes leaked resources. | Reader threads close streams and join after shutdown; regression cleanup reaps the current owner. Warning-as-error checks pass without suppression. |
| Concurrent legacy support/challenge retrieval scraped an identical original URL twice. | Per-URL in-flight claims serialize duplicate acquisition, release on failure, and allow distinct URLs to proceed concurrently. |
| CLI inspection treated fresh-v2 runs as legacy runs and misreported usage. | Persisted identity selects pure typed v2 projections, sharing the validated read-only connection; no executor or provider is created. Historical fallback remains. |
| Desktop exports could bake an incorrect fixed API origin. | Desktop configuration forces same-origin requests. Missing/wrong/blank environment regressions and request-origin assertions prevent mocked browser checks from hiding this error. |

New Python regressions are in `tests/test_audit_*.py`. Existing integrity/type,
production, governor, and cache-accounting assertions are retained. The readonly
session regression now instruments the extracted builder's actual read boundary
while retaining its one-open, schema-validation, and same-connection assertions.
New offline client/config and history smokes run in desktop CI. Environment-example
comments also distinguish historical pricing settings from fresh selected-model
presets and enabled discovery-key requirements; secrets and live gates remain blank
or disabled.

The supplied [testing handoff](../../testing-handoff-2026-10-01.md) is preserved
byte-for-byte at its referenced repository path, repairing two existing dangling
status/handoff links. Its installed-release details remain historical context.

## Final verification

Host: Apple Silicon macOS 26.6.2, Python 3.12.14, bundled Node 24.18.0. Local native
and subprocess tests used the scoped elevated runner where localhost/process-group
operations are restricted by the sandbox. No external provider was contacted.

| Check | Final result / local evidence |
| --- | --- |
| Full pytest, warnings as errors, coverage | **1,256 passed, 2 unchanged skips**, 344.16 seconds; combined line/branch coverage **81%**. `desktop/build/comprehensive-pytest-20261001.log`. |
| Ruff lint and formatting; whitespace | Passed; **170 Python files formatted**. |
| Frontend ESLint and TypeScript | Passed on final source. |
| Static desktop export | Passed while deliberately supplying an incorrect fixed API URL; same-origin guard applied. `desktop/build/comprehensive-web-build-final-20261001.log`. |
| Offline evaluation | Passed. `desktop/build/comprehensive-offline-evaluation-final-20261001.log`. |
| API/config smoke | `desktop/audit-api-smoke.cjs` passed readiness/deadline, failure, write-order/recovery, and desktop-origin checks. |
| Full frontend browser smoke | Passed. `desktop/build/comprehensive-frontend-smoke-final-20261001.log`. |
| Polling browser smoke | Passed: five snapshots, maximum same-run concurrency one, terminal/replacement/unmount cleanup. `desktop/build/comprehensive-poll-smoke-final-20261001.log`. |
| Configuration race smoke | Passed. `desktop/build/comprehensive-configuration-smoke-final-20261001.log`. |
| History race smoke | Passed. `desktop/build/comprehensive-history-smoke-final-20261001.log`. |
| Frozen backend smoke | Passed. `desktop/build/comprehensive-frozen-smoke-20261001.log`; later frontend-only guard does not change this backend. |
| Final packaged backend/native smoke | Passed: UI/backend, authentication, isolated vault cleanup, settings persistence, owned service lifecycle. `desktop/build/comprehensive-packaged-smoke-final-20261001.log`. |
| Actual packaged Electron window | Passed: authenticated renderer requests, seven empty password fields, no browser storage/renderer Node access, duplicate-launch exclusion, normal shutdown. `desktop/build/comprehensive-window-smoke-final-20261001.log`. |
| Final packaged source parity | **100 source-identity inputs and 22 exported frontend files match**. `desktop/build/comprehensive-source-parity-20261001.json`. |

The full Python gate ran after the final Python edits. Subsequent changes were
desktop export configuration, its JavaScript regression, and documentation; final
frontend/native checks ran on that rebuilt export. No checks were skipped or
criteria lowered to accept a failure.

The first packaged window failed because its export used port 8765 while the native
backend selected another port. That candidate, frontend resources, parity report,
and failing log are preserved under the `first-candidate-20261001` names in
`desktop/dist` and `desktop/build`. The final configuration guard, rebuild, origin
assertions, and actual window smoke passed. Earlier warning-as-error failures
likewise produced stream/reaping fixes rather than warning filters.

## Verified local artifact

`desktop/dist/comprehensive-audit-20261001/mac-arm64/ResearchAssistant.app`

This is an unsigned local app directory, with `READ-ME-FIRST.txt` alongside it.
It is not a published installer and has not replaced `/Applications/ResearchAssistant.app`.
The preceding verified Reviewer-route app and published September installers are
preserved. The installed app still contains the old code.

- Packaged backend SHA-256: `2fbffbb0e524a1cd769ac11e37769325044290193707735b771363bf557cd9bd`.
- Repository and packaged **source-only** identity:
  `source-sha256:7f9e05142129e7124cae130c4bc8feba32c49b193b8ca15237130e463c87f551`.
- Exact per-file frontend hashes and source paths are in the final parity JSON.
  Source-only identity excludes the frozen executable; it is not the packaged
  backend executable hash or a substitute for the runtime resume gate.

## Remaining limits and next boundary

No additional confirmed in-scope defect remains unresolved. Assessed hypotheses
without sufficient evidence were left intact: historical `RunManifest` completion
timestamp permissiveness remains a compatibility contract, and distinct original
URLs resolving to one final URL cannot be deduplicated until acquisition resolves
them. The previously documented acquisition DNS-rebinding/time-of-check limitation
remains recorded rather than claimed repaired.

Offline tests do not establish current provider access/pricing or research quality.
The 42 stage/model-choice unit combinations are exercised, but this is not a full
production-run matrix for every combination. Windows source and mocked job handling
were reviewed; native Windows was not executed. Clean-machine/minimum macOS 14,
Developer ID signing, and notarization remain unverified. Coverage includes
unexecuted branches and native Windows credential code; 81% is not complete coverage.

Installation, fresh manual research, and any release/publication require separate
user direction. Preserve existing data, credentials, failed history, and recorded
costs. Updated source identity requires a fresh run under the existing gate; do not
bypass identity checks or invent a new paid-test allowance.
