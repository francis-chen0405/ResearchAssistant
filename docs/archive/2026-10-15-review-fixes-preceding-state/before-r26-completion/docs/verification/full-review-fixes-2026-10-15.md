# Approved full-review fixes — 2026-10-15

The user approved R01–R18 from the [review report](../audits/2026-10-15/full-code-review.md).
Implementation and verification of the approved fixes are complete. The full Python
suite precedes UI-only R15–R18; the backend identity stayed unchanged, and the later
UI changes passed focused integration and complete renderer checks.
[STATUS](../project/STATUS.md) owns the current summary. This closes the approved
repair set, not the requested literal every-line manual review.
The [post-fix evidence](../audits/2026-10-15/post-fix-evidence.json) records exact
source/wheel/log hashes. [Manual coverage](../audits/2026-10-15/manual-coverage.json)
records a conservative set of fully inspected current file ranges; it does not
convert earlier targeted inspections or automated checks into full-file credit.

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

Fresh source identity: `source-sha256:0cd486b049ee8d5192ba6e5bc318cb4eb195302530a7aaa21f688c54039a0835`.
Fresh behavior uses acquisition provenance v4, PDF policy v2 and ranking v3.
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

- Full Python suite after the final proxy integration: **2,868 passed / nine existing skips**, 322.97 seconds.
- Ruff lint/format, repository boundaries, staged and unstaged whitespace: pass.
- All 24 current JavaScript files pass syntax checks.
- Frontend lint/types, generated API contracts, static export and all six offline browser smokes: pass.
- Actual-hook/component regressions: 17 pass. Later frontend/contracts/boundaries/staging integration: 20 pass. Desktop shutdown/link regressions: 21 pass.
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
- Exact 300-file wheel audit, fresh wheel/editable installs from unrelated directories, package dependency checks, prompt/font identities, fixture release/blocking and fresh/replayed discovery binding: pass.
- Additional installed wheel/editable checks run the actual PDF subprocess successfully.
- A fresh disposable frozen Mac resource candidate passes UI/backend authentication,
  temporary-vault cleanup, settings/restart persistence, owned Wigolo lifecycle and
  PDF-worker dispatch with an empty developer-tool PATH. Its bundled Node passes
  13 network/proxy checks and its bundled Chromium passes the worker/sentinel smoke.
  The three applicable staged cache tests pass. The source-only unpatched-cache
  reproduction expects `recursive_triggers=0`; the staged module deliberately sets
  it to one, so that diagnostic fails when applied unchanged to the patched bundle.
  Its complete log is retained; all four source cache tests pass normally.

The resource candidate is `/tmp/researchassistant-review-20261015-frozen/resources`.
Its exact [latest tested artifact hashes](../audits/2026-10-15/fix-evidence/frozen-artifact-r18.json)
record frozen identity `source-sha256:02316e7154a631e2b036017dd0bad8a0dd284c98e8dc352467761c9f276b5736`.
The current backend is freshly frozen; acquisition and frontend are restaged.
The UI was restaged and the resource smoke rerun after R15–R18. Original
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
