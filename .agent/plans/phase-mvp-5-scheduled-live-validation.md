# Phase MVP-5 - Scheduled Live Validation and Operational Proof

## Prerequisite and Purpose

Begin only after MVP-4's supported live CLI is complete and controlled live testing has
passed. Schedule one bounded daily invocation of that unchanged CLI and prove unattended
execution is safe, observable, reproducible, and idempotent. Do not modify Streamlit,
redesign providers/orchestration/CLI, or begin a live-frontend phase.

Use only a local Codex automation registered to this project. Do not create cron,
launchd, GitHub Actions live jobs, cloud hosting, another scheduler/provider, or browser
automation.

## Schedule and Rotation

Configure `ResearchAssistant Daily Live Validation` for 6:00 AM
`America/Los_Angeles`, once per calendar day, with a notification after every attempt.
Do not enable it until offline wrapper tests pass, a no-provider dry run succeeds, one
explicitly approved rehearsal stays within the unchanged MVP-4 limits, and the user
confirms the displayed schedule and limits.

Use this versioned five-claim rotation, one exact claim per Pacific calendar date:

1. A four-day, 32-hour workweek generally maintains or improves organizational
   productivity compared with a five-day, 40-hour workweek.
2. Expanding nuclear power is necessary for the United States to achieve a deeply
   decarbonized electricity system by 2050.
3. Heavier social-media use causes worse mental-health outcomes in adolescents.
4. Banning student smartphone use during the school day improves academic performance
   and student well-being in secondary schools.
5. Providing an unconditional basic income reduces labor-force participation among
   working-age adults.

Anchor to the first enabled Pacific date. Select by calendar date, not successful-run
count. Missed days do not shift or backfill the rotation.

## Wrapper and Idempotency

Add the smallest internal wrapper around existing `run`, `inspect-run`, and persistence
contracts. It validates rotation/configuration, selects the claim, supplies dedicated
database/output paths and unchanged budgets, writes strict machine and human reports,
and compares the previous attempt for that claim. It must not alter tracked files.

Derive run ID from schedule identity, rotation version, Pacific date, and exact claim
hash. Same-day repeats use the same ID, resume valid checkpoints, preserve attempts and
budgets, avoid duplicate Ledger/releases/provider calls, and classify an already
terminal run explicitly. A run-ID/claim/configuration collision fails closed.

## Reproducibility and Dirty Worktree

Record commit SHA, clean state, rotation/claim/hash, provider/adapter/model/prompt/schema/
normalization identities, budgets, timestamps/timezone, calls/tokens/cost, and terminal
classification. A dirty tracked worktree spends no provider budget and returns
`skipped_dirty_worktree`.

## Safety and Classification

Require both the existing live-enable flag and a scheduler-specific flag, approved
configuration, unchanged MVP-4 call/token/cost limits, deadlines/retries, dedicated
paths, non-sensitive claims, redaction, and fail-closed costs. Credentials alone never
trigger execution. Retries/fallback/resume/malformed responses share persisted budgets.

Classify exactly one of: `released`, `blocked`, `failed`, `cancelled`,
`skipped_dirty_worktree`, `configuration_error`, `budget_preflight_rejected`, or
`duplicate_terminal_run`. A blocked research result is not infrastructure failure.

## Artifacts, Notification, and Comparison

Store ignored artifacts by Pacific date: SQLite, run/claim, machine report, human
summary, brief/hash, validation/failure/cancellation details, usage/cost, and prior-run
comparison. Do not delete history automatically.

Every notification includes classification, claim, run ID, commit, duration, call
counts, tokens/cost, provider/models, source/Ledger counts, hash or reason, prior-run
comparison, and artifact path. Never include credentials, auth headers, secret-bearing
raw responses, or complete environment values.

Compare the latest completed same-claim attempt by classification, hash, added/removed
source URLs, Ledger count, validation codes, provider/model, calls, tokens, cost, and
runtime. Changed web evidence is an observation, not automatically a regression.

Preserve MVP-4 cooperative cancellation and explicit machine sleep/shutdown/partial-run
handling. Never silently backfill a missed live run.

## Tests, Rehearsal, and Activation

Network-free tests cover rotation across month/year/DST, deterministic IDs, missed days,
duplicates/restart/collisions, dirty worktree, missing flags/configuration, every budget
exhaustion, every classification/report, redaction, comparisons, stable output,
notifications, and path isolation.

The optional rehearsal uses the exact automation wrapper/configuration and requires both
flags, explicit approval, approved credentials, unchanged limits, clean worktree,
dedicated paths, and a non-sensitive claim. Report calls/tokens/cost/duration/state/
validation/artifacts. A blocked rehearsal proves scheduling only; it does not replace
MVP-3B's prior released live canary.

Before activation display automation name, project, schedule/timezone/next run, anchor
and first claim, provider/models, limits, output path, and notification policy. Require
explicit user confirmation before enabling recurring execution.

## Scope, Verification, and Report

Do not modify Streamlit/public CLI/provider stack/orchestration; add providers, browser
automation, hosting/Docker/accounts/queues/telemetry; create another scheduler; delete
history; commit; or push. Only narrow demonstrated compatibility fixes are permitted.

Run focused scheduling/wrapper/idempotency/budget/redaction/notification tests, complete
MVP-4 CLI tests, full suite, offline evaluation, Ruff, fixture and mocked scheduled
smokes, no-provider dry rehearsal, optional approved live rehearsal, same-day duplicate
verification, `git diff --check`, and Git status.

Report completion, files, automation name/ID/status/schedule/next run, anchor/rotation,
ID design, unchanged limits, dry/live rehearsal, idempotency/restart, notifications,
artifacts, verification, operational limitations, and live-frontend readiness. Leave
repository changes uncommitted.

