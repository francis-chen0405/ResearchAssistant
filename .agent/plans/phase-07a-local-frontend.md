# Phase 07A - Extremely Basic Local Frontend

## Purpose

Add a very small local Streamlit frontend around the existing Phase 6 fixture-only
pipeline. Phase 7A is limited to fixture selection, local pipeline execution, and
readable display of released or blocked results.

## Files Changed

- `frontend/streamlit_app.py`
- `frontend/README.md`
- `tests/test_phase7_frontend.py`
- `tests/test_phase0_foundation.py`
- `pyproject.toml`
- `.agent/plans/phase-07a-local-frontend.md`
- `.agent/PLANS.md`
- `README.md`
- `AGENTS.md`
- `STATUS.md`
- `HANDOFF.md`

## Implementation Design

- The frontend calls `run_fixture_pipeline()` directly and does not change Phase 6
  orchestration behavior.
- Testable frontend helper logic lives in pure Python functions:
  `discover_fixture_runs()`, `run_fixture_for_frontend()`, and
  `summarize_fixture_result()`.
- UI-facing summaries are strict Pydantic models so tests can assert structured display
  data without launching Streamlit or a browser.
- The Streamlit import is isolated to runtime UI loading so helper tests do not require
  browser execution.
- The UI displays run status, rendered brief text for released runs, block reason,
  validation errors, rendered hash when available, validation artifact hash, output
  paths, artifact counts, and audit trail metadata.

## Dependency Change

- Added `streamlit>=1.37,<2.0` because Phase 7A explicitly requires a local Streamlit
  frontend.
- No SDK, LLM, search, scraping, HTTP client, ORM, authentication, upload, database, or
  React dependency was added.

## Explicitly Out of Scope

- Core Phase 6 behavior changes
- Rewriting `orchestrator.py` or `cli.py`
- Live LLM calls
- Web research, retrieval, or scraping
- React, FastAPI, authentication, uploads, user accounts, dashboards, or database changes
- Phase 7B, Phase 8, or provider-backed behavior

## Acceptance Criteria

- Fixture discovery finds the expected fixture run directories.
- The frontend wrapper can run the valid fixture and expose released status plus final
  brief text.
- The frontend wrapper can run the invalid fixture and expose blocked status plus
  validation errors.
- Helper output is structured and displayable without launching a browser.
- Full pytest and Ruff verification pass before Phase 7A is marked complete.

## Commands Run

```bash
PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase7_frontend.py -q
```

Result: passed with 4 passed in 0.23s.

```bash
PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/test_phase0_foundation.py tests/test_phase7_frontend.py -q
```

Result: passed with 6 passed in 0.19s.

```bash
PATH="$PWD/.venv/bin:$PATH" python -m pytest
```

Result: passed with 188 passed in 1.73s.

```bash
PATH="$PWD/.venv/bin:$PATH" python -m ruff check .
PATH="$PWD/.venv/bin:$PATH" python -m ruff format --check .
```

Result: Ruff check passed; Ruff format check passed with 22 files already formatted.

```bash
PATH="$PWD/.venv/bin:$PATH" python -m pip install "streamlit>=1.37,<2.0"
```

Result: passed; Streamlit 1.59.1 was already installed in the repository virtual
environment.

```bash
streamlit run frontend/streamlit_app.py --server.headless true --server.address 127.0.0.1 --server.port 8501
```

Result: failed inside the sandbox with `PermissionError: [Errno 1] Operation not
permitted` while binding localhost. The approved local rerun with `.venv/bin/streamlit`
started successfully at `http://127.0.0.1:8501`.

```bash
curl -I --max-time 5 http://127.0.0.1:8501
```

Result: passed after approval with `HTTP/1.1 200 OK`.

## Exact Test Results

- Phase 7A focused tests: 4 passed.
- Phase 0 plus Phase 7A targeted tests: 6 passed.
- Full pytest suite: 188 passed.
- Ruff check: all checks passed.
- Ruff format check: 22 files already formatted.

## Unresolved Risks

- The UI is intentionally plain and local-only.
- No browser UI tests were added by design; helper logic is covered instead.
- Phase 7A remains fixture-only and does not prove live retrieval, scraping, provider, or
  semantic generation behavior.

## Next Phase Confirmation

Phase 7B search and scraping provider interfaces were not started.
