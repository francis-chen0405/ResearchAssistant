# Approved full-review fixes — 2026-10-15

The user approved R01–R33 from the [review report](../audits/2026-10-15/full-code-review.md).
All thirty-three repairs are implemented and pass current source, installed and frozen
Mac resource checks. The literal every-line manual review remains active.
[STATUS](../project/STATUS.md) owns current verified state.
[Post-fix evidence](../audits/2026-10-15/post-fix-evidence.json) retains exact source,
wheel, artifact and log hashes, including preceding phases. Original R01–R18
verification/evidence is also preserved byte-for-byte in the
[preceding-state archive](../archive/2026-10-15-review-fixes-preceding-state/before-r26-completion/hashes.json).
[Manual coverage](../audits/2026-10-15/manual-coverage.json) records only actually
inspected current files/ranges; automated checks do not establish manual completion.

## Changes and regression evidence

| Findings | Final behavior | Principal checks |
| --- | --- | --- |
| R01–R02 | Artifact payload run ownership is checked centrally. Result, evidence, status/history and export verify the saved claim and original released-text hash without writing data. | `test_saved_result_integrity.py`, historical/API/export compatibility suites |
| R03 | Source sockets connect to validated numeric public addresses, retaining Host and TLS identity. The user confirmed retaining browser rendering with a protected proxy. The pinned preload protects Wigolo HTTP/probe requests; each Chromium instance also owns a bounded HTTP/HTTPS proxy covering dedicated/shared-worker paths. Older unprotected HTML services fail closed. | Python HTTPX/httpcore socket probes; locked upstream integration; numeric CONNECT peer and shutdown checks; real Chromium with public worker content and zero private sentinel connections |
| R04 | Schema 18 widens only v2 admissions to rounds 1–4. Existing rows, triggers, indexes, historical declarations, backup and rollback behavior are preserved. Round five remains invalid. | Generated schemas 7–18, historical upgrades/recovery, injected migration failure, immutable-row/index preservation, full product fixture with an actual round-four admission |
| R05 | Standalone API requests cancellation, drains workers for up to 90 seconds and retires its owned service. The CLI bounds exit even after cleanup errors; desktop retains its separate owner. | Active interrupted resume retains unknown reservations, explicit owner/order checks, failure/forced-exit regression and existing lifecycle/shutdown checks |
| R06–R07 | Every evaluation verifies candidate/query/page lineage before scoring. Reports exclusively create new private files and remove only owned partial outputs on failure. | Both replay settings, complete/incomplete synthetic inventories, manifest/artifact/link collisions and concurrent-output failure |
| R08–R09 | Discovery sockets receive the remaining absolute deadline on every operation and consume unbuffered arrivals. PDF construction/enumeration/extraction runs in a killable worker with input/page/output/CPU bounds; Linux has an address-space bound and Windows uses a memory-limited owned Job. | Real httpcore trickle with measured remaining budgets; actual killed PDF subprocesses; deterministic PDF output and installed worker dispatch |
| R10 | Verified Crossref metadata must identify the exact requested normalized DOI. Missing, malformed, mismatched and unverified metadata cannot relabel a work. | Adapter and normalization callback regressions |
| R11–R13 | Successful trail retries clear stale errors; duplicate-active requests reconnect only to the returned active run; credential-free HTTP(S) links open externally. | Five compiled actual-hook regressions, existing five offline browser smokes, 21 desktop shutdown/link checks |
| R14 | New metadata ranking v3 normalizes method cues consistently. Explicit v2 dispatch retains its original scores and saved identities. | Cue, linear feature work, tie, neutrality and production-sidecar tests |
| R15–R16 | Settings must load before editing/start, failed reads offer retry, and late import completion preserves edits and owns its panel/selection. | Actual hook checks and mounted delayed/failing/retried reads and imports, including duplicate and closed-panel completion |
| R17–R18 | Pending credential actions disable key editing and reject duplicates. Late credential callbacks refresh the latest committed selection; stale responses cannot replace it. | Actual component/action checks, selection ownership between layout/passive effects, and delayed-save/model-change browser regression |
| R19–R20 | Source redirects, canonical checks and socket operations share one deadline. System DNS runs in at most four owned helpers, with bounded input/output and remaining queue/startup/resolve time; timeout kills/reaps the helper. Connections use numeric results with original Host/TLS identity. | Actual header/trickle/redirect transport checks, stalled native resolvers, slot reuse, invalid/oversize output, numeric fallback/TLS, installed and frozen startup/cleanup |
| R21 | Catalog wire fields have their own HTTP DTO; scoped supplemental schema references keep research errors separate from HTTP input-error definitions. | Frozen payload inventory unchanged, real catalog/research-error TypeScript compilation, swapped-error rejection |
| R22 | MiMo/OpenAI physical requests stream under their stage deadline and a 16 MiB response cap. Unknown usage retains the full reservation. | Both families/current and historical routes, stalled headers/trickles, concurrent deadline isolation, persisted unknown reservations and existing exact reported-usage accounting |
| R23 | Evidence joins its saved run/claim, source Ledger links, exact quotation and released synthesis fields without changing stored data or release policy. | Fresh and historical checksum-valid substitutions, reviewer links, unchanged database bytes/mtime and released hashes |
| R24 | Malformed optional scholarly URLs cannot discard valid primary/fallback URLs or neighboring records. | Fourteen new OpenAlex/arXiv cases; original ranks and typed all-invalid outcomes |
| R25 | Fresh ranking v4 uses URL identity v2 with valid IPv6 brackets. Explicit v2/v3 ranking and URL-v1 dispatch retain historical semantics; existing hostname/IPv4 identities remain unchanged. | IPv6 with/without ports, idempotence, normalization/item/work identities, numeric source acquisition and exact resume compatibility |
| R26 | Cached terminal snapshots only trigger a bounded persisted-state reread. Missing/replaced databases cannot return vanished release content; early diagnostics remain available. | Actual completed workers before/after callback eviction, removed/empty replacement databases, commit/read races and read-only preservation |
| R27 | Documented HTTP 422 responses use the actual redacted string envelope; input values stay hidden. The distinct research error definition no longer collides with FastAPI's default input-error name. | Actual invalid body/path/query/credential responses compile against generated types; unredacted and swapped error forms fail; the rest of the original inventory is unchanged |
| R28 | DOCX rejects XML-invalid characters before creating the destination. Markdown preserves original text; PDF recommends DOCX only when XML can represent it. | XML character boundaries, actual released-run export, valid Unicode/markup/tabs/lines, no partial output and unchanged database/released hashes |
| R29 | Running/partial snapshots return their already computed discovery diagnostics. | Actual active search/acquisition and interrupted polling, unchanged database bytes, historical unknowns, and rendered counts/warnings |
| R30 | Every provider completion joins its exact physical start before audit, counters or replay. Missing completions retain conservative unknown exposure. | Seven contradictory-operation consumers, current/historical storage/execution and accounting checks, API rejects corrupt release data with its existing generic integrity-error boundary, unchanged bytes/mtime |
| R31 | Cached final and production results verify their saved run/claim and original rendered hash before return or terminal reassertion. | Current and recognized historical keys, valid no-call resume, checksum-valid contradictions and unchanged artifacts |
| R32 | Completed stages retain original budget snapshots; resumed new work remains governed by current accounting. | Six actual stage interruptions, changed-input rejection, exhausted current snapshots and unknown physical reservation preservation |
| R33 | Intermediate selection/adaptive checkpoint prefixes preserve original bytes and timestamps, including completed authorization; a saved selection status can restore its completion marker. | Nine advancing-clock interruptions retain every existing artifact and physical audit prefix; current budgets still govern new calls |

Fresh source identity: `source-sha256:d6db1e0654e5fcede44f23cfc6ff62ba8548e9a27c8a067f2e4d55394158d0e9`.
Fresh behavior uses acquisition provenance v5, PDF policy v2, metadata ranking v4
and URL identity v2. Explicit URL-v1 and ranking-v2/v3 dispatch remain available.
Historical policy/artifact bytes and hashes are not regenerated. Exact resume
compatibility requires fresh research after these source changes.

The existing httpcore 1.0.9 dependency is explicitly declared as `>=1.0.9,<1.1`.
Already locked ipaddr.js 1.9.1 and Playwright 1.60.0 are explicit acquisition
dependencies; no dependency version was upgraded. The Node preload verifies exact
reviewed upstream source hashes and changes only source-fetch owners. No installed
dependency source was edited. Source checkout startup uses that protected runtime
when its locked dependencies are present; an unprotected external service cannot
silently perform HTML acquisition.

Schema fixtures now construct actual old round-three constraints before labeling
them historical. The product fixture now admits its sixth source in round four,
so its old repeated-analysis observation no longer depends on the repaired storage
failure. Current assertions require all six families and the round-four admission.

## Verification

- Current full Python suite: **3,032 passed / nine existing skips**, 325.92 seconds. The exact completed R01–R26 verification is retained in the preceding-state archive; intermediate diagnostics remain in the current evidence.
- Ruff lint/format, repository boundaries, staged and unstaged whitespace: pass.
- All 24 current JavaScript files pass syntax checks.
- Frontend lint/types, generated API contracts, static export and all six offline browser smokes: pass.
- Actual-hook/component regressions: 17 pass. R27–R28 contract/export checks: 90 pass. R29 live/partial/product checks: 35 pass. Current API/desktop/distribution/type integration: 63 pass. Desktop shutdown/link regressions: 21 pass.
- Node cache/network/proxy tests: 17 pass, including locked upstream integration.
- Real offline Chromium network-boundary smoke: pass on this Mac using a temporary profile and generated pages.
- The Chromium smoke uses an owned private HTTP/WebSocket sentinel: zero TCP
  connections reach it. Dedicated/shared workers successfully load generated
  public data; their private HTTP, WebSocket and secure-WebSocket attempts fail.
  The owned proxy covers worker paths outside Playwright's context router.
  Numeric destinations/connected peers, proxy-header removal, opaque CONNECT
  bytes, browser failure/disconnection and pending-DNS shutdown are checked.
  Peer transports, service-worker activation and page WebSockets remain blocked;
  sites depending on those features can still render incompletely.
- Native POSIX shutdown smoke: all nine generated process/group scenarios pass
  outside the sandbox, preserving the unrelated sentinel. The sandbox run's
  process-inspection sentinel assertion failed and is not counted as a pass.
- Exact 303-file wheel audit, fresh wheel/editable installs from unrelated directories, package dependency checks, prompt/font identities, fixture release/blocking and fresh/replayed discovery binding: pass.
- Both installed forms run the actual PDF and owned DNS helpers successfully.
- A fresh disposable frozen Mac resource candidate passes UI/backend authentication,
  temporary-vault cleanup, settings/restart persistence, owned Wigolo lifecycle and
  owned DNS-parent/worker and PDF dispatch with an empty developer-tool PATH.
  Its unchanged Node/Chromium files retain the preceding 13 network/proxy,
  worker/sentinel and three applicable staged cache results. Current bundled-Node
  execution of all 38 source desktop/acquisition unit checks also passes. The source-only unpatched-cache
  reproduction expects `recursive_triggers=0`; the staged module deliberately sets
  it to one, so that diagnostic fails when applied unchanged to the patched bundle.
  Its complete log is retained; all four source cache tests pass normally.

The resource candidate is `/tmp/researchassistant-review-20261015-frozen/resources`.
Its exact [latest tested artifact hashes](../audits/2026-10-15/fix-evidence/r33/frozen-artifact.json)
record frozen identity `source-sha256:4aba5c59e8b6ada5dcffe26d7ccc84caa7d7ad57beaf658d07f8db80bb4d187d`.
The current backend is freshly frozen; acquisition and frontend are restaged.
The backend and UI were rebuilt/restaged and resource smokes rerun after R30. Original
per-phase logs/artifact hashes are retained separately.
Unchanged Node 24.18.0/Chromium bytes are copied from the prior candidate. This
checks frozen resources, without creating or accepting a new Electron installer.

Native browser checks needed macOS process-port access outside the filesystem
sandbox. They used disposable browser profiles and no source-provider requests.
The sentinel smoke additionally owns one temporary loopback server; it receives
no requests from the protected page. Native process checks also required normal
process inspection outside the sandbox.
Distribution checks installed constrained packages only into fresh temporary
environments. Neither action replaced the installed application.

The completed R01–R26 owners and evidence are preserved byte-for-byte in
[before-r28-completion](../archive/2026-10-15-review-fixes-preceding-state/before-r28-completion/hashes.json).
R27–R29 diagnostics include an undersized synthetic Scout budget and a probe field-name
mistake; both were corrected and the final checks passed. The intermediate full-suite
run overlapped early R29 edits, so the final R29 2,991-test run owns that preceding phase. R30 subsequently passed the full 2,998-test run.

R30 focused storage/execution: 82 pass; API/diagnostics: 17 pass. Ruff checks 496 files.
The exact completed R29 records are preserved in
[before-r30-completion](../archive/2026-10-15-review-fixes-preceding-state/before-r30-completion/hashes.json).
Unchanged renderer and Node files retain their completed R29 checks; the R30 backend
was freshly installed/frozen and its native resource smokes passed.

## Preservation and remaining gates

The original staged binary-diff hash remains
`85f8753d0bb6ba7af20c688eab28ad10429ee43329b879d89b8db48071324cf2`.
Original unrelated work is retained; approved repairs change their owned current
files. Prior current-state documents are preserved under the
[October 15 archive](../archive/2026-10-15-review-fixes-preceding-state/INDEX.md).
No real saved research/cache/credential edits, paid research, commit, push,
installed-app replacement or public publication occurred.

No native Windows rerun or new Electron installer acceptance is claimed here.
The historical Windows target remains `44f83d9bfb7e8e2896dc44390c366e4d498be044`;
its 240-second interrupted-upgrade repair timeout and unreached installed checks
remain open. The latest uninstall harness and these new runtime/worker changes
still need native Windows verification. Physical power loss, clean/minimum-OS
acceptance and signing/notarization remain separate gates. Public release and
changed-source paid research remain unauthorized.

The original inventory contains 527 code files / 147,198 lines. Automated coverage
and the targeted inspections recorded here are not a completed every-line manual
review. Continue that work with actual per-file/range evidence.

R31–R32 verification: 73 focused/integration checks, 39 repository/distribution checks,
497 formatted Python files, full 3,023 / nine existing skips, fresh 303-file wheel/editable
installs and freshly frozen Mac resources pass. Unchanged frontend/Node checks retain
their preceding exact-byte evidence. R33 is approved and pending; R34 awaits approval.

R33: 68 resume/adaptive checks and 95 orchestration checks pass. Final source checks
pass 3,032 / nine existing skips, Ruff lint/format (498 files), boundaries, generated
types and whitespace checks. Fresh 303-file wheel/editable installs and final frozen
Mac helpers/resource smokes pass at the recorded identity. R34–R36 await approval.
