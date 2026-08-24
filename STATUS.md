# Status

## 2026-08-24 - Phase 8 source-cap and deterministic deep-analysis backfill correction

Status: Complete and verified.

- Preserved the exact run-wide v2 ceiling of 500,000 tokens, 160 physical calls, and the
  configured cost ceiling. Final Source Selection now reserves a hard 60,000-token allowance
  per source and records the reduced seven-call workload: two Extractor attempts, four
  Analyst attempts across assessment/draft, and one independent Reviewer call.
- Analyst prompts now contain only the exact candidate quote block, immediate context, and
  necessary source metadata; the complete normalized snapshot remains available for exact
  application verification and is not sent to Luna.
- Reviewer rejection is terminal for that source. The former revision plus second-Reviewer
  path is removed from normal execution while immutable Reviewer validation and Ledger
  admission remain unchanged.
- Added a typed, versioned deep-analysis backfill artifact with persisted full priority,
  original queued IDs, replacement IDs, final execution order, terminal source outcomes,
  per-source conservative token/cost reconciliation, and remaining run budget. Extraction,
  Analyst, and Reviewer terminal failures backfill the next unqueued survivor without
  duplicates or reordering; completed source artifacts and the final backfill resume
  idempotently.
- Added source attribution at the physical-call budget boundary. Exact provider usage is
  reconciled when available; missing usage remains conservatively charged, and released
  source allowance is never added back to the global `tokens_remaining` snapshot.

Verification: focused Phase-8/9/10/12 suite passes, including six-source 60k queue admission,
reduced workload metadata, Analyst prompt reduction, one-call Reviewer rejection, source
reconciliation, and restart-safe artifacts. Complete pytest passes 792 tests with 2 expected
skips; Ruff check, Ruff format check, and diff check pass. No dependency change or live paid
research run was made.

## 2026-08-21 - Budget and failure-diagnostics correction

Status: Complete and verified.

- Fresh website/API and direct v2 runs now default to a $0.20 cost ceiling alongside the
  500,000-token hard maximum.
- Terminal v2 failures are persisted before the worker returns, and an empty deep-analysis
  queue now reports the actual call, token, or cost reservation that blocked evidence work.
- The frontend preserves structured API validation messages instead of replacing them with a
  generic local-service toast, and failed runs display their actionable persisted reason.
- The launcher validates the current API version and only retires a stale ResearchAssistant
  backend process; an unrelated listener on port 8765 is reported as a conflict.
- Luna setup now rejects the OpenAI dashboard URL and points to the API endpoint, while the
  saved local route was corrected to `https://api.openai.com/v1`.
- Extraction now uses application-owned sentence ranges, and malformed adaptive Search Agent
  responses degrade to preserved Round-1 work instead of aborting the whole run.
- The local API was restarted and verified with the pinned Wigolo acquisition service healthy;
  the rebuilt frontend is serving on loopback port 3000.

Verification: complete Python suite 782 passed with 2 expected skips; focused adaptive,
production, routing, and extraction suite 89 passed with 1 expected skip; Ruff check, Ruff
format check, and diff check passed. Frontend ESLint and the Next.js 16.3.1 production build
passed. No dependency change or live paid research run was made.

## 2026-08-21 - v2 provider setup and discovery wiring

Status: Complete and verified.

- Provider setup now reports saved Keychain credentials separately from full run readiness,
  so a persisted key no longer appears unsaved when another required route is incomplete.
  Saved optional discovery keys also reload after an API restart even if the MiMo key has not
  yet been stored.
- The setup form can optionally override the Luna API base URL and model ID. Fresh v2 runs use
  the production OpenAI-compatible default route and `gpt-5.6-luna` when no override is saved,
  while missing keys and pricing caps still fail closed.
- Provider setup now captures the required MiMo-v2.5 and Luna input/output budget caps as the
  published USD-per-million-token prices and persists their exact per-token equivalents for the
  strict production routing configuration. This replaces the inaccessible terminal-only route
  pricing requirement without fabricating cost values.
- The modal remains open after a save and exposes a presence-only checklist for saved route
  settings, so clearing transient fields cannot be mistaken for a failed Keychain write.
- A failed launch due to incomplete provider configuration now keeps the user on the research
  page with the returned explanation instead of automatically reopening the provider modal.
  This separates persisted credentials from the remaining run-readiness requirement.
- The credential-save response now returns a presence-only list of accepted non-secret route
  settings. The setup panel uses that response immediately, labels incomplete setup honestly,
  accepts only plain numeric price values, and converts low-level missing-price errors into
  actionable language.
- Fresh v2 website runs can independently enable arXiv and PubMed discovery, and can enable
  optional Crossref DOI identity enrichment. arXiv is keyless; PubMed accepts an optional key;
  Crossref remains metadata-only and cannot become evidence. The v2 factory now instantiates
  the selected adapters and fingerprints the Crossref choice for restart safety.
- The result page now displays the persisted discovery providers for the run and for each
  survivor source. Historical result rendering remains unchanged.

Verification: complete Python suite 778 passed with 2 expected skips; focused API/frontend
regression suite now passes 35 tests; Ruff check, Ruff format check, and diff check passed.
Next.js ESLint and production build passed. No live provider call or dependency change was made.

## 2026-08-21 - ResearchAssistant v2 Phase 12 Production Hardening and Cutover

Status: Complete and verified.

- Added a complete restart-safe v2 production coordinator covering broad Round 1 through the
  canonical Phase 11 result envelope, including the previously missing exact-extraction bridge.
- Added persisted run-wide accounting for every MiMo normal, MiMo Pro, and Luna physical call,
  including failures/retries. Hard maxima are 160 calls and 500,000 tokens; lower configured
  ceilings fail closed. Optional continuation protects fourteen downstream calls and Phase 8
  sizes deep analysis from actual remaining calls, tokens, and cost.
- Added provider construction for all three physical model aliases and cut fresh website and
  CLI launches to v2. Historical inspection, rendering, export, immutable evidence, and
  explicitly injected compatibility paths remain under their original contracts.
- Expanded the production fingerprint to cover semantic schemas/prompts/policies, directions,
  provider adapters, model routes, ceilings, research limits, release semantics, and the final
  output contract. Cross-version/configuration resume is rejected.
- Added mocked full-path, restart, lower-budget, fingerprint, and all-direction integration
  coverage. Existing Phase 4–11 suites retain provider/stage degradation, Round 2/3 Governor,
  cancellation, direction-adversarial, Reviewer/Ledger, API/export, release-blocking, and
  rendered-hash coverage. No paid provider call or dependency change was made.

Verification:

- Complete Python suite: 772 passed, 2 expected opt-in skips, 0 failed.
- Focused Phase 12 production suite: 10 passed, including mocked Runs A–H.
- `ruff check .`, `ruff format --check .`, `git diff --check`, Python compilation, and
  launcher `zsh -n` syntax passed. Frontend ESLint and the Next.js 16.3.1 production build
  passed from the existing local dependency installation.

## 2026-08-21 - ResearchAssistant v2 Phase 11 Synthesis and Final Research Output

Status: Complete and verified.

- Added strict MiMo-v2.5-Pro synthesis input containing only exact claim, enabled directions,
  approved Ledger projections, qualification/placement metadata, typed unresolved gaps,
  deterministic stopping disclosure, and non-evidentiary recommendation state. Raw source
  text and unreviewed claims cannot reach the v2 Synthesizer.
- Added deterministic v2 final-output validation and rendering. It rejects disabled-direction
  leakage, unknown source/recommendation IDs, Ledger/provenance mismatch, malformed source
  status, and any release-integrity failure; invalid outputs have no rendered hash.
- Added result source categories, scope disclosure, remaining gaps, stopping reasons,
  append-only v2 final-output persistence, read-only API, conditional Next.js rendering, and
  v2-aware local export while preserving historical result rendering.
- Verification: all 762 Python tests passed in three complete non-overlapping batches with
  2 expected opt-in skips; focused Phase-11/API/export coverage is included (14 passed).
  `ruff check .`, `ruff format --check .`, and `git diff --check` passed. Frontend lint/build
  could not start because pnpm attempted a registry install and the registry was unavailable;
  no dependency directory was removed or changed. No live calls.

## 2026-08-20 - ResearchAssistant v2 Phase 10 Reviewer and Claim Ledger Integration

Status: Complete and verified.

- Added the v2 bridge from Phase-9 Analyst drafts through the existing narrow MiMo-v2.5-Pro
  Reviewer to deterministic `LedgerRecord` admission. It reuses Reviewer decision
  validation, `rappr_v1` approval IDs, score-pair/placement derivation, `QUALIFIED_ONLY`,
  and the one-Analyst-revision maximum.
- Added immutable v2 Ledger provenance for direction, discovery round, source family,
  recommendation state, survivor ID, and relevant Gap IDs. Non-recommended sources remain
  admissible; disabled-direction evidence is rejected before review.
- Added migration 13 `v2_ledger_admissions` with update/delete SQLite triggers. Historical
  Ledger rows remain untouched and their existing immutability triggers are unchanged.
- Verification: 748 passed, 2 expected opt-in skips across the complete offline suite;
  `ruff check .`, `ruff format --check .`, and `git diff --check` passed. No live calls.

## 2026-08-20 - ResearchAssistant v2 Phase 9 Luna Evidence Analyst

Status: Complete and verified.

- Added a restart-safe Phase-9 Analyst stage over the bounded Phase-8 queue. Every survivor
  remains in the result; queued survivors retain their exact candidate, including on final
  Analyst failure.
- Fresh-v2 semantic assessment/scoring, initial canonical factual-statement drafting, and the
  one possible Reviewer-directed revision use GPT-5.6 Luna High and a v2-only prompt. The
  historical direct-MiMo Analyst prompt and persisted records remain readable and unchanged.
- Kept MiMo-v2.5-Pro exact passage selection and revalidated immutable snapshot hashes,
  exact quote membership, offsets, bracket context, candidate identity, and provenance before
  Luna. Analyst output never assembles or changes a quote.
- Added strict proposition, claim-relationship, limitation, inferential-boundary, and reasoning
  fields. Application validation enforces support/challenge isolation and Claim Fit 3 scope
  qualification.
- Reused the existing two-axis score table, deterministic approval/placement derivation,
  `ScoreDecision`, and `StatementDraft`. Phase 9 creates no Ledger record; failed work has no
  Reviewer-ready draft and remains behind the existing Reviewer and Ledger gates.
- Every Luna attempt uses existing persisted physical-call, token, and exact-cost reservation
  and finish accounting, with one bounded retry per logical operation.

Verification:

- Focused Phase-9 suite: 7 passed.
- Complete offline Python suite: 742 passed, 2 expected opt-in skips, 1 existing Starlette
  deprecation warning.
- Ruff lint, Ruff format check, and `git diff --check`: passed.
- No live provider call was made.

## 2026-08-20 - ResearchAssistant v2 Phase 8 Source Selection and Deep-Analysis Queue

Status: Complete and verified.

- Added strict immutable contracts for the complete survivor selection input, model-only
  recommendations, selection attempts, remaining budget, per-survivor status, cumulative
  reservations, bounded queue, and restart result.
- Final Source Selection uses the configured MiMo-v2.5-Pro route, can recommend only known
  survivors and known same-direction Gap IDs, and rejects duplicate-family domination.
  One retry is allowed before deterministic complementary fallback.
- The queue preserves all survivors while prioritizing recommended sources and then
  complementary non-recommended sources. It reserves twelve worst-case physical calls per
  source plus two mandatory Synthesis calls and deterministically shrinks for the 160-call,
  token, or cost boundary.
- Every survivor persists whether it was recommended and queued, its ranks/rationale/Gap
  links, and the budget reason when it could not be deeply analyzed. Restart reuses the
  completed append-only result without another model call.
- Added offline Phase-8 regression coverage; no live call, dependency, or migration was
  added.

Verification:

- Focused Phase-8 suite: 8 passed.
- Complete offline Python suite: 735 passed, 2 expected opt-in skips, 1 existing Starlette
  deprecation warning.
- Ruff lint, Ruff format check, and `git diff --check`: passed.
- No live provider call was made.

## 2026-08-20 - ResearchAssistant v2 Phase 7 Adaptive Search Continuation

Status: Complete and verified.

- Added restart-safe adaptive continuation from persisted Luna Gap Analysis. A Round-1 stop
  creates no Round-2 plan; a continue decision invokes the MiMo-v2.5-Pro Search Agent with
  persisted Gap IDs, discovered terms, prior queries, enabled directions, and only eligible
  providers.
- Reused the existing v2 discovery, conservative clustering, batched Scout, safe acquisition,
  deterministic Probe, and survivor merge flow for Round 2 and the optional narrow Round 3.
  Luna runs again after Round 2.
- Extended the deterministic Governor so Round 3 requires a material remaining gap, Luna's
  continue recommendation, a genuinely new direction and query, provider eligibility and
  capacity, duplicate rate below 70%, and reserved protected downstream budget. Round 3 is
  capped at three queries and one provider/direction lane; Round 4 is impossible.
- Added deterministic exact-normalization and trivial-token-rewrite rejection without
  embeddings. Disabled directions/providers and exhausted provider ceilings create no work.
- Persisted every adaptive plan and reservation, targeted Gap IDs, provider outcomes, round
  execution counts, merged survivors, Governor decision, and final stopping decision in the
  existing append-only v2 artifact store.
- Added 21 offline Phase-7 tests covering one-, two-, and three-round paths, both adaptive
  stops, Governor acceptance/rejection, provider eligibility/exhaustion, duplicate saturation,
  novelty, restart, cancellation, provider degradation, direction isolation, and the hard
  three-round maximum. No live provider call, dependency, or schema migration was added.

Verification:

- Complete Python suite: 727 passed, 2 expected opt-in skips, 1 existing Starlette warning.
- Ruff lint, Ruff format check, and `git diff --check`: passed.

## 2026-08-20 - ResearchAssistant v2 Phase 3 Initial Planner and Broad Round 1

Status: Complete and verified.

- Added a fresh-v2 Initial Planner entry point that validates the v2 MiMo-v2.5-Pro route,
  performs one typed Planner request, and stops after persisting the broad Round-1 plan.
- Added one application-owned policy for enabled direction/provider Round-1 lanes,
  preserving two SERP Search, three Exa, and one OpenAlex query slots per enabled
  direction. The model cannot produce objectives, importance scores, query IDs,
  timestamps, policy identities, or future rounds.
- Added strict fresh-v2 query contracts and append-only migration 12 records for the
  initial plan and its Round-1 queries. Queries persist run, direction, provider, round,
  strategy, text, timestamps, and policy identity. Restart reconstructs the stored plan
  without another Planner call; changed provider-contract fingerprints fail closed.
- Historical `PlannerOutput`, provider infrastructure, v2 Phase 1 artifacts, and
  pre-v2 pipeline inspection remain unchanged and readable.

Verification:

- Focused v2 Phase 1–3 suite: 29 passed.
- Complete Python suite: 691 passed, 2 expected opt-in skips.
- Ruff lint and format checks plus `git diff --check`: passed.
- No live provider call was made.

## Current project state — 2026-08-17

On 2026-08-18, a live multi-provider run exposed stale ranking field limits: the
documented 20-source selection and 25-attempt backfill policies could produce selection
ranks above 10 or extraction ranks above 10, causing the entire Researcher batch to fail
validation. The typed ranking and read-only research-trail limits now match the existing
policy ceilings (20 selected, 25 acquired). Regression coverage exercises the complete
25-source acquired pool. Full Python verification passes with 661 tests and 2 expected
opt-in skips; Ruff lint/format and diff validation pass. Frontend lint/build remain blocked
by pnpm attempting an unavailable registry install from the local dependency state.

On 2026-08-18, the user explicitly expanded the configured Firecrawl fallback. Wigolo
authentication and paywall responses now receive one Firecrawl attempt. A MiMo exact-quote
failure may also trigger one direct Firecrawl re-acquisition; MiMo retries only when the
fallback returns a different non-empty snapshot. Permanent source-policy failures and
non-exact-quote model/schema failures retain their existing behavior.

MLP-5 Provider Selection & SERP Search is complete. New website runs default to all three
typed discovery sources—SERP Search, Exa, and OpenAlex—and may switch each source on or
off in Advanced, while requiring at least one. The frozen source set is part of planner
validation and the exact provider fingerprint. SERP Search runs two Google-style organic
queries per active stance per round and permits at most twelve attempted calls per run;
its subscription cost is never invented as a per-call USD value. Disabled sources need no
key and produce no work; enabled sources without a saved Keychain key fail closed before
the run begins. All source metadata remains discovery-only and follows the existing ranking
and evidence controls. Full offline verification: 655 passed, 2 expected opt-in skips;
Ruff and diff checks passed. Frontend lint/build remains unverified because pnpm attempted
an unavailable registry install from the incomplete local dependency tree.

MLP-4 Research Quality & OpenAlex Integration is complete. A corrective quality pass
adds bounded rank-ordered backfill, claim-aware soft ranking, source-anchored exact
quote selection, and a clean zero-Ledger stop. New live runs use separate
Planner lanes for three Exa web queries and one OpenAlex academic query per active stance.
Focused research is the default and performs no opposing provider or model work;
counterevidence enables the equal opposing lane without changing any configured call,
token, USD, deadline, or provider ceiling. Advanced chooses 5, 10, 15, or 20 sources,
with 10 as the default, five bounded fallbacks per target, and no wildcard or diversity
slot.

On 2026-08-17, the user explicitly authorized a substantial evidence-yield relaxation.
The discovery floor is now 5/100 instead of 20/100, current provider-backed exact quote
minimums are 20 statistical / 30 non-statistical words instead of 50/75, and a zero
claim-keyword count is retained as audit metadata for semantic Analyst review rather
than causing pre-Analyst rejection. Exact snapshot membership, sequential offsets,
immediate context, boundary and truncation rules, immutable evidence, Analyst scoring,
Reviewer approval, Ledger admission, and final validation remain strict. No fuzzy quote
repair was added.

The deterministic first ranking merges Exa/OpenAlex discovery metadata, collapses exact
canonical URLs, applies the documented 100-point score, and retains below-5 decisions in
the trail while excluding them from acquisition. After acquisition, actual normalized
page text is scored only to set extraction order; that second stage does not delete a
usable source. Focused briefs explicitly disclose that counterevidence was not requested.

OpenAlex configuration is required for new live runs, stored through the existing macOS
Keychain boundary, and enforced at no more than ten searches or nominal USD 0.01 per run.
Migration 10 adds provider and intent to persisted queries while preserving historical
read-only inspection. Terminal Next.js results expose the persisted two-stage ranking
only through a hidden post-run Research Trail drawer. MiMo estimates use reported cached
input detail when present and conservatively treat input as uncached otherwise.

The evidence-yield correction bumps its discovery, extraction, MiMo adapter/factory/
fingerprint, and orchestration policy identities, so it applies to fresh runs and cannot
silently resume an older contract. No live Exa, OpenAlex, Wigolo, Firecrawl, or MiMo call
was made, so this implementation spent no provider credit. No dependency, migration,
hosting, account, telemetry, visual redesign, or historical immutable-row rewrite was
added. The earlier MLP-4 record predates the completed MLP-5 provider-selection work; the
current MLP-5 status is recorded above.

The 2026-08-17 expanded-retrieval correction removes a stale `search_rank <= 5`
pre-Analyst candidate constraint that rejected otherwise valid exact quotes from later
bounded acquisition ranks. Candidate, provisional, and retrieval provenance now permits
ranks through 25; exact source and downstream quality/release checks are unchanged.

Verification for the 2026-08-17 corrections passed: 651 tests with 2 expected opt-in
skips, repository-wide Ruff lint and format, frontend ESLint and optimized production
build using the installed dependencies, launcher syntax, and `git diff --check`.

On 2026-08-15, the Keychain boundary was repaired after real launcher use exposed that
the command-line `security` tool cannot receive a background web request's password
prompt. Credential reads and writes now use Apple's Security framework in-process via
the Python standard library. A disposable real-login-Keychain round trip passed and was
removed; the complete offline suite now passes with 613 tests and 2 expected skips.
Secrets remain absent from command arguments, logs, responses, browser storage, and
repository files. The macOS framework availability gate recognizes its system symlink,
whose binary may live only in Apple's shared dynamic-linker cache.

## Completed research-pipeline state — 2026-08-11

MVP-11 Adaptive Research Expansion & Cost Control (Research Governor) is complete and
verified. MVP-10 Evidence Portfolio & Trail and MVP-9 Verified Quote Selection &
Deterministic Assembly remain its immutable evidence safeguards. Migration 9 records
append-only numeric research rounds constrained to 1–3, the deterministic post-Round-2
Governor decision, and the terminal research result; historical MVP-9 and MVP-10 runs
remain read-only inspectable. MLP-1 and MLP-2 do not alter these contracts.

## 2026-08-11 - MVP-9 Verified Quote Selection & Deterministic Assembly

Status: Complete and verified.

- Replaced the provider-facing Extractor `ProvisionalCandidate` output with strict
  `VerbatimQuoteSelection`. MiMo now returns only ordered exact snapshot passages and
  cannot supply brackets, context, offsets, provenance, IDs, timestamps, or a completed
  candidate artifact.
- Added deterministic application-owned quote assembly. ResearchAssistant locates the
  passages sequentially in the immutable normalized snapshot, derives immediate context
  and correct start/end/truncated markers, joins non-contiguous passages canonically,
  constructs the legacy-compatible provisional artifact, and runs the unchanged exact
  post-extraction filter before assigning a candidate ID.
- Exact-selection mismatch now fails once without retry or route switching. Malformed
  JSON/schema and approved availability failures retain bounded objective retries. No
  fuzzy matching, healing, padding, source rewriting, threshold reduction, Reviewer
  weakening, or release-gate weakening was added.
- Bumped the Extractor prompt, direct-MiMo adapter/factory/retry, post-filter, schema,
  and run-fingerprint identities. MVP-9 execution requires a new run ID; historical
  terminal runs remain inspectable under their persisted contract.
- Kept SQLite schema version 7. Semantic selections use the existing model-attempt JSON
  audit field, while assembled quote blocks and exact offsets retain the existing
  provisional/candidate columns. No migration or historical-row rewrite occurred.
- Added adversarial MVP-9 coverage for strict schema shape, multi-segment assembly,
  boundary markers, nonexistent/out-of-order passages, non-retryable mismatch, direct
  MiMo semantic output, and schema-7 preservation.

Verification:

- Focused MVP-9/MiMo/prompt/orchestration/acquisition/database selection: 107 passed,
  1 expected opt-in skip.
- Complete offline suite: 579 passed, 2 expected opt-in skips.
- Offline evaluation: 38/38 deterministic cases passed; optional live comparison was
  not enabled.
- Ruff lint/format and `git diff --check` passed.
- No dependency, migration, live Exa/Firecrawl/MiMo call, provider spending, generated
  tracked artifact, commit, push, or pull request was added.

Next phase:

- No phase after MVP-9 is authorized.

## 2026-08-10 - MVP-8.2 Evidence Browser

Status: Complete and verified.

- Added a typed, local Evidence Browser that reconstructs candidates, trusted snapshots,
  provenance, Analyst and Reviewer decisions, Ledger records, and final validation only
  through the validated read-only SQLite inspection boundary.
- Released statements trace directly to their Ledger record, approved review, exact
  quotation, trusted snapshot, and source provenance. Filters cover stance, stage,
  source URL, approval/rejection state, and release state.
- The dedicated local Streamlit page is inspection-only and labels trusted snapshot text,
  non-authoritative provider metadata, untrusted source text, and unreleased artifacts.
  It exposes no provider request headers, credentials, or edit actions.
- Added regression coverage for trail navigation, filters, unreleased labeling,
  missing/corrupt databases, redaction, and byte-for-byte non-mutation.

Verification:

- Focused Evidence Browser suite: 6 passed.
- Full offline suite passed with the existing 2 expected opt-in skips.
- Ruff lint/format, deterministic Phase 10 evaluation, and `git diff --check` passed.
- No dependency, migration, provider call, account, cloud storage, or evidence/release
  policy change was added.

## 2026-08-10 - MVP-8.1 Research Controls

- MVP-8.1 is complete and verified. Frozen strict `ResearchControls` carries bounded
  depth, length, tone, and explicit optional focus constraints. Focus is passed to the
  Planner input and is never inferred from the claim.
- Controls are included in the canonical provider policy identity and fingerprint. A
  changed control set therefore cannot resume an existing run under the same run ID.
  Depth alone maps to equal supporting/opposing acquisition limits; budgets and every
  evidence, quotation, Reviewer, Ledger, and final-validator rule remain unchanged.
- CLI launch, live UI, live status, and local export trace metadata display selected
  controls. Historical contracts without controls reconstruct with the safe defaults.
- Added regression coverage for defaults, valid/invalid controls, Planner propagation,
  immutability, and tone/focus isolation. No dependency, migration, provider, account,
  cloud service, live call, or semantic-release rule was added.

Verification:

- Focused controls/provider/CLI/live/Planner tests: 90 passed, 2 expected skips.
- Full offline suite: 565 passed, 2 expected skips.
- Ruff lint/format, deterministic Phase 10 evaluation, and `git diff --check` passed.

## 2026-08-10 - MVP-8 Briefs, Export & Performance

Status: Complete and verified.

- Added local Markdown, PDF, and DOCX export for revalidated released runs only. Each
  report carries the released run ID, rendered-brief hash, exporter version, format, and
  generation time; Markdown is deterministic for a fixed timestamp.
- Export reconstructs through the established read-only inspection path and refuses
  blocked, failed, cancelled, and running runs. It verifies final validation and the
  rendered hash before writing a local file.
- Presentation retains the exact released brief and approved factual statements, adds the
  required human-review warning, and preserves visible coverage warnings.
- Added persisted checkpoint completion to CLI inspection and the local live UI. Existing
  compatible failed-run resume behavior continues to reuse typed valid checkpoints.
- Added MVP-8 export regression coverage. No dependency, migration, live provider call,
  external storage, account, or provider change was added.

Verification:

- Full offline suite: 557 passed, 2 expected opt-in skips.
- Ruff lint and format checks, deterministic evaluation, and `git diff --check` passed.

Next phase:

- No phase after MVP-8 is authorized.

## 2026-08-10 - MVP-7.1 MiMo Consolidation Completion

Status: Complete and verified. MVP-7 direct-MiMo consolidation remains the preceding
committed milestone; MVP-7.1 repaired its provider-neutral CLI regression fixture and
completed its verification record.

- Replaced the deleted MVP-3A fixture dependency in the MVP-4 subprocess driver with
  the existing provider-neutral Phase 9 fake providers. The driver now persists a
  canonical direct-MiMo-compatible run contract, applies the requested budget, retains
  unique snapshot coverage, and blocks inside a real provider override for cross-process
  cancellation timing.
- The repaired subprocess coverage proves released, blocked, and failed terminal exits;
  configuration/budget rejection; launch redaction; inspection; exact resume identity;
  snapshot persistence; and cooperative cancellation without restoring an OpenRouter
  adapter or configuration path.
- MVP-7.1 adds no provider vendor, live call, spending, dependency, database migration,
  or change to dated historical records.

Verification:

- Complete offline suite: 549 passed, 2 expected opt-in skips.
- Ruff lint and format checks passed; `git diff --check` passed.
- Offline evaluation passed; all deterministic cases passed with no live comparison.

Next phase:

- No phase after MVP-7.1 is authorized. A future unified run-economics phase should be
  separately authorized before extending MiMo-only budget accounting to Exa and Firecrawl.

## 2026-08-10 - MVP-6.9 Acquisition and Configuration Integrity

Status: Complete and verified. MVP-6.8 was confirmed complete before implementation.
No phase after MVP-6.9 was started.

- Added frozen strict `VerifiedAcquisitionPreflight` and `MediaTypeProvenance` artifacts.
  ResearchAssistant's bounded source preflight is the only authority for verified origin
  media type, and that evidence remains tied to its validated final URL. Approved primary
  failures carry the typed preflight into Firecrawl fallback.
- Firecrawl Markdown without applicable preflight evidence is represented as
  `text/markdown`. Sanitized `metadata.contentType` values are retained only as separate
  provider declarations; missing, blank, malformed, unsupported, and non-string values
  remain unknown. Conflicts do not overwrite verified evidence.
- Preserved the existing redirect, returned-source, canonical-URL, credential, public-host,
  and SSRF checks. Firecrawl fallback now requests the already validated final URL, while
  normalization identity remains distinct from origin media-type provenance.
- Added atomic SQLite migration 7. New snapshots persist original/canonical URL context,
  normalization/acquisition identity, provider identity, and canonical provenance JSON.
  Existing rows are not rewritten and reconstruct with explicit unknown provenance.
- Bumped acquisition identity to `mvp6.9-acquisition-provenance-v3`, Firecrawl adapter
  identity to `mvp6.9-firecrawl-media-provenance-v3`, and both execution fingerprint
  identities to `mvp6.9-acquisition-configuration-integrity-v1`. Pre-MVP-6.9 acquisition
  fingerprints cannot resume under the changed semantics.
- Repaired the supported legacy MVP-2B boundary smoke example with blank
  `OPENROUTER_API_KEY=`, a valid 25,000-token ceiling, the actual gate names and approval
  phrase, and existing one-call/cost/output constraints. Offline construction proves the
  example is structurally valid; no execution gate or provider path was enabled.
- Replaced phase-bound package wording with `Evidence-constrained Debate Research Agent
  System with deterministic release validation.` and advanced only current-facing phase
  summaries. Historical records remain intact.
- Regression tests were added before implementation; the initial test module failed at
  collection on the deliberately missing provenance model. No dependency, provider call,
  integration-test opt-in, spending, commit, push, or pull request was added.

Verification:

- Focused Firecrawl/acquisition, URL-security, persistence/migration, fingerprint/resume,
  environment-example, package-metadata, and type-contract selection: 122 passed.
- Complete offline suite: 622 passed, 2 expected opt-in skips.
- Repository-wide type-contract test: passed in both focused and full suites.
- Offline evaluation: all 38 deterministic cases passed; no live provider comparison ran.
- Ruff lint passed; Ruff format check reported 65 files already formatted.
- `git diff --check`, final knowledge-graph refresh, secret/generated-artifact scan, and
  final worktree/diff review passed. No database, cache, coverage artifact, secret, or
  evaluation output is newly tracked.

Remaining limitation:

- Verified origin media type applies only to the exact final URL checked by preflight. If
  Firecrawl returns a different validated public source URL, the Markdown remains usable
  text but its origin media type is unknown; the earlier evidence remains recorded only
  against the URL for which it was established.

## 2026-08-10 - MVP-6.8 Persistence and Accounting Integrity

Status: Complete and verified. MVP-6.7 was confirmed complete before implementation.
MVP-6.9 and later phases were not started.

- Added atomic, idempotent SQLite migration 6. Four unconditional `BEFORE UPDATE`/
  `BEFORE DELETE` triggers reject direct mutation of existing `snapshots` and
  `ledger_records` rows with stable table-specific errors. Normal inserts, duplicate
  rejection, fixture execution, release reconstruction, and read-only inspection remain
  valid. No unrelated artifact table became immutable.
- Added strict exact USD handling in `money.py`. Configured ceilings, per-call caps,
  provider-reported costs, reservations, completed usage, aggregates, resume-time
  reconstruction, comparisons, provider results, inspection, and live summaries use
  finite non-negative `Decimal` values. Addition uses an explicit sufficient-precision
  local decimal context rather than the process default.
- Added canonical non-exponent SQLite text columns `reserved_cost_usd_exact` and
  `cost_usd_exact`. New writes use only those authoritative columns and leave legacy
  `REAL` values null. Noncanonical, negative, negative-zero, and non-finite exact values
  fail validation.
- Version-5 migration converts historical `REAL` values through their recoverable
  shortest float text. This is deterministic but cannot restore source decimal digits
  already lost to binary floating point; the migration does not invent precision.
- Bumped both provider fingerprints to
  `mvp6.8-persistence-accounting-integrity-v1` and accounting policy identities to
  `mvp6.8-exact-decimal-reserve-reconcile-v1`. Pre-MVP-6.8 runs require a new run ID for
  execution under the changed monetary semantics.
- Regression tests were added before fixes. The baseline produced 10 expected failures:
  direct SQL mutation, missing migration objects, precision loss, above-ceiling escape,
  exact-sum escape, and absent historical conversion. No dependency, provider call,
  provider spending, commit, push, or pull request was added.

Verification:

- Focused migration, immutability, exact-accounting, fixture reconstruction, resume,
  provider, CLI, and type-contract selection: 164 passed, 1 expected live-smoke skip.
- Complete offline suite: 605 passed, 2 expected opt-in skips.
- Repository-wide type-contract test: passed within both focused and full suites.
- Offline evaluation: all 38 deterministic cases passed; optional live comparison
  remained skipped.
- Ruff lint passed; Ruff format check reported 64 files already formatted.
- `git diff --check`, schema/trigger inspection, generated-tracked-artifact scan, and
  final worktree/diff review passed. No generated database, cache, coverage file,
  secret, or evaluation output is newly tracked.

Historical limitation:

- A pre-MVP-6.8 SQLite `REAL` contains only its already-rounded binary value. Migration
  preserves a deterministic decimal representation of that value, not an unrecoverable
  original provider string.

## 2026-08-09 - MVP-6.7 Repository-Wide Type Contract Enforcement

Status: Complete and verified. MVP-6.5 and MVP-6.6 were confirmed complete before
implementation. The contradiction-audit remediation sequence is complete. No phase
after MVP-6.7 has started or been authorized.

- Added `tests/test_type_contracts.py`, a deterministic dependency-free AST enforcement
  test. It scans repository-owned Python beneath the repository root while excluding
  recognized virtual-environment, cache, vendor, coverage, and build-output locations;
  sorts paths and diagnostics; parses every file; visits sync/async and nested functions;
  checks all parameter categories and returns; permits only unannotated `self`/`cls`;
  and reports every violation with relative path, line, qualified name, and missing field.
- The independent pre-fix inventory found 61 Python files, 1,195 function definitions,
  and 11 missing annotations across seven signatures in five test files. The enforcement
  test was added first and failed with all 11 diagnostics before correction.
- Corrected signatures in `tests/test_mvp1.py`, `tests/test_mvp3a_pipeline.py`,
  `tests/test_mvp6_3_security.py`, `tests/test_phase4.py`, and `tests/test_phase8.py`.
  Types use `pytest.MonkeyPatch`, `Path`, `Iterator[bytes]`, existing provider pipeline
  configuration/result contracts, `LLMRequest`, and the fake provider's accurate narrow
  result union. The two affected `type: ignore[no-untyped-def]` comments were removed.
- Function bodies, fixture parameter names, monkeypatch behavior, decorator ordering,
  assertions, expected values, runtime contracts, Pydantic schemas, and acceptance
  criteria are unchanged. No broad `Any`, replacement suppression, dependency, SQLite
  migration, provider call, provider spending, generated tracked artifact, or commit was
  added.

Verification:

- Regression-first baseline: isolated enforcement failed with all 11 expected
  diagnostics before corrections; after corrections it passed, 1 passed.
- Focused suites for every annotation-touched file: 145 passed, 1 expected opt-in skip.
- Complete offline suite: 579 passed, 2 expected opt-in skips.
- Offline evaluation: all 38 deterministic cases passed; optional live comparison
  remained skipped.
- Independent AST inventory after correction found zero missing annotations in 62
  repository-owned Python files.
- Ruff lint and format, in-memory Python compilation, launcher `zsh -n`, suppression and
  assertion-diff audits, dependency/migration/provider/generated-artifact/history scope
  audits, and `git diff --check` passed.

Known limitation:

- The enforcement is intentionally syntactic. It requires explicit annotations and
  prevents omissions, but it is not a substitute for a full static type checker and adds
  no such dependency.

## 2026-08-09 - MVP-6.6 Runtime Status, Budget, and Contract Integrity

Status: Complete and verified. MVP-6.5 was confirmed complete before implementation.
MVP-6.7 and the remaining repository-wide type-hint phase have not started.

- Added stable `CLIExitCode.RUNNING = 13`. Direct provider results, `inspect-run`, CLI
  subprocesses, and live-web snapshots map every `ProviderRunStatus` explicitly and
  reject unsupported future states. RUNNING output identifies the current stage without
  printing a final brief. Exit 0 remains released research or separately documented
  administrative acceptance; `cancel-run` still returns 0 only after persistence.
- Added frozen strict `ModelUsageAccounting`. Zero attempts are exact complete zero.
  Complete attempts aggregate exact token/cost values; missing token or cost components
  make only that exact aggregate unknown while preserving known subtotals, missing
  attempt IDs, and conservative reserved exposure. CLI and web displays label
  incompleteness rather than showing zero or a partial value as a total.
- Budget enforcement now uses total tokens or complete input/output totals when present,
  otherwise the full reservation. Failed, timed-out, interrupted, and running attempts
  are not inferred free. Unknown usage never releases reservation exposure; retry and
  fallback fail when remaining budget cannot be proven. Exact-limit, physical-call, and
  strict per-call reservation checks remain valid.
- Added dependency-light canonical provider-contract handling shared by both factories
  and `ProviderRunContract`. The contract is frozen and rejects invalid/duplicate JSON,
  missing/extra/non-string keys, noncanonical bytes, duplicated-field mismatch, and an
  incorrect SHA-256 during construction and persisted reconstruction. Tampering blocks
  resumption before provider work. Valid historical canonical payloads remain readable;
  `run_id` and `created_at` remain outside fingerprint inputs.
- Kept the existing payload inputs and fingerprint-version labels. The executable
  repository identity naturally changes because runtime code and its new canonical
  helper changed. Added no dependency or SQLite migration. No provider call or provider
  spending occurred. No commit was created.

Verification:

- Regression-first baseline: the new focused test module failed during collection on
  the absent typed `summarize_model_usage` API before implementation.
- Required focused CLI/subprocess, inspection, usage/budget, retry/fallback/failure,
  cancellation/reopening, contract persistence/tampering, MVP-4, MVP-5, Phase 9, MVP-3A,
  and MVP-6.5 selection: 143 passed, 1 expected opt-in skip.
- Complete offline suite: 578 passed, 2 expected opt-in skips.
- Offline evaluation: all 38 deterministic cases passed; optional live comparison
  remained skipped.
- Ruff lint passed; Ruff format check reported 61 files already formatted.
- In-memory Python compilation passed for 61 files; launcher `zsh -n`, CLI help, and
  `git diff --check` passed.
- Final status-mapping, usage calculation/display, provider-contract construction/read,
  dependency, migration, generated-artifact, provider-call, and diff reviews passed.

Known limitation:

- A historical potentially chargeable attempt with incomplete usage and no stored
  reservation remains inspectable and cancellable, but another budgeted physical call
  is refused because remaining budget cannot be proven. MVP-6.6 does not fabricate
  historical usage. Exa and Firecrawl billing remains external to MiMo accounting.

## 2026-08-09 - MVP-6.5 Immutable Run Authority and Read-Only Inspection

Status: Complete and verified. MVP-6.2 Batch A, MVP-6.3, and MVP-6.4 were confirmed
complete prerequisites. MVP-6.6 has not started.

- Added atomic SQLite migration 5,
  `database-enforced immutable runs.raw_claim`, and corrected migration 4 to
  `same-run provenance protection triggers`. Trigger `runs_raw_claim_immutable` rejects
  every actual `raw_claim` change for every status with the stable message
  `runs.raw_claim is immutable`; identical-value assignments and other mutable run
  updates remain valid. The application-level guard remains defense in depth.
- Migration 5 creates and verifies the trigger before inserting its migration record in
  one explicit transaction. Conflicting or failed installation leaves version 5
  unrecorded. Reopen is idempotent, existing claim bytes are untouched, and the public
  column shape is unchanged.
- Added a strict typed compatibility result/error and cohesive `ReadOnlyStore`. It safely
  encodes resolved paths, opens existing files with SQLite URI `mode=ro`, enables foreign
  keys and row handling, sets connection-local `query_only`, and validates the integrity,
  exact migrations, required tables, indexes, triggers, and migration-5 trigger contract.
  It does not use `immutable=1` or writable fallback.
- `inspect_provider_run`, CLI `inspect-run`, live history, live reopening, and their
  transitive store reads no longer call `init_db()` or reopen writable connections.
  Missing files, invalid SQLite, older schema, newer schema, corrupt schema, and
  permission/open failures are distinguished without mutation. Missing web history
  remains empty without file creation. Older databases require an intentional writable
  run or resume to migrate.
- Preserved typed reconstruction, partial/RUNNING and terminal inspection, bounded
  deterministic history, WAL concurrency, writable initialization/resume, same-run
  provenance, insert-only evidence, cancellation, and released-brief hash verification.
  The old claim-tampering inspection test now expects prevention at SQLite; a separate
  released-hash corruption test preserves reconstruction-integrity coverage.
- Added no dependency, ORM, provider call, or provider spending. No commit was created.

Verification:

- Regression-first baseline: the new focused suite failed at collection on the absent
  migration-5/read-only APIs before implementation.
- Focused persistence/migration, Phase 9 orchestration/inspection, MVP-4 CLI/subprocess,
  MVP-5 history/reopening, concurrency/cancellation, fixture reconstruction, provider
  restart, and release-integrity selection: 206 passed, 1 expected opt-in skip.
- Complete offline suite: 543 passed, 2 expected opt-in skips.
- Offline evaluation: all 38 deterministic cases passed; optional live comparison
  remained skipped.
- Ruff lint passed; Ruff format check reported 59 files already formatted.
- Python compilation, launcher `zsh -n`, and `git diff --check` passed.
- Direct temporary-schema inspection confirmed migration rows 1-5 and exact trigger SQL.
  Read-only inspection preserved the database SHA-256 byte-for-byte; focused tests also
  preserved schema objects, migration rows, and file modification time.
- Final dependency, provider-call, generated database/cache/coverage artifact, Git diff,
  and worktree reviews found no unrelated change or provider execution.

## 2026-08-09 - MVP-6.4 Evidence Density Threshold Calibration

Status: Complete and verified. MVP-6.2 Batch A and MVP-6.3 were confirmed complete
prerequisites. MVP-6.5 has not started.

- Changed current provider-backed quotation density from 75/75 to 50 words only when
  exact quoted segments contain both a digit and a recognized statistical marker, and
  75 words otherwise. A digit alone, marker alone, or incidental substring uses 75;
  marker matching remains case-insensitive and bounded by whole word/token boundaries.
- Kept one strict current `QuoteLengthPolicy` shared by initial filtering, Analyst input
  verification, and Ledger admission verification. Exact membership, segment order,
  offsets, immediate context, hashes, boundary markers, ellipsis counting, claim
  keywords, truncation, and provenance are unchanged. Invalid model output is rejected
  before ID assignment and is never healed or expanded.
- Preserved frozen fixture replay under the explicitly named
  `legacy-frozen-fixture-50-100-v1` policy. New provider-backed calls use the current
  default and never select that legacy object. Historical artifacts remain under their
  recorded identities and are not reinterpreted.
- Updated the shared Extractor prompt and direct MiMo instruction to state the exact
  digit-plus-marker classification, 50/75 thresholds, exact-source/no-healing rule, and
  authoritative Python validation.
- New identities are evidence policy `mvp6.4-evidence-density-50-75-v1`, Extractor
  prompt `mvp6.4-extractor-50-75-v1`, provider post-filter validator
  `mvp6.4-provider-post-filter-50-75-v1`, and canonical provider fingerprint
  `mvp6.4-evidence-density-fingerprint-v1`. The Extractor prompt SHA-256 is
  `a4f95d7468e22f6e95961d409ed7f99910ffe911b1a1788fb409b64bfc9725eb`;
  the aggregate five-prompt identity is
  `49cc02aee6025c4d2bf4a50b8ccfd97a23cb896f15ff8ecb650704ad45db33a2`.
- Both provider factory fingerprints include the current evidence-policy identity. A
  persisted 75/75 identity fails exact resume compatibility under 50/75 and requires a
  new run ID after restart. Reviewer approval, literal entailment, qualification,
  Ledger admission, renderer behavior, and final validation were not weakened.
- Added no dependency and no SQLite migration. No Exa, Wigolo, Firecrawl, MiMo,
  OpenRouter, or other live provider call or spending occurred. No commit was created.

Verification:

- Regression-first baseline: the new focused selection failed in 9 expected policy,
  prompt, and fingerprint assertions before implementation.
- Focused Researcher, Analyst, Reviewer, Ledger, renderer, final-validator,
  provider-fingerprint/resume, and frozen-fixture selection: 240 passed, 1 expected
  opt-in skip.
- Full offline suite: 517 passed, 2 expected opt-in skips.
- Offline evaluation: all 38 deterministic cases passed.
- Ruff lint passed; Ruff format check reported 58 files already formatted.
- Python compilation, launcher `zsh -n`, and `git diff --check` passed.
- Full tracked stale-policy search found only clearly dated historical 75/75 or labeled
  legacy 50/100 references. Final diff inspection found no unrelated behavior,
  dependency, database migration, generated cache/coverage artifact, or provider-call
  path execution.

## 2026-08-09 - MVP-6.3 Public Acquisition and Provenance Security

Status: Complete and verified. MVP-6.2 Batch A was the confirmed prerequisite. No phase
after MVP-6.3 has started.

- Disabled automatic source redirects and added an explicit exact-limit loop for 301,
  302, 303, 307, and 308. Every initial and redirect destination is validated before
  its request; relative targets, malformed/missing locations, loops, mixed DNS answers,
  response closing, and exact boundary behavior are covered offline.
- Strengthened the shared public URL policy for credential-free HTTP(S), valid public
  hostname syntax, prohibited local forms, global literal IPs, mandatory resolver
  success, and exclusively global resolved addresses. Unsafe destinations are never
  requested.
- Changed HTML acquisition to send Wigolo the validated final preflight URL. Firecrawl
  now validates its direct request URL, returned `sourceURL`, and recognized canonical
  provenance, failing closed on malformed, conflicting, or unsafe metadata. The narrow
  fallback allowlist is unchanged; redirect and public-source policy failures do not
  activate fallback.
- Bumped acquisition identity to `mvp6.3-public-acquisition-v2`, Firecrawl adapter
  identity to `mvp6.3-firecrawl-provenance-v2`, and direct-MiMo fingerprint identity to
  `mvp6.3-public-acquisition-fingerprint-v2`. Pre-MVP-6.3 persisted runs require a new
  run ID; historical artifacts are not reinterpreted.
- Residual limitation: validation DNS and transport DNS are separate lookups, and
  Wigolo independently fetches the validated final URL. Addresses are not socket-pinned,
  so complete DNS-rebinding protection is not claimed.
- Added no dependency and no SQLite migration. No Exa, Wigolo, Firecrawl, MiMo, or other
  live provider call or spending occurred.

Verification:

- Focused acquisition, Firecrawl, provider-factory, and persistence compatibility:
  159 passed.
- Full offline suite: 501 passed, 2 expected opt-in skips.
- Offline evaluation: all 38 deterministic cases passed.
- Ruff lint passed; Ruff format check reported 58 files already formatted.
- Python compilation, launcher `zsh -n`, and `git diff --check` passed.
- Final diff inspection found only MVP-6.3 implementation, tests, and documentation.
  `pyproject.toml`, `requirements.txt`, and `store.py` are unchanged. Tests use injected
  mocked transports and resolvers. Generated repository cache/coverage artifacts were
  removed, and no commit was created.

## 2026-08-09 - MVP-6.2 Batch A Records and Runtime Reporting

Status: Implemented and verified. MVP-6.2 remains in progress; only Batch A was
authorized. Later security, database, accounting, evidence-policy, and model-contract
batches remain pending approval and implementation. No phase after MVP-6.2 has started.

- Corrected current phase authority and the committed MVP-6/MVP-6.1 record without
  rewriting legitimately historical earlier chronology. Added the canonical MVP-6.2
  plan and documented its separately approved batch boundary.
- Replaced current SearXNG operating guidance with Exa Search `auto` metadata discovery,
  pinned loopback Wigolo `0.2.1` primary acquisition, optional narrowly gated Firecrawl
  fallback, and direct Xiaomi `mimo-v2.5-pro`. Historical SearXNG compatibility remains
  clearly labeled for old persisted runs.
- Updated secret-free CLI launch reporting and assertions to show Exa, Wigolo, MiMo,
  configured endpoints, and Firecrawl enabled/disabled state.
- Corrected the README's two expected opt-in skips and package description. Removed the
  accidentally tracked `.coverage` binary and ignored future `.coverage` output; the
  deletion remains recoverable from Git history.
- Added no dependency, provider behavior, or database migration. No provider call or
  spending occurred.

Verification:

- Focused CLI suite: 13 passed, 1 expected MVP-4 live-smoke skip.
- Full suite: 469 passed, 2 expected opt-in skips (Phase 8 live-LLM gate and MVP-4 live
  CLI smoke).
- Offline evaluation: all 38 deterministic cases passed.
- Ruff lint and format, launcher shell syntax, and `git diff --check` passed.

## 2026-08-09 - MVP-6.1 Live Worker Test Fix (`c10c844`)

Status: Complete and committed.

- Added a bounded poll so the live-worker redaction test waits for its background worker
  to leave the starting state before asserting the failed result.
- The `.coverage` binary committed alongside the test fix was accidental verification
  output and is removed from tracking by MVP-6.2 Batch A.

## 2026-08-01 - MVP-6 Post-Audit Boundary Corrections (`6e0f434`)

Status: Complete and committed as MVP-6 work.

- Connected already-normalized digital PDF text to the researcher snapshot path while rejecting
  unnormalized PDF payloads and preserving the `application/pdf` origin type.
- Removed the aggregate candidate-acquisition deadline; individual HTTP/PDF/browser deadlines
  remain bounded.
- Enforced the then-current MVP-6 75-word minimum during every downstream candidate verification and aligned
  the direct MiMo extractor instruction with 75 words.
- Expanded live redaction to all MiMo, Exa, and Firecrawl key values.
- Rejected leading/trailing claim whitespace at the direct pipeline boundary instead of silently
  changing the authoritative claim.
- Restricted package metadata to the tested Python 3.11/3.12 range.
- Enforced public-only acquisition targets across initial URLs, DNS resolution, and redirects.
- Made persisted claims immutable, verified released brief hashes on inspection, and added
  migration 4 guards against cross-run artifact splicing.
- Replaced MiMo's full artifact output contract with semantic-only response models; application
  code now constructs IDs, timestamps, provenance, routing fields, and synthesis templates.
  Extractor output is no longer silently rewritten.
- Aligned live concurrency with the per-database lock: different database files may run in
  parallel, but two runs cannot write the same SQLite database concurrently.
- Removed the unused `python-dotenv` dependency and any implied automatic `.env` loading.

Verification:

- Focused regression tests passed; the full offline suite passed with 468 tests and 2 skips.
- All 38 deterministic evaluation cases, Ruff lint/format, launcher syntax, and diff checks passed.
- No provider call was made. One unused dependency was removed and SQLite migration 4 added
  same-run integrity triggers.

## 2026-08-01 - MVP-6 Bounded-Inference Evidence Policy (`37c52a7`)

Status: Complete and committed as part of MVP-6; final full-suite verification is
recorded below.

- Changed both statistical and non-statistical quote minima to 75 words.
- Updated Analyst and Reviewer prompts so literal, materially relevant facts need not
  independently prove the complete claim, while unsupported necessity, sufficiency,
  causal, or generalized language remains rejectable.
- Mapped Claim Fit 5/4/3 to Strong/direct, Partial/indirect, and Weak/contextual evidence,
  retained qualification gates, and added cautious application-owned connective text.
- Added a deterministic coverage warning to every one-sided released brief. Zero-Ledger
  runs continue to fail closed.
- Versioned the extractor, analyst, reviewer, evidence policy, and final validator; new
  policy identity requires a new run ID. No dependency or database migration was added.
- Preserved deterministic replay of frozen fixture runs through an explicit legacy
  50-statistical/100-non-statistical quote policy. New provider-backed runs always use
  the current 75-word policy.
- Corrected the live-run conflict discovered by run
  `fabaaaf4-6624-4543-a745-9884791fd612`: Claim Fit 4 Partial evidence no longer needs an
  artificial in-statement keyword after exact-source and Reviewer approval, while Claim
  Fit 3, qualified-only, and Weak evidence remain gated. Failures now identify the stage
  being attempted, and stance model-attempt cards use persisted artifact provenance.
- Bumped the evidence policy identity to `post-mvp5-bounded-inference-v2`; use a new run
  ID after restarting the launcher.

Verification:

- Full offline suite: 461 passed, 2 skipped.
- Offline evaluation: all 38 deterministic cases passed.
- Ruff lint/format, launcher syntax, and `git diff --check` passed.
- No Exa, Wigolo, Firecrawl, or MiMo call was made; added provider cost is zero.

## 2026-08-01 - MVP-6 Exa/Wigolo/Firecrawl Provider Correction (`37c52a7`)

Status: Complete and committed as part of MVP-6 live research stabilization.

Completed:

- Replaced SearXNG discovery for new direct-MiMo runs with Exa Search `auto`. Requests
  contain the query, five-result limit, and explicit domain exclusions only; provider
  text never enters the evidence surface.
- Kept pinned loopback Wigolo `0.2.1` as primary acquisition and added optional
  Firecrawl v2 scrape fallback. Fallback is limited to Wigolo-local connection, timeout,
  malformed-response, extraction, or challenge failures and cannot bypass source access,
  paywall, authentication, content-type, size, or redirect failures.
- Added strict secret-safe Exa/Firecrawl configurations, mocked HTTP adapters, immutable
  fingerprint identities, and launcher prompts. `EXA_API_KEY` is required;
  `FIRECRAWL_API_KEY` is optional and its absence leaves Wigolo-only acquisition.
- Removed native SearXNG launch settings from the application-owned Wigolo process while
  preserving the completed research pipeline, SQLite schema, validators, MiMo route,
  and rank-five/keep-three policy.

Verification:

- New provider regression suite: 14 passed.
- Full offline suite: 451 passed, 2 skipped.
- Offline evaluation: all 38 deterministic cases passed.
- Ruff lint/format, launcher syntax, and `git diff --check` passed.
- No live Exa, Wigolo, Firecrawl, or MiMo call was made; added provider cost is zero.

Operator note:

- Double-click the launcher and enter MiMo and Exa keys. Enter a Firecrawl key in the
  optional third prompt to enable fallback, or leave it blank for Wigolo-only fetching.
- Provider changes are fingerprinted. Use a new run ID rather than trying to resume a
  run created under the former SearXNG identity.

## 2026-08-01 - MVP-5 Polished Local Live Web Interface

Status: Complete. The earlier scheduled-live-validation placeholder was superseded by
the user's explicit MVP-5 web-interface direction. MVP-6 has not started.

Completed:

- Added a separate polished live Streamlit page with exact-claim input, explicit token/
  USD/call budgets, optional run ID, safe selectable SQLite location, persisted run
  history/inspection, authoritative stage/checkpoint/usage/cost and stance progress,
  cooperative cancellation, deterministic terminal displays, released brief/hash, copy-
  friendly rendering, download, and prominent human-review warnings.
- Reused `run_mvp3b_pipeline()`, `inspect_provider_run()`, SQLite, provider contracts,
  fingerprints, checkpoints, budgets, restart behavior, cancellation, and exact MVP-4
  exit semantics. No second pipeline, provider, dependency, schema migration, or timeout
  change was added.
- Kept the original Streamlit page explicitly fixture-only. It never implies that
  fixtures use MiMo, Wigolo, or live search.
- Added a background live controller plus per-database cross-process lock. Streamlit
  reruns, refreshes, and browser sessions reconnect to SQLite and cannot start duplicate
  workers for the same database while one is active.
- Added pinned Wigolo `0.2.1`/native-SearXNG health, launch, progress, monitoring,
  redaction, and process-group ownership. Only application-owned children may be stopped;
  exact health is required and unrelated listeners are never killed.
- Added a macOS click launcher. It uses a native hidden-input dialog when the launch
  environment lacks `MIMO_API_KEY`, exports the value only to the local server process,
  and never persists it or puts it in browser state, URLs, logs, SQLite, or arguments.
- Added strict Pydantic live UI/service artifacts, safe existing-SQLite validation,
  bounded diagnostic classification for Wigolo/SearXNG/retrieval/MiMo/validation/stages,
  and a read-only persisted run-history store helper.
- Fixed the live form acknowledgement deadlock: healthy/configured users can submit the
  form, while an unchecked public/non-sensitive and human-review confirmation fails
  visibly before any run or provider spend begins.

Verification:

- Focused MVP-5: 17 passed.
- MVP-5 plus MVP-4 subprocess and fixture-frontend suites: 33 passed, 1 skipped.
- Full offline suite: 437 passed, 2 skipped.
- Offline evaluation: all 38 deterministic cases passed.
- Fixture smokes: valid released with hash
  `7fecea19e1b9f01ff3fe68ef9a2b3a79cf88f0a6fe82897332548c258cb9e89f`; invalid blocked
  with the expected `altered_statement` error.
- Mocked live-web smoke released, persisted, reopened through the Streamlit page, and
  exposed final brief/hash/download without the test credential appearing in process
  output, rendered messages, or SQLite.
- In-app browser smoke verified responsive missing-configuration/service displays,
  disabled unsafe start, readable desktop layout, exact live identity, and prominent
  human review. No actual provider call was made.
- Clean Python 3.12.13 environment installed `requirements.txt`; live UI/service imports
  and Streamlit 1.60.0 CLI passed. Python 3.11 was not locally installed and remains in
  the existing CI matrix. Local Node.js 24.18.0 and npm/npx 11.16.0 exceed the documented
  Node.js 20+ requirement.
- Ruff lint/format, launcher syntax, `git diff --check`, restart/cancellation subprocess
  coverage, service ownership/cleanup, and final Git status passed.
- Optional real MiMo/Wigolo browser test was not run; additional live cost is zero.

Known limitations:

- First-time Python/Node installation and Wigolo/SearXNG downloads remain setup steps.
  Normal macOS use thereafter is click-to-launch, with a secure key prompt when needed,
  but a visible local server process must remain running while the website is open.
- Cold/degraded native SearXNG can still exceed the unchanged fail-closed 15-second
  Search deadline. The page surfaces the responsible component/stage; it does not hide
  or indefinitely extend timeouts.
- Cancellation remains cooperative. An active synchronous provider request may finish
  or reach its deadline, and arbitrary cross-version crash recovery is not promised.
- The website is loopback/local-only with no accounts, authentication, hosting, uploads,
  cloud deployment, or scheduled automation. Direct-MiMo cost remains estimated.
- Public/non-sensitive claims and human review are mandatory.

Next exact task:

- None authorized. Do not begin MVP-6.

## 2026-08-01 - MVP-4 Usable Live CLI and MVP Release

Status: Complete. The repository is honestly a usable command-line MVP within the
documented external Wigolo/SearXNG and human-review limits. MVP-5 has not started.

Completed:

- Added `run` around the released direct-MiMo pipeline with exact claim input, explicit
  SQLite path, optional run ID, mandatory token/cost budgets, approved call ceiling,
  process-environment validation, and secret-free launch disclosure.
- Froze exit codes: released `0`, blocked `10`, failed `11`, cancelled `12`, configuration
  error `20`, and invalid input `21`. Released output includes the validated brief/hash;
  other terminal states print their deterministic validation errors or normalized stage,
  reason, and cooperative boundary.
- Expanded `inspect-run` to display authoritative claim/status, all checkpoints,
  retrieval/model attempts and failures, validation errors, usage/cost, provider/adapter/
  model/prompt/schema/normalization/policy/repository/fingerprint identities, and released
  brief/hash.
- Kept cancellation database-backed and process-independent. A subprocess proof requested
  cancellation while a mocked Planner call was active; that call completed and persisted,
  cancellation was then observed, and no subsequent call started.
- Strengthened the direct-MiMo fingerprint with operational Wigolo/deadline/acquisition,
  completion-token, call/token/cost budget, and executable source/prompt/project identity.
  Any budget change requires a new run ID; consumed usage is never reset.
- Added 12 normal MVP-4 tests plus one doubly gated optional live CLI smoke. Normal
  subprocess tests use the real CLI/orchestration/factory surfaces with mocked HTTP.
- Updated only current release documentation and environment examples. The fixture-only
  Streamlit frontend is unchanged. No dependency, database schema, Docker, hosting,
  account, broad packaging, or MVP-5 work was added.

Verification:

- Focused MVP-4 suite: 12 passed, 1 skipped.
- Full offline suite: 420 passed, 2 skipped.
- Offline evaluation: all 38 deterministic cases passed; optional live comparison skipped.
- Fixture smokes: valid released with hash
  `7fecea19e1b9f01ff3fe68ef9a2b3a79cf88f0a6fe82897332548c258cb9e89f`; invalid blocked
  with the expected `altered_statement` error.
- Mocked live CLI smoke: released with hash
  `8d5cea39448d9e1389497c72a5332bcaac86586282fb8b365ac7f18116059742`.
- Restart, changed-claim, changed-fingerprint/budget, redaction, inspection, exact exit
  codes, and second-process cancellation checks passed.
- A clean Python 3.12.13 virtual environment installed `requirements.txt`; CLI help and
  clean runtime imports passed. Python 3.11 was not locally available; the declared
  `>=3.11` support and Python 3.11/3.12 CI matrix remain unchanged.
- Ruff lint/format and `git diff --check` passed. Changes remain uncommitted.
- The optional live CLI canary was not run because the exact enable/approval gates were
  not supplied; observed additional live cost is zero.

Known limitations:

- Native SearXNG must already be bootstrapped/warmed and Wigolo `0.2.1` must already be
  running on loopback. The CLI validates configuration and provider identity but does not
  own process startup, supervision, or shutdown.
- Cold or degraded Search can exceed the fixed fail-closed deadline. Direct-MiMo costs
  remain conservative frozen-policy estimates rather than provider-confirmed billing.
- Cancellation is cooperative, not immediate. Arbitrary cross-version crash recovery is
  unsupported. The Streamlit UI remains fixture-only.
- Public/non-sensitive claims only. Every release, especially high-stakes use, requires
  human review.

Next exact task:

- None authorized. Do not begin MVP-5 without explicit user direction.

## 2026-07-31 - MVP-3B Full Live-Canary Stabilization

Status: Complete; the approved direct-MiMo positive canary released and the controlled
negative canary failed safely. MVP-4 has not started.

Completed:

- Replaced the MVP-3B LLM route with direct Xiaomi `mimo-v2.5-pro` for all five roles;
  no OpenRouter or MiniMax call occurred in either accepted canary.
- Proved pinned loopback Wigolo `0.2.1` discovery/acquisition with native SearXNG and
  Python 3.12.13. Core-only search degraded to irrelevant results; the bootstrapped
  SearXNG backend returned relevant medical sources while retaining the fixed balanced,
  five-result, no-fetch request and 15-second Search deadline.
- Added only live-demonstrated compatibility fixes: Wigolo native domain exclusions and
  serialized Search calls; thread-safe cross-stance URL/content deduplication; direct-MiMo
  prompt/schema diagnostics and deterministic Planner/Extractor/Analyst/draft/synthesis
  identity or policy fields; exact source whitespace/context and non-contiguous quote
  normalization; stance-bound Analyst scoring; usage/cost parsing; and approved connective
  template stamping from immutable Ledger records.
- Positive claim: `For adults with hypertension, regular aerobic exercise lowers resting
  systolic blood pressure.` Run `2eb99893-b919-40c9-b5b8-b482b61e1c57` released after
  deterministic final validation. It used 6 Search calls, 13 acquisitions, 9 snapshots,
  34 physical MiMo calls, 145,738 tokens, and an estimated USD 0.080223. Its persisted
  brief reconstructs stably with SHA-256
  `4f17c54f0b2d475552266026d5b6c0dd84b91a0044c1e60970dfc2e9526551ba`.
- Negative claim: `The Moon is Earth's only natural satellite.` Run
  `4defb64a-1fe2-4249-b67f-fb61cd4a2974` reached the expected typed `failed` state at the
  Researcher boundary when its approved one-call LLM ceiling was consumed by the Planner.
  It used 6 Search calls, 29 acquisitions, 12 snapshots, 1 physical MiMo call, 3,255
  tokens, and an estimated USD 0.0025555. Persistence reconstruction and secret-redaction
  checks passed.
- Both canaries used dedicated `/tmp` SQLite databases, public non-sensitive claims,
  explicit one-run approval and enable gates, strict deadlines/retries, fail-closed frozen
  pricing, and explicit maxima of 6 Search calls, 30 acquisitions, 18 snapshots, 160
  physical LLM calls, 1,000,000 tokens, and USD 1.00 for the positive run. No credential
  was found in either persisted database.

Verification:

- Focused provider, mocked pipeline, restart, and cancellation suite: 108 passed.
- Complete offline suite: 408 passed, 1 skipped.
- Offline evaluation: all 38 deterministic cases passed; optional live comparison skipped.
- Ruff lint and format checks passed.
- Persisted positive reconstruction, `git diff --check`, and final Git status passed.
- Changes remain intentionally uncommitted.

Remaining:

- Wigolo core-engine quality is unstable when only Bing remains healthy. MVP-3B success
  depends on an already bootstrapped native SearXNG sidecar and Python 3.10+; this machine
  used the Codex runtime's Python 3.12.13. Process lifecycle remains external.
- One warmed balanced SearXNG probe completed in 11.28 seconds, but the preceding cold
  probe took 16.09 seconds. The fixed 15-second deadline remains fail-closed, so cold or
  degraded searches may still time out.
- Direct-MiMo costs are frozen-policy estimates, not provider-confirmed billing amounts.
- The stack is suitable to begin the separately approved CLI MVP, subject to explicit
  Wigolo/SearXNG lifecycle and preflight handling. Do not begin MVP-4 without approval.

Next exact task:

- MVP-4 live CLI release only after explicit user direction.

## 2026-07-24 - MVP-3A Mocked Full-Provider Pipeline Integration

Status: Complete offline; no live canary or product-surface work occurred.

Completed:

- Added a strict immutable provider factory/configuration boundary that constructs only
  Wigolo `0.2.1` Search/acquisition and OpenRouter adapters, validates the approved
  MiMo Pro/MiniMax M3 routes, explicit temperatures, strict structured output, usage,
  and exact pricing coverage, and keeps `OPENROUTER_API_KEY` redacted.
- Added `run_mvp3a_pipeline()` as the narrow configured entry into the existing
  `run_provider_pipeline()`; no live CLI command was added.
- Added the approved rank-five/keep-three policy without removing the legacy
  fake-provider default. Mocked full runs execute six five-result discoveries and keep
  three usable snapshots per query, producing at most 18 snapshots from at most 30
  acquisitions.
- Preserved the production normalizer's exact text/hash/word count as the immutable
  snapshot quote surface and continued deterministic exact-offset filtering.
- Added SQLite migration 3 for immutable provider run contracts plus pre-call token/cost
  reservation columns on normalized model route attempts.
- Persisted provider, adapter, model, prompt, schema, normalization/PDF/acquisition,
  retry, budget, pricing, repository revision, and policy identities in one exact run
  fingerprint. Same run ID/claim/fingerprint resumes; changed claim or fingerprint is
  rejected before resumption.
- Added atomic call/token/cost reservation before strict physical calls, exact usage
  reconciliation, usage retention on malformed and deterministic failures, shared
  persisted totals for retries/fallback, and fail-closed unknown route/pricing behavior.
- Normalized objective routing so authentication, permanent failure, refusal,
  returned-model mismatch, unknown pricing, malformed usage, and budget failure do not
  trigger fallback. Only approved objective failures permit primary, primary retry,
  fallback, and fallback retry.
- Added provider-boundary cancellation checks. Requests are persisted, no new call
  starts after observation, and an active synchronous request is allowed to finish and
  be recorded before cancellation completes.
- Added realistic mocked HTTP tests covering full release, deterministic block,
  authentication/provider failure, malformed discovery, inaccessible and unsupported
  sources, fallback, fallback exhaustion, token/cost exhaustion, restart, fingerprint
  and claim incompatibility, terminal reinvocation, and cancellation after active LLM
  and Search boundaries.
- Added no live canary, live product CLI, Streamlit/frontend change, provider, browser
  automation, FastAPI, hosting, Docker, accounts, or MVP-3B work.

Verification:

- MVP-2B prerequisite boundary suite: 40 passed before implementation.
- Focused MVP-3A suite: 16 passed.
- Complete offline suite: 382 passed, 1 skipped; the skip is the existing explicitly
  opt-in live integration test.
- Offline evaluation: all 38 cases passed; optional live comparison skipped.
- Fixture CLI smokes: valid released with the expected stable hash; invalid blocked with
  no hash.
- Mocked full-provider smoke: passed.
- Ruff lint and format checks passed.
- `git diff --check` passed; final Git status is recorded in `HANDOFF.md`.

Remaining:

- Live Wigolo/OpenRouter payload, upstream identity, current pricing, deadlines, and cost
  reporting remain unproven until the separately authorized MVP-3B canary.
- Cancellation is cooperative and cannot interrupt an already-blocking synchronous HTTP
  request before it returns or reaches its deadline.
- The immutable fingerprint uses the caller-supplied repository revision; a future live
  command must supply a trustworthy exact revision/dirty-state identity.

Next exact task:

- MVP-3B live-canary stabilization only after explicit user direction.

## 2026-07-22 - MVP-2B Production Provider Adapters and Boundary Proof

Status: Complete offline; live boundary smoke not executed.

Completed:

- Added production-intended synchronous adapters for pinned loopback Wigolo `0.2.1` Search and
  bounded acquisition, plus direct strict-schema OpenRouter calls using MiMo Pro and MiniMax M3.
- Extended existing strict Search/Scraper contracts compatibly with provider identity, rank,
  discovery metadata, engine telemetry, URL/acquisition provenance, normalization/hash data, and
  retryable normalized failure classifications.
- Added explicit health/search/fetch/LLM deadlines, five redirects, streaming 10 MiB HTML/text and
  25 MiB PDF limits, content-type/signature checks, and exactly one controlled render retry after
  an explicit challenge or JavaScript-required result.
- Added versioned deterministic HTML, Markdown, plain-text, and narrow digital-PDF normalization;
  frozen fixtures prove byte-identical results, hashes, and exact quote offsets. Image-only and
  malformed PDFs are explicit unsupported content; OCR remains absent.
- Added direct OpenRouter JSON Schema requests with strict mode, parameter support required, data
  collection denied, no response healing, exact local Pydantic validation, exact returned-model
  checks, refusal/truncation/error normalization, and strict usage/cost handling.
- Added conservative per-model price caps, pre-call reservation checks, provider-cost recording,
  estimated-cap cost labeling when cost is absent, and full-run USD 1/token/call ceiling models.
- Migrated every default route to `mimo-v2.5-pro` with `minimax-m3` as the only fallback. Legacy
  aliases remain readable for existing artifacts; the offline evaluation corpus now tests the
  approved route while retaining frozen legacy quality comparisons as historical inputs.
- Added strict process-environment configuration and secret-safe representations. No `.env` file,
  alternate credential store, or implicit source is loaded.
- Added an ignored, fail-closed boundary smoke script requiring `--execute`, two explicit enable /
  approval gates, exact one-call limits, explicit token/cost caps, and an unused absolute output
  path. Credentials alone cannot run it.
- Added approved runtime dependencies: `httpx`, `markdown-it-py`, and `pypdf`. Node.js and pinned
  Wigolo `0.2.1` are documented live prerequisites.
- Added no SQLite migration, complete orchestration wiring, live product CLI/UI command, Streamlit
  change, browser automation, second provider stack, or MVP-3A behavior.

Verification:

- Focused MVP-2B boundary suite: 40 passed.
- Complete offline suite: 366 passed, 1 skipped. The skip remains explicitly opt-in.
- Offline evaluation: passed all 38 cases; default-route agreement 100%; optional live comparison
  skipped.
- Ruff lint and format checks passed.
- No live provider call or boundary smoke was executed, so observed live usage and cost are zero /
  unavailable. Mocked structured-output proof recorded 30 tokens and USD 0.001; cap-estimation
  proof recorded USD 0.0003.

Remaining:

- A separately approved live boundary smoke must validate the exact installed Wigolo response
  shape, OpenRouter route/model capability, upstream identity, and current cost reporting.
- Wigolo process lifecycle ownership is not connected; MVP-2B verifies a pre-existing loopback
  service identity. Full provider orchestration remains intentionally unconnected.
- No persistence schema was added for the new acquisition/model metadata because migration was
  explicitly prohibited.

Next exact task:

- MVP-3A mocked full-provider pipeline integration only after explicit user direction.

## 2026-07-21 - MVP-2A Architecture Gate

Status: Complete as a documentation-only architecture gate.

Completed:

- Inspected the repository's synchronous Search, Scraper, and LLM Protocols; strict
  prompt/output contracts; current aliases; call/retry paths; two-worker orchestration;
  budgets; snapshots/offsets; persistence/checkpoints; and attempt/version metadata.
- Evaluated two concrete stacks capable of a future live run: local Wigolo plus
  OpenRouter, and Brave Search plus local Python extraction plus OpenRouter.
- Selected pinned local Wigolo `0.2.1` for discovery/acquisition and OpenRouter with
  `xiaomi/mimo-v2.5-pro` for every LLM role plus `minimax/minimax-m3` as the only
  objective-failure fallback.
- Approved search as discovery-only, independent source fetches, rank-five/keep-three
  acquisition, separate original/final/advisory-canonical URLs, one controlled browser
  fallback, and no provider summary as snapshot content.
- Approved narrow deterministic digital-PDF support and explicit unsupported results for
  scanned, encrypted, malformed, empty, or unusably extracted PDFs.
- Defined ResearchAssistant-owned normalized plain-text snapshots, immutable refetch
  behavior, versioned normalization, a 3,000-word cap, and Python-verified exact quote
  offsets into persisted text.
- Defined strict OpenRouter JSON Schema/Pydantic handling, exact model provenance,
  objective retry/fallback, request deadlines, usage/cost reservation and reconciliation,
  public/non-sensitive data handling, secret protection, two-worker thread safety, and
  exact-fingerprint restart compatibility.
- Recorded expected normal and retry-heavy costs, proposed hard canary limits, observed
  Wigolo search/HTML/PDF/block canaries, minimum future modules, MVP-2B acceptance
  criteria, and decisions that still require user approval.
- Added no provider, dependency, environment variable, secret, network call, migration,
  live CLI behavior, test behavior, or MVP-2B implementation.

Files changed:

- `.agent/PLANS.md`
- `.agent/plans/phase-mvp-2a-architecture-gate.md`
- `ARCHITECTURE.md`
- `CONVENTIONS.md`
- `DECISIONS.md`
- `README.md`
- `STATUS.md`
- `HANDOFF.md`
- `AGENTS.md`

Verification:

- Full pytest: 310 passed, 1 skipped. The skip is the existing optional live Phase 8
  integration gate; no live option was enabled.
- Ruff lint passed; Ruff formatting check reported 34 files already formatted.
- Documentation consistency search found stale phase wording only inside dated
  historical handoffs/status entries, which remain point-in-time records.
- `git diff --check` passed.

Next exact task:

- MVP-2B live-provider implementation only after explicit user direction and approval
  of dependencies, limits/deadlines, environment-template changes, operator surface,
  and any persistence migration. MVP-2B has not started.

## 2026-07-19 - Daily Expanded CI Maintenance

Status: Complete.

Completed:

- Changed GitHub Actions from weekly to daily at 1:17 AM Pacific time and enabled push
  runs on every branch while retaining `master` pull requests and manual runs.
- Split CI into a Python 3.11/3.12 pytest matrix, one Ruff job, and one deterministic
  offline adversarial-evaluation job.
- Added the explicitly approved `pytest-cov` development dependency and branch-coverage
  reporting with missing lines and no minimum threshold.
- Added no live provider, API key, network-dependent test, or product runtime change.

Verification:

- Full pytest with branch coverage: 310 passed, 1 skipped; total coverage was 85% with
  missing lines reported and no minimum threshold.
- Offline evaluation: passed all 38 deterministic cases; optional live comparison was
  skipped.
- Ruff lint and format checks passed.
- Workflow YAML parsed successfully; `git diff --check` passed.

## 2026-07-19 - Phase MVP-1 Release-Contract Correctness

Status: Complete.

Completed:

- Removed model-authored title, displayed claim, and section headings from the
  Synthesizer input/output contracts.
- Added fixed application framing: `Research Brief`, `Claim under review`, the exact
  authoritative submitted claim, and fixed Supporting Evidence, Opposing Evidence, and
  Limitations headings.
- Added release validation for unknown/duplicate sections, canonical present-section
  order, hidden framing fields, extra model framing, and the existing complete Ledger,
  exact statement, stance, placement, entailment, template, and one-use rules.
- Added strict model-facing `ReviewerDecision`; provider-supplied approval IDs and other
  unknown fields are rejected.
- Added application-owned deterministic `rappr_v1_<sha256>` derivation after exact
  reviewed-text and decision validation, then construct the existing persisted/domain
  `StatementReviewResult`.
- Preserved legacy UUID Reviewer-result, Ledger, synthesis, and fixture readability at
  persistence boundaries. New approvals use `rappr_v1`; old serialized Synthesizer
  payloads containing framing fields are intentionally rejected and checked-in
  synthesis fixtures were updated.
- Kept legacy SQLite synthesis framing columns for database compatibility; their values
  no longer influence reconstructed synthesis or released framing.
- Fixed fixture terminal persistence so validation-blocked runs reopen as
  `RunStatus.BLOCKED`; released fixtures reopen as `RunStatus.COMPLETED`.
- Added ten focused MVP-1 tests for framing-field rejection, fixed rendering,
  adversarial framing/section attacks, application-generated stable/different IDs,
  pre-ID exact-text rejection, rejected decisions, legacy ID compatibility, and reopened
  fixture statuses, heading-like body text, and legacy SQLite framing. Existing revision,
  retry, restart, checkpoint, and persistence tests remain active.
- The independent verification pass corrected malformed nested synthesis handling so it
  blocks with a schema error instead of raising `AttributeError`, made provider validation
  use the persisted submitted claim directly, and aligned `ARCHITECTURE.md` with MVP-1.
- Added no dependency, live provider, network call, `.env` loading, live CLI command,
  frontend change, extraction-candidate work, cross-stance deduplication, database
  trigger, or unrelated schema redesign.

Compatibility effects:

- Existing persisted UUID approval IDs remain readable; new generated IDs are strings
  in the versioned `rappr_v1_<digest>` format.
- Existing SQLite synthesis rows remain readable, but their legacy title, claim, and
  heading columns are ignored by the domain/release path.
- Serialized pre-MVP-1 `SynthesisOutput` JSON with `title`, `claim_definition`, or
  `heading` is now rejected by design. Completed synthesis checkpoints backed by legacy
  SQLite rows remain readable; an interrupted run that has only a cached pre-MVP-1
  serialized synthesis result cannot resume through that artifact and requires a fresh
  run.
- Released brief text and hashes changed because framing is now fixed. The valid Phase 6
  fixture hash is `7fecea19e1b9f01ff3fe68ef9a2b3a79cf88f0a6fe82897332548c258cb9e89f`.

Verification:

- Focused MVP-1 suite: 10 passed.
- Relevant Phase 5, 6, 8, 9, and 10 suites: 126 passed, 1 skipped.
- Full repository suite: 310 passed, 1 skipped.
- The skip is the optional live Phase 8 integration test; no live option was enabled.
- Offline evaluation outside the repository: passed, 38 cases, no failures, optional
  live comparison skipped.
- Valid and invalid fixture CLI smoke runs outside the repository: released and blocked.
- Reopened fixture SQLite statuses: valid `completed`, invalid `blocked`.
- Ruff lint passed; Ruff format check reported 34 files already formatted and changed no
  files.
- `git diff --check`: passed.

Remaining risks:

- The SQLite synthesis tables retain ignored legacy framing columns until a separately
  authorized schema-cleanup phase.
- Release APIs rely on their caller to supply the authoritative submitted claim;
  fixture and provider orchestrators now pass and cross-check that value.
- Any consumer that treated the old model-authored framing fields or old rendered hashes
  as a stable external contract must migrate to the framing-free synthesis schema and
  new fixed release format.

Next exact task:

- No next phase was started. Further post-MVP hardening requires explicit user direction.


## 2026-07-17 - Phase 10 Evaluation and Adversarial Testing

Status: Complete.

Completed:

- Added a strict Pydantic, corpus-driven offline evaluation framework under
  `evaluations/`. JSON is accepted only at the corpus/output boundary; internal
  evaluation artifacts use `extra="forbid"` and immutable typed models.
- Added 38 deterministic frozen cases covering snapshot hashes, exact citation offsets,
  bracket context, final-validator mutations, unsupported claims, prompt injection,
  Analyst/Reviewer decisions, retrieval parity, primary/retry/backup/third-line routes,
  model quality, correlated errors, token/cost metadata, and completion time.
- Exercised the existing snapshot/bracket helpers and existing deterministic final
  validator directly. No validator, Reviewer rule, Ledger rule, route default, or prior
  implementation file was changed.
- Added machine-readable JSON and a human-readable Markdown summary derived from the
  same strict report, with an agreement guard and deterministic byte output for the same
  corpus.
- The final independent audit fixed narrow Phase 10 defects: regression fixture files
  now carry strict frozen expectations instead of existence-only descriptions; route
  fixtures must follow the configured aliases and one-retry path; every quality input
  must compare MiMo normal and Pro; token-bearing aliases require frozen pricing; and
  correlated-error coverage cannot be emptied or contradicted.
- Machine and human reports now label quality and pricing as frozen evaluation inputs,
  and the human summary includes per-stage quality, per-alias failure, route-agreement,
  token-coverage, and optional-live details from the same report.
- Added citation accuracy, snapshot integrity, bracket accuracy, unsupported-claim rate,
  validator escape rate, placement consistency, mutation attack block rate,
  prompt-injection resistance, score separation, Analyst and Reviewer rejection rates,
  retrieval parity, completion time, and fallback safety metrics.
- Added per-stage route outcome counts, primary success, retry, and fallback rates;
  per-alias malformed-output and exact-quote-failure rates; and frozen primary, retry,
  backup, and third-line fake-provider attempt paths.
- Added MiMo V2.5 versus MiMo V2.5 Pro quality deltas overall and by stage, plus the
  Extractor comparison between MiMo V2.5 and DeepSeek V4 Flash on the same frozen case.
- Added same-model Analyst/Reviewer correlated-error cases that remain visible by case
  ID in machine and human output.
- Added token/pricing recomputation for total cost, cost per successful artifact, and
  cost per completed run only when metadata is available.
- Added an optional live-comparison Protocol. Live comparison is skipped unless
  explicitly enabled, uses the exact frozen input/alias/snapshot identity when enabled,
  and has no repository live adapter or normal network dependency.
- Added explicit exit behavior for evaluation failures, configuration/execution
  failures, and unexpected internal errors. No case can disappear from the
  evaluated-case inventory.
- Added 30 Phase 10 tests attacking output production/agreement, metric calculations,
  snapshot/citation/bracket separation, prompt injection, hidden skipping, regression
  fixtures, validator immutability, exit codes, determinism, route consistency,
  fallback safety, live gating, correlated errors, cost arithmetic, failure rates, and
  strict corpus schemas.
- Added no dependency, live vendor, production UI, validator weakening, routing-default
  change, score inflation, hidden skip, or post-MVP hardening work.

Files changed:

- `evaluations/__init__.py`
- `evaluations/schema.py`
- `evaluations/evaluator.py`
- `evaluations/run_evaluations.py`
- `evaluations/README.md`
- `evaluations/cases/offline-corpus.json`
- `evaluations/cases/regression-fixtures/`
- `evaluations/output/.gitignore`
- `tests/test_phase10.py`
- `tests/fixtures/phase10/`
- `.agent/plans/phase-10-evaluation.md`
- `STATUS.md`
- `HANDOFF.md`

Verification:

- The four exact bare commands failed before project execution with
  `zsh: command not found: python` because bare `python` is not on `PATH`.
- The identical commands with `PATH="$PWD/.venv/bin:$PATH"` and without setting
  `PYTHONPATH` passed: offline evaluation passed; 294 passed and 1 skipped; Ruff check
  passed; Ruff format reported 33 files already formatted.
- Focused Phase 10 suite: 30 passed.
- Full repository suite: 300 passed, 1 skipped.
- `git diff --check`: passed.

Evaluation results:

- 38 cases evaluated; optional live comparison explicitly skipped.
- Citation, snapshot, bracket, placement, mutation block, prompt-injection resistance,
  retrieval parity, and fallback safety: 100%.
- Unsupported-claim rate and validator escape rate: 0%.
- Analyst rejection rate: 25%; Reviewer rejection rate: 33.33%; score separation:
  66.67%.
- MiMo Pro-minus-normal frozen quality delta: +0.05; Extractor DeepSeek Flash-minus-MiMo
  delta: -0.05.
- One same-model correlated error was explicitly reported.
- Frozen-token total cost: $0.008974; cost per successful artifact and completed run:
  $0.001495667; maximum completion time: 110 seconds.

Known limitations:

- Offline quality and pricing values are frozen evaluation inputs, not current live
  provider claims.
- No live vendor adapter exists; optional live comparison requires an injected provider.
- Bare `python` remains unavailable unless `.venv/bin` is placed first on `PATH`.

Next exact task:

- Post-MVP hardening based on evaluation results, only after explicit user direction.
- Post-MVP hardening was not started.

## 2026-07-17 - Phase 9 Real Orchestration and Controlled Concurrency

Status: Complete.

Completed:

- Added a provider-backed synchronous `run_provider_pipeline()` alongside the unchanged
  Phase 6 fixture pipeline. It creates or resumes a run and connects Planner,
  supporting/opposing Researchers, trusted snapshots, Extractor, deterministic
  post-extraction filtering, Analyst, one possible Reviewer revision, Ledger admission,
  Synthesizer, deterministic final validation/rendering, and release or block.
- Added `ThreadPoolExecutor(max_workers=2)` Researcher execution. Workers return strict
  typed result artifacts, receive equal nine-attempt retrieval limits, and never share a
  SQLite connection, cursor, or transaction.
- Added strict typed Researcher-side, paired-Researcher, analysis/Ledger, configuration,
  budget, inspection, checkpoint, cancellation, usage, and route-attempt artifacts. All
  inherit `extra="forbid"`; JSON remains confined to SQLite and CLI/export boundaries.
- Added exact Phase 8 route execution with one retry per alias for objective transient,
  timeout, malformed-output, schema, exact-quote, or deterministic validation failures.
  Every retry and fallback records the stage, alias, pinned snapshot when configured,
  attempt number, failure, retry reason, escalation reason, latency, and optional typed
  token/cost metadata.
- Enforced the Extractor route `mimo-v2.5` -> `mimo-v2.5-pro` ->
  `deepseek-v4-flash`. MiMo Pro requires an objective escalation reason; DeepSeek Flash
  is reachable only as the third-line availability fallback after MiMo Pro availability
  exhaustion.
- Kept semantic disagreement out of routing. Reviewer rejection creates the one
  architecture-approved Analyst revision and a second independent review; it does not
  silently switch models.
- Preserved every deterministic gate for fallback output. DeepSeek extraction remains
  subject to exact local Pydantic validation, snapshot integrity, exact quote/filter
  checks, Analyst and Reviewer stages, Ledger admission, and final validation.
- Added deterministic operation/attempt IDs, atomic persisted model-call reservations,
  cached typed output reuse, interrupted-attempt handling, completed-stage checkpoints,
  partial-run inspection, database-backed cancellation between stages, explicit
  released/blocked/failed/cancelled status, and restart-safe attempt history.
- Added model-call, equal per-side retrieval, optional token, and optional cost budgets.
  Budget exhaustion produces a clean explicit failed run and never creates a final hash.
- Preserved provider-reported usage on route attempts whose typed output later fails an
  exact-quote or other deterministic validation gate, so retry usage remains persisted
  and enforceable instead of being undercounted.
- Added an SQLite schema migration in `store.py` for Phase 9 checkpoints, typed stage
  artifact payloads, route attempts, and cancellation requests. This is the smallest
  compatibility change required by restart-safe Phase 9 behavior and preserves the
  convention that all schema definitions live in `init_db()`.
- Added a uniqueness guard for one provisional extraction per run/snapshot/stance and
  idempotent compare-before-insert behavior for snapshots, candidates, drafts, reviews,
  Ledger records, synthesis, and validation. Snapshots and Ledger records remain
  insert-only.
- Added the narrow Extractor-input compatibility fix needed to carry a typed
  `RetrievalRecord`, so required query/rank/retrieval provenance is never invented by a
  model.
- Added `inspect-run` and `cancel-run` CLI commands for Phase 9 databases while
  preserving `run-fixture` behavior.
- Added 27 deterministic offline Phase 9 tests covering full release, one/both
  Researcher failures, partial retrieval, extraction and Analyst failures, Reviewer
  revision and second rejection, validator block, retry/fallback policy, objective MiMo
  Pro escalation, no semantic escalation, DeepSeek gate preservation, restart,
  duplicate prevention, cancellation, database reopen, worker connection isolation,
  equal limits, budgets, usage metadata, and explicit terminal status.
- Added no dependency, live adapter, network-dependent normal test, async rewrite,
  evaluation corpus, Phase 10 metric, production UI, or Phase 10 behavior.

Files changed:

- `orchestrator.py`
- `cli.py`
- `agents/supportingresearcher.py`
- `providers/llm.py`
- `models.py` (Phase 9 typed persistence/status compatibility extension)
- `store.py` (Phase 9 schema/store compatibility extension)
- `tests/test_phase9.py`
- `.agent/plans/phase-09-orchestration.md`
- `STATUS.md`
- `HANDOFF.md`

Verification:

- The three exact bare commands from the Phase 9 prompt were run first. All failed
  before project execution with `zsh: command not found: python` because this shell does
  not expose a bare `python` executable.
- The identical required commands were run without setting `PYTHONPATH`, with
  `PATH="$PWD/.venv/bin:$PATH"`: 264 passed, 1 skipped in 4.54s; Ruff check passed; Ruff
  format reported 28 files already formatted.
- Focused Phase 9 suite: 27 passed in 2.89s.
- Full repository suite: 270 passed, 1 skipped in 4.51s.
- The single skip is the optional Phase 8 integration gate because
  `RUN_LLM_INTEGRATION_TESTS` was not enabled.

Known limitations:

- The provider-backed API requires injected Search, Scraper, and LLM implementations;
  no live vendor adapter or API-key integration exists in the repository.
- Token and cost metadata is recorded and budgeted only when a provider exposes the
  strict optional `usage_for()` result. Missing usage is recorded as unavailable and is
  never guessed.
- Bare `python` remains unavailable unless the repository `.venv/bin` directory is
  placed first on `PATH`.

Next exact task:

- Phase 10 evaluation and adversarial testing, only after explicit user direction.
- Phase 10 was not started.

## 2026-07-16 - Phase 8 LLM Provider and Structured Prompts

Status: Complete.

Completed:

- Added a vendor-isolated synchronous `LLMProvider` Protocol with strict typed requests,
  provider capability declarations, exact requested-output revalidation, and typed
  success/failure invocation provenance.
- Added validated per-stage routing with exactly one primary, up to two ordered distinct
  fallbacks, the required MiMo-first defaults, recommended temperatures, optional pinned
  model snapshot provenance, and explicit rejection of unsupported provider controls.
- Added versioned, hashed structured prompts for Planner, Extractor, Analyst, Reviewer,
  and Synthesizer with application-owned model/prompt/schema/validator authority rules.
- Added typed Planner, Extractor, Analyst, and Synthesizer LLM inputs while preserving
  the existing narrow Reviewer input.
- Added an explicit `UNTRUSTED_SOURCE_TEXT` envelope and instruction policy, plus
  snapshot/candidate integrity rechecks before source text reaches Extractor or Analyst
  prompts.
- Enforced Pydantic-only model output, exact requested schema, extra-field rejection,
  complete input artifact ID and timing provenance, typed failure/retry metadata, and no
  approved artifact on invocation failure.
- Added 34 deterministic offline Phase 8 tests covering valid stage artifacts, raw and
  malformed responses, extra fields, prompt hashing, success/failure records, retry
  metadata, forbidden Reviewer fields, prompt injection, no-network behavior, optional
  integration gating, routing validation/defaults, generation settings, provider
  capabilities, and absence of runtime failover.
- Documented the blank `RUN_LLM_INTEGRATION_TESTS` opt-in gate in `.env.example`; no
  API-key variable was added.
- Added no dependency, live adapter, API key, network call, database change, runtime
  retry/failover, real orchestration, async behavior, evaluation corpus, or Phase 9 work.

Verification:

- The exact bare `python` pytest and Ruff commands failed before project execution with
  `zsh: command not found: python`.
- The identical required commands with `PATH="$PWD/.venv/bin:$PATH"` passed without
  setting `PYTHONPATH`: 237 passed, 1 skipped in 2.14s; Ruff check passed; Ruff format
  reported 27 files already formatted.
- Focused Phase 8 suite: 34 passed, 1 skipped in 0.18s.
- Full pytest suite: 243 passed, 1 skipped in 2.28s.
- The single skip is the optional integration gate because
  `RUN_LLM_INTEGRATION_TESTS` was not enabled.

Known limitations:

- No real LLM vendor adapter or live integration test is included; normal execution is
  verified with injected fake providers only.
- Phase 8 records configured fallback order but deliberately executes neither retry nor
  fallback. Those behaviors belong to Phase 9.
- Invocation persistence and provider-backed stage coordination remain future work.
- Bare `python` is unavailable unless `.venv/bin` is placed on `PATH`.

Next exact task:

- Phase 9 real orchestration and controlled concurrency, only after explicit user
  direction.

## 2026-07-10 - Phase 7B Search and Scraping Provider Interfaces

Status: Complete.

Completed:

- Added Protocol-based synchronous `SearchProvider` and `ScraperProvider` interfaces
  with strict typed Pydantic request/response artifacts and explicit provider errors.
- Added deterministic supporting, opposing, and balanced retrieval entry points.
- Enforced three queries per side, top three per query, exactly 18 intended balanced
  attempts, equal side depth, required query exclusions, stable rank/round records, and
  original/resolved URL preservation.
- Added typed scrape outcomes recording scrape status, normalized content type, retry
  count, failures, snapshots, and duplicate references.
- Added timeout retry behavior, explicit exhausted timeouts, explicit scrape failures,
  unsupported PDF/binary handling, 3,000-word truncation, and timezone-aware retrieval
  timestamps.
- Added shared original-URL, resolved-URL, and normalized-content-hash deduplication so
  duplicates do not create duplicate snapshots, including across both sides in balanced
  retrieval.
- Ensured trusted snapshots are constructed and integrity-checked before they reach an
  optional downstream consumer.
- Froze `SourceSnapshot` through the smallest required compatibility fix in `models.py`
  so snapshot artifacts are immutable in memory as well as insert-only in SQLite.
- Cleaned duplicate/misplaced imports in the committed Phase 7A frontend because they
  prevented the required full-repository Ruff check; frontend behavior was unchanged.
- Added 21 deterministic offline tests attacking provider protocols, exact depth,
  exclusions, ranking, URL/content deduplication, retries, failures, unsupported content,
  content types, snapshot ordering, truncation, timestamp awareness, immutability,
  malformed provider outputs, typed outcome consistency, deterministic IDs, and
  real-network prohibition.
- Audited provider boundaries and added explicit rejection of non-Pydantic search and
  scrape responses before malformed values can cross typed internal boundaries.
- Strengthened retrieval outcome and batch validation so statuses, attempt counts,
  content types, snapshot provenance, and newly created snapshot collections cannot
  contradict one another.
- Added no dependency, real provider adapter, live network call, API key, LLM behavior,
  prompt, semantic scoring, renderer change, async behavior, or Phase 8 work.

Verification:

- Exact bare `python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py tests/test_phase7.py -q`:
  failed before project execution with `zsh: command not found: python`.
- Exact bare `python -m ruff check .` and `python -m ruff format --check .`: failed
  before project execution with `zsh: command not found: python`.
- Required Phase 1-7 command using `.venv/bin/python` directly: passed with 203 tests
  in 2.19s; Ruff check passed, and Ruff reported 25 files already formatted.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest`: full suite passed with 205 tests in
  2.15s before the audit; the final direct-venv run passed with 209 tests in 1.98s.

Known limitations:

- Bare `python` is unavailable unless the repository `.venv/bin` directory is placed
  on `PATH`.
- No real vendor adapter or live-network test exists; Phase 7B intentionally verifies
  behavior only through injected fake providers.
- Cross-stance deduplication is provided by `retrieve_balanced()`; standalone stance
  calls use isolated deduplication state.
- Search failures before URLs exist raise explicit `SearchProviderError` exceptions.
- Text normalization is deterministic and intentionally simple; scraper adapters must
  return extracted text rather than raw HTML interpretation.
- Provider-backed persistence and full orchestration remain later-phase work.

Next exact task:

- Phase 8 LLM provider and structured prompts, only after explicit user direction.

## 2026-07-09 - Phase 7A Extremely Basic Local Frontend

Status: Complete.

Completed:

- Added a minimal local Streamlit frontend in `frontend/streamlit_app.py` that discovers
  fixture runs under `tests/fixtures/`, runs the existing Phase 6
  `run_fixture_pipeline()` API directly, and displays released or blocked status.
- Added strict Pydantic UI summary models and pure helper functions for fixture
  discovery, fixture execution, and display summaries so tests do not need to launch a
  browser.
- Added `frontend/README.md` with the launch command:
  `streamlit run frontend/streamlit_app.py`.
- Added Phase 7A helper tests for fixture discovery, valid fixture execution, invalid
  fixture execution, and structured display information.
- Added `streamlit>=1.37,<2.0` as the only new dependency because Phase 7A explicitly
  requires a local Streamlit frontend.
- Updated the phase-plan index, Phase 7A plan, README, AGENTS, status, and handoff
  documentation to mark Phase 7A complete and Phase 7B as the next explicit boundary.
- No core Phase 6 backend behavior changed. `orchestrator.py`, `cli.py`, Ledger
  validation, renderer, synthesizer, analyst, researcher, and planner behavior were not
  changed.
- No live LLM calls, web research, scraping, React, FastAPI, authentication, uploads,
  user accounts, dashboards, database changes, provider work, Phase 7B work, or Phase 8
  work was added.

Verification:

- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase7_frontend.py -q`:
  passed with 4 passed in 0.23s.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase0_foundation.py tests/test_phase7_frontend.py -q`:
  passed with 6 passed in 0.19s.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest`: passed with 188 passed in 1.73s.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff check .`: passed, all checks passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .`: passed, 22 files
  already formatted.
- `PATH="$PWD/.venv/bin:$PATH" python -m pip install "streamlit>=1.37,<2.0"`: passed;
  Streamlit 1.59.1 was already present in the virtual environment.
- Sandboxed `streamlit run frontend/streamlit_app.py --server.headless true --server.address 127.0.0.1 --server.port 8501`:
  failed with `PermissionError: [Errno 1] Operation not permitted` while binding
  localhost.
- Approved local server launch with the repository virtual environment: passed and
  started Streamlit at `http://127.0.0.1:8501`.
- Approved localhost response check with `curl -I --max-time 5 http://127.0.0.1:8501`:
  passed with `HTTP/1.1 200 OK`.

Known limitations:

- Phase 7A is local-only and fixture-only. It does not add uploads, dashboards,
  authentication, user accounts, live retrieval, scraping, provider-backed behavior, or
  semantic generation.
- The UI is intentionally plain and thin; it renders raw validation and metadata rather
  than providing a polished product workflow.
- Streamlit brings transitive web-serving dependencies inside the local development
  environment, but no project FastAPI app, HTTP client, provider integration, or live
  network behavior was implemented.

Next exact task:

- Phase 7B search and scraping provider interfaces, only after explicit user direction.

## 2026-07-04 - Phase 6 Fixture-Only Complete Pipeline

Status: Complete.

Completed:

- Added a fixture-only offline orchestrator in `orchestrator.py` that loads local
  fixture artifacts into strict Pydantic models, filters provisional candidates through
  the deterministic Phase 3 gate, admits Reviewer-approved statements through the Phase
  4 Ledger helper, validates fixture `SynthesisOutput` through the Phase 5 release
  validator, and returns an explicit released or blocked typed result.
- Added `cli.py` with `run-fixture`, where released results and expected validation
  blocks both exit `0`, while malformed fixtures and internal pipeline failures exit
  nonzero.
- Added deterministic valid and invalid fixture runs under `tests/fixtures/`.
- Added Phase 6 tests for valid release, invalid validation block, stable hash, typed
  artifacts, run ID preservation, inspectable audit trail, idempotent reruns, database
  reopening, useful validation errors, explicit fixture failures, no network/provider
  behavior, and CLI behavior.
- Updated the phase-plan index so it identifies Phase 6 as complete and Phase 7 as the
  next explicit phase boundary.
- Persisted deterministic local `audit.json`, `result.json`, and SQLite output in a
  fixture-local `.phase6_output/` directory ignored by each fixture directory.
- No dependencies, provider abstractions, live retrieval, scraping, LLM/API calls,
  API-key reads, async code, web frameworks, ORMs, HTTP clients, or Phase 7 behavior
  were added.

Verification:

- Exact `python cli.py run-fixture tests/fixtures/basic_valid_run`: failed before
  project execution with `zsh:1: command not found: python`.
- Exact `python cli.py run-fixture tests/fixtures/invalid_release_run`: failed before
  project execution with `zsh:1: command not found: python`.
- Exact `python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py -q`:
  failed before project execution with `zsh:1: command not found: python`.
- Exact `python -m ruff check .` and `python -m ruff format --check .`: failed before
  project execution with `zsh:1: command not found: python`.
- `PATH="$PWD/.venv/bin:$PATH" python cli.py run-fixture tests/fixtures/basic_valid_run`:
  passed and released hash `cfb4182d7469c05f269150605aa24907fbc850ea7f70e4e86633a9c96f60f1ed`.
- `PATH="$PWD/.venv/bin:$PATH" python cli.py run-fixture tests/fixtures/invalid_release_run`:
  passed and returned a blocked result with an `altered_statement` validation error.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase6.py -q`: passed with
  11 passed in 1.63s.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py -q`:
  passed with 182 passed in 3.38s.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff check .`: passed, all checks passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .`: passed, 20 files
  already formatted.

Known limitations:

- Bare `python` remains unavailable in this shell unless `.venv/bin` is placed on
  `PATH`.
- Phase 6 uses fixture Analyst, Reviewer, and synthesis artifacts only; it is not a live
  provider-backed or semantically generative pipeline.
- Real search and scraping provider interfaces remain unstarted and belong to Phase 7.

Next exact task:

- Phase 7 search and scraping provider interfaces, only after explicit user direction.

## 2026-07-04 - Post-Phase-5 Documentation State Audit

Status: Complete.

Completed:

- Audited source-of-truth documentation, phase plans, `agents/`, and `tests/` against the
  current Phase 5 implementation.
- Updated `README.md` and `AGENTS.md` so they no longer describe Phase 3 as the latest
  completed phase or Phase 4 as unstarted.
- Added missing durable Phase 4 and Phase 5 decisions to `DECISIONS.md`.
- Added a current Phase 5 project-state summary to `.agent/PLANS.md`, including active
  deterministic modules, remaining placeholder agent files, current tests, and the Phase 6
  boundary.
- Clarified that `.agent/plans/` is canonical and `.agents/PLANS/` is only a compatibility
  mirror; the mirror was kept and its stale absolute Windows path was replaced with the
  canonical relative path.
- Updated older phase-plan wording where it could mislead future readers about the
  current mirror state or Phase 5 completion.
- Left dated historical status and handoff entries as point-in-time records instead of
  rewriting them wholesale.
- No implementation behavior, tests, dependencies, or Phase 6 behavior was changed.

Verification:

- Exact `python -m pytest`: failed because this shell does not have `python` on `PATH`.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest`: passed with 173 passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff check .`: passed, all checks passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .`: passed, 17 files
  already formatted.

Known limitations:

- Plain `python` remains unavailable unless the repository `.venv/bin` directory is placed
  on `PATH`.
- Phase 6 fixture-only complete pipeline has not started.
- The repo still has no orchestration, CLI, live retrieval, scraping, LLM/API calls,
  provider integrations, SDK integrations, web frameworks, ORMs, or HTTP clients.

Next exact task:

- Phase 6 fixture-only complete pipeline, only after explicit user direction.

## 2026-07-04 - Phase 5 Verification Pass

Status: Complete.

Completed:

- Inspected the Phase 5 implementation and confirmed the Phase 5 commit changed only
  `agents/synthesizer.py`, `agents/renderer.py`, `tests/test_phase5.py`,
  `tests/fixtures/phase5_expected_valid_brief.txt`,
  `.agent/plans/phase-05-release-gate.md`, `STATUS.md`, and `HANDOFF.md`.
- Confirmed final rendering uses fixed approved connective templates, exact Ledger
  factual statements, and Ledger source URLs only after final validation succeeds.
- Confirmed placement, stance, entailment, Reviewer approval ID, Ledger claim ID, and
  exact approved statement matching are enforced by the release validator.
- Added narrow Phase 5 regression coverage for raw dictionary Ledger handoffs and empty
  approved Ledger statements.
- Tightened Phase 5 typed boundaries so the synthesizer rejects raw dictionary Ledger
  records explicitly and the release validator revalidates LedgerRecord shape before
  trusting approved statement fields.
- No provider abstraction, real LLM/API call, retrieval, scraping, orchestration,
  fixture pipeline, dependency, or Phase 6 behavior was added.

Verification:

- Initial exact `python -m pytest` failed because this shell did not have `python` on
  `PATH`.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase5.py -q`: passed with
  24 passed in 0.10s.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest`: passed with 173 passed in 0.74s.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff check .`: passed, all checks passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .`: passed, 17 files
  already formatted.

Known risks:

- The plain `python` command is still unavailable unless the local `.venv/bin` directory
  is placed on `PATH`.
- Template compatibility remains deterministic configuration, not semantic review.
- Phase 6 fixture-only complete pipeline was not started.

Next exact task:

- Phase 6 fixture-only complete pipeline, only after explicit user direction.

## 2026-07-03 - Phase 5 Synthesizer Schema, Renderer, and Release Validator

Status: Complete.

Completed:

- Added deterministic `SynthesisOutput` construction in `agents/synthesizer.py` from
  typed `LedgerRecord` instances.
- Added a fixed approved non-factual connective template registry in
  `agents/renderer.py`.
- Added deterministic final validation that revalidates typed synthesis shape, rejects
  hidden renderable fields, compares every item against the Ledger, enforces section
  compatibility, enforces template compatibility, enforces one final use per Ledger
  claim, and returns no hash for invalid releases.
- Added deterministic rendering that uses only title/framing fields, approved template
  text, exact Ledger factual statements, and Ledger source URLs.
- Added SHA-256 hashing of the final rendered brief only when validation succeeds.
- Added adversarial Phase 5 tests for changed words, punctuation, capitalization, wrong
  IDs, wrong statements, Reviewer approval drift, placement drift, stance drift,
  qualified evidence promotion, side-crossing sections, unknown templates, hidden prose,
  free-form factual transitions, missing Partial/Weak warnings, Ledger overuse,
  non-Ledger statements, valid stable hashing, and invalid no-hash results.
- Added the canonical Phase 5 plan at
  `.agent/plans/phase-05-release-gate.md`.

Verification:

- `python -m pytest tests/test_phase5.py -q`: first run failed only on the intentional
  hash placeholder; final run passed with 21 passed in 0.12s.
- `python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py tests/test_phase5.py -q`:
  passed with 168 passed in 0.73s.
- `python -m ruff check .`: passed, all checks passed.
- `python -m ruff format --check .`: passed, 17 files already formatted.

Known risks:

- Template compatibility is deterministic configuration, not semantic review.
- The renderer includes Ledger `source_url` citations mechanically; no citation
  formatting beyond deterministic URL inclusion was added.
- The synthesizer helper remains deterministic and fixture-oriented. No LLM calls,
  provider integrations, retrieval, scraping, orchestration, CLI, async code, or
  external dependencies were added.

Next exact task:

- Phase 6 fixture-only complete pipeline.
- Phase 6 was not started.

## 2026-07-03 - Phase 4 Analyst Rules, Reviewer Rules, and Ledger Admission

Status: Complete.

Completed:

- Added deterministic Analyst score interpretation in `agents/analyst.py` with an
  explicit 25-row Evidence Quality and Claim Fit score-pair table.
- Added typed Analyst helpers for score decisions, Ledger-bound statement drafts, and
  Ledger admission.
- Added deterministic Reviewer input and review-result helpers in `agents/reviewer.py`.
- Enforced one-revision maximum, Reviewer approval/rejection handling, required
  `reviewer_approval_id`, exact Reviewer-approved statement matching, and rejection of
  altered statements after approval.
- Reused Phase 3 snapshot and quote verification before Ledger admission, including
  hash recomputation and exact quote-offset rechecks.
- Enforced placement immutability, Claim Fit 3 qualification requirements,
  `qualified_only` requirements, and Partial/Weak entailment qualification requirements.
- Allowed multiple Ledger records from one quote block only when each statement is
  separately drafted and separately reviewed.
- Added adversarial Phase 4 tests covering all required score pairs and Ledger
  admission guard failures.
- Added the canonical Phase 4 plan at
  `.agent/plans/phase-04-ledger-admission.md`.

Verification:

- `python -m pytest tests/test_phase4.py -q`: failed because `python` is not available
  on PATH in this shell.
- `python3 -m pytest tests/test_phase4.py -q`: failed because the system Python did not
  have `pytest` installed.
- `.venv/bin/python -m pip install -e '.[dev]'`: first failed under the sandbox due to
  blocked package-index DNS; after approval it reached the package index but failed
  because editable package discovery is not configured for the current flat layout.
- `.venv/bin/python -m pip install 'pydantic>=2.0,<3.0' 'python-dotenv>=1.0,<2.0' 'pytest>=8.0,<9.0' 'ruff>=0.8,<1.0'`:
  passed, installing only dependencies already declared in `pyproject.toml`.
- `.venv/bin/python -m pytest tests/test_phase4.py -q`: 43 passed in 0.20s.
- `.venv/bin/python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py -q`:
  147 passed in 0.87s before documentation updates and 147 passed in 0.91s after
  documentation updates.
- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m ruff format --check .`: passed.
- Exact required command
  `python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py -q`:
  initially failed with `zsh:1: command not found: python`; after the session-local
  `python` launcher was restored, passed with 147 passed in 0.82s, then 147 passed in
  0.74s after documentation updates.
- Exact required command `python -m ruff check .`: initially failed with
  `zsh:1: command not found: python`; after the launcher was restored, passed.
- Exact required command `python -m ruff format --check .`: initially failed with
  `zsh:1: command not found: python`; after the launcher was restored, passed.

Known risks:

- Qualification detection is deterministic and marker-based; it is not semantic LLM
  review.
- Reviewer approval is fixture-driven in Phase 4 and does not call an LLM.
- The exact requested `python -m ...` verification commands now pass through a
  session-local temporary launcher. If Codex creates a new temporary PATH directory
  later, that launcher may need to be restored.
- Editable installation remains blocked by missing package discovery configuration, but
  no Phase 4 packaging change was required.

Next exact task:

- Phase 5 Synthesizer schema, renderer, and release validator.
- Phase 5 was not started.

## 2026-06-27 - Documentation Consistency Pass After Phase 3

Status: Complete.

Current state:

- Phase 0 is complete.
- Phase 1 is complete.
- Phase 2 is complete.
- Post-Phase-2 hardening is complete.
- Phase 3 is complete.
- Full Phase 0-10 roadmap alignment is complete.
- Tests through Phase 3 pass.
- At that time, Phase 4 had not started.

Documentation updates in this pass:

- Updating stale project-state references in `AGENTS.md`, `DECISIONS.md`, `STATUS.md`, `HANDOFF.md`, `README.md`, and `.agent/plans/phase-02-store.md`.
- Leaving code, tests, dependencies, provider files, orchestrator files, and future agent implementations unchanged.

Verification:

- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `.\.venv\Scripts\python.exe -m ruff format --check .`: failed because it would reformat existing code/test files outside this documentation-only pass: `agents/researcher.py`, `tests/test_phase3.py`, and `utils.py`.
- `.\.venv\Scripts\python.exe -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py -q`: 104 passed, one local `.pytest_cache` permission warning.

Verification note:

- No code files were changed to satisfy the format check because this pass is documentation-only.

Known risks:

- Sentence-boundary detection remains deterministic and intentionally simple for the MVP.
- The local `.pytest_cache` directory may emit a permission warning during pytest or Git scans.

Next exact task:

- Phase 4 Analyst rules, Reviewer rules, and Ledger admission, only after explicit user direction.

## 2026-06-27 - Documentation Roadmap Alignment

Status: Complete.

Completed:

- Updated `.agent/PLANS.md` with the full Phase 0-10 roadmap.
- Added a short phase-sequencing cross-reference note to `ARCHITECTURE.md`.
- Added a short phase-gated development note to `CONVENTIONS.md`.
- Confirmed at that time that Phase 3 was complete and Phase 4 had not started.

Verification:

- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `.\.venv\Scripts\python.exe -m ruff format --check .`: failed because it would reformat existing code files outside this documentation-only pass: `agents/researcher.py`, `tests/test_phase3.py`, and `utils.py`.

Notes:

- This was a documentation-only roadmap alignment pass.
- No code files were changed.
- No Phase 4 implementation was started.
- The next exact task remains Phase 4 Analyst rules, Reviewer rules, and Ledger admission, only after explicit user direction.
- Current roadmap and formatting status is superseded by the documentation consistency pass above and the later Phase 3 verification entry.

## 2026-06-27 - Phase 3 Snapshot and Quotation Integrity

Status: Complete.

Completed:

- Added deterministic helpers for SHA-256 hashing, word counting, and UUID5 quote-block ID derivation.
- Added shared researcher post-extraction filtering in `agents/researcher.py`.
- Added strict typed Phase 3 helper artifacts for parsed quote blocks, quote metrics, and filter results.
- Implemented snapshot integrity checks that recompute `snapshot_sha256` and `word_count` from `normalized_text`.
- Implemented deterministic parsing and validation for bracketed quote blocks, segment membership, segment offsets, immediate bracket context, start/end/truncated boundary markers, quote length thresholds, statistical markers, and claim-keyword relevance.
- Ensured rejected provisional candidates return typed rejection results with no `CandidateQuoteBlock` and no `quote_block_id`.
- Added a deterministic candidate-vs-snapshot re-check function for future Analyst code without implementing Analyst scoring or Ledger behavior.
- Added adversarial Phase 3 tests for malformed quote blocks, missing or out-of-order segments, wrong bracket context, hash and word-count mismatches, boundary marker misuse, quote length thresholds, statistical marker rules, missing claim keywords, repeated segment text, ellipsis word counting, deterministic IDs, and tampered offsets.
- During final self-review, tightened statistical marker detection so incidental substrings such as `rate` inside `corporate` cannot unlock the 50-word statistical threshold, and added a metadata rejection guard before candidate ID assignment.
- Added the canonical Phase 3 plan at `.agent/plans/phase-03-snapshot-integrity.md` and linked it from `.agent/PLANS.md`.

Verification:

- `python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py -q` from the activated virtual environment: 104 passed, one local `.pytest_cache` permission warning remains.
- `.\.venv\Scripts\python.exe -m ruff check .`: passed.
- `.\.venv\Scripts\python.exe -m ruff format --check .`: passed.

Notes:

- PowerShell blocked activation of `.venv\Scripts\Activate.ps1`, and `python` was not available on PATH, so verification used the virtual environment's Python executable directly without setting `PYTHONPATH`.
- Phase 1 models, Phase 2 store code, and the SQLite schema were not changed.

Scope review:

- No retrieval, scraping, LLM calls, SDK integrations, Analyst scoring, Reviewer logic, Ledger admission, synthesis, rendering, final validation, orchestration, web frameworks, ORMs, HTTP clients, or Phase 4 work was implemented.

Safe to continue:

- Yes, after explicit user direction for Phase 4.

## 2026-06-27 - Post-Phase-2 Hardening

Status: Complete.

Completed:

- Strengthened `AGENTS.md` with explicit safety rules for destructive Git commands, phase boundaries, protected documentation content, regression tests, strict internal Pydantic artifacts, immutable release-relevant artifacts, and unchanged test expectations.
- Confirmed internal Pydantic artifacts inherit the shared `StrictModel` base with `model_config = ConfigDict(extra="forbid")`.
- Added representative extra-field rejection tests for Ledger, synthesis, validation, candidate quote, source snapshot, and model invocation artifacts.
- Added a SQLite `schema_migrations` table initialized by `init_db()` with the Phase 2 initial schema record.
- Added Phase 2 coverage proving the schema migration table and initial migration record exist after initialization.
- Reviewed the Phase 1 and Phase 2 implementation for later-phase scope creep.
- Updated the Phase 2 plan with a post-phase hardening note.

Verification:

- `pytest tests/test_phase1.py tests/test_phase2.py -q`: 81 passed, one local `.pytest_cache` permission warning remains.
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Tracked issues:

- Snapshot `snapshot_sha256` and `word_count` are not recomputed from `normalized_text` at model construction. This remains deferred until Phase 3 defines snapshot and quotation integrity behavior precisely.
- The local `.pytest_cache` directory may still produce a permission warning during pytest.

Scope review:

- No retrieval, scraper, LLM provider, orchestration, renderer, or Phase 3 snapshot-integrity implementation was found.
- Phase 3 has not started.

Safe to continue:

- Yes. The next exact task is Phase 3 snapshot and quotation integrity, only after explicit user direction.

## 2026-06-26 - Phase 2 Hardening

Status: Complete.

Completed:

- Resolved the architecture inconsistency around Claim Fit 2: Claim Fit 2 items may be retained as borderline analyst context, but they cannot enter the final Ledger unless rescored to Claim Fit 3 or higher.
- Documented and implemented two-axis Ledger eligibility: `evidence_quality >= 2`, `claim_fit >= 3`, and `total_score >= 5`, with no compensation for a failing axis.
- Added derived `ledger_score` values: 3 for total scores 5-6, 4 for total scores 7-8, and 5 for total scores 9-10.
- Enforced deterministic score-to-placement validation in `ScoreDecision` and `LedgerRecord`.
- Strengthened `PlannerOutput` validation to require exactly six queries, matching child `run_id` values, no duplicate or extra stance/round pairs, and all standard exclusion parameters.
- Strengthened `StatementReviewResult` so rejected reviews cannot carry approval fields.
- Strengthened `ValidationResult` so invalid validation results cannot carry `rendered_brief_hash`.
- Added SQLite foreign keys for clear parent-child artifact relationships from planner queries through synthesis items.
- Added `read_statement_draft()` for typed statement draft round trips.
- Updated README and Phase 2 plan notes; fixed the `HANDbOFF.md` typo in the Phase 0 plan.
- Added type annotations to Phase 2 test helpers.

Tests added or updated:

- Added scoring example coverage for eligible and ineligible two-axis combinations.
- Added tests for inconsistent placement and derived Ledger score rejection.
- Added planner validation tests for extra queries, child `run_id` mismatches, and missing exclusion parameters.
- Added review and validation result shape tests.
- Added statement draft round-trip coverage.
- Added SQLite orphan-artifact rejection tests for retrieval attempts, snapshots, candidates, analyst decisions, Ledger records, and synthesis items.
- Updated Phase 2 fixtures to create realistic parent artifact chains before inserting child records.

Verification:

- `pytest`: 73 passed; one local `.pytest_cache` permission warning remains.
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Tracked issues:

- Snapshot `snapshot_sha256` and `word_count` are not recomputed from `normalized_text` at model construction. This should be implemented in the snapshot creation or post-extraction validation phase once normalization and hashing behavior are precisely defined in code.
- The local `.pytest_cache` directory still produces a permission warning during pytest.

Safe to continue:

- Yes. The project is safe to continue to Phase 3 after explicit user direction. No Phase 3 implementation has begun.

## 2026-06-26 - Phase 2 Store

Status: Complete.

Completed:

- Implemented the SQLite persistence layer in `store.py` with `init_db()` containing all schema definitions.
- Created append-only storage for runs, planner outputs, planner queries, retrieval attempts, snapshots, provisional extractions, candidates, analyst decisions, statement review attempts, ledger records, synthesis attempts, validation runs, and model invocations.
- Enabled SQLite foreign keys on every connection via `PRAGMA foreign_keys = ON`.
- All functions accept explicit `db_path` parameters; no global connections are used.
- Read functions return Pydantic models; write functions accept Pydantic models.
- Snapshots and Ledger records are INSERT-ONLY with no update or delete functions.
- Multi-write operations use explicit transactions with rollback on failure.
- Timestamps are stored as UTC ISO-8601 strings and reconstructed as timezone-aware datetimes.
- `evidence_quality` and `claim_fit` remain separate columns; no composite score column.
- Fixed `_validate_aware_datetime` in `models.py` to handle `None` for optional datetime fields.
- Added Phase 2 tests covering database initialization, foreign-key enforcement, insert and read round trips, database close and reopen, immutable snapshot behavior, immutable Ledger behavior, transaction rollback, invalid foreign keys, typed reconstruction from stored rows, and duplicate identifier rejection.
- Added the canonical Phase 2 plan at `.agent/plans/phase-02-store.md` and linked it from `.agent/PLANS.md`.

Not completed:

- No Phase 3 implementation has begun.
- No web retrieval, LLM calls, orchestration, rendering, SDK integrations, web frameworks, ORMs, or HTTP clients were implemented.

Verification:

- `pytest tests/test_phase2.py`: 36 passed.
- `pytest tests/`: 54 passed (Phase 0: 2, Phase 1: 16, Phase 2: 36).
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Notes:

- Verification used the local `.venv` created in Phase 1.

## 2026-06-26 - Phase 1 Models

Status: Complete.

Completed:

- Read all required Phase 1 context files before editing: `AGENTS.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `DECISIONS.md`, `STATUS.md`, `HANDOFF.md`, `.agent/PLANS.md`, and `.agent/plans/phase-00-foundation.md`.
- Implemented Pydantic v2 handoff contracts in `models.py` for planner, retrieval, snapshot, candidate, scoring, reviewer, Ledger, synthesis, validation, run manifest, and model invocation artifacts.
- Added enums for run status, stage, stance, placement, entailment, retrieval status, reviewer failure codes, synthesis section types, and validator error codes.
- Enforced timezone-aware datetimes, UUID identifiers, score ranges, reviewer approval requirements, non-empty approved factual statements, ordered non-overlapping segment offsets, source/snapshot provenance, and synthesis section stance compatibility.
- Added the canonical Phase 1 plan at `.agent/plans/phase-01-models.md` and linked it from `.agent/PLANS.md`.
- Added Phase 1 tests covering valid construction and invalid score ranges, reviewer approval, placement, entailment, offsets, naive datetimes, empty approved statements, section types, and validation errors.

Not completed:

- No Phase 2 implementation has begun.
- No database operations, web retrieval, scraping, LLM calls, orchestration, rendering, SDK integrations, web frameworks, ORMs, or HTTP clients were implemented.

Verification:

- `pytest tests/test_phase1.py`: 16 passed.
- `ruff check .`: passed.
- `ruff format --check .`: passed.

Notes:

- The direct `pytest` and `python` commands were not available on PATH in this shell, so verification used a local `.venv` created with the dependencies already declared in `pyproject.toml`.

## 2026-06-26 - Phase 0 Foundation

Status: Complete.

Completed:

- Read `ARCHITECTURE.md` and `CONVENTIONS.md` completely before editing.
- Inspected the documents for Phase 0 consistency gaps.
- Updated architecture rules for typed `SynthesisOutput`, `reviewer_approval_id` propagation, stance propagation, provenance, truncated snapshot markers, sync researcher concurrency, and post-validation ID assignment.
- Updated conventions for the requested scaffold, typed handoffs, dependency boundaries, SQLite concurrency limits, provenance fields, and phase completion checks.
- Added assistant instructions, decision log, status log, handoff log, README, pyproject configuration, canonical plan index, canonical Phase 0 plan, and compatibility plan pointer.
- Added placeholder files so empty scaffold directories can be tracked.
- Added a Phase 0 scaffold/configuration test.

Not completed:

- No Phase 1 implementation has begun.

Verification:

- `pyproject.toml` parsed successfully with Python.
- `pytest`: 2 passed.
- `ruff check .`: passed.
- `ruff format --check .`: passed.
# MVP-11 — Adaptive Research Expansion & Cost Control

Status: Complete.

Completed:

- Verified MVP-10 at committed HEAD `0c20db6`, including its plan, documentation,
  migration-8 implementation, focused tests, and clean starting worktree.
- Added strict Research Governor policy, decision, budget, terminal, and numeric
  research-round artifacts. The policy fixes the maximum at three rounds and records a
  secret-free plain-language authorization/stopping explanation.
- Added migration 9 for append-only research-round, Governor-decision, and terminal
  records, with SQLite `CHECK` enforcement for round numbers 1–3 and immutable rows.
- Bumped live provider factory/fingerprint policy identity to
  `mvp11-research-governor-v1`; MVP-11 execution requires a new Run ID rather than
  resuming an older contract under changed research-round semantics.
- Updated provider orchestration to complete Round 2 when Round 1 is incomplete,
  deduplicate across all permitted rounds, authorize Round 3 only through deterministic
  application policy, and record terminal cancellation/failure without a Round 4 resume.
- Extended the read-only Evidence Browser with compact Governor progress, budget,
  duplicate-rate, productivity, authorization, and terminal-result information.

Verification:

- `pytest`: passed (2 expected opt-in skips).
- Focused Governor/MVP-9/MVP-10/type-contract regression set: 71 passed.
- `ruff check .`, `ruff format --check .`, and `git diff --check`: passed.

Next phase:

- Do not begin another phase without explicit user authorization.

# MVP-10 — Evidence Portfolio & Trail

- Added strict source-family, source-trail, portfolio, coverage, and targeted-planning models; migration 8 adds append-only tables without rewriting snapshots or Ledger rows.
- Provider orchestration now evaluates approved family coverage after round one and may issue one typed targeted Planner request before synthesis. The Evidence Browser exposes portfolio coverage and filtered trail outcomes.
- Verification: 584 passed, 2 expected opt-in skips; `ruff check .` and `ruff format --check .` passed. No live provider calls were made.

# ResearchAssistant v2 — Phase 6: Luna Gap Analysis

Status: Complete and verified.

- Added strict bounded Phase-6 Gap Analysis schemas and a Phase-5-to-Phase-6 input projection.
  It passes only source metadata and up to forty 1,200-character Probe excerpts, never full
  documents, Ledger artifacts, or model-authored factual claims.
- Added GPT-5.6 Luna High execution with one normal retry, per-attempt conservative reservation
  records, completed/stop results, and degraded persisted stop state when analysis cannot
  complete. Restart reuses either state without a further call.
- Gap results require specific enabled-direction missing-evidence gaps and typed gap-linked
  search directions; each direction has at most three gaps. Stop results contain no gaps.
- Round 2 execution was not added. No live calls or dependency changes were made.

Verification:

- Full offline suite passed in two bounded batches: 299 passed, 1 skipped (one existing
  FastAPI/httpx deprecation warning) and 407 passed, 1 skipped; 706 passed and 2 expected
  skips total.
- `ruff check .`, `ruff format --check .`, and `git diff --check` passed.

# ResearchAssistant v2 — Phase 5: Acquisition Routing, Snapshots, Probe, and Survivor Pool

Status: Complete and verified.

- Added bounded v2 routing from Scout decisions through existing Wigolo acquisition and the
  optional verified-preflight Firecrawl fallback. Preferred URLs run before retained
  alternates; successful equivalent clusters are not reacquired.
- Added append-only immutable Phase-5 output retaining provider-attempt audit records,
  strict hash-verified `SourceSnapshot` artifacts, deterministic exact-offset Probe results,
  and all usable surviving sources.
- Probe has no LLM call and never creates Claim Fit, Evidence Quality, factual claims, or
  Claim Ledger entries. Opening, conclusion, numeric, and citation signals provide
  low-overlap fallback. Failed Probe records preserve snapshots but produce no survivor.
- Verification: complete offline suite passed in two bounded batches (403 passed, 1 skipped;
  297 passed, 1 skipped), for 700 passed and 2 expected skips. `ruff check .`,
  `ruff format --check .`, and `git diff --check` passed. No live calls were made.

# ResearchAssistant v2 — Phase 4: Discovery Providers, Normalization, Clustering, and Batched Scout

Status: Complete and verified.

- Added fresh-v2 metadata normalization for OpenAlex, arXiv, PubMed, Exa, and Serper,
  retaining query, direction, round, provider-rank, source metadata, and provenance.
- Added optional non-fatal Crossref DOI identity enrichment plus canonical URL/DOI/title and
  author/year/title conservative clustering with alternate URL retention.
- Added bounded MiMo-v2.5 Scout batching (30 items), strict stable-ID response validation,
  one retry, audit accounting, deterministic all-maybe fallback, and immutable restart output.
- Verification: 5 focused Phase-4 tests passed; complete Python suite ran in two bounded
  batches (288 passed, 1 skipped; 408 passed, 1 skipped). Ruff lint/format and diff checks
  passed. No live calls were made.

# ResearchAssistant v2 — Phase 1: Contracts, Direction Controls, and Compatibility

Status: Complete and verified.

- Added strict frozen v2 direction, planning, discovery, Scout, Probe, gap, source,
  recommendation, and deep-analysis status schemas.
- Added migration 11 with immutable `v2_run_identities` and `v2_artifacts` tables.
  Historical focused/balanced controls and schema-10 inspection remain readable.
- No production pipeline, provider routing, or web controls were changed. Phase 2+
  work remains deferred.
- Verification: 673 passed, 2 skipped, 1 existing dependency warning; Ruff, formatting,
  and `git diff --check` passed. No live provider calls were made.

# ResearchAssistant v2 — Phase 2: Multi-Model Routing

Status: Complete and verified.

- Added logical stages for Scout, Gap Analysis, Search Agent, and Source Selection;
  routed the v2 target table through explicit MiMo normal, MiMo Pro, and Luna High
  aliases without changing the historical direct-MiMo pipeline.
- Added secret-safe v2 route preflight and provider-contract fingerprinting. Every v2
  route now resolves to a physical provider/model and a positive deterministic price
  cap before provider work; missing Luna endpoint/model/credential/pricing fails closed.
- Reused the Xiaomi adapter for separately bound normal/Pro aliases and retained exact
  returned-model validation. Luna is configuration-only pending later transport approval.
- Verification: complete suite 682 passed, 2 expected skips; Ruff lint/format and
  `git diff --check` passed. No live provider calls were made.
