# Phase MVP-5 - Polished Local Live Web Interface

> Post-completion provider correction (2026-08-01): for new live runs, Exa Search
> replaces native SearXNG discovery; Wigolo remains primary acquisition and optional
> Firecrawl is a narrowly gated acquisition fallback. The research pipeline, interface,
> persistence schema, validation, and MVP-5 boundary otherwise remain unchanged. See
> `DECISIONS.md` for the fail-closed fallback policy. This correction was subsequently
> committed as MVP-6 work in `37c52a7`; the plan remains here as historical context.

> Bounded-inference correction (2026-08-01): new runs use a 75-word exact quote minimum,
> separate literal statement entailment from whether one fact proves the full claim,
> render Claim Fit 5/4/3 as direct/indirect/contextual evidence, and flag one-sided briefs
> as not balanced. Exact quote/provenance checks and zero-Ledger failure remain strict.

## Superseded Placeholder and Authority

The user's explicit 2026-08-01 direction replaces the earlier scheduled-live-validation
placeholder at this canonical path. The path is retained to avoid creating a second
source of truth. Scheduled automation, claim rotation, notifications, and unattended
live execution are not part of MVP-5 and must not be implemented.

MVP-4 is the prerequisite and remains the released behavioral contract. MVP-5 ends with
a local live website and local service lifecycle; it must not begin MVP-6.

## Goal and Architecture

Provide the smallest safe, polished local Streamlit website that drives the existing
MVP-4 application/orchestrator contracts without creating another research pipeline.
Keep `frontend/streamlit_app.py` visibly fixture-only and create a separate live app.

Use the database as the authority for runs, checkpoints, attempts, budgets, status, and
release artifacts. UI session state may hold only presentation preferences and worker
handles; it must never be the authoritative run record. Execute live work outside the
Streamlit rerun thread so the page stays responsive. Permit only one active worker per
SQLite database, while allowing different database files to run concurrently. Combine that
database-wide guard with persisted MVP-4 compatibility checks so reruns, refreshes,
and reopened pages reconnect rather than duplicate calls, releases, snapshots, Ledger
entries, or workers.

Prefer a narrow typed application service around existing MVP-4 functions. If the
existing synchronous CLI boundary is safer for worker isolation, invoke it without
secrets in command arguments and preserve exact exit-code semantics: released `0`,
blocked `10`, failed `11`, cancelled `12`, configuration error `20`, invalid input `21`.

## User Surface

The live website provides:

- exact-claim input with a public/non-sensitive warning;
- explicit token and USD budgets, optional run ID, and a validated selectable SQLite
  location with a safe project-local default;
- Start Research and cooperative Cancel controls;
- live authoritative status, stage, latest checkpoint, aggregate calls/tokens/estimated
  cost, retrieval progress, and supporting/opposing progress;
- deterministic released, blocked, failed, cancelled, configuration-error, invalid-
  input, and incompatible-resume displays with actionable stage diagnostics;
- run history and inspection reconstructed from the selected database;
- released brief and SHA-256 only after final validation, with copy-friendly text and a
  direct download control;
- a prominent human-review requirement on input and released output.

Refreshing or reopening reconnects through SQLite. Terminal runs are not resumed
incorrectly. Released, blocked, and cancelled runs reconstruct without calls. Failed
runs may be reinvoked only under the exact MVP-4 claim/fingerprint contract and the UI
explains this limitation. Changed claim, budget, provider/model, prompt/schema, policy,
or executable identity fails closed and requires a new run ID.

## Configuration and Secret Safety

Use only the explicitly supplied process environment and existing approved configuration
mechanisms. Read `MIMO_API_KEY` from the server process environment; never load arbitrary
shell profiles or `.env` files. Never render, print, log, persist, send to the browser,
place in SQLite/session-state dumps/URLs/command arguments, or include the key in errors.
Redact subprocess output and exceptions before they reach logs or UI.

Missing configuration renders a friendly configuration panel and spends no provider
budget. The live identity is exactly direct Xiaomi `mimo-v2.5-pro` plus pinned loopback
Wigolo `0.2.1`. The fixture app remains clearly labeled fixture-only and must not imply
MiMo or live-search use.

## Historical MVP-5 Wigolo/SearXNG Lifecycle

The following records the original MVP-5 operating contract. It is retained for old
persisted-run compatibility and is not the current live-run stack; new runs use Exa for
discovery and Wigolo only for primary acquisition, with optional Firecrawl fallback.

Add a typed local service manager that:

- probes `127.0.0.1:8000`, verifies readiness and exact Wigolo `0.2.1` identity, and
  distinguishes Wigolo, native SearXNG, and search-readiness failures;
- can start the already approved local Wigolo/SearXNG stack with explicit executable and
  environment configuration, show progress, capture only redacted bounded diagnostics,
  and report launch failure honestly;
- records child ownership in the live application process, monitors exit state, and
  stops only children it started and still owns; it never kills an unrelated listener;
- does not falsely report health merely because a process exists or a port is open;
- preserves cooperative cancellation: an active provider request may finish or reach
  its existing deadline, and no new request begins after cancellation is observed.

No timeout is hidden or increased indefinitely. Keep the existing 15-second Search
deadline unless a tested, documented architectural change proves necessary. Surface
health/readiness and stage-specific timeout diagnostics instead.

Provide a macOS click-to-launch `.command` entry point that starts the local Streamlit
server from the repository environment and opens the live page. Document that a local
server process must remain running while the website is open. Do not add launchd,
Docker, hosting, cloud services, authentication, or another scheduler.

## Typed Boundaries and Minimal Persistence

All new internal handoffs are strict Pydantic models with
`ConfigDict(extra="forbid")` through the shared strict base. JSON/dicts are limited to
UI, subprocess, persistence, logging, or export boundaries. Prefer read-only projections
over a schema migration. Add persistence only if authoritative duplicate-worker or
service-ownership safety cannot be achieved from existing records; document and test any
approved migration before implementation.

## Implementation Sequence

1. Freeze this plan and map the live CLI, orchestrator, persistence, fingerprint,
   inspection, cancellation, exit-code, and current Streamlit contracts.
2. Add failing focused tests for typed live inspection/history/configuration/redaction,
   duplicate-start prevention, refresh/reconnection, restart mismatch, and status/exit
   mapping.
3. Implement the narrow live application service and background worker registry while
   delegating research, persistence, restart, budgets, and cancellation to MVP-4.
4. Add failing service-manager tests for healthy/unhealthy identity, SearXNG readiness,
   launch failure, ownership, monitoring, and cleanup, then implement the manager.
5. Build the separate polished live Streamlit page and update the fixture page label.
6. Add the macOS click launcher and setup/lifecycle/security/operator documentation.
7. Run focused and full verification; update current architecture/decision/status/
   handoff/README documentation and stop at MVP-5.

## Required Tests

Normal tests use mocked providers and no live network. Cover missing configuration,
healthy/unhealthy Wigolo, launch failure, released/blocked/failed/cancelled/configuration
error/invalid input, exact exit mapping, budget validation/exhaustion, restart, changed
claim, incompatible fingerprint, refresh/reconnection, duplicate starts, run history,
redaction, and released download content/hash.

Use subprocess tests for cancellation from another process, no new provider call after
cancellation observation, secret absence from UI/logs/database/arguments, and child
ownership/cleanup. Keep a real MiMo/Wigolo browser smoke optional, explicitly gated,
public/non-sensitive, and budget capped.

## Verification and Completion

Before completion run focused MVP-5 tests, MVP-4 subprocess tests, the full suite,
offline evaluation, Ruff lint and format checks, fixture-frontend smoke, mocked live-web
smoke, restart and second-process cancellation proofs, child ownership/cleanup proof,
clean installation on supported locally available Python versions, `git diff --check`,
and final Git status. Do not weaken or skip existing checks.

Document setup, exact click-to-launch behavior, local-server lifetime, service ownership,
security/redaction, provider/model identity, restart/cancellation limits, Python/Node
requirements, fixture-versus-live separation, timeout diagnostics, mandatory human
review, known limitations, and optional live-test cost.

Completion reporting must state what is usable, exact launch experience, files changed,
provider/model configuration, service lifecycle, restart/cancellation contracts, exit-
code/status mapping, verification counts, clean-install results, optional live result and
cost, security behavior, limitations, and whether normal use avoids routine terminal
interaction. Leave all changes uncommitted and stop after MVP-5.

## Explicitly Out of Scope

No scheduled live validation, automation, Docker, hosting, cloud accounts, authentication,
new provider, second pipeline, arbitrary crash recovery, secret entry in the browser,
silent shell-profile or `.env` loading, broad packaging work, timeout concealment,
validator weakening, or MVP-6 feature is permitted.
