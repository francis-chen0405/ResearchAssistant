# ResearchAssistant

ResearchAssistant is a phase-gated research system that investigates a claim with independently
controlled supporting and challenging directions and produces an evidence-constrained result.
Fresh website and CLI runs use the completed ResearchAssistant v2 production pipeline. It separates
retrieval, semantic review, Ledger admission, synthesis, and deterministic release validation so
that a released factual sentence must exactly match a separately reviewed statement in the Claim
Ledger.

The v2 research pipeline is complete through Phase 12 Production Hardening and Cutover.
The historical MVP-11/MLP product pipeline remains readable for persisted runs but is no
longer the fresh-run execution route.
It includes strict Pydantic contracts, SQLite audit
persistence, deterministic source and quotation checks, vendor-neutral provider protocols,
synchronous provider-backed orchestration, live CLI and local live website, a separate offline
fixture CLI/UI, and a deterministic adversarial evaluation framework. MVP-3B released a positive
live canary and failed a bounded negative canary safely. MVP-4 released the CLI; MVP-5 exposes the
same validated direct-MiMo pipeline through a responsive persisted web surface. MVP-6 stabilized
live research and hardened integrity/web-interface boundaries; MVP-6.1 fixed the live-worker test.
MVP-6.2 Batch A corrected current-stack records, MVP-6.3 validates every redirect
destination before local acquisition and treats Firecrawl provenance URLs as untrusted,
and MVP-6.4 introduced a shared 50-statistical/75-non-statistical exact-quote policy.
The user-authorized 2026-08-17 MLP-4 correction supersedes that current-run policy with
20/30-word thresholds, a 5/100 discovery floor, and keyword matching as audit metadata;
frozen historical fixtures retain their labeled policy. MVP-6.5 enforces submitted
claims as immutable in SQLite and makes
live history and inspection read-only at the connection boundary. MVP-6.6 gives RUNNING
its own exit code, distinguishes exact usage from incomplete known subtotals, enforces
unknown usage conservatively, and validates frozen provider contracts end to end.
MVP-6.7 enforces explicit return and named-parameter annotations on every repository-
owned Python function except conventional `self`/`cls` receivers, across production and
test code including nested functions. MVP-6.8 makes snapshot and Ledger rows immutable
through SQLite triggers and uses exact `Decimal`/canonical-text USD accounting end to end.
MVP-6.9 carries verified origin media type and final-URL context across scraper fallback,
keeps provider-declared media type separate, persists that provenance in schema migration 7,
and aligns fingerprints, offline configuration, and phase-neutral package metadata.
MVP-7.1 completed direct-MiMo consolidation, MVP-8 added safe local brief exports and
persisted progress, MVP-8.1 added fingerprinted internal research controls, and MVP-8.2 added a
read-only Evidence Browser. MVP-9 makes MiMo return only ordered exact snapshot passages;
ResearchAssistant constructs quote context, brackets, offsets, and provenance
deterministically. MVP-10 adds an append-only Evidence Portfolio and Evidence Trail with
deterministic source-family coverage. MVP-11 replaces MVP-10's one targeted expansion
with the deterministic Research Governor: an incomplete initial portfolio completes
Round 2, and only application-owned post-Round-2 policy may authorize Round 3. Research
rounds are absolutely limited to 1–3, all budgets remain cumulative, and SQLite schema
version 9 retains historical MVP-9 and MVP-10 inspection compatibility.

MLP-1 removes depth, tone, length, and focus choices from the live website. Website
runs use the existing safe defaults internally, while historical runs and CLI contracts
retain their typed control metadata for compatibility.

MLP-2 gave that simplified flow a clean local-product layout. The current provider setup
saves MiMo, Exa, OpenAlex, and optional Firecrawl keys to macOS Keychain; Advanced mode
contains research controls plus the technical run and local-service settings.

MLP-3 replaces the live Streamlit product with the clean-slate **Quiet Momentum**
Next.js experience. A strict loopback-only FastAPI adapter delegates to the existing
Python controller, so SQLite remains authoritative and the completed evidence, budget,
cancellation, fingerprint, and deterministic-release contracts are unchanged. Streamlit
remains only for the separate fixture replay and evidence-inspection utilities.

MLP-4 makes focused research the default, adds optional counterevidence, and gives the
Claim Planner separate Exa web queries and OpenAlex academic queries. Discovery metadata
is ranked before acquisition; scores below 5 are retained in the audit trail but are not
fetched. The top 5, 10, 15, or 20 sources are acquired, with five bounded fallbacks,
then deterministically reordered from
their actual text before extraction without deleting a source at this second stage. The
current quote floor is 20 statistical / 30 non-statistical exact words, and a zero
claim-keyword match remains audit metadata for semantic Analyst review. Exact snapshot,
Reviewer, Ledger, and final-release gates remain strict.

## How the system works

Fresh v2 production runs follow this path:

```text
exact claim + support/challenge controls
  -> broad Round 1 planning and provider search
  -> normalization, conservative clustering, batched Scout
  -> Wigolo acquisition with optional verified Firecrawl fallback
  -> immutable snapshots and deterministic Probe
  -> Luna Gap Analysis
  -> optional gap-directed Round 2
  -> optional Governor-authorized Round 3 (never Round 4)
  -> complete survivor pool and MiMo source recommendations
  -> budget-derived deep-analysis queue
  -> MiMo Pro exact passage selection and application quote assembly
  -> Luna Evidence Analyst
  -> MiMo Pro Reviewer and immutable Claim Ledger admission
  -> MiMo Pro Ledger-constrained synthesis
  -> canonical Phase 11 result envelope
  -> deterministic release validation and complete rendered-output hash
```

One persisted provider boundary counts every physical model attempt and retry across all
three model routes. Fresh runs cannot exceed 160 calls or 300,000 tokens and may configure
lower ceilings. Optional continuation protects downstream work; deep-analysis capacity is
derived from the actual remaining calls, tokens, and exact cost. Survivors excluded from
deep analysis remain visible with an explicit budget or failure status, while recommended
sources are a prioritized subset rather than a replacement for the complete pool.

Model routing is fixed: MiMo-v2.5 handles Scout; MiMo-v2.5-Pro handles initial planning,
adaptive search planning, source selection, exact extraction, Reviewer, and synthesis;
GPT-5.6 Luna High handles Gap Analysis and semantic Evidence Analyst work. The application,
not a model, owns direction enforcement, quote construction, score/placement derivation,
Ledger admission, research-round authorization, and release validation.

The following diagram documents the retained historical MVP/MLP pipeline used to inspect
older runs; it is not the fresh-run route after Phase 12.

```text
Raw claim
  -> Claim Planner (3 Exa queries + 1 OpenAlex query per active stance)
  -> focused Supporting Researcher, or equal Supporting and Opposing Researchers
  -> merged provider discovery ranking (discard below 5; select top 5/10/15/20)
  -> acquired-text ranking for extraction order (no second-stage deletion)
  -> trusted source snapshots and model-selected verbatim passages
  -> deterministic quote assembly and exact quotation filtering
  -> Evidence Analyst (evidence quality, claim fit, placement, statement draft)
  -> Statement Reviewer (independent approval, at most one Analyst revision)
  -> Claim Ledger (approved factual statements and provenance only)
  -> Evidence Portfolio and Trail (independent source-family coverage)
  -> Research Governor (complete Round 2; authorize Round 3 only when policy permits)
  -> Debate Synthesizer (typed structure and approved connective templates)
  -> deterministic Renderer and Validator
  -> released brief, or an explicit blocked/failed/cancelled result
```

All internal handoffs are strict Pydantic models with unknown fields forbidden. JSON is used only
at persistence, logging, fixture, evaluation, or export boundaries. Source snapshots and Ledger
records are insert-only SQLite audit artifacts.

### Main roles and provider boundaries

- **Claim Planner** defines the claim scope and ambiguity log without judging whether the
  claim is true. For each active stance it creates three typed Exa web queries and one
  OpenAlex academic query.
- **Researchers** merge Exa and OpenAlex discovery metadata, collapse exact canonical URL
  duplicates, discard scores below 5, and acquire only the configured top 5, 10, 15, or 20.
  Acquired text is scored again only to set extraction order; this second stage does not
  remove sources. Counterevidence is off by default and enables the equal opposing lane.
- **Extractor models** return only ordered exact snapshot passages. Application code
  derives brackets, immediate context, boundary markers, offsets, provenance, and the
  persisted candidate; model-authored quote envelopes are rejected by schema.
- **Evidence Analyst** rechecks snapshot and quotation integrity, scores evidence quality and claim
  fit separately, assigns placement, and drafts canonical factual statements.
- **Statement Reviewer** sees only the quote, bracket context, draft, and claim-fit score. It audits
  entailment, qualifications, neutrality, and scope before Ledger admission.
- **Claim Ledger** persists only exact Reviewer-approved statements with their evidence, scores,
  placement, IDs, and provenance.
- **Debate Synthesizer** creates a typed `SynthesisOutput` from Ledger records. It cannot paraphrase
  approved factual statements or introduce unrestricted factual prose.
- **Renderer and Validator** check exact statement text, Ledger and Reviewer IDs, stance,
  placement, entailment, section and template compatibility, and claim reuse before rendering.
- **Search, Scraper, and LLM providers** are synchronous vendor-neutral Protocols. Normal tests use
  injected offline transports. New live runs use Exa and OpenAlex Works for metadata-only discovery,
  loopback Wigolo `0.2.1` for primary acquisition, optional Firecrawl acquisition fallback, and
  direct Xiaomi `mimo-v2.5-pro` for every LLM role. Historical adapters remain covered.

Primary source acquisition never auto-follows redirects. Each initial URL and each 301,
302, 303, 307, or 308 target must independently pass the public HTTP(S), hostname,
literal-address, and injected-DNS-answer policy before a local request is sent. Wigolo
receives only the validated final URL. Firecrawl request, returned source, and recognized
canonical URLs pass the same policy before becoming provenance. Origin media type is authoritative
only when it was verified for the same final URL; Firecrawl metadata remains a separate
provider-declared claim and cannot reclassify Markdown as HTML or PDF.

Current provider-backed evidence requires at least 20 exact quoted words only when the
quoted segments contain both a digit and a recognized statistical marker (`%`, `percent`,
`rate`, `ratio`, `average`, `median`, `index`, `p-value`, `million`, `billion`, `growth`,
or `decline`). Otherwise it requires at least 30 words. Marker matching is
case-insensitive and respects word/token boundaries, so a digit alone, marker alone, or
incidental substring does not qualify. Frozen fixture replay alone retains its explicitly
labeled historical 50/100 policy. A zero claim-keyword match count is permitted as audit
metadata so synonyms and domain-specific phrasing reach semantic review. Exact
membership, offsets, context, provenance,
entailment, qualification, Reviewer approval, Ledger admission, and final validation are
unchanged.

See `ARCHITECTURE.md` for evidence rules and release invariants, and `.agent/PLANS.md` plus
`.agent/plans/` for phase history and boundaries.

## Orchestration and release behavior

`orchestrator.py` exposes fixture, injected-provider, and approved live-stack pipelines:

- `run_fixture_pipeline()` replays frozen local artifacts and is used by `cli.py` and the Streamlit
  UI. It is deterministic and makes no provider or network calls.
- `run_provider_pipeline()` executes the complete synchronous workflow with injected `SearchProvider`,
  `ScraperProvider`, and `LLMProvider` implementations. Only the two Researcher sides use a
  `ThreadPoolExecutor`, with at most two workers and no shared SQLite connection.
- `run_mvp3b_pipeline()` constructs only the approved Wigolo/direct-MiMo stack, fingerprints its
  exact provider, adapter, model, prompt, schema, normalization, evidence policy, budget, and executable
  repository identities, and is the live CLI launch surface.

Provider orchestration records deterministic operation and attempt IDs, model aliases,
prompt versions and hashes, timing, failures, escalation reasons, and typed token/cost
usage accounting. Exact totals exist only when every physical attempt reports that
component; otherwise inspection shows an unknown exact total, a known subtotal, and
conservative reserved exposure. Each model
alias may be attempted twice by default. The live CLI retries direct `mimo-v2.5-pro`
once only for approved objective failures and has no cross-provider fallback. Exact
quote-selection mismatch is non-retryable because immutable snapshot text cannot change;
semantic disagreement also never changes routes. Historical fallback aliases remain
readable for persisted artifacts.

Completed-stage checkpoints and typed stage artifacts are persisted for restart-safe reuse.
Cancellation is honored at stage boundaries. Model-call, per-side retrieval, and optional token or
cost budgets fail explicitly when exhausted. Runs finish in one of these states:

- `released`: final validation passed; the brief and SHA-256 hash are available.
- `blocked`: final validation rejected the synthesis; no brief or hash is released.
- `failed`: a provider, budget, integrity, or stage requirement could not be satisfied.
- `cancelled`: a persisted cancellation request was honored at a stage boundary.
- `running`: valid nonterminal work is in progress; no brief or release hash exists.

Partial evidence from one Researcher side may continue, but failure on both sides, no passing
candidates, or no Reviewer-approved Ledger statement fails the run.

## Repository structure

```text
agents/                 Planner, Researchers, Analyst, Reviewer, Synthesizer, Renderer
providers/              Search, scraper, and LLM Protocols and routing contracts
prompts/                Versioned structured prompts for all LLM stages
evaluations/            Phase 10 corpus, evaluator, CLI runner, and generated output location
frontend/               Typed live API/controller plus fixture and evidence utilities
web/                    Next.js live product and Motion interaction system
tests/                  Phase 0-10 tests, frontend tests, fixtures, and adversarial cases
models.py               Strict Pydantic handoff and persistence models
store.py                SQLite schema, migrations, and typed persistence operations
utils.py                Deterministic hashing and ID helpers
orchestrator.py          Fixture and provider-backed pipelines, checkpoints, retry, and budgets
cli.py                   Fixture runner plus provider-run inspection and cancellation commands
ARCHITECTURE.md          System invariants, evidence policy, and release rules
STATUS.md / HANDOFF.md   Chronological implementation and verification records
.agent/plans/            Canonical detailed phase plans
```

## Installation

Python 3.11 and 3.12 are supported. The live product requires Node.js 20.9+ and pnpm; live
Wigolo acquisition additionally requires Node.js 20+ and
pinned `wigolo@0.2.1` on loopback. Exa and OpenAlex search require API keys; Firecrawl fallback is optional.
MVP-5 can manage the local Wigolo service from the website. From the repository root, create a
virtual environment and install the declared runtime and development dependencies:

```bash
python3.11 -m venv .venv
PATH="$PWD/.venv/bin:$PATH"
python -m pip install -r requirements.txt
python -m pip install "pytest>=8.0,<9.0" "ruff>=0.8,<1.0"
cd web
pnpm install
pnpm run build
cd ..
```

If your compatible executable has another name, such as `python3.12`, use it in the first command.
This repository is a flat application layout and is run from its root; an editable package install
is not required.

The current repository environment does not expose bare `python` until `.venv/bin` is placed first
on `PATH`, so the commands below include that step.

### Environment variables

No environment variable or API key is required for the fixture pipeline, fixture-only Streamlit
utilities, offline tests, or normal Phase 10 evaluation. The live CLI reads configuration only from the
explicit process environment; it never loads `.env` automatically.

The legacy live CLI requires `MIMO_API_KEY`, `EXA_API_KEY`, and `OPENALEX_API_KEY`.
The website defaults to SERP Search, Exa, and OpenAlex enabled; it requires
`SERPSEARCH_API_KEY` only while SERP Search is selected and allows any source to be
disabled. `FIRECRAWL_API_KEY` is optional; when it is
absent, the narrow acquisition fallback is disabled and Wigolo remains the primary acquisition
path. `MIMO_BASE_URL`, `EXA_BASE_URL`, `FIRECRAWL_BASE_URL`, and `WIGOLO_BASE_URL` have approved
defaults, and `MIMO_MODEL` defaults to `mimo-v2.5-pro`. OpenAlex Works search is limited to
ten calls and nominal USD 0.01 per run. Claims must be public and non-sensitive.
Secrets are never printed, persisted, fingerprinted, or exported.

```dotenv
RUN_LLM_INTEGRATION_TESTS=
```

Export `RUN_LLM_INTEGRATION_TESTS=1` only when intentionally enabling the optional Phase 8 gate.
That test currently verifies explicit opt-in; it does not call a live provider. The separate
`scripts/mimo_live_smoke.py` path requires an enable flag, the exact execution-time approval
phrase, explicit one-call limits, token/cost caps, an absolute unused output path, and `--execute`.
Credentials alone cannot enable it. Do not run it without explicit approval for that execution.
It uses the existing `MIMO_API_KEY`. The enable flag is
`RESEARCH_ASSISTANT_LIVE_SMOKE=1`, and the exact approval gate is
`RESEARCH_ASSISTANT_LIVE_APPROVED=I_APPROVE_ONE_MIMO_LIVE_SMOKE`. The configured maximum must be
one search, acquisition, and LLM call, at most 25,000 tokens, and at most $0.05; the script remains
offline unless every gate and `--execute` are supplied.

## Running the project

Start each shell session from the repository root with:

```bash
PATH="$PWD/.venv/bin:$PATH"
```

Run the valid deterministic fixture:

```bash
python cli.py run-fixture tests/fixtures/basic_valid_run
```

Run the intentionally invalid fixture, which exits successfully with a typed `blocked` result:

```bash
python cli.py run-fixture tests/fixtures/invalid_release_run
```

Use a separate output directory when desired:

```bash
python cli.py run-fixture tests/fixtures/basic_valid_run --output-dir /tmp/researchassistant-run
```

Without `--output-dir`, fixture output is written to the fixture's ignored `.phase6_output/`
directory as SQLite, `audit.json`, and `result.json` artifacts.

Launch the local fixture browser:

```bash
streamlit run frontend/streamlit_app.py
```

The UI discovers runnable directories under `tests/fixtures/` and displays release or block status,
the final brief when available, validation errors, hashes, artifact counts, and audit metadata.

### Launch the live website on macOS

After first-time installation and the one-time website build above, double-click
`Launch ResearchAssistant.command`. The launcher starts the loopback-only Python API and
production Next.js server, then opens `127.0.0.1:3000`. Its Terminal window and local
processes must remain running while the page is open.
Use **Provider setup** in the page to enter MiMo, Exa, OpenAlex, and optional Firecrawl keys once;
the app saves them in the user's macOS login Keychain and reloads them on later launches.

Advanced mode checks exact Wigolo `0.2.1` identity and can start its pinned acquisition service.
It never treats a listener or child PID as proof of health and stops only its own process group.
The Next.js page accepts an exact claim, explicit token/USD budgets, optional run ID, and SQLite path.
Advanced includes counterevidence (off by default) and a 5/10/15/20 source target
(default 10), with five bounded fallbacks per target.
Changing research mode does not rewrite any configured usage ceiling. Depth, tone, and
report-length settings remain intentionally hidden. It
shows persisted stage/checkpoint/usage/cost and stance progress, deterministic terminal states,
run history, cooperative cancellation, released brief/hash copy/download controls, and a
hidden post-run research trail with both ranking stages.

Provider keys enter only transient password widgets on the loopback page, then move to
macOS Keychain and the local server process. They are never placed in URLs, SQLite,
logs, downloads, command arguments, or repository files. The app does not load `.env`
or shell profiles. Errors and bounded child output are redacted. Claims must be public
and non-sensitive, and every released brief requires human review.

The website's USD ceiling and estimated-cost card apply to MiMo model calls. When MiMo
returns cached-token detail, the estimate uses the published cache-hit/cache-miss split;
otherwise it conservatively treats input as uncached. Exa, OpenAlex, and Firecrawl usage
remains separate from MiMo spend. OpenAlex additionally enforces its one-cent per-run cap.

Run or resume the approved live stack with an exact claim, explicit SQLite path, and explicit token
and cost ceilings:

```bash
export MIMO_API_KEY="..."
export EXA_API_KEY="..."
export OPENALEX_API_KEY="..."
# Optional: export FIRECRAWL_API_KEY="..."
python cli.py run \
  "For adults with hypertension, regular aerobic exercise lowers resting systolic blood pressure." \
  --db-path /absolute/path/research-run.sqlite3 \
  --max-tokens 200000 \
  --max-cost-usd 0.15
```

Use `--run-id UUID` to choose a stable ID; otherwise the CLI creates one. `--max-llm-calls` defaults
to the approved ceiling of 160. At launch the CLI prints the database, run ID, exact claim,
approved stack, endpoints, model alias/pinned ID, repository identity, and budgets, but never the
credential.

Inspect or cooperatively cancel a known run from another process:

```bash
python cli.py inspect-run PATH_TO_DATABASE RUN_UUID
python cli.py cancel-run PATH_TO_DATABASE RUN_UUID --reason "requested by operator"
```

`inspect-run` never creates or migrates a database. It opens the existing file read-only,
checks its migration records and required schema objects, and reconstructs typed
artifacts through that same session. Missing, invalid, corrupt, older, newer, or
inaccessible databases fail clearly without modification. To migrate an older database
intentionally, start or resume a run with write access using `run`; the normal writable
initialization path applies migrations 5 through 10 before provider work.

Migration 5 installs `runs_raw_claim_immutable`. Direct SQL and application writes cannot
change `runs.raw_claim` after insertion in any run status; identical-value assignment is
allowed. Migration 4 remains the same-run provenance-protection migration.

Migration 6 installs unconditional update/delete rejection triggers for `snapshots` and
`ledger_records`. It also adds canonical-text reservation and usage cost columns. New
authoritative USD values are finite non-negative decimals and never use SQLite `REAL`;
legacy `REAL` columns remain compatibility-only. Historical float rows migrate
deterministically, but decimal digits already lost before persistence cannot be recovered.

Migration 7 adds nullable snapshot columns for original and canonical URLs, normalization and
acquisition identities, provider identity, and canonical media-type provenance JSON. Historical
rows remain unchanged and reconstruct with explicit unknown provenance; new rows preserve verified
origin media type separately from provider-declared metadata.

Migration 8 adds append-only source-family membership, Evidence Trail, approved portfolio, and
coverage-assessment records. Migration 9 adds append-only research-round, Research Governor
decision, and terminal-result records; SQLite rejects round values outside 1–3. Read-only
inspection keeps historical MVP-9 and MVP-10 databases reconstructable without applying either
migration. Migration 10 adds typed provider and intent columns to persisted search queries;
historical rows reconstruct as the legacy Exa broad-web lane.

Cancellation is cooperative: a synchronous request already in flight may continue to its deadline,
but its attempt is persisted and no new call starts after cancellation is observed. It does not
promise immediate interruption.

Stable `run` exit codes are:

| Result | Code |
|---|---:|
| released | 0 |
| blocked | 10 |
| failed | 11 |
| cancelled | 12 |
| running (valid, nonterminal) | 13 |
| configuration error | 20 |
| invalid input | 21 |

Exit code 0 never represents a nonterminal research result. `cancel-run` is a separate
administrative command and returns 0 after its cancellation request is successfully
persisted; that acceptance does not claim the research run has released a brief.

Budget enforcement is fail-closed across retry and fallback. Exact recorded usage counts
when available; otherwise the complete stored token/cost reservation remains exposed.
An attempt with missing usage and no defensible reservation blocks another physical call
because the remaining budget cannot be proven. Failed and timed-out requests are not
assumed free. Exa Search and Firecrawl charges remain external and are not combined with
MiMo model-call accounting.

Restart requires the same run ID, byte-exact claim, and compatible fingerprint. Any provider,
adapter, model, prompt, schema, normalization, policy, budget, or executable repository identity
change requires a new run ID. Budget changes are never applied in place, and consumed usage is
never reset. Released, blocked, and cancelled runs are reconstructed without new calls; failed runs
may resume only under the same contract and reuse valid checkpoints. Arbitrary cross-version crash
recovery is not promised.

The provider-run contract is a frozen strict Pydantic artifact. Its stored JSON must have
the exact historical identity shape, contain no duplicate keys, use canonical sorted
compact bytes, match every duplicated identity column, and hash to its stored SHA-256.
Construction, inspection, and resumption reject inconsistent records without normalizing
or repairing them. The payload input set and fingerprint-version label are unchanged in
MVP-6.6, so valid historical canonical records remain readable; executable code changes
still produce the ordinary new repository identity.

## Tests and code quality

Run the full test suite, lint checks, and formatting check:

```bash
PATH="$PWD/.venv/bin:$PATH"
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Apply Ruff formatting when intentionally changing Python files with:

```bash
python -m ruff format .
```

Normal tests are deterministic and offline. Two opt-in tests are expected to skip: the Phase 8
live-LLM gate unless `RUN_LLM_INTEGRATION_TESTS=1` is explicitly enabled, and the MVP-4 live CLI
smoke test unless both of its explicit enable and execution-approval gates are supplied. The
standard-library AST enforcement test is `tests/test_type_contracts.py`. The current
MVP-11 verification result is recorded in `STATUS.md`; exact focused,
evaluation, lint, format, compilation, launcher, and diff results are recorded in
`STATUS.md` and `HANDOFF.md`.

## Phase 10 evaluations

Run the deterministic offline corpus from the repository root:

```bash
PATH="$PWD/.venv/bin:$PATH"
python evaluations/run_evaluations.py
```

The runner evaluates 38 frozen cases and writes:

- `evaluations/output/results.json`: strict machine-readable report.
- `evaluations/output/summary.md`: human-readable summary derived from the same report.

The corpus measures snapshot, citation, and bracket integrity; unsupported-claim and validator
escape rates; mutation and prompt-injection resistance; placement and score behavior; Analyst and
Reviewer rejection; retrieval parity; route retry/fallback behavior; fallback gate safety;
per-alias failures; frozen model-quality comparisons; correlated Analyst/Reviewer errors; completion
time; and token/cost arithmetic when metadata is available. Regression fixture expectations are
stored separately from corpus expectations so expected outcomes cannot silently follow a weakened
gate.

Use `--corpus`, `--json-output`, and `--summary-output` to override paths. `--enable-live` is only an
API integration hook: from the standalone CLI it fails unless an embedding application injects a
`LiveEvaluationProvider`. Offline quality scores and pricing are frozen test inputs, not claims
about current vendor behavior or pricing.

See `evaluations/README.md` for metric and exit-code details.

## Project status

Phases 0 through 10, MVP-1 through MVP-6, and MVP-6.1 are complete committed work. MVP-6.2 Batch A
completed its documentation/current-stack correction, MVP-6.3 completed public-acquisition
redirect safety and Firecrawl provenance validation, and MVP-6.4 completed the 50/75 evidence-
density calibration. MVP-6.5 completed database-enforced claim immutability and read-only
history/inspection. MVP-6.6 completed CLI-status, usage-accounting/budget, and
provider-contract integrity. MVP-6.7 completed repository-wide signature enforcement
for production and test code, including nested functions. MVP-6.8 completed SQLite-
enforced snapshot/Ledger immutability and exact monetary accounting. The contradiction-audit
remediation sequence is complete. MVP-6.9 completed verified acquisition/media-type provenance,
schema migration 7, configuration reconciliation, and phase-neutral package metadata. MVP-10
completed the append-only Evidence Portfolio and Trail in migration 8. MVP-11 completed the
deterministic, cumulative-budget Research Governor in migration 9: Round 2 completes when
needed, Round 3 requires a typed post-Round-2 authorization, and a fourth round is impossible.
No later phase has started or been authorized.

Known limitations are:

- Pinned Wigolo startup can require a first-use Node package download. New live runs use Exa plus
  OpenAlex for discovery, Wigolo for primary acquisition, and optional Firecrawl fallback. Native SearXNG is
  retained only for historical adapters and old persisted-run compatibility.
- The website is local-only. It has no authentication, accounts, uploads, hosting, cloud service,
  or arbitrary cross-version crash recovery.
- Direct-MiMo cost is a pricing-policy estimate, not provider-confirmed billing. It accounts
  for cached input when the response reports that partition and remains conservative otherwise.
- Offline model-quality labels and prices are frozen evaluation data, not live benchmarks.
- Missing token or cost usage is never presented as zero or as an exact total. Known
  subtotals remain visible, and configured reservations provide conservative budget
  exposure without fabricating historical usage.
- Snapshot sentence boundaries and text normalization are intentionally deterministic and simple,
  not full NLP or raw-HTML parsing.
- Public-host validation occurs immediately before each source hop, but the HTTP transport performs
  its own DNS lookup and Wigolo independently fetches the validated final URL. Addresses are not
  socket-pinned, so complete DNS-rebinding prevention is not claimed.
- Final validation is deliberately syntactic and provenance-based. Semantic quality depends on the
  Analyst and Reviewer stages, and high-stakes outputs still require human review.
- MVP-9 removes model-authored quote formatting, but a selection still fails when the
  source lacks enough exact, relevant evidence or when downstream review rejects it.
- Research expansion is intentionally bounded: duplicate-heavy, unproductive, complete,
  unreservable, cancelled, failed, and round-limit outcomes finalize rather than opening
  another research round.

Every released brief still requires human review before high-stakes or external use. Scheduled
live validation and any phase after MVP-11 remain out of scope until explicitly approved.

Read `AGENTS.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `STATUS.md`, `HANDOFF.md`, and the relevant
canonical phase plan before making implementation changes.
