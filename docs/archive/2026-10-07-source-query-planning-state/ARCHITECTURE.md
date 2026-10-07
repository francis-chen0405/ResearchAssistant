# Architecture

ResearchAssistant is a local desktop application for research on a precise claim. The Electron shell serves a static Next.js renderer and starts a bundled Python backend on loopback. Research execution, provider credentials, SQLite access, and acquisition stay in the backend. The renderer has no direct filesystem, database, process, or provider access. There is no hosted application backend.

## Runtime and module ownership

| Area | Owner |
| --- | --- |
| Opt-in discovery foundations | `researchassistant.contracts.discovery_v2`, `researchassistant.research.discovery_policy`, `discovery_capabilities`, and `researchassistant.storage.discovery_store` |
| Fresh research orchestration | `researchassistant.research.v2_orchestrator`, `agents/v2_*.py` |
| Model catalogs and provider routing | `providers/model_profiles.py`, `providers/v2_routing.py`, `providers/v2_budget.py` |
| Historical provider execution | `researchassistant.research.orchestrator` |
| Source snapshots, quotations, and trust boundary | `researchassistant.evidence.evidence_core` |
| Analyst scoring, drafting, and admission | `researchassistant.evidence.evidence_analysis` |
| Shared research, evidence, and run contracts | `researchassistant.contracts.model_contracts`, `model_research`, and `model_evidence`, exported by `researchassistant.contracts.models` |
| Typed persistence and read-only inspection | `researchassistant.storage.store`; schema and migration ownership is `researchassistant.storage.store_schema` |
| Historical contract decoding and released-text reconstruction | `researchassistant.storage.historical_decode`, `researchassistant.contracts.historical`, `researchassistant.evidence.historical_render` |
| Local brief exports and embedded-font PDF layout | `researchassistant.evidence.brief_export`, `researchassistant.evidence.pdf_render`, `researchassistant/evidence/fonts/` |
| Desktop request lifecycle and views | `frontend/live_service.py`, `frontend/live_contracts.py`, `frontend/live_progress.py`, `frontend/live_history.py` |
| Local API and renderer | `frontend/api.py`, `web/` |
| Desktop shell and backend lifecycle | `desktop/main.cjs`, `desktop/backend.py`, `frontend/service_manager.py` |
| Native paths, settings, credentials, and locks | `researchassistant.platform_support.desktop_paths`, `desktop_settings`, `credential_store`, `file_lock`, and platform process helpers |

Backend modules are organized under `researchassistant/`: `contracts/` holds shared contracts, `research/` owns pipeline execution, `evidence/` owns source and result handling, `storage/` owns persistence, `platform_support/` owns host integration, `runtime/` owns application and CLI entry logic, and `common/` holds shared helpers. Provider adapters, research agents, `frontend/`, and `desktop/` remain separate top-level packages.

The root `models.py`, `store.py`, and `orchestrator.py` entries preserve historical import paths by aliasing their canonical package modules. Root `cli.py` preserves the script launcher; new imports use `researchassistant.runtime.cli`. Historical researcher and analyst paths remain compatibility facades where neutral evidence helpers now live; `agents.supportingresearcher` retains historical retrieval. Ordinary CLI and API construction select v2. Historical execution requires the explicit typed `legacy_runner` dependency; the controller's older `runner` name remains a compatibility alias.

The model contract modules depend in one direction: shared contracts, then research contracts, then evidence/result contracts. Fresh v2 stages use the neutral evidence modules directly. Model-facing output schemas remain narrow; application identity and provenance travel in typed envelopes.

## Discovery foundations

The [source-discovery plan](.agent/plans/source-discovery-v2-2026-10-05.md) defines separate opt-in contracts for conceptual/provider queries, metadata depth, candidate ranking, exact previews and one-hop expansion. Current production execution retains its prior discovery policy. New foundations reuse immutable `v2_artifacts`, freeze versions/settings/capabilities/source/schema identity, and reserve each physical request durably before transport. Native and executable modes/pagination/identity/relationships are distinct. PubMed's search and summary requests have separate checkpoints; unknown outcomes retain exposure and stop further requests under the initial recovery policy. New read-only inspection owns one validated snapshot. No schema migration or model stage is added.

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

Writable databases use schema 17 under the [database-review plan](.agent/plans/database-review-2026-10-03.md). Migration 15 adds nullable cache-write tokens and usage cost basis to route attempts; migration 16 protects same-run ownership and referenced keys during updates. Migration 17 adds measured history and native evidence indexes. Read-only inspection retains compatible schema 7–17 support. Writable run/resume owns the established migration behavior. History, status inspection, and export use validated read-only sessions and never create or migrate a database. Each public history/status/inspection/trail/browser/export request pins an explicit read snapshot before validation and uses one validated connection. Borrowed transactions remain caller-owned. Locally owned snapshots end before export layout; connections and live validation results are never cached. New requests open and validate the file again, including replacements at the same path. SQLite uses a one-second busy timeout, distinct retryable contention diagnostics, and no automatic operation replay. Existing WAL databases remain readable; writable initialization retains the default rollback-journal policy without switching existing modes.

All path-based point readers share a noncreating SQLite `mode=ro` boundary; full schema validation stays at public inspection boundaries. Caller-owned connections retain their row factory, pragmas, transaction and ownership. Historical decoding uses explicit recorded contracts for the verified August Ledger, legacy researcher and prior-policy v2 families. It verifies available provider, artifact and snapshot hashes, retains original values and reports unknown/unsafe records individually. Inspection-only types cannot authorize fresh admission or release; source/executable/provider-policy resume gates remain strict. Released-text reconstruction must match the original stored hash. Native pending evidence does not match approval/rejection filters; those filters match an explicit outcome at either Analyst or Reviewer stage.

V2 progress counts every persisted acquisition provider attempt across rounds 1–4, including failures and fallback calls. Cluster direction mapping determines assignment; unknown or conflicting ownership has a separate unassigned aggregate. Acquired sources and usable survivors remain distinct metrics. PDF exports materialize the verified released text and close read sessions before layout. ReportLab wraps and paginates text using bundled GNU Unifont 15.0.01 under its OFL license. Unsupported glyphs or complex shaping fail explicitly with Markdown/DOCX alternatives; export metadata retains the original released-content hash. A new desktop build must include the pinned dependency and bundled font assets.

The [database-review lifecycle phase](.agent/plans/database-review-2026-10-03.md) adds verified private SQLite recovery copies before writable upgrades, bounded retention after success, and explicit CLI restore into new paths. Current-schema initialization performs validation without schema writes or backups. Fresh-v2, retained legacy execution and imports share the database sidecar lock; retained synchronous ownership prevents nested acquisition. Cancellation only persists a request and leaves the worker's lock held through its write path. Shared non-mutating preflight derives required objects from executable migration boundaries and validates physical, foreign-key and same-run integrity before source writes. Current schemas are never repaired implicitly; recognized historical upgrades retain verified backups under the same lock. Source-derived tests cover writable versions 1–17; public read-only inspection still rejects 1–6. Native evidence browsing batches selected candidate relations in 500-key chunks and decodes each selected snapshot once. Imported copies and default storage folders use POSIX owner-only permissions or protected Windows owner/SYSTEM ACLs, whose native verification remains a Windows release gate.

Desktop credentials use macOS Keychain or Windows Credential Manager. Secrets stay out of logs, SQLite, exports, browser storage, and child-process arguments. OpenAlex and optional PubMed API keys are sent to their respective upstream services in HTTPS query strings. Automatic `.env` and shell-profile loading are not permitted. The application uses owned process groups/jobs for cleanup.

Detailed current rules for quotations, evidence admission, retry/accounting limits, Round 4 authorization, persistence compatibility, and resume identity are in [Research invariants](docs/research-invariants.md).

Physical-call completion artifacts separately preserve cache-write tokens and cost basis and remain the authority for v2 budgets. Route-attempt projection now preserves those fields through reservation, completion and replay without rewriting immutable artifacts or completed charges. Reservation and completion bind immutable attempt identity under SQLite write transactions; unknown or still-running usage keeps conservative exposure. Absent historical write counts or pricing bases remain unknown. Saved briefs and release hashes are not regenerated.

## Current release boundary

macOS is the first release target. Windows release work is deferred; the earlier Phase 2 native Windows matrix does not verify the current version. The unsigned Mac candidate has not passed live-quality acceptance, clean-machine installation, minimum-OS verification, signing, or notarization. The five-submission live-test allowance is exhausted and requires new explicit authorization before more paid research. See [STATUS](STATUS.md), [HANDOFF](HANDOFF.md), and [desktop operations](desktop/README.md).

The exact preceding architecture is preserved in the [Prompt 3 archive](docs/archive/2026-10-04-phase3-state/ARCHITECTURE.md). The [2026-09-26 archive](docs/archive/2026-09-26-maintenance/ARCHITECTURE.md) retains the earlier full module inventory and historical invariants; the [archive index](docs/archive/INDEX.md) lists all replaced documents. Current implementation facts remain separate from release evidence.
