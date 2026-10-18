# Repository-wide code review — 2026-10-15

Status: R01–R55 are implemented and verified; R56 awaits approval. [Verification](../../verification/full-review-fixes-2026-10-15.md) retains exact source, installed/frozen Mac checks and remaining platform limits. The user confirmed retaining browser rendering with a protected proxy. The [active plan](../../../.agent/plans/full-code-review-fixes-2026-10-15.md) tracks the incomplete every-line manual review. Original findings and baseline verification describe their pre-fix checkout.

## Scope and coverage

The starting checkout is local `master` at `94a241b52f9525cab3aff52d1f85026f081b3e85`, including its existing staged, unstaged and untracked project files. The inventory contains **1,020 files, including 527 code files and 147,198 code lines**. Installed dependencies, generated builds, ignored runtime stores and credentials are outside this source inventory. Historical archives were preserved.

The review includes a refreshed code graph, current-source inspection, HEAD-to-current comparisons across moved modules, syntax/structure checks, the full regression suite and isolated probes. Namespace-normalized AST comparisons found 1,740 of 2,057 current top-level production/tool definitions unchanged from HEAD, spanning 45,644 source lines. Equality is evidence of a move, not evidence that inherited code is correct; several findings below are inherited defects.

**Coverage limit:** all inventory entries were hashed and project code received automated checks, but manual inspection was targeted. This report does **not** establish that every one of the 147,198 lines has received an independent manual review, or that every bug has been found. The requested literal every-line manual review remains incomplete. The inventory records what exists; it must not be presented as a manual-review completion ledger.

Before fix approval, the staged diff SHA-256 was `85f8753d0bb6ba7af20c688eab28ad10429ee43329b879d89b8db48071324cf2` and the unstaged diff SHA-256 was `fb69d80dda5ed737a6dc5f10d0b485588baeb64de441ba86032bc5b0cd3fec32`. Every original inventoried file remained byte-identical during that review-only phase. Approved implementation subsequently changed the owned files; the original staged diff remains unchanged.

See [inventory](review-inventory.json) and [probe/check evidence](evidence.json). Probes used disposable generated fixtures and mocked transports. No paid research, real database/cache/credential changes, installed-app replacement, source commit/push or publication occurred.

## Findings and proposed fixes

### R01 · P1 · A valid artifact from another run is accepted and exported under the requested run

Locations: `backend/src/researchassistant/api/application_services/result_reads.py:35–50`; `backend/src/researchassistant/storage/v2_transactions.py:596–611`; `backend/src/researchassistant/evidence/brief_export.py:75–111`.

The artifact reader verifies the payload checksum but does not bind the JSON's `run_id` to its row envelope. `read_result` does not compare the parsed output with the requested run. Export then constructs metadata using the requested ID even when the materialized output belongs to another run.

**Reproduction:** generate two valid offline runs, replace A's final-artifact payload/checksum with B's valid payload in a disposable database, and restore the original schema triggers. `read_result(A)` returns B; export succeeds with A in its metadata. Schema and payload checksum validation both pass. This is a checksum-valid corruption/substitution case, not evidence that ordinary production writes currently perform this substitution.

**Fix:** validate payload/envelope/request run ownership centrally where applicable, and bind public result/export reads to the saved manifest and exact claim in the same read snapshot. Reject inconsistent records without rewriting them. Preserve explicitly recognized historical formats.

**Regression:** cross-run payload substitution must fail through result, evidence, status and all export paths; valid historical reads must remain unchanged.

### R02 · P1 · The result API trusts a stored validation flag without verifying the released-text hash

Locations: `backend/src/researchassistant/api/application_services/result_reads.py:35–50,53–119`; `backend/src/researchassistant/contracts/model_evidence.py:1100–1166`.

Parsing `V2FinalResearchOutput` checks structural relationships but does not reconstruct and verify the released-text hash. The renderer accepts this object when `release_validation.valid` is true. Export already performs the missing hash check.

**Reproduction:** change a generated final artifact's `exact_claim`, update only its outer payload checksum and retain the original release hash. The result reader returns the substituted claim as valid even though rendering it produces a different release hash.

**Fix:** share a read-only, version-aware release-materialization validator between result/evidence/status/export readers. Verify the recorded rendered hash before exposing validated release content. Never regenerate or replace historical release hashes.

**Regression:** checksum-valid changes to rendered fields must be rejected, while recognized historical rendering continues to reproduce its original hash.

### R03 · P1 · Source URL validation is vulnerable to a second DNS resolution

Locations: `backend/src/researchassistant/providers/acquisition.py:179–195,362–464`.

The public-address validator resolves a hostname, then HTTPX resolves that hostname independently when connecting. The verified public address does not constrain the connected address.

**Reproduction:** a fake socket beneath the real HTTPX/httpcore transport returns a public address for validation and `127.0.0.1` for connection. The transport connects to the private address and its generated response is accepted as source text. This probe performed no actual network I/O.

**Fix:** connect through a transport that binds each request/redirect to validated public destination addresses while retaining the original Host header and TLS hostname verification. Reject non-public peers and define proxy behavior explicitly. Review the local browser acquisition path under the same boundary; rechecking DNS alone does not close the race.

**Regression:** public-to-loopback/private rebinding, mixed address sets and redirected rebinding must fail before private content is read; legitimate HTTPS and TLS identity checks must still work.

### R04 · P1 · Round-four evidence admission contradicts the storage schema

Location: `backend/src/researchassistant/storage/store_schema.py:1472`.

The production contracts permit discovery round four, but `v2_ledger_admissions.discovery_round` has `CHECK (discovery_round BETWEEN 1 AND 3)`.

**Reproduction:** the current full offline product fixture reaches round four and releases, but saves `IntegrityError: CHECK constraint failed: discovery_round BETWEEN 1 AND 3`; admissions exist only for rounds one through three. This reconfirms the known unresolved boundary in STATUS rather than identifying a newly introduced defect.

**Fix:** add an explicit, backed-up schema migration extending this v2 admission constraint to four. Preserve historical migration definitions, rows, immutable triggers and read-only compatibility. Make schema validation select the correct historical/current table definition. Do not widen the separate legacy three-round Governor policy.

**Regression:** native/current and upgraded databases must admit valid round-four evidence, reject round five and retain historical hashes, rows and rollback/recovery guarantees.

### R05 · P2 · The standalone API does not cancel or drain its workers on shutdown

Locations: `backend/src/researchassistant/api/application.py:47–63`; `backend/src/researchassistant/api/api.py:327–330`.

Lifespan teardown only attempts an idle service stop; it never calls controller shutdown. With an active worker, it suppresses the lifecycle conflict and leaves the owned service running. The desktop wrapper has additional teardown, but the documented standalone API entry point does not.

**Reproduction:** enter and exit the actual lifespan with an active controller/owned service double. Controller shutdown and service stop are both called zero times. Real executor workers can therefore continue after API shutdown begins.

**Fix:** give the standalone runtime an explicit shutdown owner that stops admissions, requests cancellation, drains workers within the established bound and then retires owned services. Coordinate this with desktop teardown to prevent duplicate ownership or a shortened drain.

**Regression:** close the standalone server with generated active work; verify cancellation/drain, conservative reservations, owned-process cleanup and bounded exit.

### R06 · P2 · Complete evaluation scores can bypass candidate-lineage verification

Location: `evaluations/research_quality.py:464–469`.

Candidate/page reconciliation runs inside optional discovery replay. Ordinary `evaluate()` and the CLI without `--replay` calculate scores first and never perform that reconciliation.

**Reproduction:** remove unwanted candidates from the fixture manifest while retaining its complete-inventory flag and unchanged frozen provider pages. Default evaluation reports a complete inventory with precision 1.0. The same manifest is correctly rejected with replay enabled.

**Fix:** separate mandatory lineage/inventory validation from optional normalization/ranking replay. Validate complete-inventory claims before scoring in every entry point; keep genuinely incomplete historical inventories explicit.

**Regression:** both replay settings must reject missing candidates, mismatched queries/providers and unrepresented successful attempts before producing complete scores.

### R07 · P2 · Evaluation output can overwrite its input manifest or frozen artifacts

Location: `evaluations/research_quality.py:586–590`.

The CLI writes fixed output filenames with replacement semantics and does not check them against its input or registered artifacts.

**Reproduction:** put a valid fixture manifest at `bundle/results.json` and choose `bundle` as the output directory. The command reports success and replaces the manifest with a report, changing its schema and destroying the original input bytes.

**Fix:** resolve and compare output paths against the manifest and every input artifact; reject collisions including symlink/hard-link aliases. Prepare outputs before publication and use an explicit no-overwrite/fresh-output policy so prior evidence is retained.

**Regression:** direct input/output collision, artifact collision, aliases, existing output and partial-write failure must preserve original bytes.

### R08 · P2 · Buffered discovery reads defeat the wall-clock deadline

Location: `backend/src/researchassistant/providers/discovery_transport.py:76–94`.

The deadline is checked only when `iter_bytes(chunk_size=65536)` yields. That iterator can accumulate many smaller transport chunks before yielding. A trickling response can keep individual reads below their timeout while the outer wall-clock check does not execute.

**Reproduction:** a mocked stream emits 20 one-byte chunks 5 ms apart with a 20 ms configured timeout. The timeout is raised only after roughly 124 ms, after the stream finishes. Every individual chunk delay is below the read timeout.

**Fix:** enforce an absolute request deadline at the transport/read boundary, checking unbuffered arrivals and updating remaining blocking-read time. Retain decoded-byte limits, response closure, cancellation and durable unknown-attempt accounting.

**Regression:** a continuous slow trickle must stop near the absolute deadline even when it never fills the output chunk; ordinary compressed and bounded responses must remain supported.

### R09 · P2 · PDF extraction has no enforceable deadline inside a page

Location: `backend/src/researchassistant/providers/normalization.py:132–155`.

Time is checked before `extract_text()` only. PDF construction/page enumeration and one expensive page cannot be interrupted; a slow final page is returned successfully without any later deadline check.

**Reproduction:** a generated reader double spends 50 ms extracting its only page with a 1 ms deadline. Normalization succeeds after approximately 54 ms.

**Fix:** run untrusted PDF parsing/extraction in an owned, cancellable worker with a true overall deadline and resource limits. Terminate only that worker, retain the original acquisition outcome and do not issue an unaccounted retry. An extra post-page check alone does not bound a stuck extraction.

**Regression:** slow constructor, slow page enumeration and slow first/final page must time out without blocking shutdown or creating partial admitted evidence.

### R10 · P2 · Crossref can silently replace an exact DOI with another work

Locations: `backend/src/researchassistant/providers/crossref.py:44–52`; `backend/src/researchassistant/agents/v2_discovery.py:151–177,872–884`.

An exact DOI lookup accepts any returned DOI as verified. Normalization then replaces the original DOI/title/authors with that metadata without checking identifier agreement.

**Reproduction:** request `10.1234/original-work`; return a mocked Crossref message for `10.9999/different-work`. The result is marked verified, and the normalized original URL receives the different work's DOI and title.

**Fix:** normalize and compare exact identifiers before enrichment. Preserve the original identity and record a conflict/failure when the response disagrees or cannot establish its identifier. Keep optional lookup failure nonfatal; version any fresh behavior that changes identity/ranking and preserve historical dispatch.

**Regression:** mismatched/missing/malformed DOI responses must not relabel candidates or merge works; equivalent normalized DOI spellings should still enrich correctly.

### R11 · P2 · A successful research-trail retry remains hidden behind the old error

Locations: `frontend/features/results/use-result.ts:39–65`; `frontend/features/results/trail.tsx:20–27`.

`openTrail` stores an error on failure but never clears it on a new request or success. The drawer renders the error in preference to successfully loaded items.

**Reproduction:** execute the actual compiled hook with a failed first request and successful second request. The retry stores the items while `trailError` remains non-null, so the drawer still displays only the error.

**Fix:** clear the current request's error at retry start and on successful completion, retaining the existing abort/request-ownership checks.

**Regression:** fail, close/reopen and succeed; show the returned trail and discard stale request errors.

### R12 · P2 · The renderer does not reconnect to an already active run

Locations: `frontend/features/research/use-research.ts:110–120`; `backend/src/researchassistant/api/live_service.py:268–280`.

The backend returns `started=false, classification=duplicate_active` for the same active run, with a reconnection message. The frontend attaches/polls only when `started` is true.

**Reproduction:** execute the actual compiled hook with the same-run duplicate response. It displays the reconnection message but leaves both `activeRun` and `snapshot` null.

**Fix:** distinguish successful same-run reconnection from another run owning the database. Validate the returned run through a snapshot read and attach its identity without submitting another worker. Preserve the conflict behavior for a different active run.

**Regression:** same-run reconnection starts polling without another worker; different-run and externally owned database conflicts do not attach a nonexistent run.

### R13 · P2 · Valid HTTP source links do nothing in the desktop app

Location: `desktop/main.cjs:184–186`.

The source contracts and source-leads view allow HTTP(S) URLs, but Electron's external-link handler opens only HTTPS and denies the window for every URL. An HTTP source link therefore has no visible result.

**Reproduction:** execute the actual handler extracted from the current source with an external-opener double. HTTPS is forwarded; HTTP is silently discarded.

**Fix:** apply one credential-free HTTP(S) external-link policy at the desktop boundary, continue rejecting other schemes and keep all external content outside the privileged application window. Do not blindly rewrite HTTP identifiers to HTTPS.

**Regression:** valid HTTP and HTTPS sources open externally; credential-bearing, malformed and disallowed schemes remain blocked.

### R14 · P2 · Ranking cue words are not normalized like candidate words

Location: `backend/src/researchassistant/research/metadata_ranking.py:24–49,95–109`.

Candidate tokens have trailing `s` characters removed, while the method-cue set retains unnormalized words such as `methods`, `results`, `analysis` and `records`. Those explicit cues cannot match their transformed tokens.

**Reproduction:** a candidate titled `Methods results analysis records`, with no supplied type, receives `method_fit=null` and the unknown/neutral rationale despite consisting entirely of configured method cues.

**Fix:** normalize cue vocabularies through the same tokenization function, or use a consistent documented normalizer for both operands. Bind changed fresh ranking behavior to a new policy identity; retain historical ranking/replay meanings.

**Regression:** every configured cue matches its normalized text form; stable ties, direction neutrality, missing-metadata neutrality and prior-policy replay remain intact.

## Continued review findings

### R15 · P2 · A delayed preferences response overwrites the user's new budget and direction

Locations: `frontend/features/preferences/use-preferences.ts:43–59`; `frontend/app/page.tsx:26–28,118–141`; `frontend/features/research/composer.tsx:95–132`.

The preferences hook exposes editable defaults immediately and later spreads the saved settings over the current values. The page does not receive or enforce the hook's `loaded` state. A delayed read therefore discards choices the user has already made. On read failure, the warning asks the user to reopen before editing, but the controls remain available and those changes cannot be saved.

**Reproduction:** execute the actual compiled hook with a deferred preferences response. Select a **$0.50** limit and enable Challenge, then complete the read with previously saved **$10.00** and Challenge disabled. The hook changes the selected values to $10.00 and disabled. No provider or paid calls occur. The retained [continued-review evidence](continued-review-evidence.json) records the observed values.

**Proposed fix:** expose preference readiness and read errors. Keep preference editing and new-run submission unavailable until the initial read succeeds, with a visible retry action for read failure. Preserve normal debounced/ordered saves after readiness; do not change any research budget or direction policy.

**Regression:** defer the initial read, verify edits/start remain unavailable, then load and permit deliberate changes. Fail the read, retry successfully, and verify only the user's post-load values are saved and submitted. Cover the mounted page as well as the actual hook. **Approved and implemented:** seven hook checks and all six browser smokes pass, including mounted delayed/failing/retried reads, no premature save/start, and exact post-load budget/direction submission. The frozen-resource smoke also passes after restaging the UI.

### R16 · P2 · Completing history import restores stale model-budget/settings values

Locations: `frontend/features/preferences/panel.tsx:26–31,303–315`; `frontend/app/page.tsx:43–49`.

The asynchronous import callback spreads the settings captured when import began. The rest of the preferences panel remains editable during the request. Completing import therefore restores old values over deliberate changes made while it was pending. The callback also lacks disposal ownership, so closing the panel does not prevent a late selection change.

**Reproduction:** execute the actual compiled panel's Import action, change its model-cost select from **$10.00** to **$0.50** while the mocked import is pending, and return a generated imported path. The path is selected but the limit returns to **$10.00**. No database, provider or paid calls occur; [continued-review evidence](continued-review-evidence.json) retains the observed values.

**Proposed fix:** apply only the imported database path/run-ID reset through a parent callback using the latest settings. Give the import request disposal/abort ownership; ignore late UI completion after closing the panel. Temporarily disable the database-path/import controls during import, keeping other settings editable. Preserve any completed backend copy and all real source databases; cancellation must not delete imported data.

**Regression:** defer import, change budget/directions, complete it and preserve those new values while selecting the imported database. Closing the panel must prevent late selection changes; repeated import clicks must not start duplicate requests. **Approved and implemented:** eleven hook checks and the mounted delayed-import regression pass. Input/active-selection ownership is rechecked at completion; backend copies are never deleted by the UI.

### R17 · P2 · Typing during a key save can erase the new key while reporting success

Location: `frontend/components/provider-setup.tsx:119–143,265–286`.

The save action freezes the current keys, but its password inputs remain editable while `busy`. On completion it clears every field and reports success, including values typed after submission that were never sent. Remove-key completion can likewise clear intervening input.

**Reproduction:** execute the actual compiled form/input callbacks with a deferred save. Submit a generated first key, type a generated second key while saving, and finish the first request. The submitted payload contains the first value, the second value disappears, and the UI reports “Saved securely.” No real credential or provider calls occur. See [continued-review evidence](continued-review-evidence.json).

**Proposed fix:** disable credential editing during an owned pending action and prevent overlapping submissions/actions before state updates commit. Preserve transient-only secret handling and normal field clearing once the submitted action completes.

**Regression:** deferred save/remove/check actions keep password inputs unavailable; duplicate actions do not submit additional mutations; completion clears only the completed interaction and later deliberate edits remain usable. **Approved and implemented:** the pending-action guard, all seven disabled key inputs and duplicate-action rejection pass the actual component checks and mounted browser regression.

### R18 · P2 · A late provider callback can replace current configuration with an old model selection

Locations: `frontend/features/preferences/use-configuration.ts:31–73`; `frontend/components/provider-setup.tsx:130–131,187,211`; `frontend/app/page.tsx:172–174`.

`refreshConfiguration` captures the selection from its render. A pending provider action retains that callback after its dialog closes. If the user changes models and gets a successful current check before the old action completes, the retained callback starts a newer request for the old models. The monotonically increasing request ID then treats this obsolete selection as current.

**Reproduction:** execute the actual compiled configuration hook. Retain refresh for MiMo Scout, switch to GPT-6 Sol Scout and obtain `configured=true`, then invoke the retained callback as a late provider-save completion does. It checks MiMo and replaces the current configuration with `configured=false`. No network/provider calls occur; [continued-review evidence](continued-review-evidence.json) records the selected/requested models.

**Proposed fix:** make explicit refresh read the latest committed selection, and bind response ownership to that selection as well as request ID/abort state. Preserve automatic checks when selections change and normal refresh after a successful credential mutation, including a mutation completed after its dialog closes.

**Regression:** defer a provider save, close its dialog, change models and complete the current check; completing the old save must check the new models and retain their configuration. Existing stale success/failure and unmount checks must remain valid. **Approved and implemented:** explicit refresh reads the latest committed selection, and response ownership checks that selection. Seventeen total hook/component regressions and all six browser smokes pass, including a delayed save after dialog closure and a model change.

### R19 · P2 · Source preflight still has no absolute download deadline

Locations: `backend/src/researchassistant/providers/acquisition.py:180–205,247–254`; `backend/src/researchassistant/providers/public_network.py:29–43`.

The public-destination transport supports request-local absolute deadlines, but acquisition never installs one. Its HTTPX timeout therefore resets for each read, and redirects each receive a fresh full timeout. A slow source can keep preflight occupied long after its configured deadline; cancellation waits for this operation to return. R08 repaired discovery reads only, so that fix does not cover this separate acquisition path.

**Reproduction:** run the actual HTTPX/httpcore/public-destination path with a generated socket that returns one byte every 5 milliseconds. Every read honors its 20-millisecond socket timeout, but preflight accepts the complete response after 82.7 milliseconds. All thirteen read budgets remain 20 milliseconds. There are no real network calls; the [probe evidence](continued-review-evidence.json) retains the exact observation and source hashes.

**Proposed fix:** give one source-preflight operation a single monotonic deadline shared by redirects, connection/TLS/header/body reads and canonical checks. Apply the remaining time to every blocking operation, fail with the existing typed timeout, and close the owned response/socket. Preserve public-address pinning, size limits, retry accounting and historical acquisition identities; version fresh acquisition behavior as needed.

**Regression:** actual transport trickle/header cases must stop at the total budget, redirects must not reset it, and success/timeout must close streams. Keep all DNS/public-address/peer checks. **Approved and implemented.** Current verification is recorded in the [repair record](../../verification/full-review-fixes-2026-10-15.md).

### R20 · P2 · Blocking DNS resolution escapes the discovery deadline

Locations: `backend/src/researchassistant/providers/bounded_network.py:73–90`; `backend/src/researchassistant/providers/acquisition.py:453–456,485–495`; `backend/src/researchassistant/providers/public_network.py:36`.

`DeadlineBackend` delegates to synchronous `socket.create_connection`, whose socket timeout does not cover its blocking `getaddrinfo` lookup. The source preflight resolver also calls `getaddrinfo` directly. Neither resolver has an owned timeout boundary. A stalled local resolver can therefore hold discovery/acquisition and cooperative cancellation beyond their advertised deadlines, even after socket reads are bounded.

**Reproduction:** execute `bounded_send` with its actual HTTPX/httpcore transport and a generated resolver that returns an error after 120 milliseconds. A 20-millisecond absolute request deadline returns only after 125.4 milliseconds with `ConnectError`. No socket connects and no provider traffic occurs; [probe evidence](continued-review-evidence.json) records the result.

**Proposed fix:** resolve within a bounded, owned helper that can be retired at the remaining deadline; use the returned numeric addresses for connections while preserving original Host/TLS identity and source public-address/connected-peer checks. Share the caller's remaining budget through discovery and acquisition; bound helper concurrency/output and clean up on timeout/shutdown. Cover installed/frozen dispatch on each supported platform without weakening historical identity or reservation rules.

**Regression:** a resolver that never returns must time out with no connection attempt or leaked owned helper; late DNS results must not initiate work. Verify numeric sockets, fallback addresses sharing the same budget, TLS identity and native/frozen helper startup/cleanup. **Approved and implemented.** Current verification is recorded in the [repair record](../../verification/full-review-fixes-2026-10-15.md).

### R21 · P3 · Generated wire contracts describe missing catalog fields and the wrong research error

Locations: `frontend/scripts/generate_api_contracts.py:36–44,61–75,139–151`; `frontend/lib/generated/api-contracts.ts:204–222,663–670,810–816`; `backend/src/researchassistant/api/application_services/configuration.py:86–103`.

The generator substitutes the internal full `ModelOptionsPayload` for the route's smaller display projection. The generated route type consequently requires `model`, cached pricing and cap fields that the HTTP response never sends. Its supplemental schema merge also treats an existing short model name as authoritative: FastAPI's HTTP `ValidationError` wins over the distinct research `ValidationError`, so release/evidence validation errors acquire `loc/msg/type` instead of `code/location/message`.

**Reproduction:** compile an actual offline `/api/model-options` response directly against generated `ApiResponses`: all six choices fail on missing fields. Compile a real research-validation error against the generated release-error element type: it fails for missing `loc/msg/type`. Conversely, an HTTP input-validation error incorrectly passes as a research-release error. The current client narrows catalog fields with `Pick`, so existing catalog controls still work; successful release examples have empty error arrays, which leave the error collision untested. This is a generated-contract correctness defect, not evidence of lost saved research. [Probe evidence](continued-review-evidence.json) retains all three compiler outcomes.

**Proposed fix:** define the existing catalog display shape as an explicit HTTP response model and derive its generated type from that actual shape. Resolve supplemental model-name collisions with distinct schema identifiers and rewritten references; preserve historical Python class identities and wire payloads. Compile real responses directly against generated route types and cover nonempty research errors separately from HTTP input errors, including rejection of the swapped shapes.

**Regression:** catalog responses satisfy the exact generated route type; research/HTTP errors satisfy only their own types; collisions fail explicitly rather than silently binding to a different model. **Approved and implemented.** Current verification is recorded in the [repair record](../../verification/full-review-fixes-2026-10-15.md).

### R22 · P2 · Model calls can also outlive their configured stage deadline

Location: `backend/src/researchassistant/providers/mimo.py:224–241,716–720`.

The shared MiMo/OpenAI adapter sends a buffered `post` with HTTPX's per-operation timeout. It never installs a monotonic deadline or checks elapsed time during response reading. A provider that continues sending small chunks can therefore keep a model call active beyond its stage deadline, delaying cooperative cancellation and retaining an in-flight reservation. This is separate from R19's source preflight path and R08's repaired discovery path; it does not justify refunding unknown usage.

**Reproduction:** execute the actual adapter and HTTPX/httpcore with a generated socket returning one JSON byte every five milliseconds. With a 20-millisecond stage deadline, the adapter finishes buffering only after 77.2 milliseconds and reports the fixture's missing model identity, rather than a timeout. Every read receives a fresh 20-millisecond budget. No real model or credential calls occur. The same `generate` method serves the selectable fresh model routes and historical routes. [Probe evidence](continued-review-evidence.json) records exact budgets and source bytes.

**Proposed fix:** bound each physical model request by its existing stage deadline across connect/TLS/headers/body reads, using remaining time and bounded streaming before decoding. Preserve route/model selection, request payloads, retry caps and durable accounting. A timeout with unknown usage must retain its reservation and never silently replay the call. Coordinate DNS with R20 and apply fresh transport identity without rewriting historical records.

**Regression:** stalled headers and continuous trickles stop within the stage budget, close the response and retain unknown usage conservatively; successful and fully reported failures preserve exact accounting. Exercise both provider families and concurrent calls with independent deadlines. **Approved and implemented.** Current verification is recorded in the [repair record](../../verification/full-review-fixes-2026-10-15.md).

### R23 · P1 · Supplemental evidence can contradict the released statement under the same Ledger ID

Locations: `backend/src/researchassistant/api/application_services/evidence_projection.py:127–173,280–307`; `backend/src/researchassistant/contracts/model_evidence.py:538–565`.

Evidence projection verifies candidate/snapshot/record identifiers and exact quotation bytes, but it does not bind the admitted statement to the saved synthesis item using that Ledger ID, or check the admitted claim against the owning claim. The batch validator also leaves those cross-artifact relationships unchecked. Consequently the immutable released brief and its supplemental “admitted evidence” can make different factual statements under one Ledger identity.

**Reproduction:** generate an offline released run, change only one admission record's factual statement and approved claim, update its outer payload checksum, and restore the original database trigger. The result reader returns the original validated brief/hash, while the evidence reader accepts the substituted statement under the same Ledger ID. Inspection changes no database bytes. This is a checksum-valid corruption/import-consistency case; it does not establish that normal production writes currently perform this substitution. [Probe evidence](continued-review-evidence.json) retains the original/substituted observations.

**Proposed fix:** before exposing supplemental admitted evidence, validate its owning run/claim and join each released synthesis item to the corresponding admitted record. Require agreement on the statement and its recorded admission/provenance fields, using the recognized historical format. Reject inconsistent supplemental data with a clear read-only diagnostic. Preserve original release text/hashes, historical identities and valid exports; never repair or rewrite stored artifacts during inspection.

**Regression:** same-ID substituted statements/claims and mismatched admission links fail closed; valid fresh and recognized historical evidence still read unchanged. Confirm database bytes and released hashes remain unchanged. **Approved and implemented.** Current verification is recorded in the [repair record](../../verification/full-review-fixes-2026-10-15.md).

### R24 · P2 · One malformed metadata URL aborts an otherwise usable scholarly page

Locations: `backend/src/researchassistant/providers/openalex.py:292–298,328–354`; `backend/src/researchassistant/providers/arxiv.py:192–195,258–260`.

OpenAlex and arXiv URL helpers call `urlsplit` before their per-result validation handlers. A malformed bracketed host raises raw `ValueError`, aborting the complete page. OpenAlex also eagerly validates every candidate URL before choosing one, so a malformed optional alternate aborts a record whose primary URL is valid. Valid neighboring records are lost as well.

**Reproduction:** feed the actual OpenAlex adapter a mocked page with two valid primary URLs and one malformed optional alternate (`http://[`). It raises `ValueError: Invalid IPv6 URL` and returns neither valid result. The actual arXiv adapter similarly loses a valid entry after a malformed entry ID. No external calls occur; [probe evidence](continued-review-evidence.json) records both failures.

**Proposed fix:** make URL validation total for untrusted strings: malformed optional URLs are unusable metadata, not uncaught exceptions. Preserve valid primary/fallback URLs and unaffected records; an entirely unusable page should produce the existing typed empty/malformed outcome. Keep credential-free HTTP(S) and downstream public-destination checks, original ranks, raw response retention and deterministic replay.

**Regression:** malformed primary/alternate/PDF URLs cannot abort valid neighboring results, valid alternatives remain selectable, and all-invalid pages fail with a typed provider outcome. **Approved and implemented.** Current verification is recorded in the [repair record](../../verification/full-review-fixes-2026-10-15.md).

### R25 · P2 · Canonicalization removes required IPv6 brackets and breaks fresh ranking

Locations: `backend/src/researchassistant/providers/ranking.py:171–186`; `backend/src/researchassistant/research/metadata_ranking.py:56–63`; `backend/src/researchassistant/research/discovery_policy.py:131–141`.

Canonicalization reconstructs the authority from `parsed.hostname`, which omits an IPv6 literal's brackets. The resulting URL is invalid, with or without an explicit port. Fresh metadata ranking canonicalizes that saved value again to derive a work key, and fails while parsing its apparent port. This contradicts the source transport's supported public IPv6 destinations.

**Reproduction:** both `https://[2606:4700:4700::1111]/paper` and the same URL with port 8443 pass the actual public-source URL validator. Canonicalization removes their brackets; the actual `rank_metadata` path then raises a port-parsing `ValueError`. No network calls occur. [Probe evidence](continued-review-evidence.json) retains both canonical values and failures.

**Proposed fix:** reconstruct valid bracketed IPv6 authorities while preserving ports and existing hostname/IPv4 behavior. Version fresh URL/work identity behavior wherever persisted identities depend on it; retain recognized historical mapping/dispatch and the exact resume gate. Never rewrite stored IDs or canonical URLs during history inspection.

**Regression:** canonicalization is valid and idempotent for public IPv6 with/without ports, and fresh ranking/acquisition can retain the candidate. Existing hostname/IPv4, query tracking, grouping and historical identity fixtures remain unchanged. **Approved and implemented.** Current verification is recorded in the [repair record](../../verification/full-review-fixes-2026-10-15.md).

### R26 · P1 · A cached release remains authoritative after its database run disappears

Location: `backend/src/researchassistant/api/live_service.py:370–445,524–548`.

Completed workers place their terminal snapshots in `_early_results`. If a later read finds no persisted run at that path, `snapshot` still returns the cached terminal result. When a valid database exists at the same path but lacks the run, the cache is never evicted, so repeated reads continue reporting “released” with the old brief/hash. The result/evidence APIs cannot materialize that missing run, contradicting the controller's persisted-state authority.

**Reproduction:** generate a released fixture and exercise the actual completed-future eviction/cache path. Preserve its database by renaming it, then create a new empty valid database at the original path. Two successive snapshots both return the old released brief/hash, and the cache entry remains. Inspection does not modify the replacement. No real research or database files are used. [Probe evidence](continued-review-evidence.json) retains the observations.

**Proposed fix:** use cached terminal outcomes only as hints to re-read committed state; never substitute their release content when the owning persisted run is absent. Retain explicit ephemeral startup/configuration failure diagnostics where appropriate. Handle commit/read races with a bounded fresh read, and fail clearly on removed/replaced databases without creating or migrating them.

**Regression:** removed files and valid replacement databases cannot return stale released/blocked content, hashes or status. Preserve first-poll terminal-commit race handling, active startup views, rejected-resume diagnostics and read-only database behavior. **Approved and implemented.** Current verification is recorded in the [repair record](../../verification/full-review-fixes-2026-10-15.md).

### R27 · P3 · The published HTTP input-error shape contradicts the redacted response

Locations: `backend/src/researchassistant/api/application.py:95–98`; automatically generated OpenAPI 422 responses and `frontend/lib/generated/api-contracts.ts`.

The application deliberately replaces request-validation details with `{"detail":"Invalid request fields."}` to prevent secret input from appearing in errors. OpenAPI still advertises FastAPI's default `HTTPValidationError`, whose `detail` is an array of structured errors. Consequently the generated error contract cannot describe the actual response. The renderer currently accepts either shape through its error reader, so this is a published-contract contradiction rather than a demonstrated broken control.

**Reproduction:** submit an empty offline `/api/research/start` request. The actual response is HTTP 422 with a string `detail`; the same application's OpenAPI declares an array. No worker, database, credentials or provider calls occur. [Continued-review evidence](continued-review-evidence.json) retains the observation.

**Proposed fix:** document the existing redacted 422 envelope explicitly at application assembly, retain its exact response bytes and secret protection, and regenerate the renderer contract. Update the contract regression to compare actual HTTP error envelopes and research-validation errors against their own generated types. Preserve historical Python class identities and saved artifacts.

**Regression:** real invalid requests satisfy the published 422 schema, credential inputs remain absent from errors, and the rest of the frozen route/payload inventory remains unchanged. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R28 · P2 · DOCX export reports success for malformed document XML

Locations: `backend/src/researchassistant/evidence/brief_export.py:224–243`; `backend/src/researchassistant/evidence/pdf_render.py:35–57`.

The DOCX exporter escapes markup delimiters but does not reject characters that cannot appear in its XML text. Research claims and captured text may contain such control characters. The exporter writes the resulting invalid document and reports success with a matching file hash. The PDF compatibility diagnostic also recommends DOCX for these characters, although that alternative currently produces malformed XML.

**Reproduction:** generate an offline released run whose accepted exact claim contains U+0001, then call the public DOCX export. Export succeeds, but the standard XML parser rejects `word/document.xml` as not well formed. The exported file's reported hash matches; the saved database and released hash remain unchanged. [Continued-review evidence](continued-review-evidence.json) retains the exact probe and observation.

**Proposed fix:** check DOCX text representability before creating the destination, fail with a clear format-compatibility error for unsupported characters, and recommend Markdown. Keep all released text and hashes unchanged. Preserve DOCX as an alternative for ordinary Unicode that PDF cannot shape, and avoid recommending it for characters its XML cannot represent.

**Regression:** XML-invalid controls cannot produce a successful DOCX or partial destination; valid escaped text, Unicode, tabs and line breaks still export correctly. Markdown preserves the original text; PDF fallback advice names only usable alternatives. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R29 · P2 · Active-run polling discards discovery diagnostics before they reach the UI

Locations: `backend/src/researchassistant/api/live_progress.py:693–697,740–799`; `frontend/features/research/progress.tsx:142–185`.

`snapshot_from_v2_progress` computes and enriches `V2RunDiagnostics` under the validated read-only snapshot, but omits it from the returned `LiveRunSnapshot`. The field defaults to `None`. The renderer displays “Discovery so far” only when that field exists, so active runs hide provider/page counts, retained metadata and coverage warnings. The terminal-result projection correctly includes the diagnostics.

**Reproduction:** start an actual fresh controller worker using generated offline providers and pause its first acquisition after discovery has persisted. The actual HTTP poll returns `running`, `worker_active=true` and `v2_diagnostics=null`, although the same read-only source computes three logical operations, three provider requests and three retained records. The database bytes stay unchanged. [Continued-review evidence](continued-review-evidence.json) retains the probe and results.

**Proposed fix:** include the already computed diagnostics in the running/partial snapshot. Preserve optional unknown fields, historical fallback behavior, one read-only snapshot and current budget/accounting semantics. Add a regression through actual controller polling and verify that the renderer displays the received activity.

**Regression:** active discovery/acquisition and interrupted partial runs expose the available counters/messages; missing historical artifacts retain unknown values, terminal projections remain consistent and inspection never writes. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R30 · P2 · A provider completion can disagree with its physical request's operation during inspection

Location: `backend/src/researchassistant/storage/discovery_store.py:751–791` (`provider_attempt_audit`), and counter readers using those results.

The audit aligns completions to starts by attempt ID, but only checks whether each completion's operation ID appears anywhere among the run's starts. A completion naming a different existing operation therefore passes inspection. Fresh completion writes correctly require the exact owning operation; the read boundary does not enforce that same relationship. These artifacts describe durable physical requests and budget exposure, so a checksum-valid but contradictory record must not be accepted as an owned response.

**Reproduction:** generate offline released research, change only one completion's `operation_id` to another saved operation, recompute its envelope checksum and restore the exact original immutability trigger. The audit returns a start/completion pair with different operation IDs; the public controller still returns the released snapshot and provider counters. Inspection leaves the generated database unchanged. This demonstrates accepted contradictory saved data, not an observed ordinary production write of that data. [Continued-review evidence](continued-review-evidence.json) retains the probe and observation.

**Proposed fix:** validate each completion against the exact start it names before alignment, counters or replay use. Route shared counter readers through the same validated audit. Preserve missing/unknown completions and conservative reservations; reject inconsistent records read-only, without rewriting saved artifacts, hashes or charges.

**Regression:** another existing operation cannot satisfy completion ownership; valid current/historical audits, incomplete requests, public status/diagnostics and exact accounting remain unchanged. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R31 · P2 · Completed production resume trusts an invalid original release hash

Locations: `backend/src/researchassistant/research/v2_orchestrator.py:747–776,843–852`; `backend/src/researchassistant/agents/v2_final_output.py:148–163`.

Production resume parses a saved terminal result, trusts its release-validation flag and returns it without verifying the original rendered-text hash. The current path also reasserts terminal state before returning. This bypasses the shared saved-output validation already used by API/history/export readers. Cached final-stage validation compares inputs and provenance but also omits this hash check.

**Reproduction:** generate an offline released run, change only the production-result's nested release hash to 64 `f` characters, recompute its envelope checksum and restore the exact immutability trigger. Actual production resume under identical source/settings returns `released` although rendering yields a different hash. It makes zero model/search requests and leaves the database unchanged. This demonstrates accepted checksum-valid corruption, not an ordinary production write. The completed-result path is reproduced; a separate attempted final-stage probe stopped earlier at R32 and does not establish that path's reachability. [Probe evidence](continued-review-evidence.json) retains the successful completed-result reproduction.

**Proposed fix:** validate run/claim agreement and the original rendered-text hash before accepting a cached final/terminal result or reasserting release state, using compatible historical rendering. Preserve recognized historical output behavior and the exact source/settings resume gate. Reject inconsistent data without rewriting saved hashes, release decisions or research, and without new provider calls.

**Regression:** current and recognized historical cached results reject checksum-valid release/hash contradictions; valid exact resumes still return the same content without duplicate calls. **Approved and implemented.** See [verification](../../verification/full-review-fixes-2026-10-15.md).

### R32 · P1 · An ordinary interrupted resume fails because its remaining budget has decreased

Locations: `backend/src/researchassistant/research/v2_orchestrator.py:932–953`; `backend/src/researchassistant/agents/v2_gap_analysis.py:233–240`.

Replay rebuilds the Round-1 Gap Analysis input with the run's current remaining budget. The cached stage compares the entire input against the original saved input, including the earlier budget snapshot. Work completed after Gap Analysis has legitimately consumed more budget, so an otherwise identical resume fails before reaching that saved work.

**Reproduction:** interrupt an actual generated offline product run immediately before its final terminal commit, then resume with identical source/settings. No artifact substitutions or database edits are made. The only changed Gap Analysis input field is `remaining_budget`: the saved snapshot has 158 calls / 499,970 tokens / $4.99998 remaining; the resumed snapshot has 140 / 499,700 / $4.9998. Resume returns `failed` with `persisted Gap Analysis input does not match this Round-1 state` and persists a failed manifest. No new model/search requests occur. [Probe evidence](continued-review-evidence.json) retains this ordinary-interruption reproduction.

**Proposed fix:** replay completed stages against their immutable research/source/query/policy inputs and preserve their originally recorded budget snapshots. Keep current authoritative physical accounting for every new action. Review downstream replay comparisons for the same drift, without replenishing exposure, refunding unknown requests or changing historical policies and exact resume compatibility.

**Regression:** actual interruptions after completed stages through final commit can resume unchanged settings and reach the same result without duplicate requests; changed research inputs still fail, and all resumed new work respects current reservations/ceilings. **Approved and implemented.** See [verification](../../verification/full-review-fixes-2026-10-15.md).

### R33 · P2 · Resume collides with its own partially committed stage checkpoints

Locations: `backend/src/researchassistant/agents/v2_source_selection.py:341–342,375–376,447–448`; `backend/src/researchassistant/agents/adaptive_execution.py:153–183`.

Some stages commit intermediate artifacts before their completion marker. Resume rebuilds an already saved artifact with a new clock timestamp and tries to insert it under the same immutable key. Storage correctly rejects that drift, but the pipeline then persists a failed terminal result for otherwise recoverable work. Fixed-clock fixtures conceal this path.

**Reproduction:** after implementing R32, run the actual generated product pipeline with an advancing UTC clock. Interrupt immediately after committing either the source-selection survivor pool or the Round-2 execution checkpoint, then resume identical source/settings. Both resumes fail with `v2 artifact ... already exists with different data`, making zero new model/search requests. No saved artifacts are modified by the probe. [Evidence](continued-review-evidence.json) retains both ordinary-interruption cases.

**Proposed fix:** make these stage checkpoint prefixes restartable: validate and reuse their original saved content/timestamps, or commit dependent completion checkpoints atomically where appropriate. Check related writes in these stage owners for the same interrupted-prefix failure. Keep storage immutability, current reservations and unknown usage; do not overwrite saved artifacts or repeat already completed provider work.

**Regression:** advancing-clock interruptions between dependent writes can resume with original checkpoints unchanged; conflicting research inputs still fail, and completed/unknown requests keep their existing accounting. **Approved and implemented.** See [verification](../../verification/full-review-fixes-2026-10-15.md).

### R34 · P2 · An interrupted admission can drop already admitted evidence on resume

Locations: `backend/src/researchassistant/agents/v2_evidence_admission.py:75–91,161–164,231–261`; `backend/src/researchassistant/storage/v2_transactions.py:357–421`.

Evidence admission commits its immutable relational record before saving the source checkpoint. If interrupted between those writes, resume reconstructs the same admission with a new timestamp. The relational boundary correctly refuses to replace the original record. Deep analysis classifies the source as failed and the final brief can omit its already admitted evidence.

**Reproduction:** interrupt generated offline research immediately after one durable evidence-admission commit, using an advancing UTC clock. Resume identical source/settings with no saved-artifact edits. It returns `released`, but the interrupted source becomes `analyst_failed` and its admitted item is missing from the final synthesis. The underlying failure is `IntegrityError: v2 evidence admission is immutable`. The original admitted row is unchanged and no model/search calls repeat. [Evidence](continued-review-evidence.json) retains the exact probe and results.

**Proposed fix:** recover and validate an existing admission against its exact typed Analyst/candidate/provenance inputs, preserving its original timestamps and bytes. Make the relational admission and source checkpoint commit together for future writes where possible. Keep old partial prefixes recoverable without relabeling historical policies, refunding unknown usage or repeating completed model work.

**Regression:** interruption between admission/checkpoint writes retains the original admitted evidence in the resumed result; mismatched existing records still fail closed, immutable rows/hashes remain unchanged, and accounting remains exact. **Approved and implemented.** See [verification](../../verification/full-review-fixes-2026-10-15.md).

### R35 · P2 · Fourth-round survivors exceed the final selection contract's three-round capacity

Locations: `backend/src/researchassistant/contracts/research_selection.py:164`; `backend/src/researchassistant/contracts/source_selection_preview.py:27–29`; `backend/src/researchassistant/agents/v2_acquisition.py:272–284`.

Acquisition permits up to 25 retained sources per round and production now supports four rounds. The complete final-selection pool and shortlist audit still allow only 75 sources. Valid balanced settings can therefore finish discovery with more surviving sources than the next stage accepts, failing before source prioritization.

**Reproduction:** run generated offline balanced research requesting twenty sources per direction with Exa/OpenAlex, unique metadata and continuing gaps in both directions. Three rounds retain 60 survivors; Round 4 saves 80. The actual pipeline then fails with `V2SourceSelectionInput ... at most 75 items ... not 80`, after 17 model and 16 search requests to generated providers. No real data or external calls occur. [Evidence](continued-review-evidence.json) retains the exact reproduction.

**Proposed fix:** support the bounded four-round maximum of 100 survivors in fresh final-selection and shortlist contracts, with explicit versioned behavior and consistent downstream validation. Preserve older 75-source policy meanings and historical serialized records. Keep existing per-round, model-input, physical-call/token/cost and queue limits; do not drop retained sources silently or enlarge research allowances.

**Regression:** actual balanced runs with more than 75 survivors reach prioritization and retain an explicit disposition for every source; new contracts reject over 100 and old policy limits remain enforced. Queue/new model work remains bounded by current accounting. **Approved and implemented.** See [verification](../../verification/full-review-fixes-2026-10-15.md).

### R36 · P2 · CLI configuration errors echo rejected credential-bearing input

Locations: `backend/src/researchassistant/runtime/cli.py:318–320`; `backend/src/researchassistant/providers/config.py:51–74`.

The CLI prints the complete Pydantic validation error for provider configuration. The validator correctly rejects URL credentials, but Pydantic includes the rejected input value in the displayed error. A password or token in invalid configuration can therefore appear in terminal output or captured logs.

**Reproduction:** call the actual CLI configuration handler with an explicitly injected synthetic loopback URL containing `probe-secret`. It exits with configuration code 20 and echoes that synthetic password in stderr. No database is created and no identity/provider setup or external calls occur. [Evidence](continued-review-evidence.json) retains the exact observation; no real credentials were used.

**Proposed fix:** redact validation input values at the CLI configuration-error boundary while retaining safe field names and useful configuration diagnostics. Preserve exit codes, request validation behavior and historical serialized class identities/payloads. Do not relax credential-free endpoint validation.

**Regression:** rejected passwords/query tokens and other secret-bearing validation inputs never appear in stderr/stdout; safe missing-field/configuration messages and exit codes remain useful, with zero database/provider activity. **Approved and implemented.** See [verification](../../verification/full-review-fixes-2026-10-15.md).

### R37 · P2 · A source discovered in both directions can fail final reconciliation

Locations: `backend/src/researchassistant/agents/v2_discovery.py:313–321`; `backend/src/researchassistant/agents/v2_source_selection.py:230–241`; `backend/src/researchassistant/agents/round_four_reconciliation.py:156–166`.

Discovery correctly groups repeated papers and preserves every contributing query, including queries from both research directions. A survivor has one selected direction. Its final-selection provenance loses the original query direction, and reconciliation incorrectly requires every contributing query's targeted Gap to belong to the survivor's direction. A paper returned by both supporting and challenging searches can therefore stop an otherwise valid run after selection and analysis.

**Reproduction:** actual generated balanced four-round research with valid both-direction gaps and repeated paper titles across those directions reaches final selection with 80 survivors and 80 saved dispositions after R35. It then fails with `search provenance Gap ID 'gap-round-3' has mismatched direction`. No saved artifacts are edited and all model/search responses are generated offline. The [retained probe/result](continued-review-evidence.json) identify the cross-direction query provenance.

**Proposed fix:** retain and validate each contributing query's own direction in versioned fresh selection provenance, without discarding cross-direction discovery history. Validate each query/Gap against that original direction, and limit evidence credit to the admitted source's actual research direction. Preserve old serialized records, original policy meanings, exact resume gates and accounting.

**Regression:** a paper legitimately discovered in both directions releases with all original provenance retained; forged query/Gap directions still fail closed, and no cross-direction evidence credit is invented. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R38 · P2 · Interrupted discovery/acquisition sidecars prevent exact-source resume

Locations: `backend/src/researchassistant/agents/v2_discovery.py:350–356,420–426`; `backend/src/researchassistant/agents/v2_acquisition.py:237–250,482–485`.

Discovery and acquisition save their ranking sidecar before their main completion artifact. After interruption between these commits, an unchanged resume rebuilds the stage with a later timestamp. The existing immutable sidecar correctly rejects the new envelope, so the run fails instead of finishing its saved work. Discovery can also repeat a completed Scout call during this reconstruction.

**Reproduction:** interrupt actual generated production immediately after the Round-1 discovery ranking commit, then separately after the acquisition ranking commit, using an advancing UTC clock. Both exact-source resumes fail with `v2 artifact ... already exists with different data`. The original sidecar remains unchanged. Discovery repeats one generated model call; acquisition repeats no model or search calls. No artifacts are manually edited and no real data, credentials or external calls are used. [Evidence](continued-review-evidence.json) retains both cases.

**Proposed fix:** make each stage's ranking/completion writes commit together and safely recover previously possible sidecar-only prefixes from their original validated facts/timestamps. Reuse completed provider work, reject contradictory saved inputs, and retain original artifact bytes, charges, unknown reservations and exact resume compatibility.

**Regression:** advancing-clock interruptions at both stage boundaries resume successfully without replaying completed physical work; original sidecars and accounting stay unchanged, and conflicting inputs remain rejected. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R39 · P2 · Interrupted Round-4 completion rebuilds immutable execution facts

Locations: `backend/src/researchassistant/agents/v2_round_four.py:581`; `backend/src/researchassistant/agents/round_four_summary.py:380–401,432–451`.

Round 4 saves its post-plan execution facts before its completion artifact. An interruption between these writes leaves valid completed search/acquisition work. Resume reconstructs those facts with a new completion timestamp, then compares them to the immutable original facts and rejects the run.

**Reproduction:** interrupt actual generated production immediately after the post-plan facts commit, using an advancing UTC clock. Exact-source resume fails with `persisted Round-4 post-plan facts do not match the execution`, with no new model/search calls and the original facts unchanged. No saved artifacts are edited. [Evidence](continued-review-evidence.json) retains the exact offline probe and result.

**Proposed fix:** validate and reuse original saved execution facts/timestamps when rebuilding the remaining Round-4 completion checkpoint. Commit dependent completion records safely, preserve prior bytes/accounting, and reject changed execution facts without broadening authorization or replaying provider work.

**Regression:** advancing-clock interruption after facts commit resumes successfully with unchanged original facts, artifacts and physical audit; altered execution facts remain rejected. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R40 · P3 · Historical Reviewer admission cannot recover an interrupted relational commit

Locations: `backend/src/researchassistant/agents/v2_reviewer_ledger.py:119–134,204–230,396–423`.

The retained Phase-10 Reviewer bridge writes its immutable Ledger admission before its source checkpoint. On restart it reuses the completed Reviewer decision but constructs fresh review/admission timestamps. The existing relational admission rejects those changed bytes, so this historical bridge cannot complete the interrupted operation. Ordinary fresh production uses analyzer admission instead; R34 repairs that separate current path.

**Reproduction:** directly invoke the historical bridge with its existing generated typed fixture, interrupt immediately after relational admission, and resume with the exact original Analyst result and an advancing UTC clock. It raises `IntegrityError: v2 Ledger admission is immutable` without new provider calls; the original admission stays unchanged. No real data or saved artifacts are edited. [Evidence](continued-review-evidence.json) preserves the exact probe and result.

**Proposed fix:** validate/reuse the original historical approval and Ledger record and commit its dependent source checkpoint safely. Preserve historical policy/class identities, timestamps, serialization and accounting; do not activate this bridge for new production research.

**Regression:** the historical interrupted prefix resumes without changing the existing admission or repeating a provider call; contradictory original records still fail closed. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R41 · P2 · Fresh quotation context still uses historical sentence splitting

Locations: `backend/src/researchassistant/evidence/evidence_core.py:246–258,342–367,691–704`; `backend/src/researchassistant/agents/v2_extraction.py:301–318`.

Fresh extraction correctly numbers sentences with decimal/URL/abbreviation-aware segmentation, but the quote assembler and bracket validator still split surrounding context at every period. They can strip a source limitation from the preceding bracket or cut a numeric threshold in the following bracket, then validate those fragments as the immediate surrounding sentences.

**Reproduction:** select the second sentence of a generated source whose preceding sentence excludes adults older than `65.5 years` and whose following sentence states a `0.5 mg` boundary. Fresh numbering preserves both sentences correctly. The actual assembler produces preceding context `5 years.` and following context ending `above the 0.`; the deterministic context validator accepts both. These are the functions invoked by fresh v2 extraction; no database/provider activity occurs. [Evidence](continued-review-evidence.json) retains the exact probe and output.

**Proposed fix:** version fresh quote-context assembly/validation to use the same exact sentence boundaries as fresh selection. Preserve historical candidate/context validation and serialized quotes, original hashes, quote-length/scoring policies and exact resume compatibility. Do not rewrite existing evidence.

**Regression:** decimal, URL, abbreviation, boundary and repeated-text cases retain the complete immediate surrounding sentences; historical quote bytes remain valid and truncated/mismatched context still fails closed. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R42 · P2 · Fresh sentence selection can move a quotation to an earlier occurrence

Locations: `backend/src/researchassistant/evidence/evidence_core.py:246–250,314–332,601–609`; `backend/src/researchassistant/agents/v2_extraction.py:301–318`.

The model selects exact numbered sentence ranges. Assembly extracts their text but discards the selected offsets and searches from the start for matching strings. If the same sentence occurs twice, the quote silently moves to the earlier occurrence and acquires that occurrence's different surrounding context. Subsequent deterministic filtering preserves that substituted occurrence because the assembled context matches it.

**Reproduction:** in a generated document, identical outcome text appears in the second and fourth sentences. Select sentence 4, whose preceding sentence says the second cohort includes all ages. The actual assembler instead attaches sentence 1's context, stating that the first cohort excluded older adults, and the wrong following sentence. No decimal/abbreviation splitting is involved, so this is distinct from R41. [Evidence](continued-review-evidence.json) retains the exact current-function probe/output; no database/provider calls occur.

**Proposed fix:** carry fresh sentence-range offsets through quote assembly and deterministic candidate filtering so the selected occurrence owns its context and quote identity. Version new behavior where needed, retain the existing historical text-selection/validation path, and preserve old quotes, hashes, scoring and length policies.

**Regression:** selecting the later of identical sentences retains its exact selected offsets and surrounding context, including multiple ranges; historical quotes and substituted-offset rejection remain unchanged. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R43 · P3 · Flattened “Materials and methods” headings are marked unknown

Locations: `backend/src/researchassistant/research/source_preview.py:376–396`.

The inline-heading detector recognizes “Materials and methods”, but its section mapping strips only the final plural suffix and looks up the wrong spelling. The actual method section becomes `unknown`, receives no methods-section ranking weight, and is reported as missing. The equivalent “Methods and materials” heading maps correctly.

**Reproduction:** build actual current previews for otherwise identical generated flattened scientific text. “Materials and methods” produces observed sections `conclusion, results, unknown`, lists methods as missing and labels the selected methods passage unknown. “Methods and materials” produces the expected methods diagnostic. [Evidence](continued-review-evidence.json) retains both results; no database/provider calls occur.

**Proposed fix:** normalize the explicitly supported heading aliases consistently and verify their actual preview sections/diagnostics. Preserve saved preview records, hashes, historical shapes and all ranking weights, budgets and evidence-admission policies.

**Regression:** all declared multiword methods-heading aliases map to methods in flattened captures, while reference headings remain excluded and historical saved previews stay readable. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R44 · P2 · A long scholarly author display silently stops ordinary follow-up research

Locations: `backend/src/researchassistant/research/seed_expansion.py:149–177`; `backend/src/researchassistant/common/discovery_identity.py:36–53`; `backend/src/researchassistant/contracts/discovery_v2.py:376–383`.

arXiv/PubMed adapters legitimately return comma-joined author displays. Seed conversion places that whole display into one 240-character identity label. A normal longer author list raises validation during optional seed offers, before the ordinary Search Agent can plan. The continuation catches it as `no_materially_new_query` and finalizes after Round 1, even though continuing material gaps remain.

**Reproduction:** actual generated production with OpenAlex/arXiv, valid DOI/year/article metadata and a 498-character arXiv-style author display returns released after only two initial search requests. The saved continuation records one completed round, `no_materially_new_query`, and `V2WorkIdentity authors.0 ... at most 240 characters`. No follow-up Search Agent/provider work occurs. [Evidence](continued-review-evidence.json) retains the exact generated offline probe/result.

**Proposed fix:** make seed identity conversion handle bounded joined-author metadata safely and isolate unrepresentable optional seed metadata from ordinary follow-up planning, with an explicit diagnostic. Preserve original metadata, identifier/title/year agreement, history and all provider/research budgets; do not silently truncate identity-bearing names or claim that a metadata error means no new query exists.

**Regression:** realistic long author lists do not suppress ordinary continuation; unusable seed metadata has an explicit per-seed outcome, valid alternatives remain eligible, exact identity checks and accounting stay enforced. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R45 · P3 · Fresh admission-only briefs use a historical Reviewer-approval warning

Locations: `backend/src/researchassistant/evidence/renderer.py:636–657`.

When balanced research lacks one direction, the shared renderer says no “Reviewer-approved” evidence was available. Fresh production admits Analyzer-validated evidence without a Reviewer, so this warning describes the historical approval method instead of the method actually used.

**Reproduction:** render a valid current `analyzer_admitted` record and strict synthesis in balanced mode with one missing direction. The real renderer emits `no Reviewer-approved opposing evidence was available`. [Evidence](continued-review-evidence.json) retains the exact offline rendering probe.

**Proposed fix:** use approval-method-accurate coverage wording for new output through an explicit compatible rendering/version boundary. Preserve the exact historical renderer/text used to validate every saved released hash; do not rewrite existing briefs or change admission policy.

**Regression:** fresh Analyzer-admitted output uses accurate admission wording, while historical Reviewer output and original released-text hashes remain valid under their recorded rendering behavior. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R46 · P2 · Native evidence browsing accepts source text that fails its saved snapshot hash

Locations: `backend/src/researchassistant/evidence/evidence_browser.py:224–285,345–368,423–448`.

The native evidence browser constructs current snapshot/candidate models without verifying their text hashes or exact source/candidate links. Only the separate August historical Ledger branch explicitly verifies a snapshot. A corrupted native snapshot can therefore appear in released-statement traces with the trusted-normalized-text label and no compatibility issue.

**Reproduction:** create an actual released native run with the existing fixture pipeline, alter only snapshot text in that disposable database, and restore every original trigger before inspection. The real read-only browser accepts both released traces even though both snapshot hashes fail; it reports no compatibility issues and labels the source text trusted. Inspection leaves the database bytes/mtime unchanged. No real research/database data is touched. [Evidence](continued-review-evidence.json) retains the exact probe and result.

**Proposed fix:** verify native source hashes, run ownership and exact candidate/Ledger/snapshot relationships before projecting trusted/released evidence. Report unsupported or corrupt records through the existing read-only compatibility boundary, preserving recognized historical quote policies, original records/hashes and noncreating reads. Do not apply fresh admission rules to historical inspection.

**Regression:** changed text/hash/owner or contradictory quotation links cannot appear as validated released evidence; valid native and historical trails remain readable with unchanged database bytes and batched bounded reads. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R47 · P2 · Same-family duplicates violate the retained retrieval outcome contract

Locations: `backend/src/researchassistant/agents/supportingresearcher.py:844–880`; `backend/src/researchassistant/contracts/retrieval.py:53–65`.

The retained retrieval path correctly recognizes two different captures as the same source family, but emits `DUPLICATE_CONTENT` together with `failure_code=duplicate_source_family`. The outcome validator permits a failure code only for failed/unsupported retrieval. Deduplication therefore raises validation instead of safely skipping the second capture. Ordinary fresh-v2 acquisition uses its separate path.

**Reproduction:** invoke the actual retained retrieval/deduplication functions with two generated captures at different URLs and one canonical DOI. The first capture is retrieved. The second raises `RetrievalOutcome ... failed or unsupported outcomes require exactly one failure code`, after two generated scrape calls. No database or external provider activity occurs. [Evidence](continued-review-evidence.json) retains the exact probe/result.

**Proposed fix:** produce a contract-valid same-family duplicate outcome, keeping its original snapshot link and explicit duplicate explanation without labeling it a failed retrieval. Preserve historical serialized outcome meanings and source-family deduplication policy; do not repeat acquisition or enlarge any work budget.

**Regression:** differing landing/PDF captures of one canonical source skip safely, distinct families remain eligible, and failed/unsupported outcomes still require their proper failure codes. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R48 · P2 · Native provider resume rebuilds already committed Reviewer timestamps

Locations: `backend/src/researchassistant/research/historical_execution.py:2440–2451,2675–2691`.

The retained native provider runner reuses a completed Reviewer model decision but rebuilds its `StatementReviewResult` with the restart clock. If interrupted after the original review row commits and before the analysis checkpoint completes, resume tries to persist the same review with a different timestamp and fails its immutable-record comparison. This native Phase-9 runner is separate from the Phase-10 bridge in R40 and current analyzer admission in R34.

**Reproduction:** run the actual retained runner with generated providers and an advancing UTC clock. Interrupt immediately after one native Reviewer row commits, then resume unchanged source/settings. It returns failed with `existing Phase 9 Reviewer decision differs from fixture artifact`, makes no new model/search/scrape calls and preserves the original row. [Evidence](continued-review-evidence.json) retains this exact production-entry probe.

**Proposed fix:** validate/reuse the original native Reviewer/admission records and timestamps when finishing partial analysis. Reject contradictory decisions, retain original rows and accounting, and preserve historical class/schema/approval identities and exact resume compatibility.

**Regression:** interruptions after review/admission commits finish without changing existing records or repeating providers; changed statements, owners or approval facts still fail closed. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R49 · P2 · Retained round deduplication forgets original/resolved URL mappings

Locations: `backend/src/researchassistant/research/historical_execution.py:1454–1469`; `backend/src/researchassistant/agents/supportingresearcher.py:516–552`.

The retained Governor seeds snapshot IDs into original/resolved URL sets but leaves the lookup mapping from original to resolved URL empty, and omits the snapshot's original URL alias. Retrieval requires that mapping before skipping a known URL. A subsequent round therefore fetches a previously captured source again and only marks it duplicate after the scrape returns, contrary to the helper's stated no-reacquisition behavior.

**Reproduction:** derive deduplication state from a real completed generated researcher artifact, then invoke ordinary retrieval for both the same original and resolved URLs. Each makes one generated scrape and reports `duplicate_url` with one attempt; both should be skipped before transport. The seeded mapping has zero entries. No database edits or external calls occur. [Evidence](continued-review-evidence.json) retains both aliases.

**Proposed fix:** reconstruct coherent original/resolved alias mappings from all completed snapshots needed by a retained round/resume. Keep existing source-family/hash identities and immutable research intact; skip known captures before transport without resetting or refunding accounting.

**Regression:** both URL aliases and completed-round resume prefixes cause zero duplicate scrapes, while genuinely new sources remain eligible and concurrent ownership/cancellation remain bounded. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R50 · P2 · Retained Governor ignores content duplicates in its duplicate rate

Locations: `backend/src/researchassistant/research/historical_execution.py:1535–1539`.

The retained Governor counts only `duplicate_url`, although its typed retrieval outcomes also record `duplicate_content` and the policy refers to known source-family duplication. Content duplicates disappear from the reported count/rate, so the duplicate-heavy stopping condition can be missed when the other budget/work conditions permit continuation.

**Reproduction:** derive the actual Governor input from fully typed generated researcher/analysis artifacts containing two retrieved outcomes and sixteen `duplicate_content` outcomes. It reports zero duplicates out of eighteen instead of sixteen. This uses the real derivation function without changing budgets, saved records or provider activity. [Evidence](continued-review-evidence.json) retains the actual status counts and derived values.

**Proposed fix:** count all applicable typed duplicate outcomes consistently when deriving new retained-run Governor facts. Preserve the existing stopping threshold, all budgets and recorded historical decisions; do not rewrite prior audit facts or relabel old policy payloads.

**Regression:** URL/content/mixed duplicate pools report the correct count/rate and enforce the existing threshold; unavailable/failed sources stay distinct and saved decisions/accounting remain unchanged. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R51 · P3 · Query-scaling benchmark fails after schema 18

Locations: `scripts/benchmark_database_query_scale.py:220–225,307–337`.

The benchmark creates a current database, then its schema-16 downgrade removes only migration 17 and the query indexes. Schema 18 remains recorded, leaving a gap in the migration history and the newer admission constraint. The read-only validator correctly refuses that fixture before the benchmark can compare any evidence queries or emit results.

**Reproduction:** run the unchanged benchmark from the current checkout. It exits 1 with `schema migration records are incomplete or inconsistent` at the first legacy-browser read and emits no JSON measurement. All databases are its disposable generated fixtures. [Evidence](continued-review-evidence.json) retains the command wrapper, full diagnostic and result; no provider or real database activity occurs.

**Companion regression gap:** `tests/test_database_upgrade_fixture_phase2.py:119–132` labels a case schema 16 but skips its downgrade. The actual case passes with schema 18 as its input. A second retained probe observes versions 14, 15 and 18 for the nominal 14/15/16 cases. Correcting and asserting the generated input version belongs in this fix’s regression scope. No current corpus or schema rule is changed.

**Proposed fix:** construct and validate a genuine recognized schema-16 fixture from current generated data, including the later admission-schema boundary, and migrate only its comparison copy forward. Preserve strict schema validation, the historical baseline and equal-output/query measurements. Never downgrade real research databases or discard round-four admissions.

**Regression:** the actual offline benchmark reaches measurements on current source; both before/after schemas are recognized, malformed histories remain rejected and generated data that cannot be represented historically is refused. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R52 · P2 · Older evaluation writers can destroy their frozen input and each other's output

Locations: `evaluations/source_discovery.py:579–597`; `evaluations/evaluator.py:1132–1145`; `evaluations/run_evaluations.py:35–50`.

The older source-discovery and Phase-10 commands still publish reports with unconditional replacement. Either accepts its input manifest/corpus as a report destination, destroys the input bytes and returns success. They also accept identical machine/human output paths, causing Markdown to replace the JSON report. These are separate entry points from the Prompt-14 writer repaired by R07.

**Reproduction:** invoke both actual commands with valid disposable copies of their frozen inputs and set JSON output to that same input path. Both return 0 and replace the input schema with their report. A third Phase-10 invocation using one path for both reports returns 0 with only Markdown left. Original repository corpora remain unchanged; all acquisition/seed work uses existing offline fakes. [Evidence](continued-review-evidence.json) retains the exact probe and outcomes.

**Proposed fix:** check all input/output identities and distinct output destinations before writing, including frozen regression evidence and symlink/hard-link aliases. Prepare reports fully and publish with a consistent collision-safe policy that preserves frozen inputs and prior evidence. Keep corpus semantics, scoring, historical bytes and provider permissions unchanged.

**Regression:** direct/alias input collisions, regression-artifact collisions, identical report destinations and partial publication failures preserve all original bytes; valid fresh output still produces matching JSON/Markdown and existing exit behavior. **Approved and implemented.** See [current verification](../../verification/full-review-fixes-2026-10-15.md).

### R53 · P2 · Scout repeats completed batches after a precommit interruption and resets its attempt cap

Locations: `backend/src/researchassistant/agents/v2_discovery.py:473–499,833–868`.

R38 fixes a committed ranking-only prefix. A separate interruption after Scout returns but before the stage pair commits leaves no saved batch decisions. Resume invokes the identical Scout prompt again, with its local attempt counter reset to zero. Repeated interruptions can exceed the existing two-attempt-per-batch limit. The global physical audit correctly retains each call and its exposure.

**Reproduction:** interrupt the actual generated production pipeline twice immediately before its first ranking/discovery pair commit, after successful Scout responses. Exact-source resume makes the identical first-batch prompt three times despite the configured two-attempt cap, then releases. Both earlier physical starts/completions remain present. No artifacts were edited and all providers/data are generated offline. [Exact probe](continued-review-evidence.json) preserves the observed prompt hash, counts and source bytes.

**Proposed fix:** persist the exact bounded Scout plan/input, each attempt and completed typed batch outcome under an explicit checkpoint identity. Resume reuses validated original batches and enforces the same total attempt cap across restarts; an unknown physical outcome retains its reservation and cannot silently repeat. Preserve existing ranking/fallback behavior, prompt bytes, budgets, historical artifacts and exact compatibility gates.

**Regression:** interrupt before aggregate commit, between batches and after provider/attempt writes; completed batches make zero replacement calls, repeated restarts cannot exceed two attempts, unknown usage stays reserved, malformed responses retain bounded retries, and altered batch input fails closed. **Approved; implemented, final verification in progress.**

### R54 · P2 · Fresh briefs label challenging or qualifying findings as direct supporting evidence

Locations: `backend/src/researchassistant/evidence/synthesizer.py:159–181`; `backend/src/researchassistant/agents/v2_final_output.py:1098–1100`.

The item template still follows Ledger stance/search direction. Fresh Analyst policy separately records a finding's relationship to the claim. For a Strong finding from a support-directed search, the renderer chooses “Direct supporting evidence” even when the admitted relationship is challenges or qualifies. The aggregate assessment and factual item consequently contradict each other within one validated release.

**Reproduction:** use actual deterministic synthesis/final validation with complete generated Analyst/admission records (Evidence Quality 4, Claim Fit 5), once challenging and once qualifying. Both releases validate. One says “Admitted relationships: 0 supports, 1 challenges, 0 qualifies”; the other reports one qualifying finding. Both factual items begin “Direct supporting evidence.” These are contract/presentation probes with offline model fixtures; they do not assert that the generated semantic judgment is factually correct. [Exact evidence](continued-review-evidence.json) preserves the cases and initial indirect-template diagnostic.

**Proposed fix:** bind fresh per-finding wording to its validated Analyst/admission relationship, keeping search direction as provenance and preserving required qualification warnings. Version rendering/validation so historical statements, templates and released hashes reproduce unchanged. Keep source text, scores, accounting and research budgets unchanged.

**Regression:** both search directions with supports/challenges/qualifies relationships produce consistent source labels and aggregate counts; altered relationship ownership fails closed, indirect/weak qualifications remain, and prior released outputs keep their exact text and hashes. **Approved; implemented, final verification in progress.**

### R55 · P2 · Gap Analysis repeats completed calls after interruption and resets its attempt cap

Location: `backend/src/researchassistant/agents/v2_gap_analysis.py:212–329`.

Gap Analysis retains its typed result and attempt list only in memory until the aggregate stage artifact is saved. A restart after a successful physical call but before that commit starts another two-attempt loop. Unlike R53's Scout batch path, this is the independent Gap Analysis stage and needs its own durable input/attempt/outcome recovery.

**Reproduction:** interrupt actual offline production twice after successful Round-1 Gap Analysis and before its stage commit, then resume unchanged source/inputs. The stage runs three times despite its two-attempt cap and the run releases. The non-budget inputs are identical; remaining-budget changes alter the prompts. All earlier physical starts/completions remain accounted and preserved. [Exact evidence](continued-review-evidence.json) retains the corrected probe and initial misspelled-key diagnostic.

**Proposed fix:** persist exact stage input and bounded attempts/results before aggregate completion; validate and reuse completed decisions on restart, keep the cumulative two-attempt cap, and reject unknown outcomes without repeating calls or releasing their reservations. Preserve existing gap policies, historical artifacts and accounting.

**Regression:** advancing-clock interruptions before/after outcome persistence reuse known results, unknown calls stay conservative, exhausted attempts remain exhausted, changed non-budget inputs fail closed, and completed historical artifacts remain readable. **Approved; implemented, final verification in progress.**

### R56 · P2 · Source Selection repeats completed calls after interruption and resets its attempt cap

Location: `backend/src/researchassistant/agents/v2_source_selection.py:395–478`.

The Source Selection pool/shortlist is saved before its model call, but the model result and attempt records stay in memory until the aggregate queue/status write. Interrupting before that write starts a fresh two-attempt loop on resume, even when the earlier physical call completed successfully. R53 and R55 repair separate Scout and Gap Analysis paths.

**Reproduction:** interrupt actual offline production twice after successful Source Selection and before the source-status aggregate commit, then resume unchanged source/inputs. The same prompt runs three times despite the two-attempt cap; the run releases. All three requests have identical full inputs and prompt hashes. Original physical audit entries and accounting remain preserved, and resumed search calls are zero. [Exact evidence](continued-review-evidence.json) retains the generated fixture probe.

**Proposed fix:** persist the exact bounded selection input, original budget/shortlist, attempts and validated recommendations before aggregate completion. Resume completed outcomes without new calls, retain a cumulative two-attempt cap and stop on unknown outcomes while preserving reservations. Reconcile the queue against original selection accounting and current durable admission ceilings without double charging or changing research budgets, ranking, historical output or resume compatibility.

**Regression:** advancing-clock success/failure interruptions before and after outcomes, zero-budget replay of completed selection, unknown reservation preservation, exact request ownership, exhausted attempts and unchanged historical queue serialization. **Awaiting approval.**

## Verification performed before fix approval

- Full local Python suite: **2,820 passed, 9 existing skips**, 258.11 seconds.
- Ruff lint and formatting: passed; 478 files already formatted.
- Repository root/import boundaries and staged/unstaged whitespace checks: passed.
- Frontend ESLint and TypeScript checks: passed, with incremental output disabled.
- Generated renderer API contracts: match the live backend schemas.
- Desktop shutdown unit suite: **20 passed**.
- Additional syntax/data scans: 480 Python files, 16 JavaScript files and 65 JSON files parsed successfully.
- Isolated reproductions: cross-run output/export, release-hash mismatch, DNS rebinding with fake sockets, round-four admission, standalone API lifespan, evaluation lineage/overwrite, trickling discovery transport, PDF deadline, Crossref identity mismatch, trail retry, active-run reconnection, external HTTP links and ranking cue normalization.

Existing tests passing does not invalidate the missing regressions identified above. The current Windows installer repair timeout remains unexplained and has not been rerun. Its interruption oracle still needs the retained root exit, partial tree and owned descendant exit evidence already required by HANDOFF. Physical power-loss, clean/minimum-OS acceptance and signing/notarization remain separate gates. None is represented as a new passing result here.

## Approval and implementation boundary

Original R01–R14 and the later R15–R26 fixes were approved and implemented with regressions; see [verification](../../verification/full-review-fixes-2026-10-15.md). R27–R30 are also approved and implemented with regressions. R31–R32 are approved, implemented and verified. R33 is implemented and verified; R34–R36 are implemented and verified; R37–R52 are implemented and verified. Storage migration, historical decoding, ranking and network changes retain their explicit compatibility boundaries. Executable/source changes require fresh research under the existing exact resume gate; historical data, policy meanings, released hashes and unknown reservations must not be relabeled or rewritten.

The literal every-line manual pass remains outstanding. Any continuation must use the inventory to record actual inspected ranges rather than treating these automated results or the prior seventeen implementations as completion of that request.
