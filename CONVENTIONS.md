# Development conventions

Follow the active scope in the [plan index](.agent/PLANS.md) and its linked plan. Read the current architecture, decisions, status, and handoff before changes. Historical phase instructions do not authorize additional work.

## Keep project records small

- Use one active plan for a task. Add only decisions, boundaries, and checks needed to do and review that work.
- Replace current-state summaries in `STATUS.md`, `HANDOFF.md`, and `.agent/PLANS.md` when the state changes. Do not append a dated phase narrative to these current-state files.
- Keep `STATUS.md` as the sole summary of verified current state. `HANDOFF.md` records only the next action or boundary; `.agent/PLANS.md` points to the active plan and stable history.
- Put completed task details in that task's plan or verification record. Link it from [grouped history](docs/history.md); do not duplicate its chronology in root documents.
- Preserve earlier records at stable paths. For exact documents replaced by a concise current version, save a byte-for-byte snapshot and link it from the [archive index](docs/archive/INDEX.md).
- Before adding a plan or verification file, check whether the existing task record can be updated. Create another file only when it captures a distinct task or immutable result.

## Contracts and code

- Use Pydantic v2 models with `ConfigDict(extra="forbid")` for internal agent handoffs unless a documented exception applies. JSON belongs at persistence, API, logging, and export boundaries.
- Annotate every named parameter and return on repository-owned Python functions, including tests, nested functions, callbacks, and variadics. Only `self` and `cls` may be unannotated. `tests/test_type_contracts.py` enforces this contract.
- Raise clear errors or return typed failures. Do not silently return `None` on failure.
- Pass dependencies explicitly. Fresh research workers may run independently but never share a SQLite connection, cursor, transaction, or mutable handoff. Deep-analysis waves retain their four-worker cap, budget-safe priority ordering, cancellation draining, and conservative audit behavior.
- Use `researchassistant.*` imports for organized backend modules: contracts under `researchassistant.contracts`, pipeline execution under `researchassistant.research`, evidence under `researchassistant.evidence`, persistence under `researchassistant.storage`, host integration under `researchassistant.platform_support`, runtime entry points under `researchassistant.runtime`, and shared helpers under `researchassistant.common`.
- Preserve public imports, frozen fields, schemas, validators, enum values, and historical meanings during code moves. Root `models.py`, `store.py`, and `orchestrator.py` are compatibility aliases for their canonical package modules; root `cli.py` remains a launcher. `researchassistant.contracts.models` owns shared public contracts, `researchassistant.storage.store` owns typed persistence, and `researchassistant.storage.store_schema` owns schema initialization and migrations.
- Add regressions for validator or integrity defects. Never weaken tests, delete assertions, hide failures, or lower acceptance criteria to make an implementation pass.
- Avoid unrelated edits and dependencies. Any dependency change must fit the authorized scope and be recorded in the plan, status, and handoff.

## Persistence, security, and identity

- Snapshots, Ledger rows, and final artifacts are immutable; preserve database immutability and same-run provenance checks.
- History, inspection, and export use validated read-only sessions. They never create or migrate databases. Only intentional writable run/resume follows established migration behavior.
- Costs use finite non-negative `Decimal` values and canonical decimal storage. Unknown physical-call usage retains its reservation; never guess missing precision or issue refunds.
- Desktop data belongs under `researchassistant.platform_support.desktop_paths.application_data_dir()`. Preserve process locks and their ownership. Do not use checkout or bundle paths for runtime data.
- Desktop credentials use macOS Keychain or Windows Credential Manager without plaintext fallback. Secrets must stay out of logs, SQLite, exports, browser storage, and child arguments. OpenAlex and optional PubMed API keys are sent to their respective upstream services in HTTPS query strings. Do not load `.env` files or shell profiles automatically.
- Keep `prompts/*.md` in place and preserve their bytes unless an authorized plan explicitly changes them; they are executable inputs.
- Source or executable identity changes require a fresh run under the existing exact compatibility gate. The identity surface must include organized package sources as well as the existing agents, providers, frontend, and prompt sources. Preserve historical inspection/export and reject incompatible resume.
- Root source data and identity include only the documented `cli.py`, `models.py`, `orchestrator.py`, and `store.py` entry points. Keep inactive root copies out of desktop packaging and executable fingerprints.

## Packaging and verification

Base runtime dependencies are in `requirements.txt`. Development/test tools are in the `dev` optional dependency set; `httpx2` is the Starlette test client and the validated versions are pinned in `desktop/constraints.txt`. Streamlit is a separate legacy frontend installed from `requirements-legacy.txt`; it is not part of the base desktop or backend install.

Before claiming completion, run `python -m pytest`, `python -m ruff check .`, `python -m ruff format --check .`, and `git diff --check`, plus the relevant frontend and desktop checks required by the active plan. Preserve existing skips and report the target platform, artifact, and actual result. A workflow definition or a prior platform build is not evidence for the current platform/version.

`STATUS.md` is the concise verified state; `HANDOFF.md` names the next boundary and remaining checks. Completed histories remain in stable plan and verification files linked from [grouped history](docs/history.md). The previous convention set and exact prior root documents are preserved in the maintenance archive; this file replaces older phase-specific rules that conflict with the current module layout and product boundaries.
