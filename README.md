# ResearchAssistant

ResearchAssistant is a phase-gated debate research system that investigates a claim from
supporting and opposing perspectives and produces an evidence-constrained brief. It separates
retrieval, semantic review, Ledger admission, synthesis, and deterministic release validation so
that a released factual sentence must exactly match a separately reviewed statement in the Claim
Ledger.

The MVP is complete through Phase 10. The repository includes strict Pydantic contracts, SQLite
audit persistence, deterministic source and quotation checks, vendor-neutral provider protocols,
synchronous provider-backed orchestration, an offline fixture CLI and Streamlit UI, and a
deterministic adversarial evaluation framework. It does **not** include live search, scraping, or
LLM vendor adapters.

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
- **Supporting and Opposing Researchers** use the same search depth and rules. They retrieve three
  results for each of three queries per side, create immutable snapshots, ask the Extractor for
  candidate quotations, and apply deterministic offset, bracket, length, and relevance checks.
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
- **Search, Scraper, and LLM providers** are synchronous vendor-neutral Protocols. Tests inject fake
  providers; the repository supplies no live adapter, SDK, HTTP client, or API-key integration.

See `ARCHITECTURE.md` for evidence rules and release invariants, and `.agent/PLANS.md` plus
`.agent/plans/` for phase history and boundaries.

## Orchestration and release behavior

`orchestrator.py` exposes two pipelines:

- `run_fixture_pipeline()` replays frozen local artifacts and is used by `cli.py` and the Streamlit
  UI. It is deterministic and makes no provider or network calls.
- `run_provider_pipeline()` executes the complete synchronous workflow with injected `SearchProvider`,
  `ScraperProvider`, and `LLMProvider` implementations. Only the two Researcher sides use a
  `ThreadPoolExecutor`, with at most two workers and no shared SQLite connection.

Provider orchestration records deterministic operation and attempt IDs, model aliases, prompt
versions and hashes, timing, failures, escalation reasons, and optional token/cost usage. Each model
alias may be attempted twice by default. Objective transient, timeout, malformed/schema,
exact-quote, interrupted, or deterministic-validation failures can retry or advance through the
configured fallback route; semantic disagreement alone cannot switch models. Extractor routing is
MiMo V2.5, then MiMo V2.5 Pro, then DeepSeek V4 Flash, and every fallback output still passes the
same snapshot, quotation, Reviewer, Ledger, and final validation gates.

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
frontend/               Minimal fixture-only Streamlit application
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

Python 3.11 or newer is required. From the repository root, create a virtual environment with an
available Python 3.11+ executable, then install the declared runtime and development dependencies:

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
offline tests, or normal Phase 10 evaluation.

`.env.example` documents one optional test gate:

```dotenv
RUN_LLM_INTEGRATION_TESTS=
```

Export `RUN_LLM_INTEGRATION_TESTS=1` only when intentionally enabling the optional Phase 8 gate.
That test currently verifies explicit opt-in; it does not call a live provider. The repository does
not define vendor API-key variables or load environment values from `.env` automatically.

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

The provider-backed pipeline currently has no CLI command because it requires concrete provider
implementations. Embedding code should import `run_provider_pipeline()` and pass objects satisfying
the `SearchProvider`, `ScraperProvider`, and `LLMProvider` Protocols plus a SQLite `db_path`. A known
run can then be inspected or cancelled from the CLI:

```bash
python cli.py inspect-run PATH_TO_DATABASE RUN_UUID
python cli.py cancel-run PATH_TO_DATABASE RUN_UUID --reason "requested by operator"
```

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

Phases 0 through 10 are complete, including Phase 7A (local fixture frontend) and Phase 7B
(provider interfaces and deterministic retrieval). Phase 9 completed provider-backed orchestration,
and Phase 10 added the offline evaluation and adversarial testing framework. The latest documented
full verification is 300 passed and 1 optional integration test skipped, with the 38-case offline
evaluation and both Ruff checks passing.

Post-MVP hardening has not started. Known limitations are:

- No live Search, Scraper, LLM, or live-evaluation adapter is included, so live research requires
  externally supplied provider implementations.
- The Streamlit UI and public fixture CLI remain fixture-only; there is no provider-run launch CLI,
  production UI, authentication, accounts, uploads, or dashboard.
- Offline model-quality labels and prices are frozen evaluation data, not live benchmarks.
- Token and cost totals are available only when an injected LLM provider supplies strict usage
  metadata; missing usage is not estimated.
- Snapshot sentence boundaries and text normalization are intentionally deterministic and simple,
  not full NLP or raw-HTML parsing.
- Final validation is deliberately syntactic and provenance-based. Semantic quality depends on the
  Analyst and Reviewer stages, and high-stakes outputs still require human review.

Read `AGENTS.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `STATUS.md`, `HANDOFF.md`, and the relevant
canonical phase plan before making implementation changes.
