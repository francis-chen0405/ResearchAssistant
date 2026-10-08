# Source discovery v2 — shared implementation record

Authorized scope: Phases 1–5 of the six-phase source-discovery pack, delivered one requested phase at a time. Phases 1–4 are committed locally; Phase 5 is implemented in the current uncommitted source. Phase 6 product controls and final cross-phase acceptance remain the next boundary. Preserve the unrelated proposal pack and restored compatibility files. Paid transports, credentials, real databases, installation, automation, commit, push and publication are outside this Phase 5 request.

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

Initial planning is `agents/v2_initial_planner.py`; Round-1 physical search is `_run_round_one_search` in `researchassistant/research/v2_orchestrator.py`. Adaptive search execution is `agents/v2_adaptive_search.py::_execute_searches`. Phase 2 established five-result searches; Phase 3 now freezes independent metadata depth and uses the per-provider page sizes and effective caps recorded below. `agents/v2_discovery.py` owns normalization, clustering, deterministic ranking, typed sidecars and bounded Scout batches. `agents/v2_acquisition.py` owns ranked cluster shortlisting, immutable captures and deterministic Probe; `agents/v2_source_selection.py` consumes only usable survivors. Existing per-provider operation ceilings remain SERP Search 12, Exa 18, OpenAlex 10, arXiv/PubMed 6; new pages and graph/identity calls count physically against those ceilings.

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

Phase 2's provider-specific query behavior remains active. Phase 3 now owns deeper retrieval/pagination, deterministic ranking and bounded Scout/acquisition integration. Phase 4 exact previews remains the next boundary; later phases own expansion and final UI/cross-phase acceptance. Offline fixtures prove boundaries and expected fixture behavior, not live recall or research quality.

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

## Phase 3 implementation — deeper retrieval, ranking and bounded acquisition

`query_execution` freezes desired metadata depth independently of the historical source target and carries a durable per-page checkpoint. Fresh policy defaults to 20 results and permits a requested depth through 50. Every page and physical retry is observed by the owning adapter and reserved before transport; no operation can exceed three physical attempts, including retries and provider metadata subrequests. Known failures may use only the remaining bounded attempts; unknown outcomes retain exposure and are terminal for that operation. Completed pages survive cancellation/interruption and resume without replay. An independently immutable parser receipt binds parsed response digests to the completed physical attempt/hash; checksum-valid substitution of page candidates is rejected. Repeated-cursor, no-new-result and short-page terminal checkpoints remain terminal even if result persistence is interrupted. Numeric Retry-After waits through five seconds are cancellation-aware; longer or unparseable delays terminate retries conservatively. Terminal partial/degraded results are cached as such, including malformed completed responses, so an uncertain or unusable page is not silently retried.

Executable depth is provider-specific and budget-bound. SERP Search follows up to three 10-result pages for requested depth 50. OpenAlex lexical and arXiv use bounded 20-result pages, allowing 20+20+10 under a three-page operation; OpenAlex semantic can request up to 50 in one physical request. PubMed needs ESearch and ESummary for each complete page, so the three-physical-request ceiling permits one complete metadata page. Exa auto search is capped at 25 pending enterprise entitlement. Default Exa depth 20 reserves $0.02/request; a policy depth of 50, still capped to 25 results, reserves $0.03/request. The existing $0.18 total and 18-request Exa ceilings remain in force; tighter remaining provider/run budgets always lower executable depth. See the [provider reference](../../docs/source-query-provider-reference.md) for official behavior and pricing sources.

Retained metadata is capped at 300 candidates per round and 1,000 per run; physical raw-hit counts remain distinct. Initial and adaptive execution give every enabled direction/provider lane a first pass before repeating a lane’s additional strategies, preserving scarce-lane access under retention caps. Both planners compile using the exact frozen metadata-depth policy, including explicit programmatic depth 50; ordinary product settings remain Phase 6. Deterministic metadata ranking is a sidecar over common, auditable signals (directness, method/gap fit, identity completeness, novelty and diversity), with rationale and stable work/lane identity. It is direction-neutral: search provenance remains attached to its enabled lane, while support/challenge relationship is not inferred from that direction. Unknown metadata remains neutral instead of being treated as a negative signal. Identity conflicts are retained visibly and do not imply independent studies. Ranking work keys use DOI/URL anchors. Existing clustering preserves its normalized-title/DOI/URL equivalence; source-family identity is unchanged. Fair ranked selection preserves lane coverage under a cap, stable ties and duplicate work grouping.

Scout may consider at most 60 items per round in adaptive batches of at most 20, with at most two model attempts per batch. Safe model exposure may reduce this further; every retained item receives a typed disposition explaining whether it was scouted or omitted by cap/budget. Ranked acquisition shortlisting is capped at 25 clusters per round and is further lowered by physical/provider and run budgets. Ranking, Scout decisions and shortlist results never auto-admit evidence: independent acquisition, immutable source snapshots, exact extraction, Analyst and deterministic admission remain mandatory. The exact-preview typed extension is available to source-selection input construction, with deterministic Probe preview as the fallback; activating exact model-assisted previews and validating their provenance is Phase 4.

Phase 3 adds offline fixtures for page checkpoints, retry/budget bounds, deduplication, malformed/empty/repeated pages, cancellation/resume, rank ordering, minority-lane fairness, acquisition integration, preview validation/fallback and no automatic admission. These fixtures test boundary behavior and generated examples only; no live provider call or claim about real-world recall/research quality is made. Final full isolated pytest, Ruff lint/format and diff checks passed; actual evidence is recorded below.

Implementation ownership: Sol owns policy/contract, physical budget/trust boundaries, execution/store integration, ranked acquisition, typed preview fallback and final verification. Luna helpers own bounded provider adapters/pagination, ranking/Scout integration, fixtures, independent review and supporting records. No new research-model stage, dependency or database schema was introduced. The subsequent clarified conditional-review instruction authorizes its reviewed local commit.

New audit counters distinguish physical raw hits, deduplicated work keys, actual Scout coverage, shortlisted clusters, fetched immutable snapshots, usable Probe survivors and Ledger admissions; physical acquisition attempts retain their separate historical audit.

### Phase 3 final acceptance evidence

Final macOS/Python **3.12.14** run after implementation/review corrections: **2,042 passed, 3 existing skips in 141.61 seconds**. `RESEARCHASSISTANT_DATA_DIR` pointed to a new disposable directory under `/tmp`; transports and databases were offline fixtures. The skips remain explicit-approval CLI, optional LLM integration and native Windows ACL verification. Whole-repository Ruff lint passed; formatting checked **262 files**; `git diff --check` passed. No frontend/desktop surface changed, so no frontend or packaging build was required.

Focused acceptance includes primary studies at engine ranks 12/18/20, duplicate pages/providers, empty/repeated cursors, partial malformed responses, unknown metadata, null/contradictory support-lane findings, scarce-lane retention and ranking fairness, bounded Scout prompts and complete two-attempt/model-input reservation, cancelled/interrupted/resumed pages, near-zero search/model budgets, 300-item operation-count guards, actual native paging arguments, and exact preview fallback/provenance. Exa fixtures verify the $0.02/$0.03 reservations and unchanged $0.18 total; checksum-valid page/result substitutions fail, and crashes after terminal checkpoints do not send another request. The independent parser receipt is a cross-artifact provenance check within the validated immutable database, not authentication of arbitrary replacement of an entire database.

An earlier unisolated run failed on protected default-application-directory permission checks before database access and four superseded compiler-version expectations; sandbox writes were blocked. Expectations were updated only for the deliberately versioned successor identity. Review also found missing fixture annotations, page-local SERP positions, deeper Exa pricing, final-page rank offsets, terminal resume handling, parser/page provenance, retention fairness and frozen-depth threading; these were corrected and the final full suite passed. Tests and synthetic fixtures are not live-quality or recall guarantees.

The advisory graph was checked and refreshed through the supported non-persisting full index (**8,593 nodes / 54,368 edges**); live source, diffs and tests remained authoritative. Pre-change current-state archives were verified byte-for-byte against preceding committed records. No dependency, schema/migration, research-model stage, paid-service call, real credential read, real-user database mutation, installation, automation, commit, push or publication occurred. Unrelated proposal files remain untouched. Next boundary: Phase 4 exact claim-aware previews, using the working typed selection extension and deterministic Probe fallback.


### Phase 3 conditional-commit review

The user clarified the conditional-review request as Phase 3. Sol personally reviewed frozen depth, compiler/policy identity, production/adaptive integration and protected Scout input reservation, with Luna helpers independently reviewing retrieval/persistence, ranking/acquisition and running verification. The review baseline passed **2,042 tests, 3 existing skips in 137.64 seconds** with isolated temporary application data.

Three issues were corrected before commit: historical Scout calls now preserve all author metadata while fresh ranked calls keep their bounded author input; fair lane allocation first retains the best-ranked representative for each duplicate work; acquisition clusters skipped by the existing fetched-URL guard receive the declared `duplicate` disposition instead of `unavailable`. Regression tests cover cross-lane/provider duplicate selection, scarce unique-lane access, permutation stability, legacy author preservation, shared alternate-URL skips and coherent acquisition counts. The three new review files plus repository type-contract verification passed **5 tests in 1.45 seconds**; broader focused ranking/Scout/acquisition groups passed **22** and **21** tests respectively (overlapping groups).

No retrieval defect was found: native paging, physical reservation/retry caps, cancelled/resumed checkpoints, unknown exposure, parser provenance and terminal replay behavior were verified against live source/tests. The existing arXiv and PubMed pacing guards were checked against primary provider documentation and retained. The advisory graph was refreshed without persistence after corrections (**8,643 nodes / 58,428 edges**). Prior-state archives match the Phase 2 commit bytes, including DECISIONS; unrelated proposals remain untracked. No dependency, schema, frontend, desktop, model stage, paid-provider call or real-data change was introduced by review. Offline fixtures establish synthetic behavior, not live recall or research quality.

Final isolated verification after review: **2,046 passed, 3 existing skips in 136.84 seconds** on macOS/Python **3.12.14**. Full Ruff lint/format (**265 files**) and staged/working-tree whitespace checks passed. Skips remain the explicitly gated live CLI smoke, optional LLM integration and native Windows ACL check. All **56** staged files belong to Phase 3 and supporting records; proposals remain excluded. Delivered as the reviewed local commit, without push or installation. Phase 4 exact previews remains the next boundary.


## Phase 4 implementation

Authorized by Prompt 4 on October 7, 2026. This phase adds exact claim-aware previews;
Phases 1–3 were verified against committed source and their focused regression suites.
The initial implementation instruction excluded commit, paid service, credential read,
real-user database write, installation and publication. The subsequent user instruction
authorizes the reviewed local commit; other boundaries remain. The proposal pack and
unrelated files remain untouched.

Ownership: Sol implemented contracts, current/historical dispatch, acquisition/selection and
Round 1–4 integration, fingerprint binding, complete actual-input reservation and shortlist
accounting, UI display, runtime regressions and final review. Luna High implemented bounded
preview construction and acceptance fixtures; Luna Medium implemented read-only trail
projection/tests. Their main work landed, but later helper turns hit a usage limit; Sol
completed algorithm/integration review and remaining verification without claiming that the
unfinished independent review ran.

`researchassistant.research.source_preview` selects contiguous exact windows from one
owned normalized snapshot using lexical aliases, observable sections, substantive methods,
results, statistical context and negative qualifications. Reference/chrome/error/instruction
fragments cannot dominate selection. Numbered/flattened headings, Unicode and PDF markers
retain exact offsets. Neighboring spans never bridge excluded material; long paragraphs use
bounded contiguous windows. Claim-relevance and capture-usability remain separate. No
length-based or section-based full-document verification is claimed: observed study sections
are partial captures, abstracts remain abstracts, and unobserved sections remain unknown.
A substantive source with no relevant window remains a survivor with neutral Probe priority.
Empty responses have failed-attempt reasons; shell/reference-only snapshots retain their
immutable failed Probe diagnostics. The existing quote-length gate remains.

Fresh production uses Probe **v3**, preview **v2**, Source Selection input policy **v2** and
successor `source_selection_v3.md`. Existing default/explicit Probe v1/v2 and selection-v1
paths, historical prompt bytes and old serialization remain unchanged. The pre-Phase-4
production schema fingerprint is frozen at its verified c942070 value; fresh executable
prompt/schema/policy/bounds are bound separately in the exact discovery fingerprint, and
repository source identity continues to prevent incompatible resume. No migration, new
model stage, provider or dependency is introduced; nested typed previews and the audited
shortlist use existing immutable `v2_artifacts`.

Bounds: five nonoverlapping spans, 1,200 characters each, 4,800 passage characters/source,
160 exact context characters on each side/span; at most 6 claim components/target gaps.
All spans validate offsets, text, hash/run/source/lane, ordering, overlap, omission markers
and truncation. Metadata ranks remain separate from preview relevance and final model
recommendation rationale. Extraction continues to receive the complete authoritative capped
snapshot, never a preview; Analyst/admission/independent axes/release invariants are unchanged.

Complete model input (including selected adapter overhead) is limited to **24,000 tokens**.
A deterministic complementary, direction-fair whole-source prefix fits the actual rendered
input; every omitted source has a typed input-cap disposition, remains in the full persisted
pool and deterministic queue priority, and appears in read-only trail diagnostics. No arbitrary
JSON truncation or silent source loss. Every actual selection attempt reserves the complete
input plus route output allowance, counts failures/retries, and protects one existing
60,000-token/three-call source envelope. The queue retains lower configured call ceilings.
Current/historical trail readers validate typed previews against acquired snapshots and show
capture/relevance diagnostics, metadata priority, selection rationale and input omissions.
Released-brief export continues to revalidate exact released output and excludes previews.

Acceptance evidence is recorded after final verification below. Offline fixtures establish
exactness and expected fixture selection only, not live recall or research quality. Next
boundary: Phase 5 seed-paper expansion within existing provider budgets and authorized rounds.


### Phase 4 final acceptance evidence

Target: macOS arm64 source, Python **3.12.14**, fake transports, disposable SQLite/application
data and isolated static renderer output. Final full suite: **2,086 passed, 3 existing skips
in 169.75 seconds**. Skips remain explicitly gated live CLI, optional LLM integration and
native Windows ACL validation. The focused new preview/contract/type group passed **80
in 2.73 seconds**. Existing acquisition/adaptive/selection/analysis/release/export groups
passed **196 in 29.07 seconds** (overlapping full-suite coverage). Desktop-specific checks
are included in the full suite and additionally passed **19 tests in 1.93 seconds**.

| Requirement | Evidence |
| --- | --- |
| Exact offsets/context/hash/run/snapshot forgery, bounded Unicode/PDF windows | `test_claim_source_previews.py`, `test_preview_structure_review.py` |
| RePEc abstract plus irrelevant numeric refs, below-opening study methods/results, null findings, text tables, DOI-only/chrome/instructions, short/truncated/empty/no-match | 25 deterministic construction fixtures across those two files |
| Actual current acquisition and rendered physical selection request exclude known bibliography while extractor text retains it; usability independent of relevance; failed captures inspectable; resume mismatch blocked | `test_preview_runtime.py` (6 tests) |
| Deterministic whole-source shortlist, complete omissions, selected adapter overhead plus output reservation, omitted-ID rejection, no-fit/budget fallback and protected lower ceilings | `test_preview_selection_bounds.py`, `test_preview_runtime.py` |
| Probe-v1/v2 and preview-v1 golden serialization hashes, unchanged historical selection prompt/fingerprint, old read-only inspection/export/release | Golden tests plus existing foundation/history/export/final-release regressions |
| Typed current preview/metadata-rank/selection-rationale trail, read-only database bytes/mtime unchanged | `test_preview_inspection.py` (3 tests), historical-read regressions |
| Round 1–4 fresh production release/restart without bypassing extraction/Analyst/admission/Governor | `test_query_production.py` plus full existing pipeline/admission/release suites |

Repository quality: a clean overlay of committed tracked files plus Phase 4 changes/additions
passed whole-tree Ruff lint and formatting (**272 Python files**); `git diff --check` passed.
Raw workspace Ruff reports three unrelated import-order issues in untracked legacy files
`desktop_settings.py`, `history_import.py`, `model_contracts.py`; those files appeared during
verification with older timestamps and were left untouched. Raw workspace formatting passes.
The source-quality distinction is explicit; no tests/validators were weakened. Initial
integration regressions exposed claim-component naming, the Round-4 context call site,
recommendation-rationale invariants and nested selection-policy dispatch; all were corrected
before the final full passing run. The earlier full run had one policy-dispatch failure and
2,079 passing cases; it is superseded by the final result.

Renderer ESLint and TypeScript pass. An isolated **Next.js 16.3.1 webpack desktop static
export** compiled, type-checked and generated all pages; `node --check desktop/main.cjs`
passed. Package-manager commands initially attempted unavailable registry/version checks;
verification used existing installed executables directly with no dependency changes. No
packaging installation, signed distribution or installed-app replacement was performed.

The graph was refreshed without persisted artifacts (**9,390 nodes / 60,268 edges**) and
reported ready at c942070; inbound tracing verified all three adaptive/Round-4 acquisition
call sites against live code. Prior STATUS/HANDOFF/ARCHITECTURE/DECISIONS/plan index archives
were verified byte-for-byte against the pre-change commit. The proposal pack and unrelated
untracked modules remain preserved. No paid transports, secrets, real databases, schema
migration, dependency/model-stage additions, automation, commit, push or publication.

Phase 4 acceptance is complete for source and offline fixtures. Phase 5 seed-paper expansion
is the next implementation boundary; Phase 6 retains final cross-phase/product acceptance.

### Phase 4 review corrections

The independent review reproduced two defects: ordinary unspaced Chinese study text was
marked non-substantive, and a checksum-valid selection preview could refer to another
source's acquired snapshot without a history compatibility warning. Sol corrected both
findings and personally reviewed the repairs against the original exactness, historical
identity and read-only boundaries.

Han-script preview usability now requires conservative character diversity and explicit
research vocabulary, with recognized Chinese methods/discussion headings. Literal bounded
claim components match unspaced text without translation or single-character relevance.
Research sections and unheaded prose remain usable independently of relevance; repeated
text, navigation, access errors and references remain ineligible. Simplified/traditional
Chinese fixtures verify exact relevant windows and neutral unrelated captures. This change
concerns preview diagnostics and component matching; the existing quotation-length/counting
policy is unchanged, and native-text preview usability does not waive quote eligibility.

History resolves the whole acquired-source record before accepting a selection preview and
checks its cluster, direction and enabled directions in addition to snapshot/run/hash/text.
Checksum-valid fixtures with a different owner or direction produce a compatibility warning;
only the original source's independently validated Probe preview may supply a fallback.
Database bytes and modification time remain unchanged during inspection.

Eleven new regression cases cover these repairs without removing existing assertions.
Focused preview/runtime/inspection/selection and repository type-contract checks passed
**52 tests in 2.31 seconds**. Final complete verification and commit evidence follows.

Final isolated macOS/Python **3.12.14** verification after corrections: **2,097 passed,
3 existing skips in 166.81 seconds**. Skips remain the explicitly gated live CLI smoke,
optional LLM integration and native Windows ACL verification. Whole-workspace Ruff was run:
its only failures remain three import-order errors in unrelated untracked restored modules
(`desktop_settings.py`, `history_import.py`, `model_contracts.py`). All **272 tracked/Phase 4
Python files** pass lint and formatting; raw workspace formatting passes **289 files**.
Whitespace checks, installed renderer ESLint/TypeScript checks, a fresh isolated **Next.js
16.3.1 webpack desktop static export**, and desktop shell syntax pass. The five archived
current-state documents match c942070 byte-for-byte. Existing tests and historical prompt
bytes remain intact; the proposal pack and restored legacy modules remain excluded from
the reviewed local commit. No installation, push, publication or paid research is performed.


## Phase 5 implementation and acceptance

Root personally owns contracts, durable response/provenance verification, budget policy,
adaptive integration and final evidence. Three user-requested GPT-6 Luna helpers owned
bounded OpenAlex transport/documentation, ordinary handoff/runtime fixtures, and reader/UI
plumbing and planning regressions. Exclusive source ownership prevented overlapping edits;
root reviewed their changes and corrected integration defects at the source-selection and
Gap-analysis boundaries.

`providers.openalex_neighborhood` implements fixed OpenAlex work-ID or exact DOI lookup,
reference/related ID batches and a first page of citing works. Current official sources are
[API recipes](https://help.openalex.org/how-to/api-recipes/) and
[work attributes](https://help.openalex.org/data/works/attributes/). Related work is retrieved
only from reported `related_works`, using the documented ID batch filter. Incoming citations
must independently list the seed in `referenced_works`. There is no title-equivalence lookup,
LLM-created edge, second hop, pagination crawl, retry or undocumented withdrawn field.
Invalid IDs, ambiguity and conflicting DOI/title/authors/year remain unresolved. Known
retracted/withdrawn work types are excluded. Missing withdrawal metadata remains unknown;
missing/empty relationship fields have explicit unsupported/empty dispositions. Candidate
locations undergo syntactic public-host checks and the existing acquisition transport policy;
provider transport has fixed endpoints, no redirected requests, explicit deadlines and a
262,144-byte response cap.

`seed_expansion` selects at most three distinct ordinary scholarly seeds from owned usable,
relevant current-round previews and immutable acquisitions; no model call is added. It
persists seed eligibility/selection, relationship priority (references, citing, related),
relevance/work-ID tie-breaks, and failed/used/visited identities. Expanded items cannot become
seeds. Only subsequent authorized rounds 2–4 receive offers; every graph action replaces a
normal application lane slot. Existing Search Agent routing/repair reservations and Round-3
stopping apply, with Round-4 Governor authorization checked before planning and transport.
No fifth round exists. At most ten unique neighbors per seed across relationships and thirty
per run are subordinate to raw metadata, provider, slot, model and acquisition budgets.

Fresh neighborhood capability v4, seed policy v2, Search Agent neighborhood prompt and
schemas are separately frozen. Existing query-capability/compiled-query identities preserve
their historical meanings. Each identity/neighbor HTTP start reserves from the same OpenAlex
10-request/$0.01 ceiling. Identity lookup may observe two DOI records solely to detect
ambiguity; relationship requests fetch at most ten candidate records in one batch/page.
Successful response bytes and completion commit atomically, with stable parser checkpoints.
Interrupted starts retain unknown exposure and cannot repeat. Cancellation/budget exhaustion
can retain the resolved identity and pending state; resume reuses completed identity and
response bytes. Parser receipts and raw/edge metadata are revalidated against the exact
owned physical response, including operation/seed ownership and hashes; recomputing a forged
parsed hash does not authorize metadata. No schema/table/index/dependency/model-stage change.

Expanded records use the existing normalization, deduplication, metadata rank, Scout,
acquisition, exact previews, source selection, extraction, Analyst and deterministic
admission. Query text is null; actual graph action, seed/work, relation, round, provider,
lane and target Gaps remain typed provenance. New optional fields are omitted for historical
serialization. Read-only trails show neighborhood metadata, and graph action counts remain
separate from text-query attempts. Release reconstruction/export and immutable Ledger/source
families are unchanged.

| Acceptance | Evidence |
| --- | --- |
| Fixed exact ID/DOI lookup, reference/citing/related transport, ambiguity, malformed/rate-limit/outage, unsafe locations, bounded bytes, duplicate returned IDs | `test_openalex_neighborhood.py` |
| No keyword match/baseline reference reaches common Scout/acquisition, exact extraction, Analyst and admission, with action/source/snapshot/hash linkage | `test_seed_expansion_runtime.py::test_graph_neighbor_enters_full_evidence_chain` |
| Valid support-lane citing work independently reports conflicting findings and is admitted as CHALLENGES; tangential work is Scout-skipped without acquisition/admission | Parameterized full-chain and tangential runtime fixtures |
| Relevant owned previews only; no seed/capable lane; DOI mirrors/cycles; unknown/cancellation/partial resolution; crash replay without repeated HTTP; forged parser hash rejected | Runtime fixtures and graph contract regressions |
| Three seeds selected from four; ten neighbors per seed/thirty run; six accounted HTTP requests; bounded ID batch; cached replay without transport; raw candidate/response forgery rejected; late DOI metadata keeps prior work IDs visited; known failed exact lookup is not re-offered despite remaining budget | `test_seed_expansion_review.py` and foundation/store cap tests |
| Text and graph compete for slots; enabled provider/direction/Gap routing; Round-3 total cap; Round-4 Governor and lane caps; no Round 5; adapter runtime caller and Round-2 Gap continuation | `test_neighborhood_planning.py`, `test_graph_neighbor_adaptive_handoffs.py`, existing adaptive/Round-4 suites |
| Legacy trails and exported releases unchanged; read-only bytes/mtime; graph metadata/diagnostics distinct from evidence/text | `test_historical_reads_phase3.py`, planning diagnostics and existing history/export/release regressions |

Final verification is recorded below. Offline fixtures establish
bounded execution, provenance and constructed-case admission, not live research quality.
Phase 6 remains product controls and final cross-phase acceptance.


### Phase 5 review corrections and verification boundaries

Root fixed nullable-query integration in source-selection provenance and explicit graph
round ownership in Gap continuation. Raw/edge replay now compares exact re-derived metadata,
response-body hashes and physical operation/seed ownership. A checksum-valid edited response
cannot borrow its unchanged physical completion. The prior query-retention regression now
asserts both exact versioned query and neighborhood catalogs and equality of every shared
capability field, while retaining its fairness/retention/physical-request assertions.
No assertion was removed or evidence gate weakened.

A review fixture reproduced a same-W-ID record gaining DOI metadata in a later relationship;
root now retains both provider IDs and DOI aliases across all expansion edges and enforces
that rule at storage insertion. Known failed exact seed lookups are excluded from subsequent
relation offers even when costs are reported and physical headroom remains. This does not
prevent a resolved seed with a failed/unsupported relationship from trying a different
bounded relationship; unknown physical outcomes still stop all transport.

Final focused and complete-suite evidence follows below. Final source checks use fake transports, disposable SQLite/application
data and isolated desktop static outputs on macOS arm64/Python 3.12.14. Nothing is installed,
committed, pushed, published or paid. No credentials or real application databases are read.


### Phase 5 implementation-stage acceptance evidence

Final target: macOS arm64, Python **3.12.14**, fake transports, temporary application data,
disposable SQLite and isolated renderer outputs. Complete suite: **2,156 passed, 3 existing
skips in 158.27 seconds**. Skips remain gated live CLI smoke, optional LLM integration and
native Windows ACL validation. The final runtime/planning/review/type group passed **27
in 10.49 seconds**; the earlier broader graph/adapter/history/fairness/type group passed
**96 in 10.77 seconds** before the final known-failure seed-offer regression, which is covered
by the final focused and complete passing runs. Initial broad verification exposed the old
capability equality assumption; the strengthened exact-catalog/shared-field regression and
all retention assertions now pass. Later completed broad runs are superseded by this final
source result.

Ruff lint and formatting pass for all **280 tracked and Phase 5 Python files**. Raw workspace
formatting passes **297 files**; raw whole-workspace Ruff was actually run and still reports
only three pre-existing import-order problems in unrelated untracked restored modules
`desktop_settings.py`, `history_import.py`, `model_contracts.py`. Those files remain untouched.
`git diff --check` and all **14 new source/prompt/archive file** whitespace checks pass.

Installed renderer ESLint and TypeScript checks pass. The helper verified a disposable
**Next.js 16.3.1 webpack desktop static export** with `RESEARCHASSISTANT_DESKTOP=1` in
`/private/tmp/ra-neighborhood-desktop-build/out/`; compilation, TypeScript and static pages
completed successfully. `node --check desktop/main.cjs` passes. A temporary Turbopack build
rejected a dependency symlink outside its root; the supported webpack build passed with the
existing installed dependencies. No dependency download, bundle installation or installed-app
replacement was performed.

A final full advisory graph refresh reported ready with **9,691 nodes / 66,926 edges**,
without persisted graph artifacts. Live source and graph inbound traces verify both adaptive
and Round-4 offer paths and the common `_execute_searches` → `execute_expansion` runtime
caller. Five prior current-state documents in the citation-neighborhood archive match
pre-change HEAD **efbe119** byte-for-byte. Historical prompt bytes, schema 17 and release
hashes remain unchanged; complete existing release/export/history regressions pass.

Phase 5 source/offline acceptance is complete. Changes remain uncommitted. No paid service,
credential read, real database change, migration, dependency/model-stage increase, automation,
installation, commit, push or publication occurred. Phase 6 product controls and final
cross-phase acceptance remain the next request boundary. Offline fixtures do not establish
live research quality.


### Phase 5 independent review repairs and local commit

Independent review reproduced three identity defects despite the implementation-stage
passing suite: the same known OpenAlex work occupied separate DOI/non-DOI seed slots;
a DOI-only seed resolved to a work ID but could return itself without DOI metadata; and
partial author observations failed exact author-set comparison. The user's follow-up
explicitly authorized the repairs after requesting a reviewed local commit.

Seed selection and transactional storage now recognize shared DOI/provider-ID anchors before
applying the seed cap. Duplicate seed artifacts cannot bypass selection; existing identical
seed writes remain idempotent. Runtime and transactional edge insertion retain resolved seed
IDs and DOI aliases as visited, and current graph contracts also reject direct known aliases.
Compatible author subsets are accepted only alongside the existing exact ID/DOI/title/year
checks. Disjoint or non-nested conflicting author sets remain unresolved. Historical v1 edge
validation and serialization retain their meaning. No quota, dependency, schema or evidence
gate changes accompany these corrections.

Eleven new regression cases cover both alias forms, capacity for distinct seeds, storage
bypass/idempotence, resolved self-cycles, transport-free replay, partial author lists in both
directions, conflicting authors, and independent ID/DOI/title/year conflicts. Final focused
graph/runtime/store/contract/type verification: **82 passed in 23.30 seconds**. Complete suite
using fresh temporary application data: **2,167 passed, 3 existing skips in 159.14 seconds**
on macOS arm64/Python 3.12.14. All **280 tracked/new Python files** pass Ruff lint and format;
raw workspace format passes **297 files**. Whole-workspace lint was run and retains only the
same three pre-existing import-order failures in untouched untracked restored modules.
ESLint, TypeScript, desktop syntax and whitespace checks pass. Renderer source is unchanged
by the repairs; its implementation-stage isolated webpack static export remains recorded above.
The full advisory graph refresh, with no persisted artifacts, reports ready at **9,697 nodes /
66,935 edges**; live source verifies selection, storage and contract alias checks. The five
Phase 4 snapshots still match efbe119 byte-for-byte.

Phase 5 and these repairs are delivered as the reviewed local commit. The proposal pack and
unrelated restored root files remain excluded. No installation, push, publication, paid
transport, credential access or real application-data change occurred. Phase 6 remains the
next request boundary. Offline tests establish constructed behavior and provenance only.
