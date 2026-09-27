# Development conventions

Follow the [active plan](.agent/plans/audit-maintenance.md) and [current plan index](.agent/PLANS.md). Read the current architecture, decisions, status, and handoff before changes. Historical phase instructions do not authorize additional work.

## Contracts and code

- Use Pydantic v2 models with `ConfigDict(extra="forbid")` for internal agent handoffs unless a documented exception applies. JSON belongs at persistence, API, logging, and export boundaries.
- Annotate every named parameter and return on repository-owned Python functions, including tests, nested functions, callbacks, and variadics. Only `self` and `cls` may be unannotated. `tests/test_type_contracts.py` enforces this contract.
- Raise clear errors or return typed failures. Do not silently return `None` on failure.
- Pass dependencies explicitly. Fresh research workers may run independently but never share a SQLite connection, cursor, transaction, or mutable handoff. Deep-analysis waves retain their four-worker cap, budget-safe priority ordering, cancellation draining, and conservative audit behavior.
- Preserve public imports, frozen fields, schemas, validators, enum values, and historical meanings during code moves. `models.py` is the stable contract facade; `store.py` owns typed persistence and `store_schema.py` owns schema initialization and migrations.
- Add regressions for validator or integrity defects. Never weaken tests, delete assertions, hide failures, or lower acceptance criteria to make an implementation pass.
- Avoid unrelated edits and dependencies. Any dependency change must fit the authorized scope and be recorded in the plan, status, and handoff.

## Persistence, security, and identity

- Snapshots, Ledger rows, and final artifacts are immutable; preserve database immutability and same-run provenance checks.
- History, inspection, and export use validated read-only sessions. They never create or migrate databases. Only intentional writable run/resume follows established migration behavior.
- Costs use finite non-negative `Decimal` values and canonical decimal storage. Unknown physical-call usage retains its reservation; never guess missing precision or issue refunds.
- Desktop data belongs under `desktop_paths.application_data_dir()`. Preserve process locks and their ownership. Do not use checkout or bundle paths for runtime data.
- Credentials use macOS Keychain or Windows Credential Manager without plaintext fallback. Secrets must stay out of logs, SQLite, exports, browser storage, and child arguments; only the documented OpenAlex upstream HTTPS query-key exception permits a secret in a URL. Do not load `.env` files or shell profiles automatically.
- Keep `prompts/*.md` in place and preserve their bytes unless an authorized plan explicitly changes them; they are executable inputs.
- Source or executable identity changes require a fresh run under the existing exact compatibility gate. Preserve historical inspection/export and reject incompatible resume.

## Packaging and verification

Base runtime dependencies are in `requirements.txt`. Development/test tools are in the `dev` optional dependency set; `httpx2` is the Starlette test client and the validated versions are pinned in `desktop/constraints.txt`. Streamlit is a separate legacy frontend installed from `requirements-legacy.txt`; it is not part of the base desktop or backend install.

Before claiming completion, run `python -m pytest`, `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`, plus the relevant frontend and desktop checks required by the active plan. Preserve existing skips and report the target platform, artifact, and actual result. A workflow definition or a prior platform build is not evidence for the current platform/version.

`STATUS.md` is the concise verified state; `HANDOFF.md` names the next boundary and remaining checks. Completed histories are retained in stable plan files or [the archive index](docs/archive/INDEX.md). The previous convention set and exact prior root documents are preserved in the maintenance archive; this file replaces older phase-specific rules that conflict with the current module layout and product boundaries.
