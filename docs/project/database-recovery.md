## Database recovery

Use the installed backend from any working directory. For checkout setup, see
[the root guide](../../README.md#install-and-develop); run workspace commands from the repository root.

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

Add `--destination-dir /path/to/imports` to choose another destination directory. The desktop's Advanced settings import action selects the usable imported copy automatically; to use a restored path, enter it in the database path field. Imports accept read-only compatible schemas 7–18; older recognized writable schemas can be recovered and upgraded through an intentional run/resume. Fresh CLI runs create missing selected parent directories without changing existing directory permissions. Desktop paths require an existing writable parent folder; create the folder first. Invalid desktop paths are rejected before a worker starts.

Keep the `.verified.json` file beside each backup: listing and restore require it and recheck integrity, schema, foreign keys and contents. A failed upgrade retains its verified copy. Orphan `.pending-*` files and copies without valid verification records are ignored and never pruned as valid backups. Retention runs only after a successful upgrade and keeps at least one verified backup; it does not run during inspection or current-schema opens. Copies being restored are retained until a later cleanup. POSIX copies are mode `0600` and app-owned folders `0700`; caller-selected folders retain their modes. Windows applies a protected owner/SYSTEM ACL. Publication requires filesystem hard-link support (NTFS on Windows); unsupported publication or privacy setup fails before migration. Windows private-directory leaves reject junctions/reparse points before applying ACLs.

[Prompt 17 native evidence](../verification/windows-ci-durability-2026-10-13.md)
records actual Windows Server 2025/NTFS protected ACL/access-denial, link collision,
Unicode/long-path, verified-restore and killed-upgrade checks. Timing hooks stop
generated-data processes after real flush/link/SQLite operations; DELETE/WAL
writer recovery preserves unknown reservations. Process termination leaves the OS
and controller cache alive. Physical power-loss durability, including Windows
directory-entry flush ordering, remains unverified. The record provides the exact
repeatable fault points and external reset/power-cut follow-up. Windows client
release acceptance and public release remain deferred; Mac results do not verify Windows.

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`. See the [desktop build guide](../../desktop/README.md) for static export, backend builds, native smokes, and installers. A successful macOS build does not verify Windows. Tests do not require paid provider calls; opt-in integration checks remain opt-in.

For browser development, run `.venv/bin/python -m researchassistant.api.api` and `pnpm --dir frontend dev` in separate terminals. See [frontend notes](../../backend/src/researchassistant/api/README.md). The CLI retains fixture, inspection, export, and live entry points. Desktop credentials use native settings; CLI credentials come from the process environment. Never put secrets in source files or rely on automatic `.env` or shell-profile loading.

