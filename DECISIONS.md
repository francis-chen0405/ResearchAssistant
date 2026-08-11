# Decisions

## 2026-08-11 - MVP-9 Verified Quote Selection & Deterministic Assembly

- Replace the provider-facing Extractor `ProvisionalCandidate` schema with strict
  `VerbatimQuoteSelection`, containing only ordered exact snapshot passages. The model
  cannot author brackets, context, offsets, IDs, timestamps, provenance, or a completed
  candidate.
- Locate selected passages sequentially in the immutable normalized snapshot. Build the
  canonical ellipsis, immediate brackets, boundary markers, and legacy-compatible
  provisional artifact deterministically before the existing post-extraction filter.
- Fail closed without fuzzy matching, quote healing, padding, or source rewriting.
  Exact-selection mismatch is non-retryable; malformed/schema/availability failures
  retain the approved bounded objective retry policy.
- Keep SQLite schema version 7. Persist semantic selections through the existing generic
  model-attempt JSON audit field and retain the existing provisional/candidate columns
  for assembled quote blocks and exact offsets. Do not rewrite historical immutable rows.
- Bump Extractor prompt, MiMo adapter/factory/retry, post-filter, schema, and run-
  fingerprint identities. Historical terminal runs remain inspectable; MVP-9 execution
  requires a new run ID rather than cross-contract resume.
- Add no dependency and make no live provider call during implementation or verification.

## 2026-08-10 - MVP-8 Briefs, Export & Performance

- Export only a read-only reconstructed RELEASED run after rechecking valid final
  validation and the persisted rendered-brief hash. Never export blocked, failed,
  cancelled, or running output as a report.
- Keep exports local and dependency-free: deterministic Markdown plus minimal standard-
  library PDF and DOCX containers. Every export carries run ID, rendered-brief hash,
  exporter version, format, and aware generation time.
- Preserve every exact approved factual sentence and required warning. Presentation adds
  only application-owned traceability and human-review framing.
- Surface persisted checkpoint completion in CLI and local UI. Continue reusing typed,
  valid completed checkpoint artifacts on exact compatible failed-run resume.
- Do not add sharing, accounts, external storage, provider changes, live calls, schema
  changes, or evidence/release-policy changes.

## 2026-08-10 - MVP-6.9 Acquisition and Configuration Integrity

- Treat only ResearchAssistant's bounded public-host preflight and PDF signature check as
  independent origin-media verification. Firecrawl Markdown and
  `metadata.contentType` are never verification.
- Use a frozen strict `MediaTypeProvenance` with paired verified media type/verified URL
  plus a separate optional sanitized provider declaration. Preserve conflicts rather than
  allowing the provider declaration to override verified evidence; malformed,
  unsupported, empty, and non-string declarations remain unknown.
- Replace the primary preflight dictionary with a strict typed result and carry its
  public final URL, canonical URL, and verified media type through approved fallback
  failures. Firecrawl receives the verified final URL; verified media type is
  authoritative only for that exact resolved URL.
- Add SQLite migration 7 with nullable snapshot provenance columns. Do not update or
  reinterpret historical immutable rows; reconstruct their absent provenance as
  explicitly unknown.
- Bump acquisition identity to `mvp6.9-acquisition-provenance-v3`, Firecrawl adapter
  identity to `mvp6.9-firecrawl-media-provenance-v3`, and both provider fingerprint
  versions to `mvp6.9-acquisition-configuration-integrity-v1`.
- Keep the legacy MVP-2B boundary smoke supported. Add a blank `OPENROUTER_API_KEY`, use
  the valid 25,000-token example, retain exact command/enable/approval/one-call/cost/
  output gates, and prove configuration offline without provider calls.
- Use the durable package description `Evidence-constrained Debate Research Agent System
  with deterministic release validation.` and test that it remains phase-neutral.
- Add no dependency and make no live provider call. Do not begin a phase after MVP-6.9.

## 2026-08-10 - MVP-6.8 Persistence and Accounting Integrity

- Add SQLite migration 6 using the established explicit migration transaction. Install
  unconditional update/delete rejection triggers only for `snapshots` and
  `ledger_records`; do not broaden immutability to lifecycle-managed stage artifacts.
- Store authoritative model reservation and usage costs as canonical decimal text in
  new exact columns. Leave legacy `REAL` columns present for schema compatibility but
  null on new writes and non-authoritative after migration.
- Convert historical `REAL` values through their recoverable shortest float text. State
  explicitly that original decimal precision already lost to IEEE-754 cannot be
  recovered and must not be invented.
- Use strict finite non-negative `Decimal` values for configured ceilings, provider
  costs, reservations, aggregates, resume reconstruction, comparisons, and live/
  inspection summaries. Exact ceilings are inclusive.
- Bump accounting policy identity to `mvp6.8-exact-decimal-reserve-reconcile-v1` and
  provider fingerprint identity to `mvp6.8-persistence-accounting-integrity-v1` so old
  runs cannot resume under changed monetary semantics.
- Add no dependency and make no live provider call. Do not begin MVP-6.9.

## 2026-08-09 - MVP-6.7 Repository-Wide Type Contract Enforcement

- Enforce the existing no-exceptions convention on every repository-owned Python `def`
  and `async def`: explicit return annotations and explicit annotations for every named
  parameter except conventional receiver parameters named `self` or `cls`.
- Cover production and test code, including positional-only and keyword-only parameters,
  `*args`, `**kwargs`, fixtures, callbacks, methods, local helpers, nested functions,
  generators, and async functions. Lambdas remain outside the signature rule.
- Use `tests/test_type_contracts.py` as the dependency-free authority. It discovers files
  beneath the repository root, excludes recognized non-owned/generated/vendor locations,
  parses with standard-library `ast`, sorts paths and diagnostics, and reports all
  violations or parse failures in one actionable result without invoking Git.
- Correct 11 missing annotations across seven signatures in five test files with narrow
  pytest, path, iterator, project configuration/result, request, and response types.
  Remove the two affected `type: ignore[no-untyped-def]` comments; add no replacement
  suppression or broad `Any` annotation.
- Preserve every function body, fixture name, assertion, expected value, runtime
  contract, and acceptance criterion. Add no dependency, database migration, provider
  call, spending, or commit.
- Treat MVP-6.7 as the final contradiction-audit remediation phase. No later phase has
  started or been authorized.

## 2026-08-09 - MVP-6.6 Runtime Status, Budget, and Contract Integrity

- Add `CLIExitCode.RUNNING = 13` and map every `ProviderRunStatus` explicitly across
  direct CLI results, read-only inspection, subprocesses, and the live web surface. Exit
  0 remains released research or separately documented administrative acceptance; it
  never means nonterminal research.
- Use a frozen strict `ModelUsageAccounting` summary. Zero attempts are complete exact
  zero; incomplete token/cost usage makes the exact aggregate unknown while retaining
  labeled known subtotals, missing-attempt IDs, and conservative reservation exposure.
- Treat every persisted physical attempt as potentially charge-capable. Do not infer a
  free request from failure state or error text. Exact usage replaces reservation only
  for the component actually known; otherwise reservation remains budget exposure.
- Fail retry/fallback and later calls when incomplete prior usage has no usable
  reservation, because remaining budget cannot be proven. Preserve exact-limit,
  physical-call, and strict per-call reservation behavior.
- Freeze `ProviderRunContract` and centralize duplicate-key rejection, exact payload
  shape, canonical serialization, and SHA-256 validation in `provider_contract.py`.
  Keep the existing payload inputs and fingerprint-version strings; valid canonical
  historical records remain readable, while inconsistent stored records fail without
  repair.
- Add no dependency or SQLite migration, make no live provider call, incur no provider
  spending, create no commit, and do not start MVP-6.7 or repository-wide type-hint work.

## 2026-08-09 - MVP-6.5 Immutable Run Authority and Read-Only Inspection

- Add SQLite migration 5 solely for `runs.raw_claim` immutability and correct migration
  4's description to same-run provenance protection. Install and verify the
  `runs_raw_claim_immutable` trigger before recording migration 5 in the same transaction.
- Reject every actual claim change, regardless of run status or direct-SQL caller, with
  the stable secret-free message `runs.raw_claim is immutable`; permit identical-value
  assignments and preserve the application-level comparison as defense in depth.
- Use one `ReadOnlyStore` session per inspection/history operation, opened with encoded
  SQLite URI `mode=ro`, foreign keys, row handling, and connection-local `query_only`.
  Do not use `immutable=1` or writable fallback.
- Separate writable initialization/migration from read-only compatibility validation.
  Distinguish missing, invalid, older, newer, corrupt, and inaccessible databases.
  Older databases require an intentional writable run or resume and are never migrated
  by inspection.
- Preserve typed reconstruction, released-brief hash verification, partial/RUNNING
  inspection, bounded history ordering, WAL concurrency, writable run/resume behavior,
  insert-only evidence, and same-run provenance guards.
- Add no dependency, ORM, provider call, or spending. Do not start MVP-6.6.

## 2026-08-09 - MVP-6.4 Evidence Density Threshold Calibration

- Set current provider-backed quotation minima to 50 words only when exact quoted
  segments contain both a digit and a recognized statistical marker, and 75 words in
  every other case. A digit alone, marker alone, or incidental marker substring uses 75.
- Keep marker matching case-insensitive and bounded by whole word/token boundaries under
  the existing marker list. Preserve ellipsis counting, exact snapshot membership,
  offsets, brackets, hashes, ordering, truncation, claim keywords, and provenance.
- Use one strict current `QuoteLengthPolicy` for extraction, Analyst verification, and
  Ledger admission. Reject short or malformed model output before assigning an ID; do
  not heal, expand, pad, or rewrite quotations.
- Preserve the historical 50-statistical/100-non-statistical rule only as the explicitly
  named frozen-fixture replay policy. New provider-backed runs never select it and
  historical artifacts are not reinterpreted.
- Version the evidence policy as `mvp6.4-evidence-density-50-75-v1`, Extractor prompt as
  `mvp6.4-extractor-50-75-v1`, provider post-filter validator as
  `mvp6.4-provider-post-filter-50-75-v1`, and provider fingerprint as
  `mvp6.4-evidence-density-fingerprint-v1`.
- Require exact fingerprint compatibility. A run recorded under 75/75 cannot resume as
  50/75; after application restart, use a new run ID. Inspection under recorded
  historical identities remains unchanged.
- Do not weaken Reviewer approval, literal entailment, qualification preservation,
  Ledger admission, or final validation. Add no dependency or SQLite migration, make no
  provider call, and do not start MVP-6.5.

## 2026-08-09 - MVP-6.3 Public Acquisition and Provenance Security

- Disable automatic source redirects and validate each initial/redirected destination
  before the local request. Follow only 301, 302, 303, 307, and 308 through an exact
  bounded loop with relative-location resolution, loop detection, and hop-level closing.
- Require credential-free HTTP(S), valid publicly qualified hostnames or global literal
  addresses, and exclusively global resolver answers. Resolution failure, malformed
  answers, and mixed public/prohibited answers fail closed.
- Send Wigolo only the validated final preflight URL. Treat Firecrawl request URLs,
  returned `sourceURL`, and recognized canonical metadata as untrusted until the same
  public URL policy succeeds. Preserve the existing narrow fallback allowlist.
- Version acquisition as `mvp6.3-public-acquisition-v2`, Firecrawl provenance as
  `mvp6.3-firecrawl-provenance-v2`, and direct-MiMo fingerprinting as
  `mvp6.3-public-acquisition-fingerprint-v2`. Earlier persisted runs require a new run
  ID and historical artifacts are not reinterpreted.
- Do not claim complete DNS-rebinding protection: validation and transport resolution
  are separate and the validated address is not pinned to the socket.
- Add no dependency or SQLite migration and make no live provider call during offline
  verification. Do not start a phase after MVP-6.3.

## 2026-08-09 - MVP-6.2 Batch A Records and Runtime Reporting

- Treat `37c52a7` and `6e0f434` as completed MVP-6 work and `c10c844` as completed
  MVP-6.1 work. Preserve earlier dated statements as historical records when they were
  accurate at the time, while correcting MVP-6 commits that mislabeled themselves as
  merely post-MVP-5 work.
- Make MVP-6.2 the current authorized phase, divided into separately approved batches.
  Batch A does not authorize the pending security, database, accounting,
  evidence-policy, or model-contract batches, and does not complete MVP-6.2.
- Report the current live stack as Exa Search `auto` metadata discovery, pinned loopback
  Wigolo `0.2.1` primary acquisition, optional narrowly gated Firecrawl acquisition
  fallback, and direct Xiaomi `mimo-v2.5-pro` LLM roles. Keep native SearXNG only as
  clearly labeled historical compatibility for old persisted runs.
- Keep launch reporting secret-free while displaying configured provider endpoints and
  explicit Firecrawl enabled/disabled state.
- Ignore `.coverage` and remove the accidentally tracked binary introduced by MVP-6.1;
  it remains recoverable from Git history. Add no dependency or database migration.

## 2026-08-09 - MVP-6.1 Live Worker Test Fix

- Record `c10c844` as completed MVP-6.1 work. The live-worker UI test now polls briefly
  for its background worker to leave the starting state before asserting the redacted
  failure result.
- The `.coverage` binary committed with that fix was accidental build output, not a
  runtime artifact or phase deliverable.

## 2026-08-01 - MVP-6 Post-Audit Boundary Corrections

- Require public HTTP(S) destinations for acquisition, including literal IPs, DNS answers,
  and every redirect target; reject local, private, link-local, reserved, and otherwise
  non-global addresses before content is accepted.
- Make run claims immutable, verify released brief hashes during reconstruction, and add
  database guards preventing artifacts from referencing parents owned by another run.
- Give MiMo narrow semantic response schemas. Python alone creates IDs, timestamps,
  provenance, derived score routing, and synthesis templates; extra model-supplied metadata
  fails schema validation. Preserve Extractor text byte-for-byte and reject invalid quotes
  downstream instead of silently rewriting them.
- Permit live workers concurrently only when they use different SQLite database files. One
  database has one active worker, regardless of run ID, matching the cross-process file lock.
- Remove the unused `python-dotenv` dependency. Runtime configuration comes only from the
  explicitly supplied process-environment mapping; the application never auto-loads `.env`.
- Accept `application/pdf` retrieval results only after the approved Python PDF normalizer
  has produced verified plain text, a matching hash, and a matching word count. Preserve the
  truthful `application/pdf` origin type rather than relabeling extracted text as XML. Reject
  unnormalized, scanned, encrypted, malformed, empty, or otherwise unusable PDFs.
- Remove the misleading aggregate candidate-acquisition deadline. Keep the explicit preflight,
  HTML, PDF, and browser-fetch request deadlines so individual blocking operations remain bounded.
- Recheck the then-current MVP-6 75-word quote minimum whenever a candidate is verified for Analyst or
  Ledger use, even when claim keywords do not need to be recomputed.
- Require direct provider-pipeline callers to supply the byte-exact claim without leading or
  trailing whitespace; reject invalid framing rather than silently trimming it.
- Explicitly redact the MiMo, Exa, and Firecrawl key values at the live display boundary.
- Declare the actually tested Python support range, 3.11 through 3.12, in package metadata.

## 2026-08-01 - MVP-6 Bounded-Inference Evidence Policy

- Set the deterministic minimum quoted evidence length to 75 words for statistical and
  non-statistical candidates. Exact source membership, ordering, immediate bracket
  context, hashes, offsets, and qualification preservation remain mandatory.
- Separate statement entailment from full-claim proof. A Reviewer may approve a literal,
  materially relevant fact even when it does not independently prove the complete claim;
  it must still reject every factual addition or inference absent from the quotation.
- Assign Strong/direct evidence only at Claim Fit 5, Partial/indirect evidence at Claim
  Fit 4, and Weak/contextual evidence at Claim Fit 3. Partial and Weak statements retain
  application-owned warning connectives in the rendered brief. Claim Fit 3,
  qualified-only placement, and Weak evidence require explicit in-statement scope
  qualification; Claim Fit 4 Partial evidence does not require an artificial keyword
  when its literal statement and material source qualifications passed Reviewer checks.
- When approved evidence exists for only one stance, release may continue but the brief
  must state that it is not balanced and identify the missing Reviewer-approved stance.
  A run with no Reviewer-approved Ledger statement still fails closed; an empty report is
  not presented as research evidence.
- Fingerprint the new evidence policy and prompt/validator versions. Existing run IDs are
  not reinterpreted under the more permissive policy.
- Attribute a failure to the stage being attempted rather than the previously completed
  stage. Count stance model attempts through persisted snapshot/candidate artifact IDs,
  because model route stages are generic (`extractor`, `analyst`, and `reviewer`).

## 2026-08-01 - MVP-6 Retrieval Provider Correction

- Replace native SearXNG discovery in new live runs with Exa Search `auto`, using only
  titles, URLs, and discovery metadata; Exa snippets or generated content never become
  evidence.
- Keep pinned loopback Wigolo `0.2.1` as the primary public-page acquisition and exact
  evidence surface. Add Firecrawl scrape as an optional automatic fallback only when
  Wigolo itself cannot connect, times out, returns malformed output, or cannot extract a
  public HTML page.
- Never use Firecrawl to bypass authentication, paywalls, legal restrictions, access
  denial, unsupported content, size limits, redirect limits, or source-side failures.
- Require `EXA_API_KEY` for new live runs. Treat `FIRECRAWL_API_KEY` as optional; absence
  disables fallback without disabling Wigolo acquisition. Keep both secrets only in the
  local server process and exclude them from browser state, SQLite, logs, arguments, and
  the Wigolo child environment.
- Preserve the completed MVP-5 interface, direct MiMo route, SQLite schema,
  deterministic validation, budgets, restart rules, and rank-five/keep-three research
  policy. This provider correction was committed as part of MVP-6 live research
  stabilization in `37c52a7`.

## 2026-08-01 - MVP-5 Polished Local Live Web Interface

- Supersede the earlier scheduled-live-validation placeholder with the user's explicit
  MVP-5 live-web specification; scheduled automation is not implemented.
- Keep `frontend/streamlit_app.py` fixture-only and add a separate live Streamlit page
  that invokes the stable MVP-4 orchestrator service directly in a background worker.
- Treat SQLite as authoritative and use a per-database cross-process lock plus an
  in-server worker registry to prevent Streamlit reruns, refreshes, or parallel browser
  sessions from starting duplicate workers.
- Preserve released MVP-4 fingerprints, explicit budgets, restart rules, cooperative
  cancellation, provider identities, and exit mappings without a second pipeline or
  timeout-policy change.
- Manage only pinned loopback Wigolo `0.2.1` with native SearXNG settings. Verify exact
  health before enabling research, capture bounded redacted diagnostics, and terminate
  only the application-owned process group.
- Keep `MIMO_API_KEY` exclusively in the local server process environment. The macOS
  launcher uses a native hidden-input dialog when the environment lacks the key and does
  not persist it or put it in browser state, URLs, SQLite, logs, or arguments.
- Add no dependency or schema migration. Streamlit, `httpx`, SQLite, subprocess support,
  and Pydantic were already approved.

## 2026-08-01 - MVP-4 Usable Live CLI Release

- Expose `run`, `inspect-run`, and `cancel-run` around the approved direct-MiMo pipeline;
  keep `run-fixture` and the fixture-only Streamlit frontend unchanged.
- Freeze process exit codes at released `0`, blocked `10`, failed `11`, cancelled `12`,
  configuration error `20`, and invalid input `21`.
- Require a byte-exact non-empty claim, explicit database path, explicit token and cost
  budgets, and process-environment provider configuration. Print only secret-free stack,
  endpoint, model, repository, and budget identity at launch.
- Include the complete operational configuration and budgets in the immutable run
  fingerprint. Any budget change requires a new run ID; neither tightening nor loosening
  can reset or reinterpret consumed usage.
- Derive repository compatibility from a deterministic hash of the executable source,
  prompt, and project-configuration surface rather than trusting a caller-supplied label.
- Preserve cooperative cancellation: a second process persists the request, an active
  synchronous call may finish, its attempt is recorded, and no later call starts after
  observation.
- Keep the optional live CLI smoke disabled unless both exact enable/approval gates are
  supplied. MVP-4 completion does not authorize MVP-5.

## 2026-07-29 - MVP-3B Direct Xiaomi MiMo Gateway Amendment

- Replace OpenRouter with Xiaomi's direct OpenAI-compatible MiMo API as the sole MVP-3B
  LLM gateway, using `mimo-v2.5-pro` for Planner, Extractor, Analyst, Reviewer, and
  Synthesizer.
- Retain the OpenRouter implementation and mocked MVP-3A coverage as historical
  compatibility proof, but do not permit an OpenRouter or MiniMax physical call in an
  MVP-3B run.
- Use Xiaomi JSON mode plus the existing application-rendered schema and exact local
  Pydantic validation. Do not claim provider-enforced strict JSON Schema and do not add
  response healing.
- Retry the direct MiMo route once only for approved objective failures. Do not add a
  cross-provider fallback.
- Freeze conservative caps above Xiaomi's July 15, 2026 overseas pay-as-you-go prices
  and mark calculated cost as estimated because Chat Completions usage reports tokens
  without a reliable per-response USD charge.
- Read `MIMO_API_KEY` only from an explicitly supplied environment mapping and preserve
  every existing live safety gate, public/non-sensitive restriction, deterministic
  validator, persistence fingerprint, deadline, token, call, and USD ceiling.

## 2026-07-24 - MVP-3A Mocked Full-Provider Pipeline Integration

- Construct the approved stack only through an immutable strict `ProviderFactoryConfig`.
  The factory creates Wigolo Search/acquisition and OpenRouter adapters and rejects any
  role mapping other than MiMo Pro primary with MiniMax M3 as the sole fallback.
- Share immutable configuration and thread-safe `httpx.Client` instances. Wigolo Search
  protects health state with a lock, OpenRouter keeps call metadata in thread-local
  storage, acquisition keeps no mutable request state, and SQLite connections remain
  short-lived and worker-local.
- Add a typed rank-five/keep-three acquisition policy. Existing Phase 7/9 fake-provider
  defaults remain readable, while `run_mvp3a_pipeline()` always uses the approved
  five-candidate/three-snapshot policy.
- Persist one immutable provider run contract containing exact provider, adapter, model,
  prompt, schema, normalization/PDF/acquisition, retry, budget, pricing, repository, and
  policy identities. Resume requires the same run ID, claim, and fingerprint.
- Reserve calls, conservative tokens, and capped cost atomically before each physical
  call in strict MVP-3A runs; reconcile with exact reported usage afterward. A retry or
  fallback uses the same persisted totals and cannot start if its reservation does not
  fit.
- Preserve provider-reported usage for malformed, schema-invalid, model-mismatched,
  refused, and deterministically rejected responses when OpenRouter reports it.
- Observe cooperative cancellation before and after provider calls and at orchestration
  boundaries. An already-active synchronous request may finish; its attempt is persisted
  before cancellation terminates the run.
- Add SQLite migration 3 only for immutable provider-run contracts and route-attempt
  reservation columns. Do not change snapshot/Ledger insert-only behavior.

## 2026-07-22 - MVP-2B Production Provider Boundaries

- Implement only pinned loopback Wigolo `0.2.1` and direct OpenRouter HTTP adapters; add
  `httpx`, `markdown-it-py`, and `pypdf` with no LLM SDK or second provider stack.
- Make `ra-normalization-v1` normalized plain text the quote surface. Support deterministic
  HTML/Markdown/plain text and unencrypted digital PDFs; reject unusable PDFs without OCR.
- Migrate every default LLM route to MiMo Pro with MiniMax M3 as the sole fallback while
  retaining legacy aliases only for persisted-artifact compatibility.
- Use conservative frozen price caps above observed July 22, 2026 provider prices, reconcile
  provider-reported cost when present, and mark cap-calculated cost as estimated.
- Read `OPENROUTER_API_KEY` only from an explicitly supplied process environment mapping.
  Do not silently load `.env` or another credential source.
- Keep the boundary smoke outside the product CLI and require every enable, approval,
  call-count, token, cost, deadline, and dedicated-output gate. Credentials alone never run it.
- Make no SQLite migration and do not connect the complete orchestration in MVP-2B.

## 2026-07-22 - Narrow Model-Facing Provenance Envelopes

- Keep required release provenance in typed application-owned request/result envelopes
  and persisted domain artifacts when a deliberately narrow model-facing schema forbids
  contextual metadata.
- Apply this rule to `ReviewerInput` and `ReviewerDecision`: do not expose run IDs,
  timestamps, model metadata, or application-owned identifiers merely to duplicate the
  provenance already carried by `LLMRequest`, invocation records, and
  `StatementReviewResult`.
- This is a narrow exception for model context isolation, not permission for
  provenance-free application handoffs.

## 2026-07-21 - MVP-2A Architecture Gate

- Name this documentation phase **MVP-2A Architecture Gate**. It selects a live-provider
  design but does not authorize implementation, dependencies, secrets, migrations, live
  calls, or MVP-2B.
- Select pinned local Wigolo `0.2.1` for discovery and controlled source acquisition.
  Search results are discovery metadata only; every source is independently fetched and
  provider snippets, scores, evidence fields, or summaries never substitute for a
  ResearchAssistant snapshot.
- Request five ranked results for each of six queries and attempt them in rank order
  until three usable unique snapshots exist per query. Keep eighteen snapshots as the
  normal Extractor ceiling and thirty acquisition candidates as the structural maximum.
- Preserve original, final redirected, and advisory canonical URLs separately. Determine
  origin content type independently because Wigolo's REST extraction does not expose the
  original HTTP `Content-Type`.
- Allow one direct fetch and one controlled Chromium-render fallback only after a
  challenge or JavaScript-required result. Do not add authentication, clicks, typing,
  profiles, or general browser automation.
- Support digital PDFs through a narrow deterministic path. Reject scanned/image-only,
  encrypted, malformed, empty, oversized, timed-out, or unusably extracted PDFs without
  OCR. Headers, footnotes, and page markers may remain.
- Make the immutable, 3,000-word, ResearchAssistant-normalized plain-text snapshot the
  only quote authority. Normalize deterministically and version the contract. Character
  offsets always refer to stored normalized text and Python must verify
  `text[start:end] == exact_quote`. Refetches never replace snapshots.
- Use OpenRouter as the single LLM gateway. Route all five roles to
  `xiaomi/mimo-v2.5-pro`; use `minimax/minimax-m3` as the only objective-failure fallback.
  Require strict JSON Schema and exact local Pydantic revalidation.
- Permit at most primary, primary retry, fallback, and fallback retry per logical call.
  Semantic disagreement or low scores do not trigger routing. All attempts share one
  run-wide call, token, and monetary budget.
- Reserve conservative usage and capped price before calls and reconcile exact usage
  afterward. Retain usage from failed, malformed, and locally rejected outputs; fail
  closed when pricing or returned route identity cannot be established.
- Restrict live MVP research to public, non-sensitive claims. Configure OpenRouter data
  collection denied and prompt logging off, protect the API key from logs/persistence,
  and bind the unauthenticated Wigolo service to loopback only.
- Require an exact checkpoint fingerprint over repository, provider/adapter, exact
  model/upstream, prompt/schema, acquisition, normalization/PDF, retry/budget/pricing,
  and Wigolo configuration versions. Changed fingerprints require a new run; silent
  cross-version resume is unsupported.
- Keep Brave Search plus local `httpx`/`trafilatura`/`pypdf` extraction and the same
  OpenRouter route as the concrete alternative, not an additional implementation target.
- Defer approval of `httpx`, `markdown-it-py`, Node/Wigolo runtime requirements,
  response limits, deadlines, hard USD/token/call limits, environment-template changes,
  CLI/UI behavior, and schema migrations to MVP-2B.

## 2026-07-19 - Phase MVP-1 Release-Contract Correctness

- Treat brief title, displayed-claim label and text, section headings, and section order
  as application-owned release framing. The fixed title is `Research Brief`; the fixed
  label is `Claim under review`; the displayed value is the exact authoritative claim
  passed by the orchestrator.
- Remove `title`, `claim_definition`, and section `heading` from `SynthesisOutput` and
  `SynthesizerLLMInput`. The Synthesizer selects only typed sections, approved templates,
  and exact Ledger-backed items.
- Allow only supporting, opposing, and limitations sections, at most once each, in that
  application-defined order. Reject hidden or extra framing fields before release hash
  creation.
- Use a narrow `ReviewerDecision` as the LLM output. It contains exact reviewed text,
  normalized approval/rejection, an optional rejection code, and rationale; unknown
  fields, including `reviewer_approval_id`, are forbidden.
- Derive approved IDs in application code as `rappr_v1_<sha256>`, after decision-shape
  and exact-text validation. Canonical sorted compact JSON contains derivation version,
  Reviewer schema version, statement draft ID, quote block ID, exact reviewed text, and
  normalized `approved` decision only.
- Exclude timestamps, provider request/response metadata, formatting, routes, token
  usage, cost, and other unstable metadata from approval-ID derivation.
- Preserve the persisted/domain `StatementReviewResult`. Continue reading legacy UUID
  approval IDs while writing new application-owned `rappr_v1` IDs.
- Retain legacy SQLite synthesis framing columns for schema compatibility, write only
  fixed application constants into them, and ignore their contents when reconstructing
  framing-free `SynthesisOutput` artifacts.
- Preserve completed synthesis checkpoints backed by SQLite rows. Reject pre-MVP-1
  serialized synthesis payloads during an interrupted pre-checkpoint restart; those runs
  require a fresh run rather than silently accepting model-owned framing.
- Persist fixture runs as `RunStatus.RUNNING` until final validation, then update them to
  `RunStatus.COMPLETED` for release or `RunStatus.BLOCKED` for validation block.


## 2026-06-26 - Phase 0 Foundation

- Keep Phase 0 documentation-only plus scaffold-only. No working agents, database behavior, retrieval, scraping, or LLM calls are implemented.
- Use Pydantic v2 as the only model layer for internal handoffs.
- Treat `.agent/plans/` as the canonical phase-plan directory.
- Treat `.agents/PLANS/` as a requested compatibility mirror only; it must not become a second source of truth.
- Require release-relevant records to carry provenance: run IDs, prompt versions, model names, retrieval attempts, validator/filter versions, and timestamps.
- Run supporting and opposing research concurrently only through synchronous workers with no shared SQLite connection.
- Assign IDs only after the relevant deterministic validation gate passes.

## 2026-06-26 - Phase 1 Pydantic Models

- Represent internal handoff and release-relevant artifacts as strict Pydantic v2 model instances.
- Keep JSON serialization at persistence, API, logging, and export boundaries only; do not use raw dictionaries as agent handoffs.
- Carry release-critical provenance through the model layer, including UUIDs, run IDs, source or snapshot provenance, prompt/model versions, and timezone-aware timestamps.
- Require `SynthesisOutput` items to preserve Ledger IDs, reviewer approval IDs, stance, placement, entailment, and exact approved factual statements for later deterministic validation.

## 2026-06-26 - Phase 2 SQLite Store

- Use Python's standard `sqlite3` module for persistence; do not add an ORM or new database dependency.
- Keep schema definitions centralized in `store.py` inside `init_db()`.
- Open and close SQLite connections per store function and enable foreign keys on every connection.
- Treat snapshots and Ledger records as insert-only audit artifacts.
- Preserve typed boundaries: store functions accept and return Pydantic models, with JSON used only for persistence encoding of structured fields.

## 2026-06-26 - Phase 2 Scoring and Store Hardening

- Enforce two-axis Ledger eligibility with separate `evidence_quality` and `claim_fit` thresholds before deriving `ledger_score`.
- Clarify that Claim Fit 2 items may be retained as borderline Analyst context but cannot enter the final Ledger unless rescored to Claim Fit 3 or higher.
- Derive `ledger_score` deterministically from the two sub-scores only after eligibility passes.
- Enforce placement consistency from score decisions instead of allowing downstream stages to promote or rewrite placement.
- Add SQLite foreign keys for architecture-defined parent-child artifact relationships.

## 2026-06-27 - Post-Phase-2 Hardening

- Require internal Pydantic artifacts to reject unknown fields by default with `model_config = ConfigDict(extra="forbid")`, unless a specific exception is documented.
- Add representative regression coverage for extra-field rejection across Ledger, synthesis, validation, candidate, snapshot, and model-invocation artifacts.
- Track SQLite schema versioning through a `schema_migrations` table initialized by `init_db()`.
- Strengthen assistant rules against destructive Git commands, test weakening, undocumented protected-doc deletion, and beginning the next phase without explicit direction.

## 2026-06-27 - Phase 3 Snapshot and Quotation Integrity

- Keep trusted snapshot and quote-block checks deterministic and local; Phase 3 does not add retrieval, scraping, LLM calls, Analyst scoring, Reviewer logic, Ledger admission, rendering, or orchestration.
- Put shared post-extraction filtering in `agents/researcher.py` so supporting and opposing researchers can later use the same deterministic validation rules.
- Recompute snapshot SHA-256 and word count from `normalized_text` before accepting snapshot-dependent artifacts.
- Validate bracketed quote blocks by exact segment membership, sequential offsets, immediate surrounding context, boundary markers, quote length thresholds, statistical-marker rules, and claim-keyword relevance before assigning a quote-block ID.
- Return typed rejection results without candidate IDs for invalid provisional candidates.

## 2026-06-27 - Phase 0-10 Roadmap Alignment

- Treat `.agent/PLANS.md` as the compact source of truth for the full Phase 0-10 roadmap.
- Keep detailed implementation prompts out of the roadmap index; use individual `.agent/plans/phase-XX-*.md` files for phase-specific plans.
- Clarify that `ARCHITECTURE.md` defines system invariants while phase sequencing lives in `.agent/PLANS.md` and the canonical `.agent/plans/` directory.
- At the time of roadmap alignment, Phase 4 was the next unstarted phase: Analyst rules, Reviewer rules, and Ledger admission.

## 2026-07-03 - Phase 4 Analyst Rules, Reviewer Rules, and Ledger Admission

- Implement Phase 4 as deterministic typed helper surfaces in `agents/analyst.py` and `agents/reviewer.py`; do not add LLM calls or provider integrations.
- Keep score interpretation explicit with a 25-row Evidence Quality and Claim Fit table, preserving separate score axes before deriving any Ledger score.
- Reconstruct Ledger records from candidate, snapshot, Analyst decision, StatementDraft, and Reviewer approval artifacts instead of trusting caller-supplied Ledger fields.
- Reuse Phase 3 snapshot and quote verification before Ledger admission so a matching hash alone is not treated as proof that the quotation exists at the recorded offsets.
- Keep Reviewer input narrow: quote block, bracket context, draft statement, and Claim Fit score only.

## 2026-07-04 - Phase 5 Synthesizer Schema, Renderer, and Release Validator

- Build `SynthesisOutput` only from typed `LedgerRecord` instances; reject raw dictionary Ledger handoffs.
- Keep approved connective templates in `agents/renderer.py` as deterministic strict Pydantic configuration artifacts.
- Validate final releases by exact Ledger claim ID, Reviewer approval ID, statement text, placement, stance, entailment, section compatibility, template compatibility, and one-use-per-Ledger-claim rules.
- Compute the rendered brief SHA-256 hash only after final validation succeeds; invalid validation results carry no rendered hash.
- Keep Phase 5 deterministic and fixture-oriented. No fixture pipeline, orchestration, CLI, live retrieval, scraping, LLM/API calls, provider integrations, dependencies, or Phase 6 behavior was added.
