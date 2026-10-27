# Plan and verification history

This page links to retained task records at their original paths. Each record describes its dated scope and evidence; [work navigation](../.agent/PLANS.md) links follow-up owners. Routine changes do not require a history entry.

Historical setup, next-step and approval wording in these records applies to their dated scope. [STATUS](project/STATUS.md) owns current behavior, limits and next priorities; [conventions](project/CONVENTIONS.md) supersede older recordkeeping requirements.

## Recovering retired snapshots

Historical snapshots formerly under `docs/archive/` are preserved in the annotated
Git tag `archive-2026-10-23-docs-baseline`, at commit
`ca492a6285e823018bdefb10aba1ea74af2c12af`. They are omitted from the current
working tree and source archive. Active requirements and open acceptance gates
remain in current guidance. Retained records keep their existing paths.

Completed scope-only plans, superseded documentation checks and completed foundation
implementation prompts retired from the remaining records are preserved exactly at
commit `c59e54d3fcb86dd1b9f0a16242303af8fd32b608`. Repeated combined prompt packs
are also recoverable there; their individual database/source-discovery prompts remain
in the checkout. Requirements, unresolved findings and supporting acceptance evidence
remain with their current owners.

To inspect the earlier archive without changing your checkout:

```sh
git fetch origin tag archive-2026-10-23-docs-baseline
git show archive-2026-10-23-docs-baseline:docs/archive/INDEX.md
```

To list or retrieve a record from the later cleanup without switching, staging or
restoring files into the checkout:

```sh
git ls-tree -r --name-only c59e54d3fcb86dd1b9f0a16242303af8fd32b608 -- .agent/plans docs/audits docs/proposals docs/verification
git show c59e54d3fcb86dd1b9f0a16242303af8fd32b608:docs/verification/docs-test-navigation-2026-10-10.md
# Optional: save the exact record outside the checkout.
git show c59e54d3fcb86dd1b9f0a16242303af8fd32b608:docs/verification/docs-test-navigation-2026-10-10.md > /tmp/researchassistant-retired-record.md
```

The [tagged archive index](https://github.com/francis-chen0405/ResearchAssistant/blob/archive-2026-10-23-docs-baseline/docs/archive/INDEX.md)
locates the exact prior snapshots. Links into those snapshots are pinned to this
tag. Paths and hashes inside dated audit inventories and evaluation results describe
the recorded revision, rather than current file lists. Resolve the earlier archive
against the tag and later retired task records against the commit above; use an
inventory's own recorded revision for its exact payload/hash comparison. Both recovery
references preserve source records only, not research databases or credentials.
Database backup and restore use the separate [recovery procedures](project/database-recovery.md).

The last separate current handoff is retained at
[commit 1bb6476](https://github.com/francis-chen0405/ResearchAssistant/blob/1bb64766a5df09cf741052f3c58eaac04dff90e3/docs/project/HANDOFF.md).
Retrieve it without changing the checkout with
`git show 1bb64766a5df09cf741052f3c58eaac04dff90e3:docs/project/HANDOFF.md`.
References to older handoffs in dated records remain pinned to their own recorded
revision; they do not replace the current STATUS page.

## Recent reviews and repairs

- [Offline evidence-loop evaluation](verification/offline-evidence-loop-2026-10-23.md):
  saved-run integrity checked read-only; disposable capture, assessed follow-up,
  quotation, accounting and replay controls passed. Live quality remains unmeasured.

- [Source-loss recovery](../.agent/plans/source-loss-recovery-2026-10-19.md): early evidence feedback,
  source replacement, exact excerpts, saved paper leads and source outcome presentation.
  Installed as local Mac build `20261020.4`, with verified ZIP in Downloads and older
  copies removed. The first user rerun exposed a citation-neighbor validator crash;
  corrective build `20261020.5` is verified and installed. Saved diagnostic runs remain
  unchanged; final live quality is unmeasured.

- [Current Mac replacement — October 19](verification/current-app-install-2026-10-19.md): new 50/20 defaults and 30-source choice, verified local app replacement, preserved saved data and current package checks.

- [Prompt 17 Windows CI and native durability](verification/windows-ci-durability-2026-10-13.md): current-source Windows reproductions, NTFS privacy/publication, process-crash recovery, isolated native vault/Jobs and explicit power-loss/release limits.
- [Prompt 16 Mac delivery and source-archive repair candidate and installed-cache gates](verification/mac-delivery-gates-2026-10-13.md): exact current-source DMG/ZIP, confirmed FTS repair on disposable cache, preserved October 9 installation and named external signing/platform prerequisites.
- [Prompt 15 source coverage/dispositions](../.agent/plans/source-leads-quality-2026-10-13.md): same-run read-only source leads and four review repairs; live usefulness remains unmeasured.

- [Current research-quality acceptance — Prompt 14](../.agent/plans/research-quality-acceptance-2026-10-11.md): reproducible offline observation harness, provenance/unknown denominators, frozen current baseline and a separately authorized bounded live protocol.

- [Backend responsibility splits — Prompt 13](verification/backend-hotspot-split-2026-10-11.md): adaptive search, bounded Round 4, atomic storage aggregates, stage contracts and historical execution isolation.
- [Neutral contracts and historical inspection — Prompt 12](verification/contract-ownership-2026-10-10.md): dependency ownership, public shape/byte compatibility, isolated reads and ratcheted import guard.
- [Renderer feature split — Prompt 11](verification/renderer-split-2026-10-10.md): feature controllers/views, generated contracts and independent offline frontend checks.
- [Python API responsibility split — Prompt 10](verification/api-module-split-2026-10-10.md): route ownership, compatibility facades, unchanged HTTP inventory and read/lifecycle verification.
- [October 9 current-source Mac installation](verification/current-app-install-2026-10-09.md): verified local unsigned replacement and preserved saved data; public distribution remains separate.

- [Owning-folder consolidation — Prompt 08](verification/folder-consolidation-2026-10-10.md): backend/src distribution, renderer rename, installed facades, resource/identity and final verification.

### Plans

- [repository-review-2026-10-08](../.agent/plans/repository-review-2026-10-08.md) — repository-wide review, fixes and offline verification using Luna helpers and Sol integration.
- [source-discovery-v2-2026-10-05](../.agent/plans/source-discovery-v2-2026-10-05.md) — all six phases: foundations, provider queries, bounded retrieval/ranking, exact previews, one-hop seed expansion, ordinary product controls and complete offline integration acceptance; synthetic evaluation and later bounded live-test protocol.
- [database-review-2026-10-03](../.agent/plans/database-review-2026-10-03.md)
- [alpr-equity-run-fixes-2026-10-02](../.agent/plans/alpr-equity-run-fixes-2026-10-02.md)
- [alpr-run-fixes-2026-10-01](../.agent/plans/alpr-run-fixes-2026-10-01.md)
- [comprehensive-code-audit-2026-10-01](../.agent/plans/comprehensive-code-audit-2026-10-01.md)
- [discrimination-run-fixes-2026-10-01](../.agent/plans/discrimination-run-fixes-2026-10-01.md)
- [mac-current-build-release-verification-2026-09-28](../.agent/plans/mac-current-build-release-verification-2026-09-28.md)
- [private-surveillance-run-fixes-2026-10-02](../.agent/plans/private-surveillance-run-fixes-2026-10-02.md)
- [validator-and-current-docs-2026-10-02](../.agent/plans/validator-and-current-docs-2026-10-02.md)

### Verification records

- [backend-installability-2026-10-10](verification/backend-installability-2026-10-10.md) — current-layout distribution, exact wheel inventory, preserved prompt bytes, arbitrary-cwd wheel/editable and native frozen verification; Prompt 08 starting state.

- [desktop-shutdown-2026-10-10](verification/desktop-shutdown-2026-10-10.md) — bounded EOF-first quit/startup, owned process escalation, SQLite recovery and native Mac/Windows verification boundaries.

- [service-lifecycle-2026-10-10](verification/service-lifecycle-2026-10-10.md) — atomic stop/admission and confirmed credential/import guards, barrier/accounting checks and measured contention.

- [resume-status-2026-10-10](verification/resume-status-2026-10-10.md) — first-poll rejection diagnostics, explicit worker ownership/restart presentation and unchanged historical run accounting.

- [acquisition-usable-fallback-2026-10-09](verification/acquisition-usable-fallback-2026-10-09.md) — reproduced shell source-loss, bounded Probe-v4 fallback and immutable capture/replay checks.

- [citation-expansion-limits-2026-10-09](verification/citation-expansion-limits-2026-10-09.md) — reproduced retention/replay failures, versioned correction and offline quota matrix.

- [root-cleanup-2026-10-09](verification/root-cleanup-2026-10-09.md) — inactive root-copy removal and CI layout/dependency guardrails.

- [alpr-equity-run-review-2026-10-02](../docs/verification/alpr-equity-run-review-2026-10-02.md)
- [alpr-run-fixes-2026-10-01](../docs/verification/alpr-run-fixes-2026-10-01.md)
- [alpr-run-review-2026-10-01](../docs/verification/alpr-run-review-2026-10-01.md)
- [audited-app-install-2026-10-01](../docs/verification/audited-app-install-2026-10-01.md)
- [committed-app-redelivery-2026-10-02](../docs/verification/committed-app-redelivery-2026-10-02.md)
- [discrimination-run-fixes-2026-10-02](../docs/verification/discrimination-run-fixes-2026-10-02.md)
- [discrimination-run-review-2026-10-01](../docs/verification/discrimination-run-review-2026-10-01.md)
- [private-surveillance-run-fixes-2026-10-02](../docs/verification/private-surveillance-run-fixes-2026-10-02.md)
- [private-surveillance-run-review-2026-10-02](../docs/verification/private-surveillance-run-review-2026-10-02.md)
- [reviewer-route-testing-fix-2026-10-01](../docs/verification/reviewer-route-testing-fix-2026-10-01.md)

## Desktop, release, and storage

### Plans

- [adaptive-search-reliability](../.agent/plans/adaptive-search-reliability.md)
- [ci-daily-expanded-checks](../.agent/plans/ci-daily-expanded-checks.md)
- [deep-analysis-deterministic-concurrency](../.agent/plans/deep-analysis-deterministic-concurrency.md)
- [mac-release-cache-pricing](../.agent/plans/mac-release-cache-pricing.md)
- [mlp-readiness](../.agent/plans/mlp-readiness.md)
- [per-step-model-choices](../.agent/plans/per-step-model-choices.md)
- [sqlite-status-polling](../.agent/plans/sqlite-status-polling.md)

### Verification records

- [audit-maintenance](../docs/verification/audit-maintenance.md)
- [database-integrity-fixes](../docs/verification/database-integrity-fixes.md)
- [database-review-2026-10-03](../docs/audits/2026-10-03/database-review.md)
- [Database phase 4 integration](verification/database-phase4.md)
- [Database phase 4 independent review and cache checks](verification/database-phase4-review.md)
- [mac-cache-pricing](../docs/verification/mac-cache-pricing.md)
- [mac-current-build-2026-09-28](../docs/verification/mac-current-build-2026-09-28.md)
- [sqlite-status-polling](../docs/verification/sqlite-status-polling.md)

## Product and architecture

### Plans

- [phase-00-foundation](../.agent/plans/phase-00-foundation.md)
- [phase-01-models](../.agent/plans/phase-01-models.md)
- [phase-02-store](../.agent/plans/phase-02-store.md)
- [phase-03-snapshot-integrity](../.agent/plans/phase-03-snapshot-integrity.md)
- [phase-04-ledger-admission](../.agent/plans/phase-04-ledger-admission.md)
- [phase-05-release-gate](../.agent/plans/phase-05-release-gate.md)
- [phase-06-fixture-pipeline](../.agent/plans/phase-06-fixture-pipeline.md)
- [phase-07-retrieval](../.agent/plans/phase-07-retrieval.md)
- [phase-07a-local-frontend](../.agent/plans/phase-07a-local-frontend.md)
- [phase-08-llm-integration](../.agent/plans/phase-08-llm-integration.md)
- [phase-09-orchestration](../.agent/plans/phase-09-orchestration.md)
- [phase-1-desktop](../.agent/plans/phase-1-desktop.md)
- [phase-10-evaluation](../.agent/plans/phase-10-evaluation.md)
- [phase-2-cleanup](../.agent/plans/phase-2-cleanup.md)
- [phase-3-frontend-settings](../.agent/plans/phase-3-frontend-settings.md)
- [phase-mlp-1-simplified-live-experience](../.agent/plans/phase-mlp-1-simplified-live-experience.md)
- [phase-mlp-2-local-product-experience](../.agent/plans/phase-mlp-2-local-product-experience.md)
- [phase-mlp-3-nextjs-product-rebuild](../.agent/plans/phase-mlp-3-nextjs-product-rebuild.md)
- [phase-mlp-4-research-quality-openalex](../.agent/plans/phase-mlp-4-research-quality-openalex.md)
- [phase-mlp-5-provider-selection-serpsearch](../.agent/plans/phase-mlp-5-provider-selection-serpsearch.md)
- [phase-mvp-1-release-contract-correctness](../.agent/plans/phase-mvp-1-release-contract-correctness.md)
- [phase-mvp-10-evidence-portfolio-trail](../.agent/plans/phase-mvp-10-evidence-portfolio-trail.md)
- [phase-mvp-11-research-governor](../.agent/plans/phase-mvp-11-research-governor.md)
- [phase-mvp-2a-architecture-gate](../.agent/plans/phase-mvp-2a-architecture-gate.md)
- [phase-mvp-2b-production-provider-boundaries](../.agent/plans/phase-mvp-2b-production-provider-boundaries.md)
- [phase-mvp-3a-mocked-full-provider-pipeline](../.agent/plans/phase-mvp-3a-mocked-full-provider-pipeline.md)
- [phase-mvp-3b-live-canary-stabilization](../.agent/plans/phase-mvp-3b-live-canary-stabilization.md)
- [phase-mvp-4-live-cli-release](../.agent/plans/phase-mvp-4-live-cli-release.md)
- [phase-mvp-5-scheduled-live-validation](../.agent/plans/phase-mvp-5-scheduled-live-validation.md)
- [phase-mvp-6-2-integrity-provenance-runtime-contract-hardening](../.agent/plans/phase-mvp-6-2-integrity-provenance-runtime-contract-hardening.md)
- [phase-mvp-6-3-public-acquisition-provenance-security](../.agent/plans/phase-mvp-6-3-public-acquisition-provenance-security.md)
- [phase-mvp-6-4-evidence-density-threshold-calibration](../.agent/plans/phase-mvp-6-4-evidence-density-threshold-calibration.md)
- [phase-mvp-6-5-immutable-run-authority-read-only-inspection](../.agent/plans/phase-mvp-6-5-immutable-run-authority-read-only-inspection.md)
- [phase-mvp-6-6-runtime-status-budget-contract-integrity](../.agent/plans/phase-mvp-6-6-runtime-status-budget-contract-integrity.md)
- [phase-mvp-6-7-repository-wide-type-contract-enforcement](../.agent/plans/phase-mvp-6-7-repository-wide-type-contract-enforcement.md)
- [phase-mvp-6-8-persistence-accounting-integrity](../.agent/plans/phase-mvp-6-8-persistence-accounting-integrity.md)
- [phase-mvp-6-9-acquisition-configuration-integrity](../.agent/plans/phase-mvp-6-9-acquisition-configuration-integrity.md)
- [phase-mvp-7-1-mimo-consolidation-completion](../.agent/plans/phase-mvp-7-1-mimo-consolidation-completion.md)
- [phase-mvp-7-direct-mimo-consolidation](../.agent/plans/phase-mvp-7-direct-mimo-consolidation.md)
- [phase-mvp-8-1-research-controls](../.agent/plans/phase-mvp-8-1-research-controls.md)
- [phase-mvp-8-2-evidence-browser](../.agent/plans/phase-mvp-8-2-evidence-browser.md)
- [phase-mvp-8-briefs-export-performance](../.agent/plans/phase-mvp-8-briefs-export-performance.md)
- [phase-mvp-9-verified-quote-selection-deterministic-assembly](../.agent/plans/phase-mvp-9-verified-quote-selection-deterministic-assembly.md)
- [phase-v2-02-multi-model-routing](../.agent/plans/phase-v2-02-multi-model-routing.md)
- [phase-v2-03-initial-planner-round-one](../.agent/plans/phase-v2-03-initial-planner-round-one.md)
- [phase-v2-04-discovery-providers-normalization-clustering-scout](../.agent/plans/phase-v2-04-discovery-providers-normalization-clustering-scout.md)
- [phase-v2-05-acquisition-snapshots-probe-survivors](../.agent/plans/phase-v2-05-acquisition-snapshots-probe-survivors.md)
- [phase-v2-06-luna-gap-analysis](../.agent/plans/phase-v2-06-luna-gap-analysis.md)
- [phase-v2-07-adaptive-search-continuation](../.agent/plans/phase-v2-07-adaptive-search-continuation.md)
- [phase-v2-08-source-selection-deep-analysis-queue](../.agent/plans/phase-v2-08-source-selection-deep-analysis-queue.md)
- [phase-v2-09-luna-evidence-analyst](../.agent/plans/phase-v2-09-luna-evidence-analyst.md)
- [phase-v2-10-reviewer-ledger-integration](../.agent/plans/phase-v2-10-reviewer-ledger-integration.md)
- [phase-v2-11-synthesis-final-output](../.agent/plans/phase-v2-11-synthesis-final-output.md)
- [phase-v2-12-production-hardening-cutover](../.agent/plans/phase-v2-12-production-hardening-cutover.md)
- [phase-v2-13-analyzer-admission-cutover](../.agent/plans/phase-v2-13-analyzer-admission-cutover.md)
- [phase-v2-14-conditional-round-four](../.agent/plans/phase-v2-14-conditional-round-four.md)

### Verification records

- [adaptive-search-reliability](../docs/verification/adaptive-search-reliability.md)
- [phase-2](../docs/verification/phase-2.md)
- [phase-3](../docs/verification/phase-3.md)
- [planner-scout-reliability](../docs/verification/planner-scout-reliability.md)

- [Prompt 11 renderer feature split and independent checks](verification/renderer-split-2026-10-10.md).

- [Prompt 15 source dispositions, review repairs and quality boundary](../.agent/plans/source-leads-quality-2026-10-13.md).

- [Current Mac replacement — October 18](verification/current-app-install-2026-10-18.md): verified R01–R59 local build, installed/window/upgrade checks, preserved data, old-app removal and a local installer.

- [Master consolidation — October 18](../.agent/plans/publish-master-2026-10-18.md): redundant Windows branch comparison, preserved history and authorized commit/push.

- [Manual-only Windows packaging — October 18](../.agent/plans/windows-ci-trigger-2026-10-18.md): exact failed job, authorized trigger change and retained acceptance limits.

- [Mac shutdown smoke PID race — October 18](../.agent/plans/mac-smoke-pid-race-2026-10-18.md): atomic test records, strict PID checks and native verification.

## 2026-10-21 — Selection coverage and paper identity

Delivered local Mac build `20261020.6` with compact exact selection views, confirmed
DOI/title mirror grouping, alternate locations, considered/omitted coverage and
blocked/unknown dispatch reporting. Preserved source quotations, saved research,
support-only preferences and all budgets/unknown reservations. Complete offline and
installed checks are in [verification](verification/selection-coverage-repairs-2026-10-21.md).
Research-quality improvement remains unmeasured pending fresh user runs.

- [October 23 master integration](../.agent/plans/source-loss-recovery-2026-10-19.md#master-integration--october-23): reviewed e359 recovery, PDF capture and post-analysis changes integrated with current CLI defaults; full source and isolated install checks pass, frozen acquisition health remains blocked.

- [Recoverable research progress polling](../.agent/plans/recoverable-progress-polling-2026-10-23.md): local renderer deadlines, bounded retries, preserved snapshots and same-run recovery controls with confirmed cancellation.
