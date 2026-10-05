# Database phase 4 supplemental review

Reviewed 2026-10-04 against the current source, phase 1–3 implementation records, and the 2026-10-03 audit/reproduction evidence. This is a focused cross-phase source review and auxiliary-cache check; it is not a new full-suite or installed-app verification.

## Cross-phase source review

No new actionable defect was found in the reviewed F1–F9, I2–I3, X1, or legacy-lock paths. The phase fixes line up with their original reproductions and regression coverage:

| Scope | Current source review | Existing focused coverage |
| --- | --- | --- |
| F1–F5 | Historical row decoding retains record-level compatibility handling; attempt usage fields persist and replay; reservation identity and terminal completion are checked under a write transaction; writable initialization validates the recorded schema before upgrades; ownership updates and referenced-key changes are guarded. | `test_database_read_paths_phase3.py`, `test_database_attempt_integrity_phase2.py`, `test_database_cache_accounting.py`, `test_database_schema_integrity.py`, `test_database_schema_provenance_phase2.py` |
| F6–F7 | Path readers use a read-only URI boundary and retain borrowed connections; CLI-selected parents are prepared before lock acquisition. | `test_database_read_paths_phase3.py`, `test_database_attempt_caller_phase2.py`, `test_database_lifecycle_locks.py` |
| F8–F9 | V2 progress counts persisted provider attempts by resolved cluster direction, with ambiguous attribution kept unassigned; approval filters require an explicit Analyst or Reviewer outcome. | `test_database_read_paths_phase3.py`, `test_mvp10_evidence_portfolio.py` |
| I2–I3 and legacy lock | Default recovery copies use private app-owned folders, a verified SQLite backup under the shared lock, bounded retention, and non-overwriting restore to a new path. The supported legacy provider runner and desktop/CLI callers share retained database-lock ownership without nested acquisition. | `test_database_recovery.py`, `test_database_recovery_cli.py`, `test_database_lifecycle_locks.py`, `test_database_attempt_caller_phase2.py` |
| X1 | Exports preserve the released-output hash/identity; PDF output wraps and paginates with the bundled Unicode font and gives a typed error for unsupported shaping/code points. Formatting runs after the read snapshot closes. | `test_database_read_paths_phase3.py` and export coverage in `test_mvp8_2_evidence_browser.py` |

The advisory graph exposed older root-level module names and is not treated as current-source evidence. The graph tool surface available for this review did not include `index_status`; no index refresh was attempted. The source and phase tests above are the basis for the findings.

## Wigolo cache and runtime

The desktop source stages standalone Node 24.18.0 and the locked `wigolo@0.2.1` package, including `better-sqlite3` and `sqlite-vec` 0.1.9. The frozen backend launches that exact Node executable with the staged Wigolo entry point. Wigolo initializes `<application-data>/acquisition/wigolo.db`, loads the bundled vector extension, enables WAL, applies its nine migrations, and closes its connection during shutdown. This cache is external to ResearchAssistant's schema/migration and recovery system; its normal startup is a writable cache initialization, not a ResearchAssistant read-only inspection.

The isolated repository build cache at `desktop/build/mac-cache-live-acceptance/data/acquisition/wigolo.db` was checked using the bundled Node runtime and exact packaged `sqlite-vec` extension. The source was opened read-only and copied with the SQLite backup API to a disposable temporary database; all deeper checks ran on the temporary copy, which was removed afterward. The source WAL and SHM sidecars were present, and no process had those files open. Results:

- SQLite `integrity_check`: `ok`; `foreign_key_check`: zero violations; journal mode: `wal`.
- Migrations `001-sqlite-vec` through `009-content-completeness` are recorded.
- `url_cache`: 39 rows; `search_cache`: 0 rows.
- `vec_documents`, `vec_id_map`, and `vec_metadata`: 39 rows each; no missing or orphaned vector/map/metadata references.
- FTS external-content integrity checks passed for `url_cache_fts` and `feed_items_fts` on the disposable backup.
- `vec_documents` was readable with the exact native extension; all 39 vector row identifiers matched their map and metadata rows.

The installed application Wigolo cache is still unverified. Earlier evidence records `unable to open database file` for that path under the available inspection context. This review did not access installed app data, alter its cache, stop a service, or infer its health from the repository build cache. Completing that check requires a supported read-only open of the installed cache with the packaged runtime and extension, or a SQLite backup through the running Wigolo service followed by the same offline checks. If neither route is available without changing user app data, the exact limit remains unresolved.

Windows ACL and native cache behavior remain unverified on Windows. The existing POSIX verification does not establish that platform gate.

## Final-source offline packaging check

Repeated after the final executable-source edits for browser snapshot deduplication, Reviewer tie ordering, migration-17 draft lookup indexing, V2 controller error projection, inspection path validation, and historical Ledger snapshot unioning. The checkout source identity before and after this build, and at the final post-build check, was identical:

```text
source-sha256:726abcf75fcf4b212c27cb8a9f9e6272d8a4d41d402eb73ecc02d50ad06be45f
```

An isolated macOS arm64 backend-only PyInstaller build succeeded from the current checkout into `/private/tmp/ra-phase4-frontend.A78cKD/packaging/resources/backend`. The packaged identity surface exactly matched the checkout identity above. Direct byte comparisons passed for `sqlite_policy.py`, `store_schema.py`, `evidence_browser.py`, `pdf_render.py`, `application_runtime.py`, and `unifont-15.0.01.ttf`.

A separate frozen offline verifier, rebuilt with the same repository data inputs, ran without starting the application, opening the vault, starting Wigolo, or making provider calls. Its frozen identity was `source-sha256:137a99f4213608c63005296d4a9fe187b1619ba8feb90c22d131d231cae6b3a8` (the identity includes that verifier executable's own bytes). It rendered 90 Unicode lines with the embedded font to a two-page PDF, initialized a disposable database at schema 17, and opened it with full read-only compatibility validation:

```text
PASS identity=source-sha256:137a99f4213608c63005296d4a9fe187b1619ba8feb90c22d131d231cae6b3a8; font=embedded; pdf_pages=2; schema=17; db=isolated
```

Build and run records are kept in the temporary verification directory, not the repository:

| Artifact | SHA-256 |
| --- | --- |
| Packaged backend executable | `864adfeb68cdbbba16f1b38fd2b57bbb67a04015c3fbe47a6d18de51f4df7fbd` |
| Bundled Unicode font | `299459bc34e915b1c18dd38677739f41d0b2a6d79b93f480cd157ef24da675ab` |
| Packaged `sqlite_policy.py` | `9106fb534705390ed21de78bbbdd73e8732a1172c504a8203251651d0b6b21a0` |
| Packaged `store_schema.py` | `1d2e7382c6ebd4bd24643f5d99bce8581e555a9d61684c03df0eb40a8011809f` |
| Packaged `evidence_browser.py` | `236d369c61c6bd429caea66fdd3d53aea8f1a0f4f463f92ad55cefb3b2a58916` |
| Backend build log | `0710b5ad0e4a9645b2098cf7f3f26c227658b36b0a3fd7d3220a8cd83747fa96` |
| Offline verifier executable | `48e515126e38d4a76885a9893705d510696a0a8b384c05ca2cbd0e6c3d6d80bd` |
| Offline verifier build log | `d43272220f3a9c04bc97549d2674668d544cadd2cd33c37e0376c9aed836ad59` |
| Offline verifier run log | `40e24ffe3515e925e72e7904e4743365750ebcd509dd47c50e6e2aa91b8e5edd` |

The corresponding paths are under `/private/tmp/ra-phase4-frontend.A78cKD/packaging/`. The isolated backend build does not verify application launch, native credentials, installed-app replacement, or target-platform release behavior.

## Conditional-commit corrected-source packaging check

The preceding “Final-source offline packaging check” preserves the original
phase-four implementation evidence. It predates the conditional review fix for
Python 3.12 connections opened with `autocommit=True`; do not use its identity
or artifact hash as evidence for that fix. The isolated packaging and verifier
below were rebuilt from the frozen post-fix checkout.

- **Source and platform:** local macOS 26.6.2 arm64, Python 3.12.14 and
  PyInstaller 6.22.2. The current checkout identity is
  `source-sha256:489f3b513aa3ecd68546d76a7579cff4d6dc4724ad0bfc9a6fe7d2095e51c7b3`.
- **Build boundary:** a backend-only PyInstaller build and a separate frozen
  offline verifier were built into
  `/private/tmp/ra-phase4-final-packaging.VdZiKH`. PyInstaller's config/cache
  directory was redirected into that same temporary workspace. The verifier
  used only a `TemporaryDirectory` database; neither build launched the
  application or Wigolo, opened credentials, accessed the installed cache, or
  contacted a research provider.
- **Packaged-source comparison:** direct byte comparisons against the checkout
  passed for `researchassistant/storage/store.py`,
  `researchassistant/storage/store_schema.py`,
  `researchassistant/storage/sqlite_policy.py`,
  `researchassistant/runtime/application_runtime.py`,
  `researchassistant/evidence/pdf_render.py`, and
  `researchassistant/evidence/fonts/unifont-15.0.01.ttf`. The patched
  `store.py` SHA-256 is
  `f21a567579d4b94f6e0e5e2a8491af04353652f26fe21c07a6ff3d3639a440d5`;
  the packaged font SHA-256 is
  `299459bc34e915b1c18dd38677739f41d0b2a6d79b93f480cd157ef24da675ab`.
- **Frozen verifier:** exited 0 with
  `PASS identity=source-sha256:93820a807b7f488aaab26a73b953a287a650a5084250bd14af90a42a64831fa1; font=embedded; pdf_pages=2; schema=17; db=isolated`.
  As in the earlier record, frozen identity includes the verifier executable's
  bytes and is distinct from the checkout source identity.
- **Artifact hashes:** packaged backend executable
  `c8f7349775739a19911e07812a1e01f7e06ea1dd833f8ed02767314b7c805a13`;
  offline verifier executable
  `e011f342dc4d0e4b477dd8bd3bf678221a0efae44b11470e7e1a05c1ed1839f8`;
  backend build log
  `5870e7335f5b393e1d33f777054165e2b1a0cb5c31db93e14a78ec4cc6a1b65c`;
  verifier build log
  `8ed7f9139925898448e2607aa72de653f1847e1472e9b875f5adc7d41709ff51`;
  verifier run log
  `50d06a27ba764923b5d7b3d19e29774e52ee09e246deded2ec15a765c7523c4f`.

This verifies packaged inclusion and offline behavior for the patched source on
this macOS build host only. It does not change the installed-app, native
Windows, credential-backed launch, minimum-OS, or release-platform limits above.
