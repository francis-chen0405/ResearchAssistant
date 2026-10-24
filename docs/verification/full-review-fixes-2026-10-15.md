# Approved full-review fixes — 2026-10-15

All user-approved R01–R59 in the [report](../audits/2026-10-15/full-code-review.md)
are implemented and verified. Current asset review remains active; historical documentation and retained records
are excluded by subsequent user instruction. [STATUS](../project/STATUS.md) owns current state; [exact evidence](../audits/2026-10-15/post-fix-evidence.json)
retains identities, artifact hashes, diagnostics and preceding phase results.

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
| R34 | Relational analyzer admission and source checkpoint commit in one transaction; old partial rows are validated and reused with original timestamps. | Actual advancing-clock current/old prefix recovery, rollback on conflicting artifact, contradictory admission rejection |
| R35 | Fresh selection/shortlist v3 support the four-round maximum of 100; old policies keep 75. Token cap and all accounting limits stay unchanged. | Actual >75-source balanced release, 100/101 boundaries, old-policy rejection/exact resume, complete dispositions and read-only current/legacy history |
| R36 | CLI Pydantic configuration failures expose only safe owned field labels. | Password/query/fragment/context/extra-key redaction, useful safe missing-key diagnostic, no database/provider setup |
| R37 | Versioned selection provenance retains each query direction; Gap credit stays within its lane. | Real balanced cross-direction release, false-direction rejection and exact legacy serialization |
| R38 | Ranking/discovery and acquisition/audit commit together; older partial records recover without replacement Scout calls. | Advancing-clock current/old prefixes, immutable audit/artifact prefixes and transactional rollback; missing legacy Scout decisions have an explicit ranking fallback |
| R39 | Round-4 completion reuses validated original execution facts and commits with them. | Current/old prefix interruptions retain original facts and provider work |
| R40, R48 | Historical Reviewer paths preserve validated committed review/admission timestamps; bridge admission/checkpoint is atomic. | Actual native and Phase-10 prefix resumes, zero repeated completed requests and rollback |
| R41–R42 | Fresh quotation selection carries exact occurrence offsets and consistent sentence context under filter v2. | Decimal limitations, repeated single/multiple segments, invalid offsets and unchanged historical assembly |
| R43–R45 | Methods headings are recognized; optional overlong author identity metadata cannot stop planning; new approval wording is versioned. | Five heading aliases, long-author seed and production planning, historical rendered-text/hash reconstruction |
| R46 | Native source hashes, exact quotations and ownership/approval links validate before trusted display. | Corruption cases, per-record historical diagnostics, valid neighbors and bounded query batching |
| R47, R49–R50 | Retained retrieval skips same-family captures and known URL aliases; Governor counts URL/content duplicates correctly. | Typed duplicate outcomes, completed-round alias seeding, exact saved decisions and unchanged thresholds/accounting |
| R51 | Benchmark constructs validated schema 16, preserves rows, refuses Round-4 admissions and labels schema 18 accurately. | Actual 2/10/40/1000-candidate benchmark, equal typed output, rollback and corrected 14/15/16 upgrade fixtures |
| R52 | Older evaluation outputs require distinct fresh paths and remove only owned partial files on failure. | Input/artifact/link collisions, publication races and exact valid JSON/Markdown scores |
| R53, R55 | Scout/Gap retain exact original inputs and cumulative bounded attempts; replay known outcomes, stop on unknown outcomes and preserve reservations. | 17 intent/outcome/aggregate interruptions, advancing clocks, original budget replay, actual production audit-prefix and unknown-reservation checks |
| R54 | Fresh Strong labels follow admitted supports/challenges/qualifies relationships under synthesis v2 / validator v4. Original v2/v3 rendering remains exact. | 22 direction/relationship/Claim Fit, saved-hash, corrupted-label, foreign-assessment and Analyzer-only label cases |
| R56 | Selection freezes exact bounded input, estimate, shortlist and original budget; replay reuses known recommendations and cumulative attempts without double subtraction. | Actual production/preaggregate cuts, exhausted budgets, invalid recommendations, exact invocation ownership and unknown reservations |
| R57 | Initial Planner saves exact input/one intent/typed outcome and original date; valid publication prefixes recover without another call. | Every request/publication boundary, known/unknown outcomes, original/modern partial projections and completed invocation requirements |
| R58–R59 | Checkout readiness shares one monotonic deadline; maintained guides match current security/schema/identity behavior. | Five launcher process scenarios, actual Mac curl stalls, owned cleanup and 89 resolved guide targets |

## Current verification

- Complete Python suite: **3,195 passed / nine existing skips**, 445.73 seconds;
  all 44 R56–R59 new cases pass. Focused selection: 90 pass; corrected resume
  confirmation: 59 pass. Prior compatibility evidence is retained.
- Ruff lint/format: 518 files; repository boundaries and staged/unstaged whitespace pass.
- Current frontend lint/types and generated API contracts pass. Renderer/Node bytes
  remain unchanged from R29; its exact static export, 17 hook checks, six offline
  browsers, 38 desktop/acquisition units and nine native shutdown scenarios remain
  retained and were not rerun for R56–R59.
- Exact 304-file wheel audit and fresh wheel/editable installations pass from
  unrelated directories, including dependencies/prompts/font, valid/blocked fixture
  release, exact binding replay and owned DNS/PDF startup and cleanup.
- Separate frozen Mac resources pass authentication, smoke-only native vault
  cleanup, settings restart, acquisition lifecycle and owned DNS/PDF helpers with
  empty PATH and unrelated working directories. Native process/vault checks used
  normal macOS permissions and generated data. The installed app and preceding
  candidate are preserved. No Electron installer acceptance is claimed.
- The offline query benchmark completes at 2, 10, 40 and 1,000 candidates with equal
  typed output. At 1,000 it records 6,009 baseline versus 19 current SELECTs.
  Timings/cache conditions are retained as measured diagnostics, not live quality.

Source identity: `source-sha256:fe0cc617eaba0753c9895d0a5f4a983f07946c594c7054d9696775250dcf937c`.

Frozen identity: `source-sha256:721663605cbebb699899af04610598f4f137748125952f5f8c1a3fc0a22a7d6a`.
Resources: `/tmp/researchassistant-review-r56-r59-frozen/resources`.
[Exact resource hashes](../audits/2026-10-15/fix-evidence/r56-r59/ra-reviewed-frozen-artifact-r56-r59.json)
record unchanged Node/Chromium/acquisition/renderer bytes and the newly frozen backend.

## Compatibility and recovery limits

Schema 18, existing acquisition/ranking/URL policies and selection/shortlist v3
retain their bounded meanings. Query-direction provenance v2 and fresh quotation
context filter v2 have explicit recorded dispatch; old absent fields and quotation
contexts remain unchanged. Fresh synthesis v2 and renderer validator v4 use relationship-aware admitted wording
for Analyzer records; saved v2/v3 validators reproduce historical text and hashes.
Scout/Gap/Selection/Planner journal intent before dispatch and the typed outcome before aggregate
commit; an intent without an outcome remains unknown and is never silently retried. No prompt, scoring,
length, research-budget or reservation policy changes.

Older ranking-only checkpoints were written after Scout but did not save its
model decisions. Recovery records `partial-ranking-recovery-v1`, makes zero new
Scout calls and uses the existing deterministic maybe/ranking fallback. The original
physical audit retains all charges and unknown reservations. This does not recover
lost model decisions or label them model approval. New paired commits prevent that
prefix. Completed acquisition captures and validated historical admission/facts
reuse their original records; conflicting input still fails closed.

Original pre-fix probes and intermediate failed checks are preserved with hashes.
Diagnostics include a tuple/list offset comparison caught by compatibility tests,
a missing test filename/typecheck script and a fake model missing neighborhood
output. The first full run passed 3,111 with one stale pre-R41 fingerprint assertion;
the corrected check verifies the exact new context-policy field and retains the
original fingerprint for all other fields. Final regressions preserve prior assertions. Original contract fixtures
remain unchanged: tests verify only the explicit approved schema additions before
comparing every historical schema byte.

## Preservation and remaining gates

The original staged diff remains
`85f8753d0bb6ba7af20c688eab28ad10429ee43329b879d89b8db48071324cf2`.
Unrelated work, the October 9 installed app, real databases/cache/credentials,
historical policies/artifacts/released hashes and conservative accounting remain
preserved. No paid research, commit, push, app replacement or public release occurred.
Exact preceding owners and completed phase details are in the
[archive](https://github.com/francis-chen0405/ResearchAssistant/blob/archive-2026-10-23-docs-baseline/docs/archive/2026-10-15-review-fixes-preceding-state/INDEX.md), including
[the pre-R37–R52 verification state](https://github.com/francis-chen0405/ResearchAssistant/blob/archive-2026-10-23-docs-baseline/docs/archive/2026-10-15-review-fixes-preceding-state/before-r37-r52-verification/hashes.json).

Native Windows has not rerun these repairs. Historical target
`44f83d9bfb7e8e2896dc44390c366e4d498be044` retains the 240-second interrupted-upgrade
repair timeout and unreached installed acceptance. Physical power loss,
clean/minimum-OS acceptance, Windows ARM64, signing/SmartScreen and Mac
signing/notarization remain open. Local Mac checks do not close those gates.

The [manual ledger](../audits/2026-10-15/manual-coverage.json) records actual full reads.
All application/tooling/test code has full reads. The user excluded historical
records from further review: 341 of the former 365 pending entries were old records,
and four others were already-read current guidance. The active inventory now holds
20 current assets. Earlier coverage totals remain dated verification evidence;
hashes/tests do not establish manual completion or absence of bugs.

R53–R55 diagnostics retain all initial/intermediate failures: incomplete generated
bindings, incorrect Claim Fit 3 fixture expectations, tuple-shaped corruption fixtures,
and the stale exact template registry assertion. The first two full runs each failed
only that stale whitelist; the final post-correction run passes all 3,151 tests.
Historical brief text/hash assertions remain unchanged. All preceding raw hashes
were rechecked before adding current logs.

R56–R59 are implemented and verified. The first full run retained one obsolete
unknown-Planner retry expectation (3,194 pass / one failure / nine skips). Its
replacement preserves active/cancelled UI checks and requires zero repeated calls
and exactly unchanged unknown accounting. Final full validation passes all 3,195.
Original probes, intermediate fixture failures and all 349 preceding raw evidence
hashes remain retained; updated guides resolve 89 local path targets.
