# MLP-4 — Research Quality & OpenAlex Integration

Status: Complete and verified on 2026-08-15; corrective quality passes verified on
2026-08-15 and 2026-08-17, including expanded retrieval yield.

## Authority and intent

MLP-4 improves discovery quality, source prioritization, research-mode control,
progress accuracy, and research transparency before the separately deferred MLP-5
visual redesign. The current Next.js visual language remains in place except for the
minimal controls and disclosures required by this phase.

The user explicitly authorized these product decisions:

- Exa and OpenAlex are complementary default discovery providers.
- The Claim Planner produces separate provider-appropriate query plans rather than
  sending one shared query string to both providers.
- Counterevidence is optional and disabled by default.
- Disabling counterevidence does not reduce or otherwise rewrite any run-level model
  call, token, USD, deadline, or provider-usage ceiling. It only avoids opposing-side
  work, so actual usage may be lower.
- Deterministic source selection uses the highest-ranked sources only. There is no
  diversity slot and no wildcard slot.
- The default source target is ten per active stance per research round. Advanced mode
  may select five, ten, fifteen, or twenty. The historical seven-source control remains
  readable but is not offered for new live runs.
- Discovery results scoring below 5/100 leave the active acquisition pool. Their
  discard decision remains append-only audit history rather than being erased.
- Current provider-backed quotes require 20 exact words when statistically classified
  and 30 otherwise. A zero claim-keyword match count is retained as audit metadata and
  proceeds to semantic Analyst review.
- Deterministic exact quotation, snapshot, offset, context, boundary, Reviewer, Ledger,
  and final-release validation remain in force.

## Architecture changes

### Research mode

Add a frozen strict `ResearchMode` with `focused` and `balanced` values to the existing
frozen `ResearchControls`. `focused` is the default and corresponds to the website
toggle being off. `balanced` runs equal supporting and opposing work. Mode and source
target are part of canonical controls JSON, the provider policy identity, and the exact
run fingerprint. Historical controls without these fields reconstruct under their
recorded legacy default rather than being reinterpreted.

### Provider-specific planning

The Planner returns one strict typed provider plan containing separate query
collections:

- Exa: three web-oriented queries for each active stance, with typed intent such as
  broad web, institutional, current/news, or limitations.
- OpenAlex: one academic query for each active stance per research round, written for
  scholarly title/abstract/full-text search rather than web search syntax.

Balanced mode requires both supporting and opposing provider plans. Focused mode
requires supporting plans only and forbids fabricated empty opposing plans. OpenAlex
normal search runs first. One semantic search fallback may use the same typed academic
intent only when the normal result set is objectively weak or terminology-mismatched.

### OpenAlex boundary

Implement a synchronous strict OpenAlex adapter with the already approved `httpx`
dependency. It reads `OPENALEX_API_KEY` only from the explicit environment/Keychain
boundary and never returns, logs, persists, fingerprints, or exports the key. OpenAlex's
official API requires `api_key` in the upstream HTTPS query, so that one provider call is
a documented transport exception to the general no-secret-in-URL rule. The key remains
forbidden from browser/application URLs and all surfaced request or error metadata.

- Search Works only; do not call the paid OpenAlex content/PDF endpoint.
- Parse strict title, work ID, DOI, publication year, work type, citation count,
  retraction status, relevance, primary/best-OA locations, and access metadata.
- Reject retracted works. Do not require open access, a citation minimum, recency, or a
  PDF.
- Prefer a safe public work, DOI, publisher, repository, or PDF landing URL for normal
  ResearchAssistant acquisition.
- Reserve before each OpenAlex search and enforce an exact per-run maximum of ten
  search calls and nominal USD 0.01. The daily free allowance is display context, not
  permission to exceed the run ceiling.
- Missing configuration blocks a new run. A configured transient OpenAlex failure
  allows Exa to continue in a typed, visible degraded mode.

### Composite discovery and ranking

For each active stance and research round, execute the provider-specific query plan,
merge normalized result metadata, collapse exact canonical URL duplicates, and retain
provider provenance. Provider snippets and metadata remain discovery-only and can
never become trusted evidence.

Stage A ranks the merged discovery pool before acquisition on a 100-point scale:

- claim/query relevance: 35
- provider-query intent match: 20
- document directness/specificity: 15
- metadata completeness: 10
- likely accessibility: 10
- source novelty relative to already selected exact source families: 10

Deterministic penalties:

- generic homepage: minus 15
- marketing or community page for an empirical query: minus 20
- clearly unrelated title: minus 10

There is no near-duplicate penalty. Exact canonical duplicates are collapsed rather
than scored twice. Results below 5 are recorded as discarded and never fetched.

The remaining results are ordered by score with stable provider/rank/URL tie-breakers.
The worker keeps a bounded ranked fallback pool: targets of five, ten, fifteen, and
twenty may attempt at most ten, fifteen, twenty, and twenty-five sources respectively.
Extraction proceeds in ranked
order and stops once the configured target passes deterministic quote validation, so a
retrieval or exact-selection failure can backfill from the next source without unbounded
retry work. No diversity or wildcard reservation overrides rank.

Stage B runs after ResearchAssistant has independently acquired and normalized a page.
It deterministically evaluates readability, actual claim-term coverage, document
specificity, and generic/promotional-page evidence, then orders the usable snapshots
for model extraction. It does not modify immutable snapshots and does not bypass the
existing post-extraction filter.

### Mode-aware pipeline and release

- Focused mode does not start an opposing worker, does not fabricate opposing outputs,
  and does not let the Research Governor treat the intentionally absent stance as a
  coverage failure.
- Balanced mode preserves equal per-side configuration and standards.
- The final brief explicitly says when counterevidence was not requested. It never
  claims balance in focused mode.
- History, resume compatibility, inspection, exports, and the research trail retain
  the selected mode and source target.
- All existing token, USD, call, deadline, and provider ceilings remain numerically
  unchanged when mode changes. Budgets are ceilings, not work targets.

### Progress and research trail

Make live progress monotonically cumulative while separately exposing the current
round. Add a typed loopback research-trail response assembled from persisted queries,
provider results, ranking decisions, retrieval attempts, snapshots, candidate quotes,
reviews, portfolio records, Governor decisions, and usage records.

The existing website gains only minimal functional controls:

- `Include counterevidence`, off by default
- Advanced `Sources per side per round`: 5, 10, 15, or 20; default 10
- required OpenAlex Keychain field and provider readiness
- hidden `View research trail` disclosure
- honest provider, cumulative-progress, and conservative-cost labels

The full Living Evidence visual redesign remains MLP-5.

## Persistence and compatibility

Use strict frozen Pydantic artifacts and additive SQLite migration 10 for append-only
provider discovery and ranking decisions if the existing trail schema cannot represent
the complete score components and provider/query provenance without ambiguity. Never
rewrite historical snapshots, Ledger records, or terminal runs. Read-only inspection
must continue to distinguish old compatible databases from databases requiring an
intentional writable migration.

Bump planner prompt/schema, discovery/ranking policy, provider adapter/factory,
Research Governor, and provider-fingerprint identities. Same-run resume requires the
exact MLP-4 contract. Historical terminal runs remain readable.

## Implementation sequence

1. Add regression tests for new controls, provider-specific Planner output, focused and
   balanced validation, source-target bounds, and fingerprint compatibility.
2. Implement secure OpenAlex configuration, Keychain/API setup, strict adapter parsing,
   nominal search accounting, and failure normalization.
3. Implement the provider-specific Planner contract and prompt, then the composite
   Exa/OpenAlex discovery coordinator.
4. Add append-only ranking artifacts/persistence and deterministic Stage A/Stage B
   ranking with the 5-point discard floor and top-N acquisition.
5. Make Researchers, orchestration, Governor, synthesis/release framing, history, and
   resume behavior mode-aware without weakening post-extraction or release gates.
6. Fix cumulative monotonic progress and expose the typed hidden research trail.
7. Add the minimal Next.js controls and provider setup fields after reading the local
   Next.js 16 documentation under `web/node_modules/next/dist/docs/`.
8. Update README, architecture, conventions, decisions, status, handoff, environment
   template, and operator guidance.

## Offline acceptance

- Separate Exa and OpenAlex queries are required and provider-appropriate.
- Focused mode is the default and creates no opposing provider or model work.
- Balanced mode preserves equal side configuration.
- Mode changes do not change any configured run-level usage ceiling.
- OpenAlex secrets never cross a disclosure boundary.
- OpenAlex never exceeds ten searches or nominal USD 0.01 per run.
- Retracted works are rejected; non-OA, low-citation, older, and non-PDF works are not
  globally rejected.
- Scores are deterministic; results below 5 cannot be acquired; top-N order is stable;
  claim facets are optional soft bonuses rather than hard keyword gates, and no diversity
  or wildcard override exists.
- Current provider-backed quotes use 20 statistical / 30 non-statistical exact words;
  zero keyword matches remain visible audit metadata for semantic Analyst review.
- Exact snapshot membership, offsets, context, boundary rules, Reviewer, Ledger, and
  final validation retain their adversarial acceptance tests.
- Focused reports explicitly disclose that counterevidence was not requested.
- Progress is cumulative and monotonic across research rounds.
- Old terminal runs remain readable and old writable databases migrate only through an
  intentional run/resume path.
- `pytest`, `ruff check .`, `ruff format --check .`, frontend lint, frontend production
  build, launcher syntax, `git diff --check`, and desktop/narrow browser QA pass.

## Controlled live acceptance

Live provider tests are separately gated after offline acceptance and require explicit
user approval for that spend. Use public non-sensitive claims, a fresh Run ID, the
ten-call OpenAlex ceiling, and no automatic paid rerun. Compare discovery yield,
accessible-source yield, candidate yield, irrelevant-acquisition rate, academic-source
yield, source-family coverage, MiMo usage, provider failures, runtime, and cost.

## Explicitly out of scope

- MLP-5 visual redesign or reuse of Haoqi/OhhMyDesign styling
- Semantic Scholar or any provider beyond Exa, OpenAlex, Wigolo, Firecrawl, and MiMo
- OpenAlex paid content/PDF retrieval
- WebGL, custom cursor, sound, particles, elaborate scroll choreography, or hosting
- Accounts, public network binding, cloud persistence, telemetry, or analytics
- Further weakening snapshot integrity, exact quotation assembly, Reviewer approval,
  Ledger admission, deterministic final validation, human review, or public/non-sensitive
  restrictions
- Live provider calls during normal offline implementation and verification
