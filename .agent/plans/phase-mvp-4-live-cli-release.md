# Phase MVP-4 - Usable Live CLI and MVP Release

## Prerequisite and Purpose

Begin only after MVP-3B produces a released positive live canary and a safe negative
canary. Expose the smallest usable CLI around the already validated provider pipeline.
Do not modify the fixture-only Streamlit frontend or begin MVP-5.

## Commands

Implement or complete `run`, `inspect-run`, and `cancel-run` using existing CLI
conventions. `run` accepts an exact claim, explicit database path, optional run ID, and
explicit token/cost budgets, and validates provider configuration before execution.
Claim/output file conveniences are optional and must not delay the core path.

At launch print database path, run ID, exact claim, approved provider stack, model
aliases/pinned IDs, and budgets—never secrets.

Define stable tested numeric exit codes for released, blocked, failed, cancelled,
configuration error, and invalid input. Released output prints the validated brief and
hash. Blocked prints deterministic validation errors. Failed prints normalized stage and
reason. Cancelled prints the observed cooperative boundary without claiming immediate
interruption.

`inspect-run` displays authoritative claim, status, checkpoints, attempts/failures,
validation errors, usage/cost, provider/model/prompt/schema/normalization identities,
and final brief/hash when released.

`cancel-run` must work from a second process. Persist cancellation; check before/after
calls and at orchestration boundaries; start no new call after observation; permit an
active request to continue until its deadline.

## Restart Contract

- Same run ID plus exact same claim and compatible fingerprint: resume.
- Same run ID plus different claim: reject.
- Changed provider/model/prompt/schema/adapter/normalization/policy/repository identity:
  reject resume and require a new run.
- Define whether budget changes may only tighten unused capacity or require a new run;
  never reset consumed usage.
- Skip valid checkpoints; preserve attempts/budgets; do not duplicate snapshots, Ledger,
  or releases; document terminal-run reinvocation; do not promise arbitrary cross-version
  crash recovery.

## Tests and Clean Installation

Normal tests use mocked providers. Add subprocess tests for valid/missing configuration,
all terminal states, budgets, cancellation, inspection, exact exit codes, redaction,
restart, and changed-claim rejection. Add one optional budget-capped live CLI smoke that
is skipped unless explicitly enabled and approved.

Verify documented setup on supported clean Python versions. Permit only narrow packaging
corrections needed for the documented installation; do not add Docker, hosting, accounts,
or broad packaging work.

## Documentation, Verification, and Report

Update only relevant current documentation and the MVP-4 plan. Clearly distinguish the
live CLI, approved stack, fixture-only Streamlit, restart/cancellation limits, Python
support, human-review requirement, and known limitations.

Run focused/subprocess CLI tests, full suite, offline evaluation, Ruff, fixture and mocked
CLI smokes, restart and second-process cancellation verification, clean-install checks,
optional approved live CLI canary, `git diff --check`, and Git status.

Report the completion contract, files, commands/exit codes, configuration, restart and
cancellation contracts, clean-install and optional canary results/cost, verification
counts, limitations, and whether the repository is honestly a usable MVP. Leave changes
uncommitted.

