# Prompt 17 — Windows CI and native durability

Investigation started October 13 and continued October 14, 2026. Windows public
release remains **deferred**. CI artifacts are unsigned test artifacts; uploading
source and running Actions does not authorize publishing or replacing an installed app.

## Source and evidence provenance

The user's working checkout stays on dirty `master`, HEAD
`94a241b52f9525cab3aff52d1f85026f081b3e85`; remote `master` was independently checked at
`27aeb95ca0b6c6999ba34b2cfd60c5b84a49200c`. The user explicitly approved uploading the
reviewed 1,001-file source snapshot and running Windows CI on
`codex/windows-ci-durability-20261013`. An independent disposable clone owns these
verification commits. The parent checkout's index, installed Mac app, real history,
cache and native credential entries are preserved. Runtime data, credentials, local
environment files and build outputs are excluded from the source archive.

The initial archive SHA-256 is
`147831dbb0d3141e782442f26bdd73ebcf3bee29c9fad2db00f5199955234c03`.
Its manifest, successor manifests and raw API/job logs are retained locally under
`desktop/build/prompt17-evidence/`. The baseline commit has local HEAD as its parent;
it is a snapshot of the dirty current source, not a claim that committed `master`
already contained that source. Current tested code target:
`44f83d9bfb7e8e2896dc44390c366e4d498be044`. Its 1,012-file archive is SHA-256
`fd9abb267fc7df139e922d4d2c83fc679aab0b8267576d667238b5afb900404f`;
manifest SHA-256 is
`9bd1f0f42ee0941e5b14ed064cb08e8061ae1d7df916b470918adc93da24b975`.
The snapshot's runtime/test/workflow bytes match the Git target; the local review
fixes below are a subsequent change without a new Windows run. Git normalizes line endings
in the historical `docs/audits/2026-10-01/coverage.csv`; it is the only snapshot/Git
payload byte difference and is outside executable identity. Final guidance is a
companion to the tested snapshot. The [machine-readable supplement](windows-ci-durability-2026-10-13.json)
binds completed runs, reports and installer hashes.

The graph was checked and refreshed without persistence. It is an advisory map;
the private-file helper, recovery publication/flush calls, Windows Job ownership,
credential functions and deep-analysis call site were verified in live source.

## Historical failures and current reproductions

| Revision / Windows run | Verified result |
| --- | --- |
| `4a1d1cc`, [job 111064698744](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/37075607007/job/111064698744) | 2 failed / 1,341 passed / 5 skipped, 1,005.26 s. The retained log establishes missing `signal.SIGKILL` in a POSIX-mocked test and a 30-second mocked CLI timeout. The timeout's underlying cause is not established by that log. These historical failures do not establish persistence in current source. |
| Remote `27aeb95`, [run 37890664962](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/37890664962) | 5 failed / 2,218 passed / 12 skipped, 1,290.72 s: illegal `?` filename, implicit source codec, POSIX signal mock, unlinking an open Windows CRT file, cancellation entry wait. Mac sibling success is separate evidence. |
| Current-source baseline `7a76ce2`, [run 38503112723](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38503112723) | 14 failed / 2,783 passed / 15 skipped, 2,734.61 s. In addition to portable fixture defects: API fixture backslash normalization, export privacy, executable archive mode, seven 30-second CLI timeouts and one source-lead expectation failure. |
| `0ca1101`, [run 38503902214](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38503902214) | Focused native reproduction: 3 failed / 3 passed, 23.69 s. Illegal filename, missing POSIX signal and open-file unlink reproduced. |
| `f258b10`, [run 38506258392](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38506258392) | Focused original regressions: 6 passed. New storage/process/security selection: 1 failed / 16 passed. A real NTFS junction was incorrectly accepted as a private directory, following its target ACL. |
| `dbae451`, [run 38506712104](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38506712104) | 17 storage/process/security selection / 6 focused passed. Full Windows: 3 failed / 2,806 passed / 15 skipped, 1,669.55 s; API normalization, export ACL and source archive mode remained. The earlier CLI timeouts and source-lead test passed unchanged. |
| `ce846d8`, [run 38509359051](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38509359051) | 18 storage/process/security selection / 10 focused passed. Full Windows: 1 failed / 2,809 passed / 15 skipped, 1,603.16 s; cancellation fixture waited five seconds for the entire four-round prefix. Mac matrix succeeded. Windows packaging was not reached. |
| `987c5aa`, [run 38648050855](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38648050855) | 18 storage/process/security checks and ten focused regressions passed. Full Mac desktop/installer job passed. Full Windows: 1 failed / 2,809 passed / 15 skipped, 1,958.40 s; matching-resume fixture timed the entire research pipeline within ten seconds. Cancellation-entry fix passed. |
| `e6ed4fa`, [desktop run 38648848338](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38648848338), [automatic CI 38648822561](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38648822561) | 18 storage/process/security checks passed in 15.99 s; ten focused regressions passed in 44.68 s. Automatic Python 3.11/3.12, Ruff, frontend and offline evaluations pass. Mac desktop/packaging passes. Full Windows: 2 failed / 2,808 passed / 15 skipped, 2,379.82 s: the original 30-second mocked CLI deadline and a missing expected URL-5 source admission. Both passed focused runs; their intermittent root causes remain unestablished. |
| `44f83d9`, [target desktop run 38652359869](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38652359869), [automatic CI 38652325933](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38652325933) | 18 storage/process/security checks passed in 8.45 s; 11 focused regressions passed in 32.68 s. All five automatic CI jobs and Mac desktop/packaging pass. Windows build/cache/browser/frozen-vault/window/forced-Electron and unsigned NSIS build pass. Installed smoke fails: attempt 1 timed out installing the historical comparison build; diagnostic attempt 2 installed it, reached the interruption checkpoint, then timed out repairing with the candidate (240 seconds each). Full Windows: 2,810 passed / 15 existing skips, 1,880.66 s; Windows Ruff/format, frontend lint/types, distribution and 20 shutdown unit checks pass. Both packaging attempts failed; the full Windows quality job passed. |

Superseded redundant full matrix jobs were cancelled after their independent
reproduction evidence was retained. Cancellation is never reported as a pass.

## Corrections and unchanged acceptance

- `private_directory` rejects Windows directory reparse points before applying
  owner/SYSTEM privacy. Actual junction creation, refusal and unchanged target ACL
  are native regressions. POSIX directory behavior remains unchanged.
- Saved-research export now uses the shared protected private directory/file
  constructors. POSIX `mode=` alone did not establish Windows privacy. Native
  assertions inspect protected owner/SYSTEM ACLs on the export directory and every
  exported file; the existing POSIX mode and byte/provenance assertions remain.
- Source archives use Git's executable index metadata on Windows, whose file stat
  lacks the POSIX executable bit. The exact executable-mode assertion remains;
  fixtures explicitly record that bit in their disposable repository.
- Portable test fixtures use a legal Windows question-mark character while keeping
  the POSIX `?` case, read UTF-8 source explicitly, supply the mocked POSIX signal,
  and model inode replacement without unlinking an open CRT file. API JSON fixture
  normalization handles escaped Windows paths while preserving exact response equality.
- Cancellation setup now signals the actual deep-analysis boundary before the
  original five-second entry guard. Release/drain cleanup always runs, thread
  exceptions surface, and the ten-second drain, four-worker bound, absent aggregate
  and conservative physical-call audit assertions remain intact. No production
  cancellation or watchdog deadline was increased.

- The matching-resume status fixture previously blocked bundle construction, then
  required a complete research pipeline in ten seconds. The confirmed native failure
  occurred in that unrelated full-run wait. It now pauses the real model call,
  proves compatibility and active/cleared-rejection status, then requests the real
  controller cancellation. All prior assertions and the ten-second drain remain;
  an explicit `cancelled` terminal-state assertion is added. Full released-pipeline
  integration tests remain in the unfiltered suite.
- Windows packaging now runs in an independent job, with the same build/cache,
  browser, frozen, window, real Electron and NSIS installed-upgrade checks. Windows
  full Python/quality remains a separate job. Either failure keeps the workflow
  red; moving packaging does not bypass a failing assertion. Actual installer
  files and incomplete hash reports are retained when a later installed smoke fails.
- The independent Ubuntu Python 3.11/3.12 CI used floating dependencies, unlike
  desktop CI. Its prior `ce846d8` runs each failed 27 tests after resolving
  Pydantic 2.14.1 / FastAPI 0.143.0 instead of validated Pydantic 2.13.4 /
  FastAPI 0.141.1. Saved JSON schema hashes, API responses and generated observation
  schemas differed. CI now applies the existing `desktop/constraints.txt`, including
  isolated distribution verification; no fixture hash or public schema was changed.
  One of those failures also exposed the new long-path test's short-root assumption;
  it now adds padding until the actual path exceeds 300 characters on every runner.

No dependency pin was changed. No evidence admission rule, research prompt, source policy, budget,
unknown reservation or exact source/executable resume gate was relaxed. The complete
suite retains existing opt-in/platform skips. Diagnostic subprocess timing does not
replace or lengthen the CLI tests' original 30-second assertion.

The target native diagnostic releases its generated research run but records an
additional round-four source as `analyst_failed` with
`IntegrityError: CHECK constraint failed: discovery_round BETWEEN 1 AND 3`.
Ten separate local generated pipelines reproduce this same constraint. The live
contract permits round four while the existing ledger-admission schema check does
not. This is a separate unresolved storage-contract defect; it does not explain
missing expected source 1 or 5 in the intermittent full-suite failures. No admission
policy or historical schema was rewritten to hide it.

## Native scope and fault-injection limits

The Windows checks run on GitHub `windows-2025`, **Windows Server 2025 Datacenter
10.0.26100 x64**, with **NTFS** C:/D: volumes, Python 3.12.10. They do not establish
acceptance on consumer Windows 10/11, ARM64, non-NTFS storage, network shares or
unprivileged clean desktops. Native security tests require NTFS and fail on a
different filesystem; they do not silently substitute mocks.

The 18-test storage/security/process selection contains **16 checks using native
operations and two mocked bootstrap/Job-assignment ordering checks**. The latter
prove failure ordering only. The separate 11 focused regressions mix real local
storage/CLI operations with fake research providers; they establish no live provider
quality. JUnit records retain every test name so these categories can be audited.

| Property | Actual operations and limits |
| --- | --- |
| Privacy | Real protected DACL inspection on live DB, backup directory/file, verification marker, restored file and exports. A real restricted impersonation token reads a public control but gets `ERROR_ACCESS_DENIED` for the private file; owner access succeeds. This does not represent a separate interactive user or adversarial concurrent reparse swapping. |
| Publication and no overwrite | Native hard links, existing destination and symlink collisions, unchanged sentinel bytes, verified backup/restore and directory-junction refusal. Python library checks use generated paths with accented/CJK characters, `%`, `#`, spaces and lengths above 300 characters. Frozen/installed paths above 300 characters were not exercised. |
| Interrupted schema upgrade | Generated schema-16 database in SQLite DELETE journal mode. Parent-owned `TerminateProcess` after actual file flush, backup link, marker link, uncommitted version-17 migration and committed migration. Restart checks integrity, foreign keys, exact saved row, expected schema 16/17, released process locks, valid-marker selection and backup restore. Only timing is injected. |
| Interrupted writer/accounting | Actual killed writer in DELETE and WAL journal modes. The saved running manifest and physical-call audit remain unchanged; unknown completion keeps its 12,500-token / $0.25 reservation. |
| Credential Manager | Real Unicode credential write/read, separate-process persistence, replacement and deletion of a random `ResearchAssistant.Smoke.*.WindowsCi` target. No production target is read or changed. |
| Process ownership | Native nested kill-on-close Jobs cover children/grandchildren while an unrelated sentinel survives. Mocked API ordering checks remain distinct from native process tests. Real Electron forced quit additionally uses production main with a test clock and disposable Python stubs; report its actual job result separately. |
| Installer | Both unsigned candidate builds and pre-install native smokes pass. Attempt 1 timed out installing the historical build. Attempt 2 installed that build, observed old executable removal while the upgrade root remained alive, closed its owned Job, then timed out during candidate repair. Installed frozen/window, historical data/vault upgrade and uninstall were not reached. The checkpoint records no nonzero-exit assertion or descendant-handle inventory, so no complete interrupted-upgrade/repair or rollback acceptance is claimed. |

Repeat the filesystem/crash checks from the repository root on a disposable Windows
NTFS volume after installing constrained `backend[dev]` dependencies:

```powershell
python -m pytest tests/test_native_storage_durability.py tests/test_native_windows_security.py tests/test_desktop_shutdown.py -v
```

`tests/storage_crash_driver.py` emits a ready marker only after the selected actual
operation and then pauses. The parent kills that exact child handle, reopens the
database, checks row/schema/integrity and recovers the verified backup. The five
named phases are recorded in the test parameters. No live database is a test input.
Timing hooks are fault injection; SQLite/filesystem/ACL/vault/process operations are native.

**Physical power-loss durability remains unverified.** `TerminateProcess` leaves
the kernel and storage controller alive. It cannot discard Windows page cache,
device volatile cache or NTFS metadata writes. The current Windows
`_flush_directory` path does not flush a directory handle. Successful file fsync,
hard-link publication and process-crash recovery therefore do not prove durable
directory-entry ordering after sudden power removal.
The available disposable Windows environment is a GitHub-hosted ephemeral runner;
this session has no external host/device power control and retained cold-restart
disk image with which to verify that property.

A repeatable follow-up requires a disposable Windows VM or sacrificial device with
recorded OS/NTFS/device/cache settings, an out-of-band host controller and generated
fixtures. Reuse the five marker boundaries, hard-reset/power-cut externally without
guest shutdown, cold-start, and run the same integrity/schema/row/verified-marker
and restore checks. Retain pre/post disk images, phase acknowledgements and artifact
hashes; repeat cuts around link/marker publication and commit. A VM reset with a
live host cache still does not establish physical-device power-loss behavior.

For each cut, first create a new folder on that disposable NTFS volume and initialize
only a generated fixture (replace the example path with the recorded fresh folder):

```powershell
python -c "from pathlib import Path; from tests.test_native_storage_durability import _old_database; p=Path('D:/RA-fault-unique/crash.sqlite3'); assert not p.exists(); p.parent.mkdir(); _old_database(p)"
python -u tests/storage_crash_driver.py D:/RA-fault-unique/crash.sqlite3 backup-linked
```

Capture the emitted `backup-linked` marker on the host, cut/reset externally, and
after cold start use `_contents` for integrity/schema/row validation and the normal
`list-backups`/`restore-backup` CLI against that recorded fixture. Check before any
writable reopen: schema must be 16 except the acknowledged committed boundary,
where it must be 17; the `crash-run` row must match the pre-cut copy. A backup is
eligible only with a valid matching marker and must restore to a new destination.
The `marker-linked` and both migration boundaries must retain a verified backup;
the two earlier boundaries must advertise none, as in the process-crash tests.
Repeat with fresh folders for the other four phase names above. A missing marker,
lost row, corrupted database or unavailable committed schema is a recorded failure,
not a reason to regenerate the fixture or change the expected result.

## Quality, packaging and release boundary

Local macOS 26.6.2 (25G83) arm64 / Python 3.12.14 provides separate source validation.
The native-target local baseline is **2,816 passed / nine platform/opt-in skips**,
249.45 seconds. Target Ubuntu Python 3.11.17 is **2,810 passed / 15 skips**, 621.48
seconds; Python 3.12.15 is **2,814 passed / 11 skips**, 783.37 seconds, both with
branch coverage. Mac CI is **2,815 passed / ten skips**, 281.02 seconds, followed by
successful full desktop packaging. The target full Windows suite is **2,810 passed / 15 existing skips**, 1,880.66
seconds; distribution verification, 20 shutdown unit checks, Ruff/format and
frontend lint/types also pass on that Windows runner. The POSIX group smoke emits
its explicit platform skip; native Windows Jobs are exercised separately.
Ruff/format (477 files), repository boundaries,
generated frontend contracts and staged/unstaged whitespace pass. Frontend lint,
types/static build, five offline browser checks, desktop unit and native Mac process
checks have separate logs. Sandbox loopback/`ps` restrictions were resolved by the
authorized unsandboxed native invocation; those attempts are not Windows evidence.

The unsigned Windows installer is SHA-256
`50f5af62a6de6a59f93a41f1536e3b5a7e33d58cad65effb90304bcee6bd9fd7`,
retained in [artifact 11935168730](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38652359869/artifacts/11935168730).
Its artifact ZIP digest is
`57a79a1992a56aef590d1647984259be3b01165999fcb6a16d099f0fe8f4ce9a`.
The downloaded ZIP and enclosed installer were independently hashed against these
values. Static PE inspection found an empty embedded certificate table; native
Authenticode/catalog trust was not tested. This macOS byte inspection is separate
from Windows execution evidence.
[Job 116153955494](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38652359869/job/116153955494)
failed in `install(old, destination)`: the SHA-bound historical comparison installer
remained alive through `process.wait(timeout=240)` in the isolated Unicode path.
The current and historical source pin the same NSIS template version and settings;
the templates recognize `/S`, `/currentuser` and a final unquoted `/D=` remainder.
No installer window/process/file-progress capture establishes the timeout's cause.
No Unicode, privilege or compression explanation is asserted from that trace.

The same-source [diagnostic rerun, job 116165774688](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38652359869/job/116165774688)
passes the historical installation and reaches the owned-Job interruption checkpoint.
It then fails at `install(installer, destination)` (line 167), repairing the partial
installation: `subprocess.TimeoutExpired` after the original 240 seconds. Thus the
first setup timeout did not reproduce at that phase, but native repair still has a
verified blocker. The root cause is not established by the retained job and runner
logs. The checkpoint only observes old executable removal with a live installer
root before closing the Job; it does not record a nonzero exit assertion or exact
NSIS descendant handles. Those observations need strengthening before accepting
installer interruption recovery. No current installed runtime/window, data/vault
upgrade or uninstall result follows the failed repair.

The rerun candidate installer is SHA-256
`6f82a5a17dc234f6f5da2eba92981fba3c093ac4d6d9c49296a1d14023f89525`,
from its native report; [artifact 11938020157](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38652359869/artifacts/11938020157)
has ZIP digest
`48ac8cb41176054850c2fefe4251d1f64d6f6ba4f568dbd2fb2912bebe1abfb5`.
This second binary was not independently downloaded; its report ZIP was downloaded
and its digest verified. Both attempts identify Server 2025 build 26100 and NTFS
C:/D:. The workflow's final attempt-2 conclusion is **failure**, with full Windows
quality, Mac and independent native-selection jobs passed. Its runner diagnostic
archive and exact failed stack are retained locally.

Windows packaging must actually execute locked dependency installation, build,
native acquisition/cache smoke, offline browser tests, frozen backend, window,
real Electron forced quit, NSIS packaging and installed upgrade checks before a
passing packaging claim. The workflow archives native environment/JUnit reports
even when another job fails; definitions and uploaded empty directories are not
acceptance evidence.

The October 9 installed Mac app and Prompt 16 DMG/ZIP remain preceding artifacts.
The private-file code fix changes the source identity, so the earlier Mac candidate
cannot represent the new source. No app was adopted or public release published.
Signing, clean Windows client/minimum-OS behavior, device power-loss evidence and
explicit publication authorization remain separate gates. Mac Developer ID,
notarization, clean-machine/macOS 14 and genuine live-research quality gates remain
as recorded in [Prompt 16](mac-delivery-gates-2026-10-13.md).

## Local review fixes

The uninstall invocation now appends NSIS's final `_?=` directory tail without
quotes, so the waited process performs removal instead of returning from a
temporary-uninstaller bootstrap. A zero exit is insufficient: every installed
file/directory except the in-place uninstaller itself must be absent. A separate
generated file must retain its exact hash before the smoke reports success. This
checks a disposable sibling fixture, not Windows application-data retention or
native credential preservation.

Four offline regression cases exercise the literal NSIS tail with a spaced Unicode
path and reject a zero exit leaving the app, resources or another installed file.
They mock process execution; native NSIS was not rerun. These harness/test bytes
are outside `44f83d9`, whose recorded native results and repair blocker remain unchanged.

The retained `python-macos-final.log` still ends with 2,816 passed / nine skips in
249.45 seconds. Its actual SHA-256 is
`893ed73c4f528881d6a309e6251e826ea381c44132521fc5b1a9be6fc8fa932f`;
the stale supplement entry was corrected without changing the log. All 65 retained
raw-evidence hashes now match. The supplement retains the preceding incorrect hash
and identifies this local follow-up separately from native evidence.

Local follow-up validation: **2,820 passed / nine existing skips**, 260.64 seconds,
macOS arm64 / Python 3.12.14. The focused installer/type/build selection passes
eight checks. Ruff/format (478 files), repository boundaries, staged/unstaged
whitespace and 20 desktop shutdown unit checks pass. The supplement records the
separate follow-up log and hash. No Windows installer or application was executed
or replaced by these local checks.
