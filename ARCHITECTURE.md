# Architecture

Current product: the Phase 1 local desktop application with the completed v2
Phase 14 research pipeline. [Phase 2 cleanup](.agent/plans/phase-2-cleanup.md) is complete.
Phase 3 frontend and supported settings work is authorized and in progress. [Desktop operations](desktop/README.md)
cover installers, data, credentials, service ownership and release verification.

## Module boundaries

| Responsibility | Owner |
| --- | --- |
| Fresh research execution | `v2_orchestrator.py`, existing `agents/v2_*.py` stages |
| Historical provider execution and inspection | `orchestrator.py` |
| Frozen offline fixture replay and audit files | `fixture_pipeline.py` |
| Shared deterministic compare-before-insert helpers | `pipeline_artifacts.py` |
| Stable domain imports | `models.py`, explicit exports of the modules below |
| Shared evidence, historical contracts and run lifecycle | `model_contracts.py` |
| V2 discovery, planning, gaps, continuation and queue contracts | `model_research.py` |
| V2 analysis, admission and final-result contracts | `model_evidence.py` |
| Typed persistence and validated read-only sessions | `store.py` |
| Schema definitions, migrations and schema integrity checks | `store_schema.py` |
| Configuration preflight, worker ownership, cancellation and snapshots | `frontend/live_service.py` |
| Typed local application requests and view contracts | `frontend/live_contracts.py` |
| Persisted progress and conservative usage projections | `frontend/live_progress.py` |
| Read-only history and research-trail projections | `frontend/live_history.py` |
| Shared executable identity and stable exit codes | `application_runtime.py` |
| Local API and browser presentation | `frontend/api.py`, `web/` |
| Desktop lifecycle | `desktop/main.cjs`, `desktop/backend.py`, `frontend/service_manager.py` |
| Platform storage, vault and exclusion | `desktop_paths.py`, `desktop_settings.py`, `credential_store.py`, `file_lock.py`, `process_tree.py` |

Dependencies between model implementation modules are one-way: shared contracts →
research contracts → evidence/result contracts. The latter also uses shared contracts.
They do not import the compatibility facade. Existing `models`, `store`,
`orchestrator` and controller entry points remain available. `store.init_db()` supplies
its connection factory to schema initialization; schema code has no artifact readers.
The live controller delegates history/progress work and retains locks and workers.
The CLI delegates identity to the shared application boundary; neither the desktop
backend nor the live service imports the CLI merely to compute identity.

## Runtime and research flow

Electron serves a static Next.js export through its bundled Python loopback API.
The renderer has no Node, SQLite, filesystem, process or provider access. A per-launch
token authenticates the shell's local requests; secrets stay in the native vault and
transient backend memory. Wigolo runs under separately bundled standalone Node to
preserve native-addon ABI compatibility. Installation replaces the application,
not user data. Windows uses an owned job; macOS uses owned process groups.

Fresh website and CLI requests use this existing synchronous v2 sequence:

```text
exact claim + enabled directions + frozen configuration
  → Initial Planner → metadata discovery/normalization/clustering → Scout
  → independent acquisition → immutable snapshot → deterministic Probe
  → bounded Luna Gap Analysis → optional adaptive Round 2 / Governor Round 3
  → optional post-Round-3 Gap Analysis and Governor-authorized Round 4
  → complete survivor pool → recommendation and budget-derived priority
  → exact extraction → Luna Analyst → deterministic Analyzer Admission
  → typed admitted-evidence projection → deterministic synthesis
  → deterministic final validation → rendered output and release hash
```

Scout uses MiMo-v2.5; Planner, Search Agent, Source Selection and exact Extractor use
MiMo-v2.5-Pro. Gap Analysis and Evidence Analyst use the configured Luna High route.
Fresh Analyst assessment and statement drafting use one call per successfully extracted
source. Fresh synthesis makes no model call and fresh runs make no Reviewer call.
Analyzer Admission checks structure/provenance/policy; it does not independently prove
entailment. Results retain the explicit not-independently-reviewer-approved disclosure.

Discovery supports the configured OpenAlex, arXiv, PubMed, Exa and SERP lanes. Crossref
is optional identity metadata only. Snippets, abstracts, recommendations and Probe
passages are never admitted factual evidence. Wigolo and optional Firecrawl keep their
existing bounded acquisition/fallback policies. No cleanup change alters those policies.

## Invariants

- Internal handoffs are strict Pydantic models. JSON belongs at persistence, HTTP,
  logging and export boundaries. Application-owned identity/provenance remains outside
  narrow model-facing schemas where required, in typed envelopes.
- Exact claim, direction/provider controls, model routes/prices, policy/prompt/schema
  identities, budgets and executable identity govern resume. A mismatch requires a new
  run. Completed compatible work is reused; historical rows are never relabeled as v2.
- Every physical model attempt reserves calls, tokens and exact decimal USD before
  transport. Failures and retries count. Unknown usage retains conservative exposure;
  missing usage is never zero or a refund. Maximum fresh ceilings remain 160 calls and
  500,000 tokens with lower configured limits supported. Provider-specific search and
  acquisition limits remain separate. No synthetic per-call subscription price is added.
- Optional continuation protects downstream work. Deep analysis retains the existing
  60,000-token source allowance and three-call envelope (two extraction attempts and
  one Analyst call), and preserves actual failed/rejected/budget-prevented states.
- The database-scoped `.mvp5.lock` covers the whole fresh run. The controller transfers
  its existing ownership explicitly. Workers never share SQLite connections/cursors or
  mutable handoffs. Cancellation is cooperative at existing stage/provider boundaries;
  an in-flight call may reach its deadline and remains conservatively accounted.
- Source snapshots, Ledger records and final artifacts are immutable. Acquisition
  normalizes supported text deterministically and preserves original/final/canonical
  URL and independently verified media provenance. Historical missing provenance is
  unknown, never invented. Public URL/redirect validation remains mandatory; transport
  DNS is not socket-pinned. Digital PDFs require usable embedded text; no OCR is added.
- Quotes are exact ordered passages in stored normalized text with rechecked hash,
  offsets, immediate context and explicit boundary/truncation markers. No fuzzy repair,
  padding, source replacement or paraphrase is allowed. The current 20 statistical /
  30 other word policy and legacy frozen-fixture 50/100 policy remain distinct.
  Statistical classification requires both a digit and a whole-token marker. Keyword
  counts remain audit metadata, including zero. Snapshots retain the 3,000-word cap.
- Evidence Quality and Claim Fit are independent 1–5 axes. Both must be at least 2;
  a derived Ledger score cannot compensate for failure. Claim Fit 2 is qualified-only;
  Claim Fit 3 is ordinary eligible. Placement, entailment and qualification are copied
  unchanged. Exact statement and provenance validation precede admission IDs.
- Rendering uses fixed application framing, approved connectives and exact admitted
  statements. Unknown IDs, direction/placement/provenance drift, altered text or invalid
  results block release and produce no release hash. Export revalidates released output.
- Round 4 requires completed non-degraded Round 3, material enabled-direction gaps and
  a typed Governor authorization with full conservative reservation. It permits at most
  two provider lanes and two queries per lane per enabled direction, four queries per
  direction. There is no Round 5 or post-Round-4 Gap call. Preauthorization opportunities
  remain distinct from actual post-plan novelty/productivity facts.
- Gap identity persists across rounds: direction, claim dimension and unsupported
  component must agree. Coverage requires the original Gap ID, targeted Round-4 query
  provenance, analyzer admission and explicit Analyst addressed-gap declaration.
- Credentials never enter app URLs, logs, SQLite, exports, browser storage or child
  arguments. OpenAlex's existing upstream HTTPS query-key exception remains narrowly
  transport-only. No automatic `.env` or shell-profile loading is permitted.

## Persistence and compatibility

SQLite remains schema 13, with the original SQL, migration order, transaction/rollback
behavior, descriptions and immutable triggers. `ReadOnlyStore` opens existing compatible
schema 7–13 databases via encoded URI `mode=ro`, enables foreign keys and `query_only`,
and validates integrity/schema. It never initializes, migrates, creates a missing file,
or falls back to writable access; `immutable=1` is not used with possible WAL writers.
Intentional writable run/resume retains the existing migration behavior.

Historical provider, Reviewer-backed, portfolio/Governor, inspection/export and frozen
fixture contracts remain executable. They are required by existing callers/tests and
persisted artifacts; none was declared unused or removed. Legacy SQLite framing and
REAL cost columns remain for compatibility. Historical REAL precision cannot be recovered.

Root Python modules and recursive `agents`, `providers`, `frontend` sources plus `prompts`
remain in the packaged identity surface. Frozen builds additionally hash executable
bytes. Phase 2 changes source layout, so restart the app and start a new run. Historical
inspection/export remains valid; exact resume checks are not relaxed. No prompt semantics,
model schema, research policy or database semantics change in this cleanup.

## Historical design record

The full pre-cleanup architecture is preserved verbatim in
[the archive](docs/archive/pre-phase-2/ARCHITECTURE.md), including dated MVP/MLP/v2
narratives and historical schemas. This document replaces their competing current-state
claims with the verified module map and invariants above. The
[archive index](docs/archive/README.md) identifies exact replacements and retained plans.

## Phase 3 presentation and settings

`web/components/workspace.tsx` owns the shared workspace frame, progress path and evidence
presentation. `web/lib/preview.ts` contains only fictional local example data. Native modal
behavior lives in `web/components/dialog.tsx`; transient credential entry lives in
`web/components/provider-setup.tsx`. `web/lib/api.ts` remains the frontend API boundary.

`providers/model_profiles.py` owns the strict supported catalog and copied-environment
resolution. `frontend/profile_preflight.py` checks the first planner reservation offline;
it does not promise a complete run fits every budget. `frontend/provider_connections.py`
performs explicit fixed-host model-list authentication checks without generation, with
presence-only disclosure for source providers lacking a configured free check. Preferences
add a backward-compatible profile default; exact provider/model/budget values remain frozen
by existing per-run contracts. No database, prompt, research-policy or dependency change.
See [model settings](docs/model-settings.md) for maintained caps and compatibility details.
