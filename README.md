# ResearchAssistant

ResearchAssistant is a local desktop application for source-backed research on a claim. Choose Support, Challenge, or both. The local Python backend discovers sources, preserves exact evidence and provenance, investigates gaps within budget, and releases only deterministically validated results. Historical runs remain readable and exportable. There is no hosted application backend.

## Install and run

The desktop application bundles its runtime; end users do not install Python, Node, or Docker. The latest public Apple Silicon DMG/ZIP is the [September 28 unsigned test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928), built from `ac49404`. It does **not** include the October fixes in current source or the locally installed app, so do not treat it as current. It is unsigned and unnotarized; macOS may block its first launch. Clean-machine/macOS 14 checks and Developer ID signing/notarization remain open. Current delivery facts and the Windows deferral are in [STATUS](STATUS.md) and [desktop operations](desktop/README.md).

## Develop and verify

Use Python 3.12, Node 24.18.0, and the committed locks. From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -c desktop/constraints.txt -r requirements.txt -r desktop/requirements-build.txt httpx2 pytest pytest-cov ruff
pnpm --dir web install --frozen-lockfile
npm ci --prefix desktop
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
git diff --check
pnpm --dir web lint
pnpm --dir web exec tsc --noEmit
```

The constraints file pins the validated environment. `httpx2`, pytest, pytest-cov, and Ruff are explicit development/test packages in the install command because setuptools editable installation is not supported by the repository's package layout. For a base Python install, use `python -m pip install -c desktop/constraints.txt -r requirements.txt`. The legacy Streamlit frontend is intentionally separate from the base install: `python -m pip install -c desktop/constraints.txt -r requirements-legacy.txt`. Its constrained no-index dry run has been verified.

The canonical CLI module is `researchassistant.runtime.cli`; run `python -m researchassistant.runtime.cli --help` from the repository root. Root `cli.py` remains available as the existing script launcher, and `models.py`, `store.py`, and `orchestrator.py` remain compatibility imports. New backend imports should use the `researchassistant.*` package paths documented in [architecture](ARCHITECTURE.md).

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`. See the [desktop build guide](desktop/README.md) for static export, backend builds, native smokes, and installers. A successful macOS build does not verify Windows. Tests do not require paid provider calls; opt-in integration checks remain opt-in.

For browser development, run `.venv/bin/python -m frontend.api` and `pnpm --dir web dev` in separate terminals. See [frontend notes](frontend/README.md). The CLI retains fixture, inspection, export, and live entry points. Desktop credentials use native settings; CLI credentials come from the process environment. Never put secrets in source files or rely on automatic `.env` or shell-profile loading.

## Project guidance

- [Architecture](ARCHITECTURE.md): runtime, module ownership, and research flow. [Research invariants](docs/research-invariants.md) records the detailed current evidence and storage rules.
- [Conventions](CONVENTIONS.md), [decisions](DECISIONS.md), and [plans](.agent/PLANS.md): development rules and current scope.
- [Status](STATUS.md) and [handoff](HANDOFF.md): verified state, open checks, and next boundary.
- [Grouped plan and verification history](docs/history.md): links to every retained plan and verification record.
- [Archive index](docs/archive/INDEX.md): exact prior snapshots and archived documents.

The long historical README was archived verbatim on 2026-09-26. This replacement puts current installation, development, and release guidance first.
