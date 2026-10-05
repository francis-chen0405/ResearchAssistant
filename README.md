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

## Database recovery

Writable database upgrades retain verified SQLite backups beside the database, in `<database-name>.backups/` under the database's parent directory. The default is three backups. Set `RESEARCHASSISTANT_BACKUP_COUNT` to a positive integer to change the retention count. Backups are created for writable schema upgrades; history inspection and export remain read-only.

List available verified backups with:

```sh
python -m researchassistant.runtime.cli list-backups --db-path /path/to/live-runs.sqlite3
```

Restore a selected backup to a new file path. The restore command will not replace an existing database:

```sh
python -m researchassistant.runtime.cli restore-backup \
  --backup-path /path/to/live-runs.sqlite3.backups/backup.sqlite3 \
  --output-path /path/to/restored-live-runs.sqlite3
```

Use the restored file with `run --db-path ... --run-id ...` to resume a run. Resume still requires the exact persisted claim and pipeline/provider fingerprint; a restored backup does not relax those checks. Import an existing database into app storage with:

```sh
python -m researchassistant.runtime.cli import-history --source-path /path/to/older.sqlite3
```

Add `--destination-dir /path/to/imports` to choose another destination directory. The desktop's Advanced settings import action selects the usable imported copy automatically; to use a restored path, enter it in the database path field. Imports accept read-only compatible schemas 7–17; older recognized writable schemas can be recovered and upgraded through an intentional run/resume. Fresh CLI runs create missing selected parent directories without changing existing directory permissions. Desktop paths require an existing writable parent folder; create the folder first. Invalid desktop paths are rejected before a worker starts.

Keep the `.verified.json` file beside each backup: listing and restore require it and recheck integrity, schema, foreign keys and contents. A failed upgrade retains its verified copy. Orphan `.pending-*` files and copies without valid verification records are ignored and never pruned as valid backups. Retention runs only after a successful upgrade and keeps at least one verified backup; it does not run during inspection or current-schema opens. Copies being restored are retained until a later cleanup. POSIX copies are mode `0600` and app-owned folders `0700`; caller-selected folders retain their modes. Windows applies a protected owner/SYSTEM ACL. Publication requires filesystem hard-link support (NTFS on Windows); native Windows ACL and power-loss durability verification remain release gates. Unsupported publication or privacy setup fails before migration.

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`. See the [desktop build guide](desktop/README.md) for static export, backend builds, native smokes, and installers. A successful macOS build does not verify Windows. Tests do not require paid provider calls; opt-in integration checks remain opt-in.

For browser development, run `.venv/bin/python -m frontend.api` and `pnpm --dir web dev` in separate terminals. See [frontend notes](frontend/README.md). The CLI retains fixture, inspection, export, and live entry points. Desktop credentials use native settings; CLI credentials come from the process environment. Never put secrets in source files or rely on automatic `.env` or shell-profile loading.

## Project guidance

- [Architecture](ARCHITECTURE.md): runtime, module ownership, and research flow. [Research invariants](docs/research-invariants.md) records the detailed current evidence and storage rules.
- [Conventions](CONVENTIONS.md), [decisions](DECISIONS.md), and [plans](.agent/PLANS.md): development rules and current scope.
- [Status](STATUS.md) and [handoff](HANDOFF.md): verified state, open checks, and next boundary.
- [Grouped plan and verification history](docs/history.md): links to every retained plan and verification record.
- [Archive index](docs/archive/INDEX.md): exact prior snapshots and archived documents.

The long historical README was archived verbatim on 2026-09-26. This replacement puts current installation, development, and release guidance first.
