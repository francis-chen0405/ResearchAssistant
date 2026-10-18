# ResearchAssistant

ResearchAssistant is a local desktop application for source-backed research on a claim.
Choose Support, Challenge, or both. It discovers sources, preserves exact evidence and
provenance, investigates gaps within budget, and releases deterministically validated
results. Historical runs remain readable and exportable. There is no hosted backend.

[Current status](docs/project/STATUS.md) owns verified source and installed-build facts.
This folder migration requires a fresh research run under the existing compatibility
gate. Replacing the installed native app or publishing a release is a separate action.

## Install and develop

The desktop application bundles its runtimes. Python developers can install the backend
and run the console command from any working directory:

```sh
python -m pip install ./backend
researchassistant --help
```

For a checkout, use Python 3.12, Node 24.18.0 and the committed locks:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -c desktop/constraints.txt -e "./backend[dev]" -r desktop/requirements-build.txt
pnpm --dir frontend install --frozen-lockfile
npm ci --prefix desktop
.venv/bin/python -m researchassistant.api.api
# In another terminal:
pnpm --dir frontend dev
```

On Windows, use `.venv\Scripts\python.exe` for the Python launcher.
The console command, `python -m cli` and root `python cli.py` remain supported after
installation. Historical `models`, `store`, `orchestrator`, `agents`, `providers` and
Python `frontend` imports are installed facades; new code uses `researchassistant.*`.
The Next.js folder and historical Python namespace coexist through the installed backend.
Optional Streamlit fixture UI dependencies are in `backend/requirements-legacy.txt`.
Credentials come from native desktop settings or the CLI process environment; `.env`
files and shell profiles are never loaded automatically.

## Folder owners

| Folder | Responsibility |
| --- | --- |
| `backend/` | Installable Python distribution, runtime, API, agents, providers and packaged resources |
| `frontend/` | Next.js renderer |
| `desktop/` | Electron shell, acquisition runtime and native packaging |
| `tests/`, `evaluations/` | Regressions and offline research/integrity benchmarks |
| `docs/project/` | Current architecture, conventions, decisions, status and handoff |
| `docs/verification/`, `docs/archive/` | Verification evidence and preserved historical snapshots |
| `scripts/`, `.github/` | Workspace tooling and CI |
| `.agent/` | Plan index and retained plans |

Root `pyproject.toml` configures workspace tests/lint; `backend/pyproject.toml` owns
package discovery, runtime dependencies, data manifests and the console command.
`cli.py` and `Launch ResearchAssistant.command` are explicit transition launchers.
The historical `.agents/PLANS/` record retains its stable path.

## Verify and package

```sh
.venv/bin/python scripts/check_repository_boundaries.py
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
git diff --check
pnpm --dir frontend lint
pnpm --dir frontend exec tsc --noEmit
.venv/bin/python scripts/verify_distribution.py --constraints desktop/constraints.txt
```

Build a wheel with `python -m pip wheel --no-deps --wheel-dir /path/to/dist ./backend`.
The verifier audits exact installed files and bytes and exercises wheel/editable CLI,
API, fake-provider fixtures, prompts, font, identity and Unicode PDF output outside
the checkout. All 18 prompt bytes and font bytes retain their historical meaning.
Tests and offline evaluations need no paid provider calls.

See [desktop operations](desktop/README.md) for static export, native builds/smokes and
installers, [database recovery](docs/project/database-recovery.md) for read-only history,
backups and restore, and [backend/API notes](backend/src/researchassistant/api/README.md)
for browser development.

## Project guidance

[Architecture](docs/project/ARCHITECTURE.md), [conventions](docs/project/CONVENTIONS.md),
[decisions](docs/project/DECISIONS.md), [plan index](.agent/PLANS.md),
[status](docs/project/STATUS.md), [handoff](docs/project/HANDOFF.md),
[grouped history](docs/history.md) and [archive index](docs/archive/INDEX.md).
