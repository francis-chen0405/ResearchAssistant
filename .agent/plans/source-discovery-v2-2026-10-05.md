# Source discovery v2 — shared implementation record

Authorized scope: completed Prompt 1 foundations and Prompt 2 provider-aware query planning/compilation, within a six-prompt pack delivered one requested phase at a time. The user's subsequent “Review 2 and then commit if it's good” authorizes review corrections and a local Phase 2 commit after verification. Preserve the unrelated untracked proposal pack. Paid transports, credentials, real databases, installation, automation, push and publication remain outside this phase.

## Original Phase 1 specification and ownership

- `researchassistant.contracts.discovery_v2`: immutable strict contracts, explicit identities, query versus graph actions, metadata/candidate dispositions, exact snapshot previews, seed/edge provenance, counters, request reservations and compatibility binding.
- `researchassistant.research.discovery_capabilities`: versioned, conservative native/provider capability catalog with official provenance; adapters remain unchanged.
- `researchassistant.research.discovery_policy`: deterministic fair allocation, stable work grouping, effective depth and downstream model protection.
- `researchassistant.storage.discovery_store`: typed artifact registry, immutable checkpoints and atomic durable reservations in existing `v2_artifacts`; no migration or process cache.
- Existing policies, prompt bytes, public model contracts and historical fingerprints retain their original meanings. The new contract is opt-in foundation data; missing client settings mean historical runtime policy. Explicit new settings are bound separately and cannot resume an existing legacy run.

Policy ceilings: metadata depth 20 (configurable 1–50), physical pages/attempts per operation at most 3, raw retained candidates round/run 300/1,000, Scout round 60 bounded further by available model exposure, acquisition clusters round 25. Expansion seeds/hops/neighbors/run candidates 3/1/10/30. Caps are not promised allocations; provider and remaining run budgets dominate. Fair allocation uses stable direction/provider order, round-robin quotas, independent of arrival order.

Accounting: search, identity and neighbor pages use the same applicable provider physical-call/cost reservation. Durable starts precede transport, terminal records are immutable; unknown starts retain full exposure and cannot be replayed. A new attempt needs a new reservation and counts against the three-attempt logical bound. Existing model reservation owners remain `providers.v2_budget` and store route attempts; optional discovery planning must protect downstream calls/tokens/dollars first. No new model stage.

Trust boundary: metadata, ranks, previews and edges are discovery only. Existing acquisition → immutable snapshot → exact extraction → Analyst → admission is mandatory. Search direction never implies evidence relationship. Round 4 authorization and Round 1–4 lifecycle remain unchanged.

## Phase 1 acceptance tracking

Complete: live owner map, official capability evidence, typed contracts, store/accounting, focused regressions, review, Python full suite/lint/format/diff. Later phases must use the exact contracts and owners below. Runtime integration remains Phase 2–6 and requires each corresponding instruction.

## Live source map (Phase 1)

Initial planning is `agents/v2_initial_planner.py`; Round-1 physical search is `_run_round_one_search` in `researchassistant/research/v2_orchestrator.py`. Adaptive search execution is `agents/v2_adaptive_search.py::_execute_searches`. Both currently request five results and keep their existing policy. `agents/v2_discovery.py` owns normalization, clustering and twenty-item Scout batches. `agents/v2_acquisition.py` owns the existing 25-cluster limit, immutable captures and deterministic Probe; `agents/v2_source_selection.py` consumes only usable survivors. Existing per-provider ceilings remain SERP Search 12, Exa 18, OpenAlex 10, arXiv/PubMed 6; new pages and graph/identity calls count physically against those ceilings.

`ResearchControls.sources_per_stance_per_round` is the frozen source target used by historical acquisition and surfaced by API/desktop settings. It is not metadata depth. API/configuration owners are `frontend/api.py`, `frontend/live_contracts.py`, `researchassistant/runtime/cli.py`, `researchassistant/platform_support/desktop_settings.py`, `web/lib/api.ts` and `web/app/page.tsx`. None is changed in Phase 1. History/trail/status owners remain `frontend/live_history.py` and `frontend/live_progress.py`; new detached inspection is provided by the discovery store until Phase 6 connects presentation.

`V2ProductionFingerprint` and the current semantic-policy payload remain unchanged; a golden regression preserves their existing hash for fixed inputs. `repository_identity` already hashes recursive `researchassistant` sources, so the new contracts/helpers enter packaged source identity without widening or changing the historical fingerprint schema. The graph had stale root-module entries and no exposed `index_status`; refreshed through supported `index_repository` and verified live sources.

## Exact foundation inventory for later phases

Import directly from `researchassistant.contracts.discovery_v2`:

| Area | Contracts |
| --- | --- |
| Policy and capability identity | `V2DiscoveryPolicy`, `V2ProviderCapabilities`, `V2DiscoveryClientSettings` |
| Planning and physical action | `V2ConceptGroup`, `V2ConceptualQuery`, `V2SanitizedParameter`, `V2CompiledQueryAction`, `V2IdentityLookupAction`, `V2GraphNeighborAction`, `V2DiscoveryOperation` |
| Raw, grouping, ranking and outcomes | `V2SourceLocation`, `V2WorkIdentity`, `V2RawDiscoveryCandidate`, `V2RankComponents`, `V2NormalizedDiscoveryCandidate`, `V2CandidateDisposition` |
| Exact owned previews | `V2PreviewRequest`, `V2PreviewSpan`, `V2PreviewResult` |
| Seeds, work resolution and one-hop provenance | `V2SeedEligibility`, `V2WorkResolution`, `V2ExpansionEdge`, `V2ExpansionResult` |
| Frozen run identity and physical accounting | `V2DiscoveryBinding`, `V2DiscoveryProviderBudget`, `V2DiscoveryFailure`, `V2ProviderAttemptStart`, `V2ProviderAttemptCompletion`, `V2DiscoveryAuditCounters` |

All persisted top-level values derive from `V2DiscoveryArtifact`; immutable component values derive from `V2DiscoveryValue`. `artifact_id = discovery_id(run_id, concrete class name, identity_key)`. **Logical operation IDs are action artifact IDs**, not the wrapping `V2DiscoveryOperation` checkpoint ID. Parents, candidate response hashes and returned IDs must agree with durable provider attempts. Gap IDs retain the existing string identity and same-run/direction Gap ownership; they are not relabeled as UUIDs.

Version identities are `source-discovery-v2-2026-10-05-v1`, `source-discovery-contracts-v1`, `source-provider-capabilities-v1`, `source-query-compiler-v1`, `source-candidate-ranking-v1`, `source-claim-preview-v1` and `source-seed-expansion-v1`. Native capabilities and executable capabilities are separate. Exa's existing auto request is explicitly `provider_default`; OpenAlex's semantic switch is `semantic`. Planned native graph/lookup actions can explain pending/skipped work, but transport reservation rejects capabilities that current adapters cannot execute.

`discovery_policy` owns `fair_candidate_quotas` (retention, Scout and acquisition), `effective_metadata_depth`, `stable_work_key`, `stable_candidate_order`, `safe_optional_model_prefix`, `scout_candidate_capacity`, `discovery_contract_schema_hash` and `build_discovery_binding`. Raw-retention headroom constrains only retention; Scout and acquisition allocate existing candidates under their independent ceilings. The optional-work helper retains the eight-call downstream reserve and protects its conservative tokens/dollars before fitting a prefix of actual selected-route reservations. It is an affordability calculation: the existing `BudgetedV2LLMProvider` remains the durable model-call owner.

`discovery_store` owns typed dispatch/inspection, frozen binding, immutable operation/page starts and completions, raw/normalized candidate insertion, exact previews, seed/expansion insertion, work-resolution/disposition audit and derived counters. It reuses immutable `v2_artifacts` under `source-discovery-v1:`. No schema, table, index, dependency or prompt-byte change. Starts are committed under `BEGIN IMMEDIATE` before transport. Completions have immutable exact replay; starts never grant replay permission. Reservations match frozen per-request cost bases; unknown cost retains the reservation, and known cost above it raises retained exposure. The new recovery policy is explicitly **stop** after an unknown outcome; later recovery would need a separately versioned policy. A completed page cannot be requested again as an automatic retry.

Expansion counts unique work keys across relationships/providers for each seed and across the run, with eligible seeds deduplicated by work identity. Every eligible seed needs the stored usable snapshot and same-work location/identifier linkage. Previews require the exact persisted acquisition payload, matching cluster/snapshot/lane, exact submitted claim, hash, offsets and text/context. They remain selection metadata and cannot authorize evidence admission.

## Evidence and limitations

Focused tests cover contracts, capabilities, deterministic fairness/depth, model protection, fake physical reservations and races, ownership/replay/hash corruption, exact snapshots, global expansion bounds and historical fingerprint stability. One initial broad run lacked an isolated application-data override: existing API tests reached protected default-directory permission checks and failed before database access; sandbox blocked writes. Final verification uses a disposable `RESEARCHASSISTANT_DATA_DIR`. No actual provider transport, key read, real-user database mutation, installed-app replacement or release.

Phase 2 must compile provider-specific actions and activate only its completed query behavior; later phases own pagination/Scout integration, previews, expansion, and final UI/cross-phase acceptance. Offline fixtures prove boundaries and expected fixture behavior, not live research quality.

### Final policy clarification

The three-operation bound includes **all physical HTTP requests**, including retries and metadata subrequests. PubMed needs ESearch plus ESummary for one complete metadata page. `physical_requests_per_page=2` therefore permits one complete page under the three-request bound, with a remaining request available only for a bounded known failure. A metadata start explicitly binds `request_kind`, the completed primary attempt ID/hash, sanitized parameters and its own reservation. The six-request PubMed run ceiling is unchanged. Metadata-record counters count records in each physical response; unique-work candidates count retained grouping keys separately.

`executable_pagination` prevents a native capability from overstating current adapter depth. Current SERP Search supports one executable ten-result page, even though the native API supports later pages; an executable twenty-result operation is unavailable until the later adapter phase explicitly versions/declares pagination support. Requested depth stays separate from effective depth. `effective_metadata_depth(..., executable=False)` may inspect native potential but cannot authorize transport. Current opt-in bindings authorize only their declared providers/actions; an undeclared auxiliary metadata transport is unavailable and must be skipped rather than hidden behind normalization.

## Final Phase 1 acceptance

Target: macOS arm64 source, Python 3.12, fake transports/fixtures and temporary SQLite databases. Luna helpers owned capability research, initial store implementation and focused contract/store fixtures; Sol owned architecture/contracts/policy, integration and final review. Review corrected typed artifact identity lookup, exact snapshot linkage, grouped round/run limits, immutable response membership, read-only connection ownership, integer count validation, executable pagination and PubMed search/summary accounting.

| Requirement | Actual acceptance evidence |
| --- | --- |
| Bounds, immutable strict values, metadata unknowns, credentials, IDs, serialization, incompatible settings | `test_discovery_foundations_contracts.py` (39 tests), including fixed legacy fingerprint meaning and DOI syntax/normalization |
| Official native capability evidence and executable restrictions | `test_discovery_capabilities.py` (9 tests) |
| Stable fair quotas/order/grouping, effective depth, zero/near-exhausted model capacity and downstream reserve | `test_discovery_policy.py` (23 tests), including downstream allocation at exhausted raw-retention caps |
| Atomic reservation races, unknown interrupted starts, immutable replay, provider cost exposure, corruption and old-run binding | `test_discovery_store.py` (6 tests) |
| Cross-run/response membership, exact owned previews, seed linkage and global expansion caps | `test_discovery_store_acceptance.py` (7 tests) |
| Compiled JSON/fingerprint round trip, three physical pages, cumulative depth, read-only old/new history, PubMed subrequests, native/executable pagination, credential-bearing work IDs | `test_discovery_integration.py` (7 tests) |
| Later-round snapshot lookup, distinct query/path-case/port URL identities, failed unknown-attempt audit consistency | `test_discovery_review.py` (5 tests) |

The original implementation's 82 focused tests were included in its isolated full suite: **1,879 passed, 3 existing skips in 97.05 seconds**. `.venv/bin/python -m ruff check .`, `.venv/bin/python -m ruff format --check .` and tracked/new-file diff whitespace checks passed. No frontend/desktop checks were required because those surfaces are unchanged. The graph was refreshed after the final additions without writing a persisted graph artifact. No dependency, schema, migration, current public contract or executable prompt-byte changes; no live quality claim. Phase 1 has no remaining required foundation/accounting TODO.

## Conditional-commit review

Sol reviewed the shared contracts, accounting and integration boundaries hands-on, with Luna helpers independently reviewing storage and policy/contracts and running verification. Five issues were corrected before delivery: earlier acquisition outputs no longer mask a matching later-round snapshot; seed URL matching preserves work-defining query values, path case and ports; failed requests with unknown outcomes are reported consistently with the execution stop policy; raw-retention exhaustion no longer blocks Scout/acquisition of existing candidates; and verified DOI contracts reject malformed identifiers with shared normalization for grouping.

Fourteen additional cases bring discovery-focused coverage to **96 passing tests**. Native-only graph/identity action contracts remain valid for planned pending/skipped outcomes; durable reservation still rejects those actions unless the frozen capability explicitly permits execution. No production call sites import the new discovery owners. The archived prior-state files were checked byte-for-byte against the previous commit. The proposal pack remains untracked by the prior scope instruction; this review authorizes only the Phase 1 source and supporting records for a local commit.

Final isolated macOS/Python **3.12.14** verification after the corrections: **1,893 passed, 3 existing skips in 101.94 seconds**; focused tests **96 passed in 1.68 seconds**. Full Ruff lint and formatting checks passed (**231 files**); staged and working-tree whitespace checks passed. The advisory graph was refreshed without persistence after the source additions and conclusions were verified against live source/tests. No schema, dependencies, executable prompts, frontend or desktop surfaces changed. Delivered as a local conditional-review commit; no push or installation.


## Phase 2 implementation and ownership

Fresh production planning uses concept-only successors `v2_initial_planner_v2.md` and `search_agent_v2.md` through the existing selected Planner/Search Agent stages. The strict output owns only bounded phrases, at most three aliases per group and optional method/outcome groups. Application-owned initial lanes and adaptive lane indices retain providers, directions, round numbers, strategies, query IDs and original Gap IDs. Initial broad searches avoid optional narrowing; explicit gap/method/outcome queries add bounded evidence concepts. Exact submitted claims remain unchanged; fresh claim-component focus requires exact substrings. The Search Agent's existing two-attempt repair owner returns precise schema/compiler/novelty feedback and never issues another search to fill a rejected slot.

`researchassistant.research.query_compiler` owns deterministic single-page native syntax, validation, executable capabilities, canonical fingerprinting and conceptual/mode novelty. `query_execution` is the shared Round-1/adaptive/Round-4 executor and freezes query compiler **v2**, executable capabilities **v2**, successor prompts/schemas, query modes, provider configuration, source identity and effective budgets. `providers.discovery_transport` exposes scoped physical request observations to this owner. `discovery_store` retains the durable immutable artifact/reservation owner; no table, migration or dependency is added. `ResearchDirection(s)` moved to a dependency-independent contract module with its historical exports unchanged.

All five configured adapters send the actual compiled parameters. OpenAlex semantic mode uses `search.semantic`, lexical mode uses `search`; both current documented prices are $0.001 per request with distinct frozen mode identities. No paid rerank, filter/lookup, semantic fallback or hidden Exa fallback is enabled. Default production remains lexical OpenAlex; deliberate programmatic `query_modes` selects semantic. Ordinary client mode controls belong to Phase 6. Exa uses natural intent and `type=auto`; SERP uses bounded quoted/OR phrases and verified `exact_match=true`; arXiv uses explicit title/abstract fields; PubMed uses `[tiab]` and separately reserves ESearch/ESummary. No configured Serper adapter exists; unsupported Serper/modes are rejected before transport.

Every observed physical request matches its compiled owner/parameters before reservation. PubMed metadata IDs must come from its completed primary response, with parent attempt/hash linkage. Parameters persisted in the audit omit secrets. URL/query/encoded length, syntax/control characters, ambiguous bare acronyms, normalized aliases and declared modes are checked before transport. Cancellation is typed and checked before each request; HTTP deadlines remain bounded. Known 429/502/503/504 failures can retry within the three-physical-request operation bound only when cost is known; PubMed allows at most two primary attempts to leave capacity for summary. Unknown outcomes are never retried or refunded. Reported OpenAlex/Exa cost is parsed exactly; absent cost stays unknown and exposure remains reserved. Configured tighter OpenAlex ceilings are retained; physical counts, retries and summaries constrain adaptive lane allocation. Existing provider ceilings remain 10/6/6/18/12 for OpenAlex/arXiv/PubMed/Exa/SERP respectively.

Historical prompt files retain their bytes and explicit legacy planning dispatch remains covered by the original regression fixtures. Old optional `compiled_query=None` artifacts retain their meaning. The legacy production fingerprint payload/golden hash remains unchanged; fresh execution also requires the new immutable binding and source/prompt/schema identity. Incompatible mode/configuration/source resume requires a fresh run. Completed history stays readable. Round 1–4, Round-4 Governor authorization, no Round 5, challenge-only behavior, independent acquisition/snapshot/extraction/Analyst/admission and final release gates are exercised by the fresh fixture pipeline.

### Documented compiled examples

Official URLs and verification dates **2026-10-06/07** are recorded in [provider reference](../../docs/source-query-provider-reference.md). Prices are bounded policy inputs, not guarantees of future upstream behavior.

| Lane | Representative compiled request |
| --- | --- |
| ALPR crime, OpenAlex lexical | `search=("automated license plate readers" OR "ALPR" OR "license plate recognition") AND ("crime investigation")`, `per_page=5` |
| ALPR discrimination, OpenAlex lexical | Same technology group `AND ("racial discrimination" OR "disparate impact")`; no exclusions of null/challenging results |
| OpenAlex semantic | `search.semantic=automated license plate readers (also called ALPR, license plate recognition); crime investigation`, `per_page=5`; no Boolean/filter/rerank parameters |
| arXiv | `(ti:"automated license plate readers" OR abs:"automated license plate readers" OR ti:"ALPR" OR abs:"ALPR") AND (ti:"crime investigation" OR abs:"crime investigation")`, `start=0`, relevance descending |
| Biomedical PubMed | `("maternal health"[tiab] OR "pregnancy care"[tiab] OR "obstetric care"[tiab]) AND ("hypertension"[tiab])`, `db=pubmed`, `retmode=json`, `retmax=5` |
| Normative Exa | `school zoning policy (also called school attendance boundaries); community debate (also called local public discussion)`, `type=auto`, `numResults=5` |
| Normative SERP | `("school zoning policy" OR "school attendance boundaries") ("community debate" OR "local public discussion")`, `page=1`, `exact_match=true` |

### Phase 2 acceptance evidence

Luna helpers owned official-doc research/adapters, conceptual handoffs and fixtures, production fixture construction and independent review. Sol owned compiler/execution architecture, budget/trust-boundary decisions, critical integration, source review and final acceptance. Review corrected adaptive wrapper ownership, Round-4 request unpacking, physical budget headroom, lower configured limits, Exa reported costs, exact native parameter ownership, PubMed returned-ID bounds, metadata counts, non-2xx handling and durable failure classification.

| Requirement | Evidence |
| --- | --- |
| Strict concept-only schema, disabled lanes, bounded aliases, compiler syntax/Unicode/quotes/length/acronyms/modes | `test_v2_query_planning_contracts.py`, `test_query_compiler.py`, initial/adaptive Planner regressions |
| Actual native request payloads for all five configured providers | `test_v2_compiled_provider_parameters.py` with mock HTTP transports |
| Genuine semantic Round-1 execution, adaptive compiler use, physical PubMed pairs/retries/cancellation/caps/configuration | `test_query_execution.py` with durable temporary database audit |
| ALPR crime/discrimination, biomedical and normative web queries; tighter OpenAlex limits and reported Exa cost | `test_query_acceptance.py` |
| Two-attempt repair, conceptual duplicates/trivial proposals, mode novelty, preserved Gap/round ownership | `test_v2_phase7_adaptive_search.py` and reliability regressions |
| Fresh full lifecycle, Governor-only Round 4, compiled queries in each round, challenge-only admission, terminal read/restart and frozen mode mismatch | `test_query_production.py`; retained legacy production fixtures remain explicit |
| Historical contracts/fingerprints/accounting and downstream model/source limits | Full existing suite, including Phase 1 foundation/store tests and fixed production hash regression |

The conditional review established a baseline of **1,951 passed, 3 existing skips in 110.49 seconds**, with disposable application data on macOS arm64/Python **3.12.14**. Resume review corrected relational-projection comparison so the complete compiled artifact is retained and native relational fields still agree. Verification uses only fixtures, mocked transports and temporary databases. Offline results do not prove live research quality. No frontend/desktop surfaces changed, so their builds are not required for this phase. Retrieval depth/pagination/ranking and Scout allocation remain Phase 3; exact previews, seed expansion and product mode/settings presentation remain later authorized phases. This phase retains ordinary five-result query requests and introduces no additional acquisition or research round.

### Phase 2 conditional-commit review

Sol reviewed the implementation hands-on with Luna helpers independently reviewing contracts/storage and running verification. Corrections made before commit:

- A legacy selector cannot bypass a fresh run's immutable query binding, even when its cached terminal result exists; historical unbound dispatch remains covered. Valid reordered legacy Planner responses retain their original order.
- Semantic and Exa natural-intent queries describe optional method/outcome alternatives as evidence context, reserving “also called” for actual aliases. Explicit empty modes are rejected rather than defaulted.
- Compiled native requests require the scoped durable execution owner. Fresh compiler-bound runs reject an uncompiled request before calling an adapter. Historical unbound requests retain their adapter path.
- OpenAlex semantic starts are spaced at least one second apart per adapter instance, including known retries. Cancellation while waiting is checked before durable reservation. Actual send-start timestamps preserve spacing despite variable reservation latency. Separate adapters or processes sharing an account are outside this limiter.
- Round-4 query allowance counts complete logical PubMed queries from physical request headroom; three available requests yield one query, while one request stops before constructing a fresh planning contract.

Regression evidence is in `test_query_review.py`, `test_query_transport_review.py`, `test_query_round_four_review.py`, compiler tests and native-parameter fixtures. Focused review checks passed: **37 transport/execution tests**, **8 acceptance/production tests**, **101 Round-4/production tests**, and **15 resume/initial-planning tests**. These groups overlap and are not an aggregate count. The advisory graph was checked and refreshed; after a degraded integrity result, its supported rebuild succeeded without persistence (**6,385 nodes / 47,142 edges**). Live sources, diffs and tests remained authoritative. Prior-state archives match the preceding committed bytes; proposals remain untracked.

The first final full run found missing annotations in new test helpers (**1,968 passed, 3 skipped, 1 failed**). Explicit helper types were added without changing application behavior; the repository type-contract test and both affected suites then passed **18 tests in 1.67 seconds**. Final native-parameter review also restored explicit SERP phrase/Unicode/page/verbatim assertions. Whole-repository Ruff lint and format passed (**245 files**).

Final isolated full verification after all corrections: **1,969 passed, 3 existing skips in 109.05 seconds** on macOS/Python **3.12.14**. The skips are the explicit-approval CLI fixture, optional LLM integration and native Windows ACL verification. Full Ruff lint/format and staged/working-tree whitespace checks passed. All 53 staged files belong to Phase 2 and its supporting records; proposals remain excluded. Delivered as the user-authorized reviewed local commit, without push or installation. No remaining required Phase 2 correction was identified; offline verification does not establish live retrieval quality.
