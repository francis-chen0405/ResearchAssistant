# ResearchAssistant

ResearchAssistant is a phase-gated debate research system that investigates a claim from
supporting and opposing perspectives and produces an evidence-constrained brief. It separates
retrieval, semantic review, Ledger admission, synthesis, and deterministic release validation so
that a released factual sentence must exactly match a separately reviewed statement in the Claim
Ledger.

The repository is complete through MVP-5. It includes strict Pydantic contracts, SQLite audit
persistence, deterministic source and quotation checks, vendor-neutral provider protocols,
synchronous provider-backed orchestration, live CLI and local live website, a separate offline
fixture CLI/UI, and a deterministic adversarial evaluation framework. MVP-3B released a positive
live canary and failed a bounded negative canary safely. MVP-4 released the CLI; MVP-5 exposes the
same validated direct-MiMo pipeline through a responsive persisted web surface.

## How the system works

```text
Raw claim
  -> Claim Planner (3 supporting queries + 3 opposing queries)
  -> Supporting and Opposing Researchers (run concurrently, equal limits)
  -> trusted source snapshots and exact quotation filtering
  -> Evidence Analyst (evidence quality, claim fit, placement, statement draft)
  -> Statement Reviewer (independent approval, at most one Analyst revision)
  -> Claim Ledger (approved factual statements and provenance only)
  -> Debate Synthesizer (typed structure and approved connective templates)
  -> deterministic Renderer and Validator
  -> released brief, or an explicit blocked/failed/cancelled result
```

All internal handoffs are strict Pydantic models with unknown fields forbidden. JSON is used only
at persistence, logging, fixture, evaluation, or export boundaries. Source snapshots and Ledger
records are insert-only SQLite audit artifacts.

### Main roles and provider boundaries

- **Claim Planner** defines the claim scope, ambiguity log, and exactly six searches without
  judging whether the claim is true.
- **Supporting and Opposing Researchers** use the same search depth and rules. Live and strict
  mocked runs rank five results and attempt them until three usable unique snapshots exist for each
  query, then apply the same deterministic quotation gates.
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
  injected offline transports. The approved live stack is loopback Wigolo `0.2.1` with native
  SearXNG for discovery/acquisition and direct Xiaomi `mimo-v2.5-pro` for every LLM role. Historical
  OpenRouter adapters remain covered but are not used by the live CLI.

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
  exact provider, adapter, model, prompt, schema, normalization, policy, budget, and executable
  repository identities, and is the live CLI launch surface.

Provider orchestration records deterministic operation and attempt IDs, model aliases, prompt
versions and hashes, timing, failures, escalation reasons, and optional token/cost usage. Each model
alias may be attempted twice by default. The live CLI retries direct `mimo-v2.5-pro` once only for
approved objective failures and has no cross-provider fallback. Semantic disagreement never changes
routes. Historical fallback aliases remain readable for persisted artifacts.

Completed-stage checkpoints and typed stage artifacts are persisted for restart-safe reuse.
Cancellation is honored at stage boundaries. Model-call, per-side retrieval, and optional token or
cost budgets fail explicitly when exhausted. Runs finish in one of these states:

- `released`: final validation passed; the brief and SHA-256 hash are available.
- `blocked`: final validation rejected the synthesis; no brief or hash is released.
- `failed`: a provider, budget, integrity, or stage requirement could not be satisfied.
- `cancelled`: a persisted cancellation request was honored at a stage boundary.

Partial evidence from one Researcher side may continue, but failure on both sides, no passing
candidates, or no Reviewer-approved Ledger statement fails the run.

## Repository structure

```text
agents/                 Planner, Researchers, Analyst, Reviewer, Synthesizer, Renderer
providers/              Search, scraper, and LLM Protocols and routing contracts
prompts/                Versioned structured prompts for all LLM stages
evaluations/            Phase 10 corpus, evaluator, CLI runner, and generated output location
frontend/               Separate fixture-only and live Streamlit applications
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

Python 3.11 and 3.12 are supported. Live Wigolo use additionally requires Node.js 20+, pinned
`wigolo@0.2.1`, and native SearXNG resources, all bound to loopback. MVP-5 can manage this local
stack from the website. From the repository root, create a virtual environment and install the
declared runtime and development dependencies:

```bash
python3.11 -m venv .venv
PATH="$PWD/.venv/bin:$PATH"
python -m pip install -r requirements.txt
python -m pip install "pytest>=8.0,<9.0" "ruff>=0.8,<1.0"
```

If your compatible executable has another name, such as `python3.12`, use it in the first command.
This repository is a flat application layout and is run from its root; an editable package install
is not required.

The current repository environment does not expose bare `python` until `.venv/bin` is placed first
on `PATH`, so the commands below include that step.

### Environment variables

No environment variable or API key is required for the fixture pipeline, Streamlit frontend,
offline tests, or normal Phase 10 evaluation. The live CLI reads configuration only from the
explicit process environment; it never loads `.env` automatically.

The live CLI requires `MIMO_API_KEY`. `MIMO_BASE_URL` and `MIMO_MODEL` default to the only approved
values, and `WIGOLO_BASE_URL` defaults to `http://127.0.0.1:8000`. Claims must be public and
non-sensitive. Secrets are never printed, persisted, fingerprinted, or exported.

```dotenv
RUN_LLM_INTEGRATION_TESTS=
```

Export `RUN_LLM_INTEGRATION_TESTS=1` only when intentionally enabling the optional Phase 8 gate.
That test currently verifies explicit opt-in; it does not call a live provider. The separate
`scripts/mvp2b_live_smoke.py` path requires an enable flag, the exact execution-time approval
phrase, explicit one-call limits, token/cost caps, an absolute unused output path, and `--execute`.
Credentials alone cannot enable it. Do not run it without explicit approval for that execution.

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

After first-time installation, double-click `Launch ResearchAssistant.command`. If the key is not
already in the launcher environment, macOS requests `MIMO_API_KEY` in a native hidden-input dialog
for that launch only. No terminal commands are required during normal use. The launcher opens the
live page at `127.0.0.1:8501`; its Terminal window/local server must remain running while the page
is open.

The sidebar checks exact Wigolo `0.2.1` identity and can start the pinned stack with native SearXNG.
It never treats a listener or child PID as proof of health and stops only its own process group.
The page accepts an exact claim, explicit token/USD budgets, optional run ID, and SQLite path. It
shows persisted stage/checkpoint/usage/cost and stance progress, deterministic terminal states,
run history, cooperative cancellation, and released brief/hash copy/download controls.

The browser never receives `MIMO_API_KEY`; it stays in the local server process. The app does not
load `.env` or shell profiles. Errors and bounded child output are redacted. Claims must be public
and non-sensitive, and every released brief requires human review.

Run or resume the approved live stack with an exact claim, explicit SQLite path, and explicit token
and cost ceilings:

```bash
export MIMO_API_KEY="..."
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
| configuration error | 20 |
| invalid input | 21 |

Restart requires the same run ID, byte-exact claim, and compatible fingerprint. Any provider,
adapter, model, prompt, schema, normalization, policy, budget, or executable repository identity
change requires a new run ID. Budget changes are never applied in place, and consumed usage is
never reset. Released, blocked, and cancelled runs are reconstructed without new calls; failed runs
may resume only under the same contract and reuse valid checkpoints. Arbitrary cross-version crash
recovery is not promised.

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

Normal tests are deterministic and offline. The only normal skip is the optional Phase 8 LLM
integration gate unless `RUN_LLM_INTEGRATION_TESTS=1` is explicitly enabled.

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

Phases 0 through 10 and MVP-1 through MVP-5 are complete. MVP-5 is the local live web release
boundary. No MVP-6 work has started.

Known limitations are:

- Wigolo/native SearXNG startup can require first-use downloads and warming. Cold or degraded
  search can still exceed the unchanged fixed fail-closed 15-second deadline.
- The website is local-only. It has no authentication, accounts, uploads, hosting, cloud service,
  or arbitrary cross-version crash recovery.
- Direct-MiMo cost is a conservative frozen-policy estimate, not provider-confirmed billing.
- Offline model-quality labels and prices are frozen evaluation data, not live benchmarks.
- Token and cost totals are available only when an injected LLM provider supplies strict usage
  metadata; missing usage is not estimated.
- Snapshot sentence boundaries and text normalization are intentionally deterministic and simple,
  not full NLP or raw-HTML parsing.
- Final validation is deliberately syntactic and provenance-based. Semantic quality depends on the
  Analyst and Reviewer stages, and high-stakes outputs still require human review.

Every released brief still requires human review before high-stakes or external use. Scheduled
live validation and MVP-6 are out of scope until explicitly approved.

Read `AGENTS.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `STATUS.md`, `HANDOFF.md`, and the relevant
canonical phase plan before making implementation changes.
