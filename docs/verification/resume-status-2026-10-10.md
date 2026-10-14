# Rejected resume status — October 10, 2026

## Scope and evidence

Correct the production-boundary defect from Prompt 04 in `frontend/live_service.py`.
Reviewed current AGENTS, conventions, architecture, decisions, status, handoff and
plan navigation. Started at local `master` HEAD `94a241b52f9525cab3aff52d1f85026f081b3e85`
with the existing staged cleanup and unstaged acquisition/citation changes. Those
changes and the untracked proposal/prompt pack are preserved. Graph freshness was
checked, the working-tree graph refreshed, and completion/projection traces checked
against live source. The graph is advisory; some inferred edges are inaccurate.

The original `/private/tmp/researchassistant-runtime-audit-94a241b-probes.py` reproduced
`invalid_input` from metadata depth 20→50 after a real physical-call reservation,
zero model/search calls, then `running` from polling with no active worker and no
cached failure. Its independent service-lifecycle probe remains outside this fix.
The rebuilt `/private/tmp/researchassistant-resume-status-94a241b-probe.py` verifies
`invalid_input` within the first poll, persisted status `running`, worker ownership
false, retained rejection and zero provider calls. Durable regressions live in
`tests/test_live_resume_status.py`; the temporary probe is supplementary evidence.

## Presentation and persistence decision

- `persisted_status` reports the manifest's original status. `worker_active` reports
  an unfinished Future owned by this controller. Neither field infers ownership
  from a database status. Inspection does not acquire, probe or create lock files;
  another process's ownership is not asserted.
- `attempt_diagnostic` contains the latest redacted startup/configuration/execution
  failure. It is deliberately **ephemeral**: the existing 32-outcome cache retains
  it across polls of an existing database until a new worker starts, bounded cache
  eviction, or controller restart. A no-database outcome retains its existing
  one-shot polling behavior. No attempt journal, migration or database write is added.
- An unfinished saved run without this app's worker projects as `interrupted`.
  A rejected attempt projects its error classification/message and preserves all
  saved progress, frozen settings and conservative accounting alongside that error.
  After restart, the attempt text is absent, but the interrupted/no-worker message
  still offers compatible resume or a fresh run; it never claims active execution.
- Active progress and committed terminal projections remain authoritative. Terminal
  results may carry a separate attempt diagnostic, while classification, message,
  output and hashes remain the committed result's. Completion during a pinned poll
  causes one fresh validated read when needed; cached terminal results cannot bypass
  inspection of the current file. Completion/eviction cannot consume or erase a
  rejection observed during the read.
- The renderer treats `interrupted` as stopped, displays the actionable diagnostic,
  exposes the original frozen settings and removes active cancellation/polling.
  A completed result and its brief remain visible beside a rejected later attempt.
  Resume remains through the existing start API; no new resume button or provider
  execution path is introduced.

## Invariants and compatibility

Tests interrupt immediately after a real production reservation and drive the real
controller start/worker/completion path. Rejection makes zero model, discovery or
acquisition calls. The entire SQLite file hash, persisted fields/artifacts and the
physical-call audit are unchanged; tokens/cost remain conservatively reserved.
Matching-settings resume clears the stale diagnostic, executes the model, and
preserves the original unresolved start and unknown completion. Compatible resume
may still stop under the original budget/pipeline rules; no refund or success is invented.

Coverage includes interrupted/incompatible resume, matching resume with active
polling, a released run rejecting changed settings, early failures with/without
persisted progress and secret redaction, restart with planned/running manifests,
completion both before and after eviction during polling, and terminal commit
superseding an older progress read. Existing read-only compatibility, replacement
validation, one-session polling and history tests remain enforced.

The API adds defaulted fields and the `interrupted` presentation classification.
Consumers enumerating statuses must recognize it as stopped. Renderer fields are
optional for older API responses. SQLite schema 17 and historical artifact formats
are unchanged. The exact source/settings compatibility gate is unchanged: installing
changed executable sources can still require a new run for an older frozen identity.
This change does not weaken that gate or rewrite historical identities.

## Verification

macOS arm64, repository Python 3.12.14; offline fixtures and disposable databases only.

- Focused lifecycle/audit/read-only/production/type suite: **116 passed**.
- Full Python suite: **2,314 passed, 3 existing skips in 241.42 seconds**.
- Ruff lint/format: pass, **300 Python files**; repository boundaries pass.
- Web ESLint and TypeScript: pass. Next.js 16.3.1 webpack desktop static export: pass.
- Fresh browser polling smoke: pass for overlap, terminal stop, rejected resume,
  restart/no-worker, committed-result diagnostics, run replacement and unmount.
- Browser UI and history race smokes: pass against the fresh export.
- Staged/unstaged/new-file whitespace: pass.

The local smoke servers required execution outside the loopback-restricting sandbox.
The package-manager wrapper attempted a dependency refresh; the build was completed
using the already installed Next.js executable. No dependency change, paid call,
real research database write, native app installation, staging, commit or push occurred.
