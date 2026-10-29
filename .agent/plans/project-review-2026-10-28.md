# Project review and repairs

User scope: review the entire project with Luna subagents at xhigh reasoning,
repair verified defects, and validate the combined changes.

## Boundaries

- Review research/providers, contracts/storage/evidence, frontend/desktop, and
  API/runtime/platform/tooling in separate ownership areas.
- Verify graph findings against current source and concrete regressions.
- Preserve saved research, immutable artifacts, prompts, credential isolation,
  conservative accounting and exact resume compatibility.
- Use offline fixtures only. No paid calls, app installation or publication.

## Work

- [x] Read repository guidance and verify graph freshness against HEAD.
- [x] Dispatch three Luna reviewers with xhigh reasoning.
- [x] Confirm defects and implement focused repairs with regressions.
- [x] Review the combined diff and run complete backend and relevant UI checks.
- [x] Report actual repairs, validation and remaining limits.

## Validation

Repairs cover exact budget arithmetic and published evaluation costs, unknown
later-page search reporting, credential URL and progress-error handling, desktop
startup readiness, and source-archive privacy/publication recovery. Each has a
regression. Complete offline Python suite on macOS/Python 3.12: **3,246 passed,
9 skipped**. The initial full run caught an API error-mapping compatibility
regression; narrowing the mapping to database contention preserved the original
corruption boundary. The complete suite then passed against the final source.

Frontend hooks (31), lint, TypeScript, the static export and all six offline browser
smokes pass. Desktop/acquisition Node checks (40) pass. The offline adversarial,
source-discovery and source-lead evaluations pass. Isolated wheel/editable
verification passes for the final 311-file wheel and both clean installations.
The code graph has been refreshed from the final source. Final Ruff, formatting,
repository boundaries, generated API contracts and diff checks pass.

Changes are source-only. Installed application replacement, paid provider calls,
live research-quality acceptance and native Windows acceptance were not performed.
