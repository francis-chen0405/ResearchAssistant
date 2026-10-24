# Development conventions

The current user request defines scope. Read the current architecture, decisions and [status](STATUS.md) before changes; use [the plan index](../../.agent/PLANS.md) for follow-up owners and any active plan. Completed records and historical phase instructions do not authorize additional work.

## Keep project records small

- Routine changes do not require a new plan, verification report, audit, historical snapshot or history entry. Put routine validation results in the commit or PR description and final response.
- Keep `STATUS.md` as the single plain-language summary of behavior, material limitations, acceptance state and next priorities. Update it only when those facts change; replace stale content instead of appending dated narratives, hashes or test logs.
- When complexity or risk warrants a plan, use one lightweight active plan with the decisions, boundaries and checks needed to do and review that work. Update it instead of creating successive records. The plan index is navigation, not another status page.
- Record durable architectural decisions in the existing decisions document. Create a dedicated report only for a concrete continuing need or an explicit user request. Do not create a report merely because a change is complete.
- Preserve necessary runtime evidence, accounting, provenance, security requirements and incident information. These rules simplify development records; they do not permit deleting research artifacts or weakening verification.
- Preserve active requirements and unresolved findings in current guidance. Retired documents are recoverable through Git; use [history recovery](../history.md#recovering-retired-snapshots). Do not create replacement archives or snapshot current guidance. Retain other completed records until separately reviewed; their dated instructions do not govern new work.

## Contracts and code

- Use Pydantic v2 models with `ConfigDict(extra="forbid")` for internal agent handoffs unless a documented exception applies. JSON belongs at persistence, API, logging, and export boundaries.
- Annotate every named parameter and return on repository-owned Python functions, including tests, nested functions, callbacks, and variadics. Only `self` and `cls` may be unannotated. `tests/test_type_contracts.py` enforces this contract.
- Raise clear errors or return typed failures. Do not silently return `None` on failure.
- Pass dependencies explicitly. Fresh research workers may run independently but never share a SQLite connection, cursor, transaction, or mutable handoff. Deep-analysis waves retain their four-worker cap, budget-safe priority ordering, cancellation draining, and conservative audit behavior.
- Use `researchassistant.*` imports for organized backend modules: contracts under `researchassistant.contracts`, pipeline execution under `researchassistant.research`, evidence under `researchassistant.evidence`, persistence under `researchassistant.storage`, host integration under `researchassistant.platform_support`, runtime entry points under `researchassistant.runtime`, and shared helpers under `researchassistant.common`.
- Preserve public imports, frozen fields, schemas, validators, enum values, and historical meanings during code moves. Installed `models`, `store`, and `orchestrator` facades in `backend/src/` are compatibility aliases for their canonical package modules; the CLI facade is `backend/src/cli.py` after backend installation. `researchassistant.contracts.models` owns shared public contracts, `researchassistant.storage.store` owns typed persistence, and `researchassistant.storage.store_schema` owns schema initialization and migrations.
- Add regressions for validator or integrity defects. Never weaken tests, delete assertions, hide failures, or lower acceptance criteria to make an implementation pass.
- Avoid unrelated edits and dependencies. Explain an authorized dependency change and its validation in the commit or PR description; update an active plan or durable guidance only when the change affects their purpose.

## Persistence, security, and identity

- Snapshots, Ledger rows, and final artifacts are immutable; preserve database immutability and same-run provenance checks.
- History, inspection, and export use validated read-only sessions. They never create or migrate databases. Only intentional writable run/resume follows established migration behavior.
- Costs use finite non-negative `Decimal` values and canonical decimal storage. Unknown physical-call usage retains its reservation; never guess missing precision or issue refunds.
- Desktop data belongs under `researchassistant.platform_support.desktop_paths.application_data_dir()`. Preserve process locks and their ownership. Do not use checkout or bundle paths for runtime data.
- Desktop credentials use macOS Keychain or Windows Credential Manager without plaintext fallback. Secrets must stay out of logs, SQLite, exports, browser storage, and child arguments. OpenAlex and optional PubMed API keys are sent to their respective upstream services in HTTPS query strings. Do not load `.env` files or shell profiles automatically.
- Keep canonical `backend/src/researchassistant/prompts/*.md` resources in place and preserve their bytes unless an authorized plan explicitly changes them; they are executable inputs. Prompts and fonts are backend-owned packaged resources; their historical bytes remain unchanged.
- Source or executable identity changes require a fresh run under the existing exact compatibility gate. The identity surface must include organized package sources as well as the canonical agents, providers, API, installed facades, and prompt sources. Preserve historical inspection/export and reject incompatible resume.
- Executable identity includes backend distribution configuration, sources, installed facades, prompts and font, under their current `backend/` paths. Root transition launchers are outside the installed runtime surface. Keep inactive root copies out of desktop packaging and executable fingerprints.

## Packaging and verification

Run `python scripts/check_repository_boundaries.py` for the fast layout/import guard,
also enforced by CI and `tests/test_repository_boundaries.py`. It checks tracked root ownership and staged additions, respecting pending working-tree removals, and permits no root Python files. The root owner allowlist covers only README and the documented owning folders; `.agents/PLANS/` is a retained historical-path exception. Put implementations
in their owned package; do not expand the allowlist for a convenience copy.

The same check scans every Python file under `backend/src/researchassistant/contracts` and
`backend/src/researchassistant/storage` for static imports, including function-local and
`TYPE_CHECKING` imports and relative forms. Contracts cannot add provider, agent or
research imports; storage cannot add agent or research imports. The legacy
`orchestrator` import and both top-level and `researchassistant.*` namespaces are
covered. Computed/dynamic imports are outside this small AST check; do not use
them to bypass a boundary.

`scripts/dependency-boundary-baseline.json` is empty after all six reviewed exceptions
migrated in [Prompt 12](../verification/contract-ownership-2026-10-10.md). New symbols, importing
the same symbol again, or moving an exception to another file fail. When migrating
an exception, remove its baseline entry in the same change; stale entries fail so
the allowance ratchets down. An intentional new exception requires an explicit
architecture decision and a reviewed source/import/reason entry in that JSON file,
plus the focused guard tests. Do not regenerate the baseline automatically. Storage
still uses two pure provider helpers (URL canonicalization and cached-response parsing);
the guard deliberately permits provider imports in storage. Fresh-process tests block
historical orchestration during history, inspection, CLI inspection and export. A root
entry-point change must separately reconcile the allowlist, build staging, identity,
compatibility tests and documentation.

`backend/pyproject.toml` declares the supported distribution, console command, namespace package discovery and prompt/font data. Keep its runtime dependencies aligned with `backend/requirements.txt`. Install development tools with `pip install -e "./backend[dev]"`; `httpx2` is the Starlette test client and validated versions are pinned in `desktop/constraints.txt`. Streamlit remains a separate legacy dependency in `backend/requirements-legacy.txt`.

Run `python scripts/verify_distribution.py --constraints desktop/constraints.txt` after packaging/resource changes. It builds with an isolated backend, audits exact wheel files/bytes, and tests fresh wheel/editable environments from unrelated working directories. The backend-owned build hook (also exposed at `scripts/build_distribution.py`) preserves exact `backend/pyproject.toml` bytes under `researchassistant/_distribution/` for installed identity; its logical identity name is `backend/pyproject.toml`; installed source names are `backend/src/...`. Keep relative source/resource paths and every executable byte in the fingerprint; frozen identity additionally binds the executable and rejects every missing prompt.

Run workspace commands from the repository root with the installed development environment.
Use [the test map](../../tests/README.md) to discover owner tests, broader integration
coverage and native/browser checks. A focused selection supplements full collection;
historical milestone names do not define the current architecture.

For routine changes, run `python -m pytest -c tests/pyproject.toml tests -m core`
and the concrete tests for every changed owner, including its slow cases. The broader
`-m "not slow"` selection is useful additional feedback; it is not full verification.
The [test map](../../tests/README.md#development-feedback) explains both selections
and their limits. Do not interpret a passing core selection as application acceptance.

Run the complete `python -m pytest tests` locally for changes crossing subsystem
boundaries or affecting evidence integrity, accounting, persistence/schema behavior,
historical compatibility, process lifecycle, packaging, or test selection/configuration.
Use the full suite when the impact is uncertain. CI keeps the complete suite and
coverage runs unfiltered; never make a local selection the default collection policy.

Always run `python -m ruff check --config tests/pyproject.toml .`,
`python -m ruff format --config tests/pyproject.toml --check .`, `git diff --check`,
and `git diff --cached --check`, plus relevant frontend and desktop checks. Preserve
existing skips and report the target platform, artifact, selection and actual result.
A workflow definition or a prior platform build is not evidence for the current
platform/version.

`STATUS.md` owns the current state and next priorities. Retained completed records are discoverable through [grouped history](../history.md); routine changes need no new history entry. Earlier guidance is recoverable through Git. These conventions supersede conflicting recordkeeping instructions in completed plans, old prompts and reports; their dated evidence and substantive requirements retain their meaning.
