# Prompt 13 — backend responsibility splits

## Scope and review boundaries

Completed locally as five sequential changes: adaptive search, Round 4, storage,
stage contracts, then historical execution isolation. Each owner passed focused
tests, the full Python suite, Ruff lint/format and both whitespace checks before the
next owner changed. Only mechanical moves, compatibility exports and explicit dependency
forwarding were made. Policies, quotas, SQL/migrations, prompts, UI and saved data
retain their original behavior and bytes. File sizes are review navigation, not
evidence of research quality improvement.

The starting checkout was dirty `master` at `94a241b`. No branch switch, staging,
commit, fetch or push occurred. The original staged binary diff is byte-identical.
Exactly the five original backend owners below changed; all other original backend
Python files match their starting bytes. Twenty-seven responsibility owners were
added. Original sources, staged diff, resource/identity snapshots, AST comparisons and
per-step logs remain under `/private/tmp/researchassistant-prompt13/`. Exact prior
guidance is retained in the [archive](../archive/2026-10-11-hotspot-split-state/README.md).

The graph was checked/refreshed before discovery and after moves. Traces covered
adaptive continuation, Round 4, portfolio persistence, model accounting, initial
planning and historical execution. The final named index is ready at the unchanged
HEAD. Live imports, original source, diffs and tests verified graph findings. A Luna
helper performed read-only inventory/source comparisons; the parent implemented and
verified each move.

## Ownership

Paths below are relative to `backend/src/researchassistant/`.

| Former owner | Before → retained path lines | Responsibility owners |
| --- | --- | --- |
| `agents/v2_adaptive_search.py` | 2,247 → 1,114 | `adaptive_planning` (914): planning/repair/novelty; `adaptive_execution` (265): physical execution/checkpoints; `adaptive_summary` (268): summaries/merging/completion; `adaptive_handoffs` (298): typed state/keys. Retained path owns budget-aware continuation and exports. |
| `agents/v2_round_four.py` | 1,774 → 674 | `round_four_authorization` (294): Governor/reservations/terminal authorization; `round_four_planning` (297): accepted requests/plans; `round_four_reconciliation` (417): admitted-evidence reconciliation; `round_four_summary` (452) and `round_four_handoffs` (134). Retained path owns bounded scheduling and exports. |
| `storage/store.py` | 3,218 → 1,309 | Connection/read-session boundary and typed compatibility wrappers remain here. Aggregate responsibilities are mapped below. |
| `contracts/model_research.py` | 2,569 → 418 | `research_policy` (154), `research_planning` (633), `research_discovery` (335), `research_acquisition` (269), `research_coverage` (298), `research_gaps` (490), `research_round_four` (243), `research_selection` (455), `research_historical` (142). Retained path is a compatible export facade. |
| `research/orchestrator.py` | 3,735 → 7 | Whole executor isolated in `historical_execution.py` (3,817 including compatibility metadata). Both old imports alias that module, preserving one globals namespace. The state machine was not reduced or internally sliced. |

The adaptive wrapper passes the currently replaceable artifact writer into planning.
The Round-4 wrapper passes the currently replaceable request builder/plan assembler.
Typed dependencies preserve crash injection, cancellation between requests and
empty-plan tests. Scheduling, reservation arithmetic, protected continuation, hard
Round-4 ceiling and absence of Round 5 are unchanged.

Stage-contract dependencies are acyclic. Shared Gap/claim identity and continuity
validators belong only to `research_coverage`; identities/caps belong only to
`research_policy`. No stage owner imports the facade, execution, agents or providers.
Validators/serializers move with their owning models.

## Storage transactions and recovery

| Owner | Lines | Boundary retained |
| --- | ---: | --- |
| `portfolio_transactions` | 310 | Portfolio/source-family/evidence-trail batch in one immediate transaction, including rollback, partial projection repair and replay timestamps. |
| `evidence_transactions` | 855 | Snapshot, quote, Analyst, Ledger, draft/review and synthesis integrity operations with original same-run checks and connection scopes. |
| `v2_transactions` | 611 | Immutable v2 writes, initial-plan/query/artifact aggregate and terminal-artifact/manifest aggregate; internal connection-scoped inserts stay with these transactions. |
| `model_accounting_store` | 434 | Serialized reserve/finish accounting, one-winner concurrency, exact replay/conflict rejection and conservative unknown exposure. |
| `legacy_planning_store` | 222 | Historical planner, search/retrieval aggregate and provider-contract persistence. |
| `run_state_store` | 276 | Manifest, bounded historical rounds, Governor state and cancellation. |
| `checkpoint_store` | 239 | Stage artifact/checkpoint persistence with original replay/commit behavior. |
| `store_types` | 122 | Shared reader types, errors and codecs; historical class qualification preserved. |

The 66 I/O wrappers keep old signatures/defaults and resolve `store._connect` and
`store._read_connection` at call time. Operations receive typed factories explicitly;
they never import the facade or share connections between workers. Factories are
forwarded across helper/delegation calls where required. No original BEGIN, SQL,
commit, rollback or close sequence changed. Schema/migration/backup owners were not edited.

Semantic checks cover late portfolio rollback, terminal manifest failure rollback,
interrupted terminal repair without new calls, initial-planner rollback, conflicting/
identical concurrent finishes, one-winner reservations, unknown usage retention,
verified backups, failed migration retry, schema 7–17 reads, caller-owned snapshots
and historical Markdown/PDF exports.

An old test inspected reader-body locations inside `store.py`. Its replacement invokes
every public path reader, intercepts the shared boundary, requires the exact source
path and proves a never-created database stays absent. Existing byte/mtime, snapshot
ownership, corruption and schema assertions remain.

## Public compatibility and identity

The fixture retains **116 public class expectations**: **102 schemas/configurations**,
**12 enum mappings** and **2 historical exception identities**. Exports resolve to the
same class objects; moved classes retain historical `__module__` and pickle class
round trips. Installed `models`, `store`, `orchestrator` and agent aliases remain
compatible. All original public names remain; historical execution preserves every
original top-level statement and export.

**360 original class/function bodies** have exactly one owner: adaptive **46**, Round 4
**34**, storage **103**, contracts **102**, historical **75**. AST bodies match, with only
explicit dependency arguments/call names normalized for the forwarding seams/factories.
Original constants, validators and serialized-field definitions retain values/order.
Behavioral tests cover exact JSON, omitted historical defaults, immutable release hashes
and recognized saved-policy dispatch.

Fresh processes resolve all nine stage contract groups with execution/agents/providers
blocked. History/API/CLI inspection, trails, browsing and exports block **all three**
historical executor names, including the new owner, on both August fixtures. Database
bytes/mtime and release hashes remain unchanged. Explicit legacy execution and its
module-global replacement seams still work.

All **18** prompts, **3** font/license/README resources and the prompt marker retain
original SHA-256 values. Intended source-path/content identity changed from
`source-sha256:3768f41771f0fe210ceda310b7867b7963df52c9c8ec1a549b5aec63dc2a577f`
to `source-sha256:4a9ce91342ff8933f7942d83dced1cd70b56f77ac80eac017e6a632aab5b2dc4`.
No fingerprint policy or stored fingerprint was rewritten. A fake-run regression
persists the recorded pre-split identity and proves current-source resume rejects it
before provider calls or database byte/mtime changes. Such runs require a new ID.

## Verification

Checks ran on **macOS arm64 / Python 3.12.14**, using isolated data/fake providers.

| Step | Focused | Full Python | Ruff/format/whitespace |
| --- | ---: | ---: | --- |
| Adaptive search | 308 passed | 2,549 passed, 5 existing skips | Pass; 426 files |
| Round 4 | 257 passed | 2,549 passed, 5 existing skips | Pass; 431 files |
| Storage | 519 passed | 2,549 passed, 5 existing skips | Pass; 439 files |
| Stage contracts | 474 passed | 2,558 passed, 5 existing skips | Pass; 448 files |
| Historical isolation / final source | 419 passed | **2,565 passed, 5 existing skips** | Pass; **449 files** |

Both staged/unstaged whitespace passed after every step. The first adaptive full run
had one ten-second CLI subprocess timeout after its expected invalid-input diagnostic;
the isolated test and unchanged full-suite rerun passed. No assertion/timeout was
weakened. All subsequent per-owner suites pass. Final collection: **2,570 tests**;
final full run: 235.03 seconds.

- Both offline evaluations pass: **38** integrity cases and **6** synthetic discovery
  scenarios. Live comparison is disabled; no new research-quality claim follows.
- Exact **293-file** wheel bytes and fresh wheel/editable installs from unrelated
  directories pass: aliases, equal source identity, credential-free API, released/
  blocked fixtures, three-page PDF and fresh/replayed discovery bindings.
  [Wheel inventory](backend-hotspot-split-2026-10-11-wheel-files.txt).
- Generated renderer API types match live schemas; root/dependency/type boundaries
  pass. No renderer implementation or dependency lock changed.
- Desktop **20 unit checks** pass. Native POSIX shutdown covers normal/stuck/startup
  and six actual-manager handoff/crash cases. Real Electron startup-stall/deadline
  cleanup passes with the accelerated test clock. The initial sandbox attempt could
  not execute `ps`; rerunning with process inspection access passed without changes.
- `desktop/build.py --backend-only` rebuilt with PyInstaller 6.22.2, retaining existing
  frontend/Node/acquisition/browser resources. Frozen backend SHA-256:
  `94c047460129204e8bd3d1ffa6f2479ed3f545f6d4254090b340fee95840209d`.
  `desktop/smoke.py desktop/build/resources` passes authentication/origin protection,
  durable preferences/restart identity, uniquely named native-vault cleanup and owned
  Wigolo start/stop, without Python/Node on PATH. `desktop/ui-smoke.cjs` passes the real
  window, seven empty credential fields, browser/Node isolation, duplicate exclusion
  and normal shutdown against this backend. Native checks used required loopback/
  process/test-vault access outside the sandbox. All **288** bundled source/resource
  payloads byte-match the current canonical packaging manifest.

Logs, reports, original snapshots and install environments remain under
`/private/tmp/researchassistant-prompt13/`. No paid call, real database mutation,
installed-app replacement, installer or public release occurred.
[STATUS](../project/STATUS.md) owns current verification/installed-build provenance.

## Remaining oversized owners and deferrals

| Owner | Lines | Reason to retain this boundary now |
| --- | ---: | --- |
| `research/historical_execution.py` | 3,817 | Inactive, explicitly selected legacy state machine. Deeper slicing risks coupled restart/routing/cancellation and globals seams. Inspection is separately isolated/tested. |
| `storage/store_schema.py` | 1,896 | Ordered schema/migration/verification owner; SQL/migrations are outside this mechanical split. |
| `storage/discovery_store.py` | 1,655 | Immutable binding/physical-attempt lifecycle across artifacts needs separate aggregate/transaction review. |
| `contracts/model_contracts.py` | 1,586 | Widely shared base/legacy surface needs its own staged schema inventory. |
| `research/v2_orchestrator.py` | 1,556 | Ordered production stage/replay coordinator needs separate review. |
| `agents/v2_acquisition.py` | 1,181 | Capture/Probe/fallback and immutable snapshot identity are coupled. |
| `research/query_execution.py` | 1,176 | Reservation-before-I/O, pagination/replay and unknown outcomes need separate review. |
| `agents/v2_final_output.py` / `contracts/model_evidence.py` | 1,168 / 1,166 | Release provenance/terminal gates and evidence schemas need their own compatibility boundary. |
| `agents/v2_discovery.py` / `agents/supportingresearcher.py` | 1,038 / 1,013 | Discovery/admission and retained retrieval orchestration were outside these owners. |

`storage/store.py` (1,309) and `agents/v2_adaptive_search.py` (1,114) remain large partly
because they preserve typed signatures/broad exports. Their retained responsibilities
are connection/session ownership and budget-aware continuation. Transaction/planning/
physical-execution bodies each have a single extracted owner. Further facade compression
would not itself improve those boundaries or research quality.

Next is source review/commit or separately authorized platform/delivery work. Python 3.11,
Linux, native Windows/Jobs, current installers, clean-machine/minimum-OS acceptance and
signing/notarization were not rerun. The installed October 9 app was not replaced;
paid quality acceptance remains under its existing exhausted allowance.
