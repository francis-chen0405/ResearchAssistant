# Architecture

ResearchAssistant is a local desktop application for research on a precise claim. The Electron shell serves a static Next.js renderer and starts a bundled Python backend on loopback. Research execution, provider credentials, SQLite access, and acquisition stay in the backend. The renderer has no direct filesystem, database, process, or provider access. There is no hosted application backend.

## Runtime and module ownership

| Area | Owner |
| --- | --- |
| Fresh research orchestration | `v2_orchestrator.py`, `agents/v2_*.py` |
| Model catalogs and provider routing | `providers/model_profiles.py`, `providers/v2_routing.py`, `providers/v2_budget.py` |
| Historical provider execution | `orchestrator.py` |
| Source snapshots, quotations, and trust boundary | `evidence_core.py` |
| Analyst scoring, drafting, and admission | `evidence_analysis.py` |
| Shared research, evidence, and run contracts | `model_contracts.py`, `model_research.py`, `model_evidence.py`, exported by `models.py` |
| Typed persistence and read-only inspection | `store.py`; schema and migration ownership is `store_schema.py` |
| Desktop request lifecycle and views | `frontend/live_service.py`, `frontend/live_contracts.py`, `frontend/live_progress.py`, `frontend/live_history.py` |
| Local API and renderer | `frontend/api.py`, `web/` |
| Desktop shell and backend lifecycle | `desktop/main.cjs`, `desktop/backend.py`, `frontend/service_manager.py` |
| Native paths, settings, credentials, and locks | `desktop_paths.py`, `desktop_settings.py`, `credential_store.py`, `file_lock.py`, platform process helpers |

`models.py`, `store.py`, `orchestrator.py`, and controller entry points preserve stable public imports. Historical researcher and analyst paths remain compatibility facades where neutral evidence helpers now live; `agents.supportingresearcher` retains historical retrieval. Ordinary CLI and API construction select v2. Historical execution requires the explicit typed `legacy_runner` dependency; the controller's older `runner` name remains a compatibility alias.

The model contract modules depend in one direction: shared contracts, then research contracts, then evidence/result contracts. Fresh v2 stages use the neutral evidence modules directly. Model-facing output schemas remain narrow; application identity and provenance travel in typed envelopes.

## Research execution

Fresh website and CLI requests follow this pipeline:

```text
claim and enabled directions + frozen run configuration
  → initial plan → metadata discovery, normalization, clustering, Scout
  → independent acquisition → immutable source snapshots → deterministic Probe
  → bounded gap analysis and authorized adaptive search
  → complete survivor pool → Source Selection model stage
  → deterministic recommendation and budget-derived priority
  → exact extraction → Evidence Analyst → deterministic admission
  → typed admitted-evidence projection → deterministic synthesis and validation
  → rendered result and release hash
```

The seven active model stages are Planner, Scout, Gap Analysis, Search Agent, Source Selection, exact Extractor, and Evidence Analyst. Each has an explicit selectable route from GPT-6 Luna High/XHigh, MiMo v2.6 Pro/Flash, GPT-6 Sol High, and GPT-5.6 Terra High. Scout and exact Extractor default to Luna High; the other stages default to Luna XHigh. The default model budget is $0.20 and can be selected up to $20. Route, effort/thinking mode, price cap, stage allowance, and selected model are frozen into run identity. Historical Standard runs retain their prior routes and persisted identities. See [model settings](docs/model-settings.md) for the supported catalog.

Each physical model attempt reserves calls, tokens, and conservative cost before transport. Failures and retries count. Unknown outcomes retain reserved exposure; absent usage is never treated as zero or refunded. Existing global ceilings are 160 calls and 500,000 tokens, with lower configured limits supported. Search and acquisition have separate limits. No synthetic per-call subscription price is added.

Deep analysis uses priority-ordered waves of at most four source workers. Each wave is limited to a budget-safe priority prefix; extraction, Analyst work, and admission stay sequential within a source. Workers do not share SQLite connections or mutable handoffs. Cancellation drains in-flight work, preserves audit exposure, and does not write aggregate completion for a cancelled run.

Discovery may use configured OpenAlex, arXiv, PubMed, Exa, and SERP lanes. Crossref is identity metadata only. Search snippets, abstracts, recommendations, and Probe passages are not admitted as factual evidence. Acquisition and fallback behavior stay bounded by their existing policies.

## Evidence and persistence invariants

- Internal stage handoffs are strict Pydantic models. JSON is used at persistence, API, logging, and export boundaries.
- Exact claim, directions, providers, model routes, prompts, schemas, policy identities, budgets, and executable identity govern resume. A mismatch requires a new run. Historical records are never relabeled as v2.
- Source snapshots, Ledger records, and final artifacts are immutable. Acquisition preserves original/final/canonical URL and independently verified media provenance; unknown historical provenance is not invented.
- Quotes must be exact ordered passages from stored normalized text with verified hashes, offsets, context, and boundary markers. No fuzzy repair, paraphrase, padding, or source substitution is allowed.
- Evidence Quality and Claim Fit are separate 1–5 axes. Both must pass admission policy. Admission checks structure, provenance, and policy; it does not independently prove entailment. Fresh synthesis and final validation are deterministic and do not call a Reviewer.
- Round 4 requires completed non-degraded Round 3 and typed Governor authorization. It is bounded to two provider lanes and two queries per lane per enabled direction; there is no Round 5.
- A database-scoped `.mvp5.lock` covers the fresh run. Cancellation is cooperative at existing stage/provider boundaries; an in-flight provider request may reach its deadline and remains conservatively accounted.

SQLite remains schema 13 for writable current databases. Read-only inspection supports compatible schema 7–13 databases. Writable run/resume owns the established migration behavior. History, status inspection, and export use validated read-only sessions and never create or migrate a database. Each v2 status request uses one request-scoped validated connection; it does not cache connections or validation results. Subsequent requests observe committed changes.

Credentials use macOS Keychain or Windows Credential Manager. Secrets stay out of logs, SQLite, exports, browser storage, and child-process arguments. The existing OpenAlex integration has one narrow exception: its API key is sent in an upstream HTTPS query string. Automatic `.env` and shell-profile loading are not permitted. The application uses owned process groups/jobs for cleanup.

Detailed current rules for quotations, evidence admission, retry/accounting limits, Round 4 authorization, persistence compatibility, and resume identity are in [Research invariants](docs/research-invariants.md).

## Current release boundary

macOS is the first release target. Windows release work is deferred; the earlier Phase 2 native Windows matrix does not verify the current version. The unsigned Mac candidate has not passed live-quality acceptance, clean-machine installation, minimum-OS verification, signing, or notarization. The five-submission live-test allowance is exhausted and requires new explicit authorization before more paid research. See [STATUS](STATUS.md), [HANDOFF](HANDOFF.md), and [desktop operations](desktop/README.md).

The exact preceding architecture, including the full module inventory and historical invariants, is preserved in the [2026-09-26 archive](docs/archive/2026-09-26-maintenance/ARCHITECTURE.md). The [archive index](docs/archive/INDEX.md) lists all replaced documents. This replacement starts with the application architecture and separates current implementation facts from release evidence.
