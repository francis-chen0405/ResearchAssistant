# Explicit pipeline selection

Status: complete; explicitly authorized on 2026-09-20 and verified on 2026-09-21. Work directly on local
`master`, starting at clean `311f2e4`, after the completed SQLite status-polling phase.

## Scope and design

Replace CLI function-identity detection with explicit typed legacy-runner and
repository-identity injection. Ordinary CLI and API construction selects v2.
Historical subprocess tests pass their dependencies explicitly. Give the controller
a named `legacy_runner` parameter and retain `runner` as a compatibility alias;
reject conflicting injections before allocating worker resources.

The callable dependency protocol describes application wiring, not an agent artifact;
internal research handoffs retain their strict Pydantic contracts. Keep the public
historical pipeline and legacy helper imports. No broad extraction is needed to fix
selection. Root Python additions remain covered by packaging and source identity.

## Acceptance

- Default CLI/controller execution selects v2 even if the historical CLI export is rebound.
- Explicit legacy injection preserves configuration, output, exits, errors, redaction,
  restart, budget and cancellation behavior; deterministic identity injection is explicit.
- Historical imports and existing controller callers remain compatible.
- Source/executable identity changes require fresh runs; historical inspection/export
  remains read-only. Database schema, payloads, policies and validators do not change.
- Run targeted selection, CLI subprocess, live-controller and historical tests; full
  pytest and Ruff checks; frontend lint/types/export and established offline UI/API smokes;
  `git diff --check`. No paid/live provider call or dependency addition.
- Update authority, status and handoff with actual evidence. Commit directly to local
  `master`; no branch/worktree creation, merge, push or publication.

## Delivery record

The CLI now selects v2 unconditionally for ordinary construction. Historical execution
requires an explicit typed `legacy_runner`, and deterministic tests can inject an
`identity_provider`; rebinding the historical function export no longer changes the
factory or pipeline. `LiveResearchController` exposes `legacy_runner`, retains `runner`
as a compatibility alias, and rejects conflicting injection before allocating workers.
The historical orchestrator and legacy evidence-helper modules remain available and
their shared-helper ownership is recorded as intentional follow-up debt.

Verification passed: 1,026 Python tests with two existing skips; Ruff lint/format;
frontend ESLint, TypeScript and production export; offline frontend acceptance;
offline status-polling acceptance; and `git diff --check`. No provider calls, paid
research, dependency, schema, prompt, budget, route, packaging, install, push or
publication occurred. The source identity surface changed, so new runs are required
for exact resume; historical inspection and export remain readable.

## Follow-up boundary

Neutral ownership for shared legacy evidence helpers is separate future work. Mac-first
release gates and the exhausted paid-test allowance remain in force. No packaging or
installation is part of this phase.
