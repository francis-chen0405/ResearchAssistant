# Debate Research Agent System

## Fresh v2 Production Architecture — Post-Phase-13 Conditional Round Four

`v2_orchestrator.py` is the only fresh website/CLI research coordinator. It joins the
completed Phase 3–12 boundaries without replacing their append-only artifacts:

```text
claim + direction controls -> broad Round 1 -> normalize/cluster -> Scout
-> acquisition -> deterministic Probe -> Luna Gap Analysis
-> optional Round 2 -> optional Governor-authorized Round 3
-> post-Round-3 Luna Gap Analysis -> optional Governor-authorized Round 4
-> complete survivor pool -> recommendation -> budget-derived queue
-> exact extraction -> Luna Evidence Analyst (assessment + statement)
-> deterministic Analyzer Admission -> Claim Ledger projection
-> Ledger-only synthesis -> Phase 13 result envelope
-> deterministic release validation -> rendered-output hash
```

The persisted `BudgetedV2LLMProvider` is the run-wide authority for every physical model
attempt, including failures and retries. The immutable ceiling is at most 160 calls and
500,000 tokens, with lower configured values supported. It reserves conservatively before
each physical call, reconciles exact usage when available, and preserves uncertain exposure.
Optional research receives budget only after the downstream reserve; the versioned source-selection
policy derives queue capacity from the remaining call/token/cost budget and retains a status for
every survivor.

The direct `run_v2_production_pipeline()` boundary acquires the same database-scoped
`.mvp5.lock` used by the live controller for the complete run. This serializes independent
callers before they can reserve budget or perform provider work. The live controller retains
ownership of that lock and explicitly transfers ownership to the direct coordinator, so it does
not acquire the same lock twice. A reservation persistence error is fail-closed; if the immutable
start row was committed before the error, the provider refreshes its audit view and retains that
conservative exposure.

Fresh routing is MiMo-v2.5 for Scout; MiMo-v2.5-Pro for Planner, Search Agent, Source
Selection, and exact Extractor; and GPT-5.6 Luna High for Gap Analysis and Evidence Analyst.
Fresh v2 synthesis is deterministic Python assembly and makes no Synthesizer model call;
the historical direct-MiMo synthesis route remains available only for compatibility. Each
successfully extracted source receives one Analyst call. All direction, provider/round
eligibility, exact quote assembly, score/placement derivation, Analyzer Admission, and final
release decisions remain application-owned. The production
fingerprint covers routes/models/prices, custom prompt hashes, key schemas, direction/provider
controls, provider adapter policies, evidence/admission and release policies,
research-governor settings, downstream reserve, ceilings, the post-Round-3 Gap and Round-4
policies, and the post-Phase-13 final-output contract.

Every stage is restart-safe. Compatible completed artifacts are reused; incomplete physical
attempts remain charged conservatively. Cross-claim, cross-route, cross-provider-policy, or
cross-semantic-policy resume fails before new work. Historical provider contracts, evidence,
rendering, inspection, and exports remain under their original versions and are never migrated
or reinterpreted as v2.

## Agent Roster

**Claim Planner** — Defines scope, logical angles, and search strategy.
**Supporting Evidence Researcher** — Finds affirming evidence; extracts candidate quotations.
**Opposing Evidence Researcher** — Finds contradicting or limiting evidence; extracts candidate quotations.
**Evidence Analyst** — Scores evidence on two dimensions, verifies quotations against trusted snapshots, and returns the final factual statement in the same call.
**Analyzer Admission** — Performs deterministic provenance, score, placement, qualification, and statement checks before creating an analyzer-admitted evidence record.
**Claim Ledger** — Stores analyzer-admitted fresh-v2 factual statements and their evidence, scoring, placement, and provenance records; historical Reviewer-approved records remain supported.
**Debate Synthesizer** — Deterministically builds a typed structured brief from approved Ledger
records and fixed non-factual connective templates; historical direct-MiMo arrangement remains
compatibility-only.
**Deterministic Final Renderer & Validator** — Renders the final brief; blocks release unless every factual sentence exactly matches an approved Ledger statement.

In balanced mode, Supporting and Opposing Researchers may run in parallel; focused mode
runs only the Supporting Researcher. All other stages run sequentially. Parallel
execution means the coordinator may start two synchronous researcher workers and join
them before the Analyst runs. Do not introduce async, and never share a SQLite
connection, cursor, transaction, or in-memory mutable handoff between workers. Each
worker returns typed Pydantic output to the coordinator; any persistence is performed
after workers finish or through worker-local short-lived SQLite connections.

## Historical MVP/MLP Workflow (retained compatibility)

```text
Raw Claim
  ↓
Claim Planner
(per active stance: 3 Exa web queries + 1 OpenAlex academic query)
  ↓
┌──────────────────────────────────────────────────────────────┐
│ Supporting Researcher              Opposing Researcher        │
│ Execute S1, S2, S3                 Execute O1, O2, O3        │
│ Rank 5; keep 3 snapshots/query   Rank 5; keep 3 snapshots/query │
│           ↓                                  ↓               │
│ Trusted Snapshot Creation          Trusted Snapshot Creation  │
│           ↓                                  ↓               │
│ LLM Verbatim Selection             LLM Verbatim Selection     │
│ Application Quote Assembly         Application Quote Assembly │
│           ↓                                  ↓               │
│ Post-Extraction Filter             Post-Extraction Filter     │
└───────────────┬──────────────────────────────┬───────────────┘
                ↓                              ↓
        Evidence Analyst
        (Dual scoring, snapshot audit, canonical statement drafts)
                ↓
        Statement Reviewer
        (Independent entailment, qualification, neutrality, and scope audit)
                ↓
        Claim Ledger
        (Reviewer-approved factual statements and provenance only)
                ↓
        Debate Synthesizer
        (`SynthesisOutput` Pydantic model only; JSON-serializable)
                ↓
        Deterministic Final Renderer & Validator
        (Exact Ledger matching + schema checks)
                ↓
        Final Brief (Released only if valid: true)
```

## Core Architectural Principle

Retrieval, semantic assessment, deterministic admission, and deterministic release are strictly separated. Researchers identify candidates. Fresh v2 Luna Analyst calls score evidence on two independent dimensions and return exact factual statements. Analyzer Admission verifies structure, provenance, scores, placement, qualification, and exact statement identity; it does not independently prove entailment. The final stage permits only analyzer-admitted statements as factual content and labels that reduced safety boundary. Historical Reviewer-backed artifacts retain their original interpretation.

MVP-10 adds an auditable Evidence Portfolio before synthesis. MVP-11 replaces its
single targeted-expansion limit with a deterministic Research Governor: Round 1 proceeds
normally, an incomplete portfolio completes Round 2, and only a typed post-Round-2
application decision may authorize Round 3. Historical MVP-11 runs may not contain a Round 4.
The separately versioned fresh-v2 post-Phase-13 contract may authorize one conditional Round 4
only after a completed, non-degraded Round 3. Duplicates
remain immutable audit records rather than independent portfolio evidence, and all
provider budgets remain cumulative across every permitted round.

## Phase Sequencing

`ARCHITECTURE.md` defines system invariants, evidence rules, and release rules. Phase sequencing lives in `.agent/PLANS.md` and individual `.agent/plans/phase-XX-*.md` files. If a phase prompt conflicts with architecture, architecture wins unless the user explicitly approves an architecture change.

Phases 0-10, MVP-1 through MVP-6, and MVP-6.1 are completed committed work. MVP-6.2
Batch A completed its records/current-stack correction. MVP-6.3 is the completed public-
acquisition and provenance-security phase: redirect destinations are validated before
each local request, and Firecrawl-returned URLs are untrusted until independently
validated. MVP-6.4 completed the evidence-density calibration: new provider-backed runs
use 50 quoted words for statistical evidence and 75 for all other evidence. It did not
implement the pending database, CLI-status, usage-accounting, provider-contract, or
type-hint batches. MVP-6.5 adds database-enforced claim immutability and validated
read-only history/inspection. MVP-6.6 adds distinct nonterminal exit semantics,
complete/conservative model-usage accounting, and immutable self-consistent provider
contracts. MVP-6.7 enforces complete Python function-signature annotations repository-
wide. MVP-6.8 adds SQLite-enforced snapshot/Ledger immutability and canonical exact-
decimal USD accounting through storage, aggregation, reservation, comparison, resume,
and inspection. MVP-6.9 separates independently verified origin media type from
provider-declared metadata, carries verified preflight evidence across Firecrawl fallback,
repairs the legacy boundary-smoke example, and makes package wording phase-neutral. The
contradiction-audit remediation sequence, MVP-7.1, MVP-8, MVP-8.1, and MVP-8.2 are
complete. MVP-9 Verified Quote Selection & Deterministic Assembly, MVP-10 Evidence
Portfolio & Trail, and MVP-11 Adaptive Research Expansion & Cost Control are complete.
MVP-11 is the latest completed research-pipeline phase. MLP-1 Simplified Live Experience,
MLP-2 Local Product Experience, MLP-3 Next.js Product Rebuild, and MLP-4 Research Quality
& OpenAlex Integration are complete. MLP-4 is the latest completed product-experience
phase and preserves every completed release invariant. MLP-5 Provider Selection & SERP
Search is complete and preserves every completed release invariant.

## MVP-2A Live Provider Architecture Gate

MVP-2A approves the design below for a future MVP-2B implementation. It does not claim
that the live adapters, process management, dependency changes, migrations, or live-run
surface already exist.

MVP-2B subsequently implemented the approved production-intended boundaries, and MVP-3A
connected them to the existing provider pipeline through a strict immutable factory for
mocked HTTP execution. MVP-3A persists an exact compatibility fingerprint and conservative
pre-call reservations, uses rank-five/keep-three acquisition, and observes cooperative
cancellation at provider/orchestration boundaries. It does not claim live-canary proof,
managed Wigolo lifecycle, a live CLI, or MVP-3B completion.

### MVP-3B Direct Xiaomi MiMo Amendment

On 2026-07-29 the user explicitly replaced OpenRouter with Xiaomi's direct MiMo API as
the sole MVP-3B LLM gateway. This amendment applies to MVP-3B and future live work; the
MVP-2B/MVP-3A OpenRouter implementation and tests are retained only in dated project
records; MVP-7 removes their executable code.

- Every LLM role uses direct `mimo-v2.5-pro` at the configured Xiaomi HTTPS base URL.
- No OpenRouter or MiniMax call is permitted in an MVP-3B run. Objective failures may
  retry the same MiMo route once; there is no cross-provider fallback.
- Xiaomi JSON mode is a syntax control, not strict schema enforcement. Requests use
  `response_format: {"type": "json_object"}`, explicitly demand JSON matching the
  application-provided schema, and undergo exact local Pydantic revalidation without
  response healing.
- The adapter reads `MIMO_API_KEY` only from an explicitly supplied environment mapping.
  Secrets remain redacted and must never enter logs, persistence, fingerprints, or
  exported artifacts.
- Returned model identity must equal `mimo-v2.5-pro`. Usage tokens are parsed strictly.
  Because the Chat Completions response does not provide a reliable per-response USD
  charge, cost is conservatively calculated from a frozen, dated price cap and labeled
  estimated.
- The approved live ceilings, public/non-sensitive restriction, deadlines, immutable
  fingerprints, rank-five/keep-three acquisition, deterministic release gate, and
  explicit per-run approval requirement remain unchanged.

### MVP-4 Live CLI Release Contract

MVP-4 exposes the validated MVP-3B stack through `run`, `inspect-run`, and `cancel-run`.
The live command accepts only an exact public/non-sensitive claim, explicit SQLite path,
optional run ID, and explicit token/cost ceilings. It validates direct-MiMo and loopback
Wigolo configuration before creating a run and prints only secret-free launch identity.

Resume requires the same run ID, byte-exact claim, and an exact fingerprint over provider,
adapter, model, prompt, schema, acquisition/normalization, policy, budget, and executable
repository identities. Any budget change requires a new run; consumed usage is never reset.
Released, blocked, and cancelled runs reconstruct without new calls. Failed runs may resume
under the exact same contract and reuse valid checkpoints. Arbitrary cross-version recovery
is not promised.

Cancellation is persisted and may be requested by another process. Checks occur before and
after provider calls and at orchestration boundaries. An active synchronous request may finish
or reach its deadline, but no new call starts after cancellation is observed. The fixture-only
Streamlit frontend remains unchanged and cannot launch live research.

### MVP-5 Local Live Web Interface Contract

MVP-5 adds a separate local Streamlit interface around the unchanged MVP-4 live
application/orchestrator and SQLite contracts. The fixture frontend remains explicitly
fixture-only. The live page uses SQLite as authority, executes the synchronous live run
in a background worker, and prevents duplicate database workers with application and
cross-process locks. Refresh and reopen operations inspect persistence rather than
recreating calls or release artifacts.

The local service manager verifies exact Wigolo `0.2.1` identity on loopback, starts only
the pinned `npx -y wigolo@0.2.1 serve` acquisition service, monitors bounded redacted
output, and stops only its owned process group. Health is not inferred from a port or
process alone. New live discovery uses metadata-only Exa Search `auto`. Wigolo remains
the primary public-page acquisition and exact evidence surface; optional Firecrawl is
gated behind Wigolo-local timeout/connection/malformed/extraction/challenge failures and
never bypasses authentication, paywalls, access denial, unsupported content, or source
policy failures.

MLP-2 permits provider keys to enter the loopback-only page through transient password
widgets. They are immediately stored in the user's macOS login Keychain and applied only
to the local server process; they never enter URLs, SQLite, logs, downloads,
provider child-process arguments, or repository files. The launcher does not request or
transport keys. Explicit process-environment configuration remains supported, and the
application does not load `.env` files or shell profiles.
Cooperative cancellation, fingerprints, budgets, restart compatibility, terminal
semantics, and human review remain exactly as released in MVP-4.

### MLP-3 Next.js Product Boundary

MLP-3 makes the Next.js App Router application in `web/` the live product. Its browser
code owns presentation, interaction, local polling, responsive layout, and meaningful
motion only. It has no direct provider, process, filesystem, Keychain, or SQLite access.

The strict FastAPI adapter in `frontend/api.py` binds to `127.0.0.1:8765`, rejects
non-loopback hosts and nonlocal browser origins, disables public API documentation, and
serializes strict Pydantic models only at the HTTP boundary. It delegates all run,
history, cancellation, service, and credential behavior to the existing typed Python
services. SQLite remains the authoritative run state, and the browser never invents
provider progress before persistence exposes it.

Credentials enter transient password fields and cross only the loopback API boundary.
The adapter passes them to the macOS Keychain boundary, which calls Apple's Security
framework in-process so a background request never needs a terminal password prompt and
no secret enters process arguments. It then applies them to its own explicit process
environment and returns status without returning a secret. Keys
remain forbidden in URLs, browser persistence, logs, SQLite, downloads, repository files,
and child-process arguments. The Streamlit dependency remains solely for the fixture
replay and read-only evidence utilities; it is not part of the live-product path.

### MLP-4 Research Quality and OpenAlex Boundary

MLP-4 makes focused research the default and balanced counterevidence an explicit
option. Focused mode runs only supporting-side work; balanced mode retains equal
supporting/opposing standards. Changing mode never changes configured run-level call,
token, USD, deadline, or provider ceilings. The selected mode and source target are
frozen controls and exact fingerprint inputs.

The Claim Planner produces separate provider-appropriate plans for every active stance:
three Exa web queries and one OpenAlex academic query per research round. Exa and
OpenAlex metadata are discovery-only. Every source is still independently acquired and
normalized before it can become evidence. OpenAlex is limited to ten search calls and
nominal USD 0.01 per run; its paid content endpoint is not used. Retracted works are
rejected, while open access, citation count, age, and PDF availability are not global
eligibility requirements.

OpenAlex officially requires its API key as an `api_key` parameter on the upstream HTTPS
request. This is the only MLP-4 exception to the general no-secret-in-URL transport
rule. The key remains forbidden in browser/application URLs, logs, errors, SQLite,
history, exports, fingerprints, and any persisted or displayed request metadata.

Discovery results are merged, exact canonical duplicates are collapsed, and
deterministic Stage-A ranking selects the highest-scored sources. Scores below 5/100
leave the acquisition pool but remain append-only trail records. New live runs target
five, ten, fifteen, or twenty usable snapshots per active stance per round, default ten,
and retain five bounded fallbacks per target. The historical seven-source control is
read-only compatibility only. There are no diversity or wildcard overrides. Stage-B
ranking orders independently acquired,
normalized snapshots for extraction. Neither ranking stage replaces or weakens exact
snapshot/quotation checks, Reviewer approval, Ledger
admission, or deterministic final validation.

### MLP-5 Provider Selection and SERP Search Boundary

New website runs freeze an ordered nonempty selection of SERP Search, Exa, and OpenAlex
in `ResearchControls` and the exact provider fingerprint. All three default on; disabled
sources create no plan, call, or configuration requirement. The Planner creates two
SERP Search, three Exa, and one OpenAlex query for each selected provider per active
stance. SERP Search uses bearer authentication, retains only normalized organic HTTP(S)
results, and is limited to twelve attempted calls per run. Its subscription cost is not
invented as a per-call USD value. All provider results remain discovery-only and merge
through the existing ranking, acquisition, snapshot, quotation, review, Ledger, and
release gates unchanged.

### MVP-6.4 Evidence Density Policy

New provider-backed runs require at least 50 exactly verified quoted words when the
quotation contains both a digit and a recognized statistical marker, and at least 75
words otherwise. Digit-only and marker-only quotations use 75. Marker matching is
case-insensitive and respects word/token boundaries, so incidental substrings do not
qualify. Frozen fixture replay alone retains its explicitly named legacy 50-statistical/
100-non-statistical contract. The
Reviewer continues to require literal statement entailment, neutral framing, and all
material qualifications, but does not require one approved fact to prove the complete
debated claim. Claim Fit 5 is rendered as direct evidence, Claim Fit 4 as indirect
evidence that is not independently decisive, and Claim Fit 3 as contextual evidence that
does not independently establish the claim. Partial evidence is qualified by the
application-owned indirect connective; Claim Fit 2, qualified-only, and Weak statements
also require explicit statement scope qualification. A one-sided Ledger produces a
deterministic not-balanced coverage warning; zero approved Ledger statements still fail
closed.

### MLP-4 Evidence-Yield Relaxation

On 2026-08-17 the user explicitly authorized a substantially more permissive evidence
funnel. New provider-backed runs use a 5/100 discovery floor, require 20 exact quoted
words for digit-plus-statistical-marker evidence and 30 otherwise, and retain
`claim_keyword_match_count` as non-negative audit metadata rather than a pre-Analyst
acceptance gate. This supersedes the current-run 20-point and 50/75 thresholds above;
frozen fixture replay retains its labeled historical 50/100 policy.

The relaxation does not permit fuzzy quotation matching, invented or healed source
text, incorrect offsets, altered context, mutable snapshots, unreviewed Ledger entry,
or validator bypass. Lower-quality and synonym-based candidates may reach the Analyst,
which still applies separate Evidence Quality and Claim Fit scoring before the
independent Reviewer and deterministic release gate.

### MVP-6.5 Immutable Run Authority and Read-Only Inspection

SQLite migration 5 installs `runs_raw_claim_immutable`, a `BEFORE UPDATE OF raw_claim`
trigger on `runs`. It aborts every actual claim change for every status with the stable
message `runs.raw_claim is immutable`, while identical-value assignments remain valid.
Trigger installation and the migration record are atomic. Migration 4 is solely the
same-run provenance-protection migration; the application-level `update_run()` check
remains defense in depth.

History and inspection are non-mutating operations. They open an existing database
through URI `mode=ro`, enable foreign keys and row reconstruction, set connection-local
`query_only`, validate migration records and required schema objects, and reuse that
session for transitive reads. They never call `init_db()`, create a missing file, migrate
an older schema, or fall back to writable access. Older databases require an intentional
writable run or resume. Newer, invalid, corrupt, missing, and inaccessible databases
produce explicit compatibility failures. `immutable=1` is not used because live WAL
writers may coexist with inspection.

### MVP-6.6 Runtime Status, Budget, and Contract Integrity

Every provider result status has an explicit process meaning. RELEASED is 0, BLOCKED is
10, FAILED is 11, CANCELLED is 12, and RUNNING is 13. RUNNING is a valid nonterminal
research result and never means that a brief exists. Exit 0 may also acknowledge a
separate documented administrative action, such as persisting a cancellation request,
but never represents nonterminal research output. Unknown future statuses fail clearly.

Model-call accounting distinguishes exact totals from known subtotals. Zero attempts are
complete exact zero. For every physical attempt, token usage is exact only when total
tokens are reported or both input and output tokens are present; cost is exact only when
explicitly recorded. Any missing component makes that aggregate exact total unknown,
while known values remain labeled subtotals. Failed, timed-out, interrupted, and running
attempts are never presumed free. Exa and Firecrawl billing remains outside MiMo
model-call accounting.

Before retry, fallback, or another physical model call, budget exposure uses exact usage
where known and the full stored reservation where usage is unknown. Unknown usage never
releases its reservation. If an attempt has neither actual usage nor a defensible
reservation, the next call fails closed because remaining budget cannot be proven.
Exact-limit exposure is allowed; exposure above a ceiling is rejected. Physical-call and
per-call reservation ceilings remain unchanged.

`ProviderRunContract` is a frozen strict Pydantic artifact. Its existing payload is the
exact canonical sorted compact JSON object containing fingerprint version plus provider,
adapter, model, prompt, schema, normalization, policy, and repository identities.
Duplicate, missing, extra, non-string, mismatched, noncanonical, or incorrectly hashed
payloads fail on construction and persisted reconstruction. `run_id` and `created_at`
remain outside fingerprint inputs. Valid historical canonical payloads remain readable;
inconsistent stored data is rejected without repair. The payload input set and
fingerprint version did not change, while the ordinary executable repository identity
changes because MVP-6.6 changes runtime code.

### MVP-6.7 Repository-Wide Type Contract Enforcement

Every repository-owned Python `def` and `async def` has an explicit return annotation,
and every named positional-only, positional-or-keyword, keyword-only, variadic
positional, and variadic keyword parameter has an explicit annotation. Only conventional
receiver parameters named `self` or `cls` may be unannotated. The contract covers
production and test code, including fixtures, callbacks, local helpers, nested functions,
methods, generators, and async functions; lambdas are not function signatures for this
rule.

`tests/test_type_contracts.py` enforces the contract with deterministic standard-library
AST parsing over repository-owned Python files. It sorts files and diagnostics, reports
all missing annotations with path, line, and discoverable qualified name, and treats an
unparseable owned file as a failure. MVP-6.7 changes annotations and enforcement only;
runtime behavior, Pydantic schemas, persistence, provider behavior, evidence policy,
budgets, exit codes, and acceptance criteria are unchanged.

### MVP-6.8 Persistence and Accounting Integrity

SQLite migration 6 installs unconditional `BEFORE UPDATE` and `BEFORE DELETE` triggers
for `snapshots` and `ledger_records`. Every existing-row mutation aborts with a stable
table-specific error; inserts, duplicate-key rejection, reconstruction, and read-only
inspection retain their established behavior. Trigger creation, exact-cost migration,
verification, and the migration record are atomic and idempotent. Other artifact tables
are intentionally outside this immutability scope.

Authoritative USD accounting uses finite non-negative `Decimal` values. Provider decimal
strings, configured ceilings, per-call caps, reservations, completed usage, aggregates,
resume reconstruction, comparisons, and operator summaries never pass through binary
float. SQLite stores new authoritative reservation and usage costs as canonical non-
exponent decimal text in `reserved_cost_usd_exact` and `cost_usd_exact`; the legacy
`REAL` columns remain compatibility-only and are null for new writes.

Migration converts historical `REAL` values through the shortest deterministic decimal
text representation of the already-stored float. This preserves the value SQLite can
recover but cannot restore source digits previously lost to IEEE-754, and no missing
precision is invented. Exact-limit exposure remains allowed; any amount above the limit
is rejected. The accounting policy and provider fingerprint identities are bumped to
prevent incompatible same-run resumption.

### MVP-6.9 Acquisition and Configuration Integrity

Origin media type is authoritative only when ResearchAssistant independently establishes
it through the bounded public-host source preflight, including the narrow PDF-signature
check. Firecrawl-returned Markdown is an acquisition representation, never proof of the
origin type. A strict frozen media-type provenance artifact stores the verified type and
the exact URL at which it was verified separately from an optional sanitized Firecrawl
declaration. Empty, malformed, unsupported, or non-string declarations remain unknown.

When primary preflight succeeds but Wigolo later fails with an approved fallback code, a
strict verified-preflight artifact crosses the fallback boundary. Firecrawl receives the
validated final URL. The verified media type remains authoritative only when the returned
source URL is the same verified URL; otherwise the response remains Markdown with the
earlier evidence explicitly tied to its different URL. Conflicting verified and provider-
declared values are preserved separately and never resolved in the provider's favor.

SQLite migration 7 adds nullable snapshot provenance columns without rewriting historical
immutable snapshot rows. Historical rows reconstruct with explicitly unknown media-type
provenance; new rows preserve URL, normalization, acquisition, provider, and media-type
semantics. Acquisition, Firecrawl-adapter, and provider-fingerprint identities are bumped,
so pre-MVP-6.9 runs cannot resume under the new semantics with the same run ID.

### MVP-8 Brief Export and Progress Contract

Only a read-only reconstructed RELEASED run may be exported. Export rechecks valid final
validation and the SHA-256 of the reconstructed rendered brief against the persisted
release hash; BLOCKED, FAILED, CANCELLED, and RUNNING runs never produce a report.
Local Markdown, PDF, and DOCX exports preserve the released brief verbatim and add only
application-owned trace metadata and the required human-review warning. Every export
identifies the released run ID, rendered-brief hash, exporter version, format, and an
aware generation timestamp. Export never mutates the run, Ledger, synthesis, validation,
or release state. Progress surfaces report persisted completed checkpoints; compatible
failed-run resumes reuse their typed, valid completed checkpoint artifacts.

### MVP-9 Verified Quote Selection and Deterministic Assembly

The Extractor model returns only a strict `VerbatimQuoteSelection`: one ordered tuple of
exact passages copied from the immutable normalized snapshot. It never authors brackets,
context, offsets, IDs, timestamps, provenance, or a completed candidate. ResearchAssistant
locates the passages sequentially, derives the immediate preceding and following sentences
or the correct start/end/truncated marker, joins non-contiguous passages with the canonical
ellipsis, and constructs the existing `ProvisionalCandidate` before the unchanged
post-extraction filter runs.

Exact selection mismatch is non-retryable because another model attempt cannot make
altered or invented text appear in an immutable snapshot. Malformed JSON, schema failure,
timeout, and other approved objective availability failures retain their bounded retry
semantics. Application assembly never heals or fuzzy-matches text.

SQLite remains at schema version 7. The semantic selection is stored at the existing
generic model-attempt JSON audit boundary, while assembled quote blocks and validated
offsets continue using the existing provisional/candidate columns. Historical rows are
not rewritten and terminal runs remain inspectable. New execution uses bumped prompt,
adapter, factory, retry, post-filter, schema, and fingerprint identities, so an older
run contract requires a new run ID under MVP-9.

### MVP-10 Evidence Portfolio and Trail

MVP-10 adds an append-only source-family, source-outcome, approved-portfolio, and
coverage trail in SQLite migration 8. Source-family identity prefers canonical source URL,
then resolved source URL, then immutable snapshot hash. Duplicates remain visible trail
records but do not receive model extraction or count as independent evidence. Coverage is
strong at three or more independent families with opposing or limitation evidence,
adequate at three or more otherwise, limited at one or two, and insufficient at zero.
Historical MVP-9 databases remain read-only inspectable without migration.

### MVP-11 Adaptive Research Expansion and Cost Control

MVP-11 replaces MVP-10's single expansion limit with the deterministic Research Governor.
An incomplete Round 1 completes Round 2; only application-owned policy after completed
Round 2 may authorize Round 3. Research round records are constrained to numeric values
1–3 in strict Pydantic artifacts and SQLite migration 9. A started Round 2 or Round 3
finishes unless cancellation, a hard ceiling, or unavoidable terminal provider or
infrastructure failure intervenes. The Governor records duplicate rate, recent
productivity, remaining normalized search angles, and conservative cumulative-budget
reservation before its one Round-3 decision. Governor decisions and terminal outcomes
are append-only, terminal runs do not start another round, and new Governor contracts
require a new Run ID. MVP-9 quotation, Reviewer/Ledger, and final-validator safeguards
remain unchanged.

### Approved Stack and Role Mapping

- Search and source acquisition: Exa Search `auto` plus OpenAlex Works search for
  provider-specific metadata-only discovery, pinned
  local Wigolo `0.2.1` over loopback for primary acquisition, and optional Firecrawl for
  the narrowly approved fallback failures. Search is discovery only; provider snippets,
  evidence fields, relevance scores, and summaries can never become trusted content.
- Historical MVP-2B/MVP-3A LLM gateway: OpenRouter with
  `xiaomi/mimo-v2.5-pro` primary and `minimax/minimax-m3` fallback. MVP-3B live runs use
  the direct Xiaomi MiMo amendment above instead.
- Structured output: strict JSON Schema derived from the exact requested Pydantic model,
  followed by local Pydantic revalidation. No response-healing layer is permitted.
- ResearchAssistant remains vendor-independent at the existing Protocol boundaries, but
  MVP-2B should implement only these concrete adapters. Do not create an additional
  general multi-provider framework without a separately demonstrated need.

The complete stack comparison, observed canaries, deadlines, cost model, dependencies,
environment, and acceptance limits are in
`.agent/plans/phase-mvp-2a-architecture-gate.md`.

### Discovery and Acquisition Contract

Each of the six Planner queries requests five ranked discovery results with no search-
time fetch. Each Researcher attempts candidates in rank order until three usable unique
snapshots exist for that query or all five candidates are exhausted. Therefore eighteen
snapshots remain the normal Extractor ceiling while thirty ranked acquisitions are the
structural maximum. Supporting and opposing workers retain equal limits.

Every candidate is fetched independently. Persist the original discovery URL and final
redirected URL separately. A source-declared canonical URL is advisory metadata and may
not replace either. Independently determine source media type from bounded HTTP metadata
and, when ambiguous, a bounded signature check. Neither Wigolo nor Firecrawl Markdown is
proof of the origin `Content-Type`, and Firecrawl `metadata.contentType` remains a separate
provider declaration rather than verified evidence.

Use a direct non-rendered fetch first. Only an explicit challenge or JavaScript-required
outcome permits one final Chromium-rendered attempt. No authentication, clicks, typing,
browser profiles, or general browser automation are allowed. Paywalls, persistent bot
protection, inaccessible pages, and failed rendering produce typed unusable-source
outcomes and cause the worker to continue down the ranked list. Use at most five
redirects. The proposed implementation caps are 10 MiB for HTML/text and 25 MiB for PDF;
MVP-2B must obtain dependency, deadline, and cap approval before implementation.

MVP-6.3 disables automatic source redirects and implements the five-redirect ceiling as
an explicit loop over 301, 302, 303, 307, and 308. Every initial or redirected URL is
validated before its local request: only credential-free HTTP(S), syntactically valid
public hostnames or global literal addresses, and DNS results containing exclusively
global addresses are permitted. Relative locations resolve against the current hop;
missing/malformed locations and loops fail closed. Wigolo receives the validated final
preflight URL. Firecrawl request URLs, returned source URLs, and recognized canonical
URLs are untrusted until they pass the same policy. The validation lookup and the HTTP
transport lookup are separate, so this is not socket-level DNS pinning and does not
claim complete DNS-rebinding prevention.

### Supported Content and PDF Policy

The MVP supports extracted HTML/article text, plain text, and a narrow deterministic
digital-PDF path. PDFs must be unencrypted, parseable, within configured size/page/time
limits, and contain usable embedded text. Scanned/image-only, encrypted, malformed,
empty, or unusably extracted PDFs return a normalized unsupported-content result; OCR is
out of scope. Page markers, headers, and footnotes may remain in extracted PDF text.

### Authoritative Snapshot and Quotation Contract

Provider Markdown, raw HTML, and PDF bytes are acquisition representations, not the
authoritative quotation surface. ResearchAssistant deterministically converts supported
content to normalized plain text, applies its 3,000-word limit, and persists an immutable
snapshot before any Extractor call.

The versioned normalizer must use deterministic charset handling; normalize Unicode to
NFC and line endings to `\n`; convert non-breaking spaces to spaces; collapse horizontal
whitespace; trim line edges; limit blank-line runs; retain visible link text but not
Markdown syntax or link destinations; and remove boilerplate only through deterministic
rules. The snapshot SHA-256 and word count are computed from the exact stored text.

All quote offsets refer to that normalized stored text. The LLM selects ordered exact
snapshot passages only. Python locates them sequentially, accepts each only when
`normalized_text[start_char:end_char] == exact_quote`, and deterministically constructs
the canonical bracketed quote envelope. Persist the normalization version,
verified origin media type and its verified URL, separately sanitized provider-declared
media type, acquisition version, original/final/canonical URLs, provider identity, and
optional provider-payload hash with the snapshot provenance. Normalization metadata is
not origin-media proof. A refetch may create a new snapshot but can never replace an
existing one.

### Live Retry, Budget, Data, and Restart Rules

- A logical LLM operation may attempt primary, retry primary once, fallback, and retry
  fallback once. Only timeout, 408/429/retryable 5xx, malformed JSON, schema/Pydantic, or
  approved deterministic validation failures qualify. Exact-selection mismatch,
  semantic disagreement, and low scores do not retry or switch models. Every physical
  attempt consumes the same run budget.
- Atomically reserve conservative tokens and capped price before each strict call;
  reconcile exact provider usage afterward. Retain usage from malformed, failed, and
  locally rejected responses. Missing final usage retains the full reservation; missing
  usage without a usable reservation makes the remaining budget unprovable and blocks
  retry/fallback. Do not call a fallback the remaining budget cannot cover, and fail
  closed when current pricing or route identity is unknown.
- The proposed hard run ceiling is USD 1.00, 1,000,000 tokens, and 160 physical LLM
  calls. Search and extraction still receive explicit usage/cost records, including zero
  local cost. These limits require explicit MVP-2B approval.
- Live MVP research is public and non-sensitive only. Wigolo receives public queries,
  URLs, and content locally. OpenRouter and the selected upstream receive role-specific
  claims/prompts and necessary source text. Configure data collection denied and prompt
  logging off, but do not claim a confidential/sensitive mode.
- Persist provider identity, adapter version, exact returned model/upstream, prompt and
  schema versions/hashes, normalization/PDF/retry/budget/pricing policy versions,
  repository revision, timing, status, and usage/cost per attempt or checkpoint. Resume
  only on an exact run-fingerprint match; changed code, adapter, model, prompt, schema,
  acquisition, normalization, or policy requires a new run.
- One future managed Wigolo process may serve both synchronous Researcher workers. The
  adapter must be thread-safe; workers retain separate SQLite connections and no shared
  mutable handoffs. Start only the pinned loopback service after health/identity checks,
  and stop only a child process ResearchAssistant owns.

## Run Provenance

The numbered contracts below preserve the historical MVP/MLP evidence and Reviewer
interfaces. Fresh v2 Phase 13 uses the Analyzer Admission contract described at the top of
this document and in the Phase 13 section below; it does not reinterpret historical records.

Every persisted artifact and every application-owned Pydantic handoff or envelope that can affect release must carry provenance. At minimum, release-relevant records include `run_id`, UTC ISO-8601 timestamps for creation or validation, and the stage-specific fields listed below. Retrieval records include `retrieval_attempt_id`, `query_id`, `query_round`, search rank, URL, status, and timestamp. LLM-produced records include `prompt_version`, `model_name`, and timestamp. Deterministic validators include the validator or filter version and validation timestamp. A deliberately narrow model-facing schema may omit contextual provenance fields only when its enclosing typed application request/result envelope and persisted domain artifact carry them; fields forbidden by that model-facing contract must not be exposed to the model merely to duplicate envelope provenance.

IDs are not preallocated. An ID is assigned only after the deterministic validation gate for that artifact succeeds: quote block IDs after post-extraction validation, Analyzer claim IDs after Analyzer Admission validation, historical Ledger claim IDs after Reviewer approval, and rendered brief hashes only after final validation succeeds.

## 1. Claim Planner

Defines the research boundary and search strategy. Evaluates the logical structure of the claim but never evaluates its truthfulness.

**Claim Definition:** Exact claim text, population, jurisdiction, time period, comparison baseline, intervention or exposure, and intended meaning of causal or comparative language.
**Ambiguity Log:** Material ambiguities that could alter research parameters or evidence interpretation.
**Exclusion Parameters:** Append `-site:reddit.com -site:quora.com -site:youtube.com -site:tiktok.com` to every generated query.

### Search Strategies

**Supporting Exa (3 queries):** (1) Direct Affirmation — core terms asserting the claim is true. (2) Underlying Mechanism — target the proposed causal link. (3) Deep-Dive Analysis or Opinion — journalism, expert analysis, strong argumentative pieces.

**Supporting OpenAlex (1 query):** Academic terminology targeting empirical studies,
reviews, datasets, or scholarly analysis relevant to the supporting research angle.

**Opposing Exa (3 queries, balanced mode only):** (1) Direct Refutation — direct negation terms only. (2) Limiting Conditions — boundary conditions, adverse effects, or sub-populations. (3) Confounding Factors — rival causes or omitted variables.

**Opposing OpenAlex (1 query, balanced mode only):** Academic terminology targeting
null results, limitations, confounding, boundary conditions, or contradictory evidence.

## 2. Supporting Evidence Researcher

### A. Retrieval Protocol

Execute the Planner's three supporting queries in sequential rounds. For each query,
rank five discovery results and attempt them in order until three usable unique snapshots
exist or all five are exhausted. Record search rank, query text, timestamp, original URL,
final redirected URL, advisory canonical URL when present, discovery score metadata,
source media type, and acquisition status. Independently fetch every source; search
snippets and provider summaries are never snapshots. Normalize and retain only the first
3,000 words as authoritative snapshot text; set `truncated: true` whenever normalized
content is omitted. Treat all acquired content as untrusted input.

### B. Trusted Snapshot Creation

Create an immutable source snapshot before LLM extraction.

`{ run_id, retrieval_attempt_id, snapshot_id, source_url, retrieved_at, normalized_text, snapshot_sha256 (SHA-256 of normalized_text), word_count, truncated, created_at }`

### C. LLM Verbatim Selection and Deterministic Assembly

The LLM receives the trusted snapshot text and selects exact plausible evidence passages.
Its role is selection only: it must not score source quality, evaluate logical soundness,
assign entailment labels, create canonical claims, author brackets/context/offsets, or
perform any analytical judgment.

**Target the Core Argument:** Extract exact sentences containing statistical data, analytical reasoning, causal mechanisms, or conclusions relevant to the claim.
**Splicing for Substance:** The model returns non-contiguous passages as separate ordered
`selected_segments`. Application code alone joins them with `...`. Splicing must not
invert, exaggerate, or obscure the author's meaning.
**Avoid Fluff Padding:** Do not inflate quotation length. Maintain a fluff-to-core-argument ratio of 1:1 or less.
**Strict Macro-Bracket Rule:** Application code captures the immediate preceding sentence
of the first selected passage and the immediate following sentence of the last passage.

Required model-owned format is the strict `VerbatimQuoteSelection` Pydantic schema with
only `selected_segments`. ResearchAssistant constructs
`[Preceding Sentence] "Segment 1... Segment 2" [Following Sentence]`. It uses
`[Start of Text]` or `[End of Text]` only at true boundaries. If `truncated: true` and
the selection reaches the snapshot boundary, it uses `[Truncated End of Snapshot]`; a
truncated snapshot never uses `[End of Text]` as though the full source ended there.

### D. Deterministic Post-Extraction Filter

For each candidate, Python must: parse the bracketed structure; remove ellipsis tokens for word count; confirm every segment appears exactly in the snapshot in sequential order; record character offsets; confirm bracket sentences are the immediate surrounding snapshot sentences; reject `[End of Text]` when `truncated: true`; apply length and marker rules; reject failures before assigning an ID.

**Relevance:** Configured claim-keyword matches are counted and persisted as audit metadata. Zero matches do not reject a source before semantic Analyst review because a source may use synonyms, narrower terminology, or domain-specific language.
**Substance and Data Density:** For current provider-backed runs, if the quoted segments contain at least one digit and one recognized statistical marker, the minimum length is 20 words. Otherwise, the minimum length is 30 words. Statistical markers are `%`, `percent`, `rate`, `ratio`, `average`, `median`, `index`, `p-value`, `million`, `billion`, `growth`, and `decline`; matching is case-insensitive and respects word/token boundaries. A digit alone, a marker alone, or an incidental substring uses 30. Frozen historical fixture replay explicitly retains the legacy 50/100 policy and may not supply it to a new provider-backed run.

### E. ID Assignment

After all checks pass, generate:
```python
uuid5(namespace=URL_NAMESPACE, name=f"{source_url}::{snapshot_sha256}::{segment_offsets}")
```
Failed candidates receive no ID and never reach the Analyst.

### F. Candidate Handoff Schema

Each passing candidate includes: `run_id`, `stance` (`supporting | opposing`), `quote_block_id` (UUID), `source_url`, `retrieval_attempt_id`, `query_id`, `query_round`, `search_rank`, `retrieved_at`, `snapshot_id`, `snapshot_sha256`, `snapshot_created_at`, `extracted_quote_block` (bracketed), `segment_offsets` (char ranges), `raw_segment_word_count`, `has_statistical_markers`, `claim_keyword_match_count`, `truncated`, `extraction_prompt_version`, `extraction_model_name`, `extracted_at`, `post_filter_version`, and `post_filter_validated_at`. No scores, entailment labels, or analytical rationales. Deliver all candidates from one round as a single typed Pydantic collection.

## 3. Opposing Evidence Researcher

Follows the exact protocol of the Supporting Evidence Researcher, executing the three opposing queries with identical retrieval depth, snapshot format, extraction rules, post-extraction filter, candidate schema, and logging requirements.

## 4. Evidence Analyst & Claim Ledger

The Analyst performs semantic quality control, verifies evidence against trusted snapshots, and produces canonical factual statements for deterministic downstream use. It does not search the public web or perform new extraction.

### A. Snapshot Integrity Verification

Load stored text via `snapshot_id`; recompute SHA-256 and confirm it equals `snapshot_sha256`; confirm every segment matches recorded offsets in sequential order; confirm bracket sentences are the immediate surrounding sentences. Reject on any failure. A matching hash alone never proves a quotation exists in the source.

### B. Dual-Dimension Scoring

Each candidate is scored independently on two dimensions. The two scores must be assigned separately and must not be averaged or combined into a single value.

**Evidence Quality (1–5)** — Strength of the source and excerpt on its own terms, independent of the claim. 5: peer-reviewed empirical work, large dataset, clear methodology. 4: strong analytical piece, credible institution. 3: credible but limited data or secondary reporting. 2: speculative, vague, or methodologically weak. 1: unreliable regardless of topic.

**Claim Fit (1–5)** — Precision with which the excerpt addresses the claim as worded, including all qualifications and superlatives. 5: directly addresses exact claim, population, mechanism, and scope. 4: addresses core claim with minor gaps. 3: addresses a related or narrower version. 2: tangential; requires inferential bridging. 1: does not address the claim as stated.

Ledger eligibility is based on both axes, not on a compensating combined score. Evidence Quality
must be at least 2 and Claim Fit must be at least 2. Evidence with Evidence Quality below 2 or
Claim Fit below 2 is never eligible for the final Ledger. The derived `ledger_score` remains a
3–5 summary calculated from the two scores after both minimum thresholds pass; it does not
override either threshold.

Claim Fit 2 items may enter the final Ledger only as `qualified_only` evidence and require an
explicit scope or reliability qualification. Claim Fit 3 items are ordinary eligible evidence
and are not rejected solely because they are contextual or narrower than the complete claim.

Derived Ledger score:

| Total score | Ledger score |
|---|---|
| 5–6 | 3 |
| 7–8 | 4 |
| 9–10 | 5 |

Note truncation; reduce Evidence Quality if missing text could materially change the excerpt's meaning.

### C. Placement Assignment

The Analyst assigns `placement` deterministically from the score pair and derived Ledger score; it is binding on the Synthesizer and Renderer.

| Condition | Placement |
|---|---|
| Claim Fit is 2 | `qualified_only` |
| Otherwise, derived Ledger score is 5 | `primary` |
| Otherwise, derived Ledger score is 4 | `secondary` |
| Otherwise, derived Ledger score is 3 | `supporting` |

`qualified_only` requires an explicit scope or reliability caveat. The Synthesizer may not promote a `qualified_only` item to a higher tier.

### D. Entailment Classification

**Strong** — excerpt directly supports the statement. **Partial** — supports a qualified or narrower version. **Weak** — limited support requiring explicit caution. Entailment is independent of placement; a `primary` claim may carry Partial entailment if the statement is appropriately narrowed.

### E. Canonical Approved Factual Statement (Draft)

For every approved quote, the Analyst drafts one or more canonical factual statements. Each draft must be fully entailed by the quotation and brackets, preserve all material qualifications, add no outside facts, stand alone grammatically, contain no rhetorical connective, and accurately reflect the Claim Fit score. Claim Fit 2 statements must preserve an explicit qualification; Claim Fit 3 statements may be ordinary eligible evidence when fully entailed and no broader than the source. Drafts are submitted to the Statement Reviewer before Ledger entry and are not yet approved.

### F. Statement Reviewer

The Statement Reviewer is a separate LLM call receiving only the extracted quote block, the bracket sentences, the draft statement, and the assigned Claim Fit score. It has no access to the Evidence Quality score, the claim under debate, or any broader research context. It must confirm: (1) the statement is fully entailed by the quotation and brackets without outside inference; (2) all material qualifications are preserved; (3) no framing, emphasis, or omission systematically favors one side; (4) the statement's scope is consistent with the Claim Fit score — a Claim Fit 2 statement must remain qualified-only, while Claim Fit 3 must not be rejected solely because it is contextual or narrower than the full claim.

If all conditions are met, the Reviewer returns `approved: true` and the statement enters the Ledger unchanged. On any failure it returns `approved: false` with a failure code and brief rationale. The Analyst may revise and resubmit once; a second failure rejects the quote block entirely. The Reviewer must not suggest replacement wording; its role is audit only.

The model-facing Reviewer decision never contains an approval ID. After the application
validates the exact reviewed statement and approved decision shape, it derives the
versioned `rappr_v1_<sha256>` approval ID from the canonical stable review input.
Persisted legacy UUID approval IDs remain readable.

### G. Ledger Record Schema

```json
{
  "run_id": "UUID string",
  "ledger_claim_id": "UUID string",
  "quote_block_id": "UUID string",
  "stance": "supporting | opposing",
  "approved_factual_statement": "exact approved sentence",
  "approved_claim_text": "exact quote block with brackets",
  "evidence_quality": "1 through 5",
  "claim_fit": "1 through 5",
  "ledger_score": "3, 4, or 5",
  "placement": "primary | secondary | supporting | qualified_only",
  "entailment": "Strong, Partial, or Weak",
  "source_url": "string",
  "retrieval_attempt_id": "UUID string",
  "snapshot_id": "string",
  "snapshot_sha256": "string",
  "segment_offsets": [{"start_char": "integer", "end_char": "integer"}],
  "analyst_prompt_version": "string",
  "analyst_model_name": "string",
  "analyst_completed_at": "UTC ISO-8601 timestamp",
  "reviewer_prompt_version": "string",
  "reviewer_model_name": "string",
  "reviewed_at": "UTC ISO-8601 timestamp",
  "reviewer_approval_id": "legacy UUID string or rappr_v1_<sha256>",
  "ledger_validated_at": "UTC ISO-8601 timestamp"
}
```

Each `ledger_claim_id` maps to exactly one approved factual statement. A quote block may support multiple Ledger claims only when each statement is separately entailed and separately reviewed.

## 5. Debate Synthesizer

Constructs the debate brief from approved Ledger records. It returns a typed `SynthesisOutput` Pydantic model — never free-form prose or a raw dictionary. JSON serialization is permitted only at persistence, API, logging, or export boundaries.

### Operational Rules

- Use only approved Ledger claims; add no new factual claims.
- Copy every `approved_factual_statement` exactly; never paraphrase, merge, shorten, or expand.
- Order by `placement`: `primary` → `secondary` → `supporting`; `qualified_only` items must use the scope or reliability template and may not be promoted.
- Do not manufacture balance when evidence is one-sided.
- Partial and Weak entailment claims require the entailment qualification template.
- Use only approved connective template IDs; no free-form transitions containing factual content.

### `SynthesisOutput` Model Schema (JSON Representation)

```json
{
  "run_id": "UUID string",
  "synthesizer_prompt_version": "string",
  "synthesizer_model_name": "string",
  "created_at": "UTC ISO-8601 timestamp",
  "sections": [{
    "section_type": "supporting | opposing | limitations",
    "items": [{
      "connective_template_id": "string",
      "ledger_claim_id": "UUID string",
      "reviewer_approval_id": "legacy UUID string or rappr_v1_<sha256>",
      "stance": "supporting | opposing",
      "placement": "must match Ledger value exactly",
      "entailment": "must match Ledger value exactly",
      "approved_factual_statement": "exact Ledger string"
    }]
  }]
}
```

Within the application, this structure must be validated, instantiated, and passed to the Renderer as a `SynthesisOutput` Pydantic model. The JSON form above is a serialization representation only and must not be used as a raw-dictionary agent handoff. The `stance`, `placement`, `entailment`, `ledger_claim_id`, `reviewer_approval_id`, and `approved_factual_statement` fields are copied from the Ledger unchanged.

The Synthesizer cannot provide the brief title, displayed claim, claim label, section
headings, or other framing prose. Those fields are application-owned release structure.

## 6. Deterministic Final Renderer & Validator

### A. Fixed Connective Templates

The renderer may use only pre-approved non-factual templates. The complete enumerated list must be defined at deployment and stored in the validator's configuration. No template may contain domain-specific factual claims. Examples:
```text
Supporting evidence:
Opposing evidence:
A limitation is:
The source provides partial support:
The source provides weak support:
This source addresses a narrower version of the claim:
This source's reliability is limited:
```

### B. Exact Claim Validation

For every rendered item confirm: `ledger_claim_id` exists in the Ledger; `reviewer_approval_id` matches the Ledger record; statement exactly matches the Ledger string; `placement`, `stance`, and `entailment` match the Ledger values; statement appears no more than permitted; supporting Ledger items appear only in supporting-compatible sections and opposing Ledger items appear only in opposing-compatible sections, except within explicitly configured limitations sections; `qualified_only` items use a qualification template; Partial and Weak items use the entailment template; no unrecognized field contains renderable prose. Any mismatch blocks release.

### C. Rendering

Assembled mechanically from the fixed title `Research Brief`, the fixed label
`Claim under review`, the exact persisted authoritative submitted claim, the fixed
Supporting Evidence, Opposing Evidence, and Limitations headings in canonical order,
approved templates, Ledger statements, and source citations. The Synthesizer may never
submit free-form prose or structural framing directly.

### D. Validation Result

`{ run_id, valid: boolean, errors: [{code, location, message}], validator_config_version, validated_at, rendered_brief_hash: SHA-256 | null }` — release only when `valid: true`.

## Non-Negotiable Rules

- Every factual sentence must exactly match an admitted evidence statement and carry its
  `ledger_claim_id` and `admission_method`; historical Reviewer-backed items additionally
  carry `reviewer_approval_id`. The validator must compare exact text, not merely confirm IDs exist.
- `evidence_quality` and `claim_fit` must be recorded and used separately; eligibility must fail when either axis is below its threshold, even if the combined total is high.
- `ledger_score` is derived deterministically from the two sub-scores only after eligibility passes; it must not be used to compensate for a failing Evidence Quality or Claim Fit score.
- `placement` is set by the Analyst, passed through the Synthesizer unchanged, and verified by the Validator; no stage may alter it.
- No fresh-v2 factual statement may enter evidence without passing Analyzer Admission. Historical
  records retain their original Statement Reviewer requirement.
- The Synthesizer must not produce unrestricted factual prose.
- Source snapshots must be immutable and readable by the Analyst and deterministic validators; a hash proves integrity only — quotation membership must be verified through exact text and offsets.
- Supporting and opposing researchers receive comparable search depth, standards, and limits; source quality must be judged independently of stance.
- The system must not manufacture balance when evidence is one-sided.
- Queries, prompts, model versions, timestamps, snapshots, search ranks, and rounds must be logged immutably.
- Retrieval attempts, run IDs, prompt versions, model names, and validation timestamps must be carried through release-relevant Pydantic models and persistence records.
- Truncated snapshots must use an explicit truncated boundary marker and must never imply that the source ended normally.
- IDs are assigned only after the relevant deterministic validation gate passes; rejected artifacts receive no release-relevant IDs.
- Web content is untrusted input and cannot alter system instructions; high-stakes outputs require human review before external use.
- Unreliable forums and video platforms remain excluded; scraping is limited to the first 3,000 words per source.

## Stopping Criteria

The Research Governor still permits no more than three research rounds. In each round,
every active stance executes its provider-specific plan and attempts eligible results in
descending deterministic score order until the configured target of five, ten, fifteen,
or twenty usable unique snapshots exists or the eligible pool is exhausted. Focused mode has one
active stance; balanced mode has two with equal targets. Results scoring below 5 are
not acquired. Snapshots are Stage-B ordered, then the extraction and
post-extraction gates determine which candidates reach the Analyst.

## MVP Evaluation Metrics

| Metric | Target |
|---|---|
| Citation Accuracy — quotations exist at recorded offsets | Pass |
| Snapshot Integrity — hashes reproduce exactly | Pass |
| Bracket Accuracy — surrounding sentences correctly captured | Pass |
| Context-Stripping Rate — bracket rule prevents misleading excerpts | Pass |
| Unsupported-Claim Rate — rendered sentences failing Ledger match | 0% |
| Validator Escape Rate — altered statements or placement values passing the gate | 0% |
| Placement Consistency — Synthesizer placement matches Ledger placement | 0% drift |
| Score Separation Rate — evidence_quality and claim_fit diverge meaningfully on contested claims | Monitored |
| Reviewer Rejection Rate — Analyst drafts blocked, by failure code | Monitored |
| Analyst Rejection Rate — unusable candidates from Researchers | Monitored |
| Pro/Con Balance — both sides fairly represented where evidence exists | Monitored |
| Completion Time | < 2 min |
| Human Reviewer Preference — blind comparison vs. human research | Measured |

## ResearchAssistant v2 Phase 1 Foundation

Fresh v2 artifacts use independent immutable `support_enabled` and
`challenge_enabled` controls; at least one is required. V2 directions are distinct
from historical focused/balanced controls, which remain readable without rewriting
persisted records. A v2 run identity fixes `researchassistant-v2` with the Phase-1
policy identity before append-only v2 artifacts can be recorded. This phase adds no
new research control flow, provider behavior, or UI behavior.

## ResearchAssistant v2 Phase 2 Multi-Model Routing

V2 model selection is expressed through logical aliases and a frozen stage-routing
table, never scattered provider model strings. Fresh v2 routing preflight resolves every
enabled logical route to a secret-free physical provider/model identity and an exact,
positive price cap before provider work can begin. MiMo normal and MiMo Pro are separate
Xiaomi-compatible routes with returned-model validation. Luna High is configuration-only
until a later authorized phase supplies a verified transport; its endpoint, credential,
physical model identifier, and pricing are explicit deployment configuration. Routing,
physical provider/model identity, prompt and schema versions, pricing, and relevant
non-secret provider settings are all provider-contract fingerprint inputs. Historical
direct-MiMo contracts and persisted stage aliases remain readable.

## ResearchAssistant v2 Phase 3 Initial Planner and Broad Round 1

Fresh v2 startup performs exactly one MiMo-v2.5-Pro Initial Planner call and creates only
the broad Round-1 plan. The exact submitted claim is retained unchanged; scope records
are limited to material interpretations or ambiguities. A single application-owned v2
policy determines the valid provider/strategy lanes for enabled directions and enabled
discovery providers, preserving the established two SERP Search, three Exa, and one
OpenAlex slots per enabled direction. The model supplies only scope text and query text
for those lanes; application code owns IDs, timestamps, policy identity, and validation.

Round-1 plans and queries are append-only records carrying run, direction, provider,
numeric round `1`, strategy, query text, timestamps, and policy identity. Disabled
directions and providers, invalid lanes, duplicate IDs, and normalized duplicate query
text within a provider/direction/round lane fail before persistence. No objective,
importance score, targeted replan, Round 2, or Round 3 query is created in this phase.
Historical planner outputs and pre-v2 pipelines remain readable.

## ResearchAssistant v2 Phase 4 Discovery, Identity, Clustering, and Scout

Fresh-v2 Round-1 discovery supports OpenAlex, arXiv, PubMed, Exa, and Serper. Every result
is normalized into a typed metadata-only artifact carrying original provider/query metadata,
direction, round, provider rank, source identity fields, and an immutable provenance chain.
Snippets, abstracts, provider metadata, and optional Crossref bibliographic enrichment are
discovery metadata only and cannot be cited as evidence or used for Claim Ledger admission.

Before Scout, canonical URLs remove tracking parameters and conservative same-source
clustering may use exact canonical URL, DOI, strong normalized-title equality, or exact
author/year/title identity. Clusters retain preferred and alternate URLs, provider/query
references, and all metadata provenance; topical similarity never creates a cluster.

Scout uses the existing v2 MiMo-v2.5 normal route and receives batches of at most 30
metadata-only candidates. It returns exactly one application-owned stable-ID decision per
item: `retrieve`, `maybe`, or `skip`. Unknown, duplicate, missing, malformed, or wrong-run
responses are rejected. Scout is recall-biased, cannot assess evidence quality or Ledger
eligibility, cannot generate factual claims, and cannot promote disabled directions. One
bounded retry is allowed; a repeated failure is persisted as audit data and falls back to
deterministic ranking with all affected candidates retained as `maybe`.

## ResearchAssistant v2 Phase 5 Acquisition, Snapshot, Probe, and Survivor Boundary

Fresh-v2 acquisition consumes only conservative Phase-4 source clusters. It orders Scout
`retrieve` records ahead of deterministic discovery rank and Scout `maybe` records, and
does not normally acquire Scout `skip` records. A cluster attempts its preferred URL before
bounded retained alternates. One successful equivalent source prevents repeat acquisition.

Wigolo remains the primary acquisition boundary. Firecrawl is optional and may run only as
the existing approved fallback after a qualifying Wigolo failure that carries independently
validated preflight provenance. Phase 5 neither bypasses URL/redirect validation nor weakens
media-type provenance, PDF restrictions, normalization, or snapshot hashing.

Each success is a strict immutable `SourceSnapshot` stored inside the append-only v2 artifact
with source-cluster identity and provider audit chain. Probe deterministically ranks exact
sentence windows from that stored text without an LLM call. It retains snapshot ID/hash and
character offsets, uses opening/conclusion/evidence-density/citation fallback windows, and
does not assess Claim Fit, Evidence Quality, factual truth, or Ledger eligibility. Only a
successful snapshot with one or more Probe windows enters the survivor pool. Probe failure
preserves its snapshot and audit record but yields no Gap-Analysis input.

## ResearchAssistant v2 Phase 6 Luna Gap Analysis

After Round 1, GPT-5.6 Luna High receives only bounded, persisted discovery, survivor,
Probe, failure, duplicate-family, query-history, and budget context. It returns typed,
priority-ordered material gaps, gap-linked search directions, discovered terminology, and
an explicit continue-or-stop recommendation. The result is advisory: it cannot execute
searches, raise application limits, create evidence, or enter the Claim Ledger.

## ResearchAssistant v2 Phase 7 Adaptive Search Continuation

Adaptive continuation begins only from persisted Gap Analysis. A Round-1 stop creates no
Round-2 plan. When continuation is useful, the MiMo-v2.5-Pro Search Agent proposes only
queries linked to persisted Gap IDs, using discovered terminology and complete prior-query
history. Application policy validates enabled directions and providers, authoritative
provider-round ceilings, budget reservations, and exact or clearly trivial query rewrites.

Each authorized round reuses the existing v2 sequence: provider search, normalization and
conservative clustering, batched Scout, acquisition, deterministic Probe, and survivor
merge. Luna runs again after Round 2. A deterministic Governor—not the model—then permits a
narrow Round 3 only when a material gap, continued Luna recommendation, new direction,
eligible provider, materially new query, provider capacity, and protected downstream
budget all remain. Duplicate saturation of at least 70% stops continuation. Round 3 has at
most three queries and one query per provider/direction lane. The historical Phase-7 contract
has no Round 4, recursive continuation, automatic citation tree, or disabled-direction search.

## Historical ResearchAssistant v2 Phase 8 Source Selection and Deep-Analysis Queue

After adaptive searching stops, the complete merged survivor pool remains an immutable,
append-only input. Final Source Selection sends MiMo-v2.5-Pro only the exact claim, enabled
directions, survivor metadata, deterministic source-family identities, bounded Probe
passages, Gap history, and search-round provenance. Its ordered recommendations may contain
only survivor IDs and short rationales with optional known Gap IDs. Application validation
rejects invented sources, wrong-direction gaps, duplicates, more than ten recommendations
per direction, and family domination while unused families remain. A failed attempt is
retried once; repeated failure or insufficient safe selection budget uses deterministic
family-round-robin ordering without removing a survivor.

Recommendation is workload prioritization, not factual validation, evidence approval, or
Claim Ledger admission. The deterministic deep-analysis queue places recommended survivors
first, then complementary non-recommended survivors, and retains the longest safe prefix.
Each source has a hard 60,000-token allowance and a seven-call workload envelope: two
Extractor attempts, up to two attempts for each of two Analyst operations, and one
independent Reviewer call. Normal Reviewer rejection is terminal for that source; there is
no Reviewer-directed Analyst revision or second Reviewer call. Two additional physical
calls and route-priced tokens/cost are reserved for mandatory Synthesis. Every survivor
persists recommendation, full priority order, queue status, source attribution, and the
physical-call, token, or cost reason when budget prevents deep analysis. Terminal extraction,
Analyst, or Reviewer outcomes are replaced from the unqueued deterministic priority pool by
a versioned typed backfill artifact. The hard total remains 160 physical calls and the
run-wide token ceiling remains exactly 500,000.

## Historical ResearchAssistant v2 Phase 9 Luna Evidence Analyst

Deep analysis accepts only Phase-8 queued survivors paired with an exact
`CandidateQuoteBlock` and its immutable `SourceSnapshot`. MiMo-v2.5-Pro remains the v2
Extractor route and selects snapshot passages only. Before semantic analysis, application
code revalidates the snapshot hash, exact segment membership, offsets, bracket context,
candidate identity, length policy, and provenance; Analyst output cannot rewrite any of it.

Historical Phase-9 Analyst work used a v2-only prompt and GPT-5.6 Luna High for two logical
operations: semantic proposition/relationship assessment and scoring, then initial canonical
factual-statement drafting. The prompt contains only the exact candidate quote block,
immediate context, and necessary metadata; it does not contain the complete snapshot. Source text,
the narrowest supported proposition, and the proposition's relationship to the requested
claim remain separate typed fields. Material limitations, inferential boundaries, and
rationale persist with the assessment. Application validation prevents support/challenge
crossing while allowing a qualification in either enabled direction.

The existing 25-pair Evidence Quality / Claim Fit table remains authoritative. Application
code derives approval, Ledger score, placement, and Claim Fit 2 qualification requirements,
then constructs the existing `ScoreDecision` and `StatementDraft`. Every Luna physical
attempt uses the persisted `model_route_attempts` reservation/finish boundary with the
configured route's conservative tokens and exact cost, and each logical operation has at
most two attempts. A final Analyst failure retains the survivor and exact candidate with a
failed deep-analysis state but no Reviewer-ready draft. Phase 9 creates no `LedgerRecord`;
separate Reviewer approval and deterministic Ledger admission remain mandatory.

## Historical ResearchAssistant v2 Phase 10 Reviewer and Claim Ledger Integration

Phase 10 connects Phase-9 Reviewer-ready drafts to the established downstream quality
gate. Historical Phase-10 Reviewer calls used MiMo-v2.5-Pro and received only the existing narrow
Reviewer input. The application preserves exact Reviewer decision validation and derives
the existing versioned approval ID; the Reviewer cannot supply IDs, confidence, or
replacement wording. One independent Reviewer call is allowed per source. Rejection is
terminal for that source and triggers Phase-12 deterministic backfill; no Analyst revision
or second Reviewer audit occurs.

The existing score-pair table, placement derivation, Claim Fit 2 qualification rule,
`QUALIFIED_ONLY` restriction, and `admit_ledger_record` validation remain authoritative.
V2 Ledger admission adds immutable sidecar provenance for direction, discovery round,
source family, recommendation state, survivor ID, and relevant Gap IDs. Recommendation
is informational only. Application policy rejects disabled-direction evidence before any
Reviewer call. Migration 13 adds only append-only v2 Ledger-admission rows; it does not
rewrite or weaken historical Ledger records or their SQLite immutability triggers.

## Historical ResearchAssistant v2 Phase 11 Synthesis and Final Research Output

Historical Phase-11 synthesis sent MiMo-v2.5-Pro only a strict typed projection of the exact claim,
enabled directions, Reviewer-approved Ledger statements, deterministic placement and
entailment, qualified-only statements, unresolved typed gaps, stopping disclosure, and
non-evidentiary recommendation metadata. It never receives raw source text, snapshots,
quotes, unreviewed Analyst output, or a route to reinterpret sources. The model selects and
orders approved Ledger IDs only; the application copies their canonical factual statements.

The final result discloses the chosen direction, recommendation subset, complete surviving
pool, unresolved gaps, and deterministic stopping reason. It labels each source as
recommended-and-analyzed, recommended-without-Ledger-evidence, surviving-and-analyzed,
surviving-not-deeply-analyzed, or budget-prevented. Support-only and challenge-only results
must not contain or imply evidence from the disabled direction. V2 final validation layers
direction/provenance/source/recommendation checks over exact Ledger validation and hashes the
complete mechanically rendered output only after every check succeeds.

## ResearchAssistant v2 Phase 13 Analyzer Admission Cutover

Fresh v2 replaces the historical Reviewer boundary with one concise GPT-5.6 Luna High Analyst
call per successfully extracted source. The typed response contains the two scores, direction,
exact candidate identity, entailment and qualification fields, and the final factual statement.
There is no fresh-v2 self-revision, duplicate drafting call, `ReviewerDecision`, or
`LLMStage.REVIEWER` request.

Deep analysis reserves three physical calls per source: up to two exact-extraction attempts and
one Analyst call. It processes the full deterministic priority pool until the run-wide budget
is reached. Every source retains its actual terminal state: analyzed, analyzer-rejected,
analyzer-failed, not queued, or budget-prevented. Persisted per-source artifact keys are unique.

`V2EvidenceAdmissionBatchResult` performs the deterministic boundary after Analyst execution.
It admits only analyzer-approved sources that pass exact quote and snapshot provenance,
direction, score, placement, qualification, and final-statement checks. It derives the claim ID
from the Phase-13 admission policy, run, source, and statement. Analyzer-admitted records have
no Reviewer approval ID; rejected and failed sources create no evidence record.

Synthesis, final validation, API, UI, and export accept the analyzer-admitted projection and
display that it was not independently reviewer-approved. Phase-13 keys, policy identities,
fingerprints, and budget constants are additive. Phase-12 and earlier Reviewer, Ledger,
extraction, budget, and final-output artifacts remain readable with their original meaning.
Fresh synthesis is deterministic Python assembly of the typed analyzer-admitted projection and
makes no Synthesizer model call; direct MiMo synthesis remains compatibility-only for historical
Reviewer-backed artifacts.

## ResearchAssistant v2 Post-Phase-13 Conditional Round Four

Only a completed, non-degraded fresh-v2 Round 3 may enter one post-Round-3 Luna Gap Analysis.
The Gap input is cumulative across Rounds 1–3 and remains bounded to persisted metadata, Probe
passages, families, duplicate/acquisition outcomes, strategy history, and remaining budget. The
application first proves that two possible Gap attempts and the complete protected downstream
workload fit. The Gap result is immutable even when unavailable or degraded.

A `Gap ID` is the stable identity of one unresolved evidence gap across rounds. Reusing an ID
requires the same enabled research direction and the same explicit claim-linked identity:
`claim_dimension` plus `unsupported_claim_component`. Rationale and explanatory missing-evidence
wording may evolve as evidence is analyzed, but a genuinely new evidence gap receives a new ID and
a semantically duplicate gap cannot receive a second ID. Gap Analysis, source-selection history,
and reconciliation reject conflicting or duplicate semantic identities instead of merging them.
Historical artifacts without claim-linked fields remain readable as legacy unknown identity and are
never heuristically reinterpreted.

Round 4 is a one-shot, application-owned Governor decision, never a recursive continuation. It
requires material enabled-direction gaps, continued research, an eligible provider, a
non-duplicate Round 3, a bounded novel-query opportunity, a bounded productivity opportunity,
and a conservative reservation before the Search Agent call. These two opportunities are
preauthorization checks, not observations of an unexecuted plan. It allows at most two provider
lanes and two queries per provider/direction lane, with at most four queries per enabled
direction. Its reservation includes two Gap attempts, one Search Agent attempt, worst-case Scout
attempts, provider search/acquisition capacity, and protected downstream physical-call, token,
and cost capacity. It uses distinct post-Phase-13 artifact keys and policy/fingerprint identities;
it does not reinterpret Phase-13 artifacts.

Only after deterministic plan validation may the accepted novel-query IDs and actual execution
productivity be recorded in the typed post-plan facts artifact. Empty, repeated, invalid, or
fully rejected plans produce no post-plan facts.

After Round 4, no model may run Gap Analysis or authorize further research. Deterministic
reconciliation starts from the original post-Round-3 gaps and marks one covered only when an
enabled-direction Round-4 source has matching targeted-gap provenance, Analyzer Admission, and
an explicit Analyst `addressed_gap_ids` declaration. All other gaps remain not attempted,
unavailable, or unresolved in the final disclosure.
