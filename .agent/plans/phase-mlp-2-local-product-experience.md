# MLP-2 — Local Product Experience

Status: Complete and verified on 2026-08-14.

## Authority and boundary

The user explicitly authorized MLP-2 on 2026-08-14 after committing completed MLP-1.
MLP-2 redesigns the local live website using the supplied Quin reference for overall
spacing, simplicity, typography, soft borders, and restrained color—not as a literal
copy.

MLP-2 does not add user accounts, email login, hosting, cloud storage, a new provider,
or a second research pipeline. The top-level setup action is local provider setup rather
than account signup.

## Product experience

- Replace the dense administrative first screen with a clean navigation bar, centered
  research hero, concise claim input, and one primary Start Research action.
- Provide top-level History, Provider setup, and Advanced mode actions.
- Move budgets, database path, run ID, local-service controls, provider status, and
  diagnostics into a secondary Advanced side panel.
- Preserve persisted history, live progress, cancellation, released brief display, and
  every MVP-11 evidence/release invariant.

## Credential contract

- Provider setup accepts MiMo, Exa, and optional Firecrawl API keys on the loopback-only
  page and immediately saves them to the user's macOS login Keychain.
- Password widgets are transient and clear on submit. Keys never enter URLs, SQLite,
  logs, downloads, provider child-process arguments, or repository files.
- The Keychain password is supplied to `/usr/bin/security` through standard input, never
  as a command-line argument.
- The launcher no longer blocks on native key dialogs. The application loads saved
  credentials from Keychain and falls back to the local setup panel when required keys
  are absent.
- No `.env` loading, email/password identity, shared account, or cloud sync is added.

## Compatibility

- Website-created runs keep `DEFAULT_RESEARCH_CONTROLS` from MLP-1.
- Existing databases, run fingerprints, CLI configuration, historical controls,
  read-only inspection, budgets, and resume requirements remain intact.
- No dependency or SQLite migration is added.

## Verification

- Add regression-first tests for strict secret-safe credentials, Keychain command
  construction, launcher behavior, clean primary layout, Provider setup, Advanced mode,
  existing live states, and secret redaction.
- Run focused tests, complete `pytest`, `ruff check .`, `ruff format --check .`, launcher
  syntax, and `git diff --check`.
- Inspect the rendered desktop and narrow layouts in the local browser.
