# Current decisions

This file records decisions that still govern current behavior. The exact preceding decision history is preserved in the [2026-09-26 archive](docs/archive/2026-09-26-maintenance/DECISIONS.md); older complete records are indexed in [the archive guide](docs/archive/INDEX.md). Completed plan files remain authoritative evidence for their implementation details.

## Research execution

- Fresh website, API, and ordinary CLI requests select the v2 pipeline. Historical provider execution remains available only through the explicit `legacy_runner` dependency. See [explicit pipeline selection](.agent/plans/explicit-pipeline-selection.md).
- Fresh v2 stages import neutral source-evidence and Analyst helpers. Historical agent imports and the historical orchestrator remain supported compatibility surfaces. See [neutral evidence ownership](.agent/plans/neutral-evidence-ownership.md).
- Fresh deep analysis uses deterministic priority waves of at most four sources. Dispatch only a budget-safe priority prefix, do not share SQLite connections or mutable handoffs across workers, and drain in-flight work on cancellation. See [deep-analysis concurrency](.agent/plans/deep-analysis-deterministic-concurrency.md).
- Each of seven active model stages has an explicit selectable route. A selected choice, route settings, price cap, stage allowance, and run configuration participate in frozen identity. Defaults and the historical Standard profile remain distinct. See [per-step model choices](.agent/plans/per-step-model-choices.md) and [model settings](docs/model-settings.md).
- Physical provider attempts reserve their calls, tokens, and conservative cost before transport. Unknown or missing usage does not erase exposure. Historical costs and run identities are not rewritten.

## Evidence, storage, and application boundaries

- Exact quotations, source provenance, separate Evidence Quality and Claim Fit scores, immutable Ledger/output artifacts, and deterministic final validation remain required. Analyzer Admission checks structure and policy; it is not independent proof of entailment.
- The authorized [database integrity plan](.agent/plans/database-integrity-fixes.md) adds schema 14 for nullable cache-token accounting fields; historical schema 7–13 inspection remains supported. History and status inspection use validated read-only access. Each v2 status request owns one validated session; polling does not overlap requests. No WAL or broader persistence redesign is inferred. See [SQLite status polling](.agent/plans/sqlite-status-polling.md).
- Credentials remain in native macOS Keychain or Windows Credential Manager. Secrets are not placed in browser storage, logs, SQLite, exports, or child arguments; the documented OpenAlex upstream HTTPS query-key exception is the only URL exception. Runtime data remains outside the application bundle and checkout.
- Package metadata uses the Python distribution name `researchassistant`, version `0.1.0`; user-facing CLI and application copy use `ResearchAssistant`. Streamlit remains outside the base install and is installed only through `requirements-legacy.txt`. The `dev` dependency set includes `httpx2` for Starlette tests; versions are constrained in `desktop/constraints.txt`.

## Release boundary

macOS remains the first release target and Windows release work is deferred. The five-submission paid acceptance allowance is exhausted; further live research requires new explicit authorization. The unsigned Mac candidate has not cleared live-quality acceptance, clean-machine installation, minimum-OS, signing, or notarization gates. The earlier Phase 2 Windows matrix does not verify the current version. See [desktop operations](desktop/README.md) and the current [status](STATUS.md).

The current authorized work is [database integrity fixes](.agent/plans/database-integrity-fixes.md). It does not renew paid-test allowance or change research policy, persisted historical data, or the release boundary.
