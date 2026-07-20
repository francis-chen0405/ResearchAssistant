# CI Maintenance - Daily Expanded Checks

## Purpose

Expand repository automation without beginning another product phase or adding live,
network-dependent behavior.

## Changes

- Run CI after pushes to every branch, for pull requests targeting `master`, manually,
  and daily at 1:17 AM in `America/Los_Angeles`.
- Run the complete pytest suite on Python 3.11 and 3.12.
- Run Ruff lint and format checks once per workflow run.
- Run the existing deterministic 38-case offline evaluation once per workflow run.
- Add the user-approved `pytest-cov` development dependency and report branch coverage
  with missing lines, without enforcing a minimum threshold.

## Acceptance Criteria

- The workflow schedule, triggers, and matrix parse successfully.
- Full pytest with coverage, the offline evaluation, Ruff lint, and Ruff format checks
  pass.
- Coverage is visible but cannot fail solely for being below a percentage.
- No live provider, API key, network test, runtime behavior, or product-phase work is
  added.
