# Architecture

ResearchAssistant is a local desktop application for research on a precise claim. The Electron shell serves a static Next.js renderer and starts a bundled Python backend on loopback. Research execution, provider credentials, SQLite access, and acquisition stay in the backend. The renderer has no direct filesystem, database, process, or provider access. There is no hosted application backend.

## Runtime and module ownership

| Area | Owner |
| --- | --- |
| Fresh research orchestration | `researchassistant.research.v2_orchestrator`, `agents/v2_*.py` |
| Model catalogs and provider routing | `providers/model_profiles.py`, `providers/v2_routing.py`, `providers/v2_budget.py` |
| Historical provider execution | `researchassistant.research.orchestrator` |
| Source snapshots, quotations, and trust boundary | `researchassistant.evidence.evidence_core` |
| Analyst scoring, drafting, and admission | `researchassistant.evidence.evidence_analysis` |
| Shared research, evidence, and run contracts | `researchassistant.contracts.model_contracts`, `model_research`, and `model_evidence`, exported by `researchassistant.contracts.models` |
| Typed persistence and read-only inspection | `researchassistant.storage.store`; schema and migration ownership is `researchassistant.storage.store_schema` |
| Desktop request lifecycle and views | `frontend/live_service.py`, `frontend/live_contracts.py`, `frontend/live_progress.py`, `frontend/live_history.py` |
| Local API and renderer | `frontend/api.py`, `web/` |
| Desktop shell and backend lifecycle | `desktop/main.cjs`, `desktop/backend.py`, `frontend/service_manager.py` |
| Native paths, settings, credentials, and locks | `researchassistant.platform_support.desktop_paths`, `desktop_settings`, `credential_store`, `file_lock`, and platform process helpers |

Backend modules are organized under `researchassistant/`: `contracts/` holds shared contracts, `research/` owns pipeline execution, `evidence/` owns source and result handling, `storage/` owns persistence, `platform_support/` owns host integration, `runtime/` owns application and CLI entry logic, and `common/` holds shared helpers. Provider adapters, research agents, `frontend/`, and `desktop/` remain separate top-level packages.

The root `models.py`, `store.py`, and `orchestrator.py` entries preserve historical import paths by aliasing their canonical package modules. Root `cli.py` preserves the script launcher; new imports use `researchassistant.runtime.cli`. Historical researcher and analyst paths remain compatibility facades where neutral evidence helpers now live; `agents.supportingresearcher` retains historical retrieval. Ordinary CLI and API construction select v2. Historical execution requires the explicit typed `legacy_runner` dependency; the controller's older `runner` name remains a compatibility alias.

The model contract modules depend in one direction: shared contracts, then research contracts, then evidence/result contracts. Fresh v2 stages use the neutral evidence modules directly. Model-facing output schemas remain narrow; application identity and provenance travel in typed envelopes.

## Research execution

The approved [ALPR equity repair](.agent/plans/alpr-equity-run-fixes-2026-10-02.md) versions fresh Probe usability and post-analysis terminal status. Unusable captures do not enter source selection. The final evidence/coverage outcome is computed after admission and included in new releases; an earlier source-pool search decision does not establish evidence sufficiency. Historical Probe-v1 and assessment-v1 artifacts retain their parsing, rendering and hash behavior. Reassessment does not automatically extend search or budgets. Display-only archive lineage and PDF-title fallbacks preserve source identity and captured metadata.

The approved [private-surveillance repair](.agent/plans/private-surveillance-run-fixes-2026-10-02.md) versions fresh Analyst/admission behavior so evidence relationship is independent of search direction, while enabled-lane provenance remains mandatory. A deterministic post-analysis assessment supplements the pre-analysis search decision; it does not prove the claim or automatically extend research budgets. Historical policies and artifacts retain their original meanings.

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
- The approved discrimination-run repair versions new Analyst/admission policy to exclude unrelated material from claim evidence. Historical unrelated records retain their original policy and remain readable. Exact extraction renders one complete numbered snapshot under the untrusted-source boundary; quotation assembly still uses the original immutable text. Per-source cap blocks are distinct from run-wide budget exhaustion and allow analysis of remaining sources.
- Round 4 requires completed non-degraded Round 3 and typed Governor authorization. It is bounded to two provider lanes and two queries per lane per enabled direction; there is no Round 5.
- A database-scoped `.mvp5.lock` covers the fresh run. Cancellation is cooperative at existing stage/provider boundaries; an in-flight provider request may reach its deadline and remains conservatively accounted.

Writable databases use schema 16 under the [database-review plan](.agent/plans/database-review-2026-10-03.md). Migration 15 adds nullable cache-write tokens and usage cost basis to route attempts; migration 16 protects same-run ownership and referenced keys during updates. Read-only inspection retains compatible schema 7–16 support. Writable run/resume owns the established migration behavior. History, status inspection, and export use validated read-only sessions and never create or migrate a database. Each v2 status request uses one request-scoped validated connection; it does not cache connections or validation results. Subsequent requests observe committed changes.

The [database-review lifecycle phase](.agent/plans/database-review-2026-10-03.md) adds verified private SQLite recovery copies before writable upgrades, bounded retention after success, and explicit CLI restore into new paths. Current-schema initialization performs validation without schema writes or backups. Fresh-v2, retained legacy execution and imports share the database sidecar lock; retained synchronous ownership prevents nested acquisition. Cancellation only persists a request and leaves the worker's lock held through its write path. Shared non-mutating preflight derives required objects from executable migration boundaries and validates physical, foreign-key and same-run integrity before source writes. Current schemas are never repaired implicitly; recognized historical upgrades retain verified backups under the same lock. Source-derived tests cover writable versions 1–16; public read-only inspection still rejects 1–6. Imported copies and default storage folders use POSIX owner-only permissions or protected Windows owner/SYSTEM ACLs, whose native verification remains a Windows release gate.

Desktop credentials use macOS Keychain or Windows Credential Manager. Secrets stay out of logs, SQLite, exports, browser storage, and child-process arguments. OpenAlex and optional PubMed API keys are sent to their respective upstream services in HTTPS query strings. Automatic `.env` and shell-profile loading are not permitted. The application uses owned process groups/jobs for cleanup.

Detailed current rules for quotations, evidence admission, retry/accounting limits, Round 4 authorization, persistence compatibility, and resume identity are in [Research invariants](docs/research-invariants.md).

Physical-call completion artifacts separately preserve cache-write tokens and cost basis and remain the authority for v2 budgets. Route-attempt projection now preserves those fields through reservation, completion and replay without rewriting immutable artifacts or completed charges. Reservation and completion bind immutable attempt identity under SQLite write transactions; unknown or still-running usage keeps conservative exposure. Absent historical write counts or pricing bases remain unknown. Saved briefs and release hashes are not regenerated.

## Current release boundary

macOS is the first release target. Windows release work is deferred; the earlier Phase 2 native Windows matrix does not verify the current version. The unsigned Mac candidate has not passed live-quality acceptance, clean-machine installation, minimum-OS verification, signing, or notarization. The five-submission live-test allowance is exhausted and requires new explicit authorization before more paid research. See [STATUS](STATUS.md), [HANDOFF](HANDOFF.md), and [desktop operations](desktop/README.md).

The exact preceding architecture, including the full module inventory and historical invariants, is preserved in the [2026-09-26 archive](docs/archive/2026-09-26-maintenance/ARCHITECTURE.md). The [archive index](docs/archive/INDEX.md) lists all replaced documents. This replacement starts with the application architecture and separates current implementation facts from release evidence.
