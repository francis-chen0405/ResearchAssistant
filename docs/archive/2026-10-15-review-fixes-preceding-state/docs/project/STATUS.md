# Current status

[Prompt 17 Windows CI and native durability](../verification/windows-ci-durability-2026-10-13.md)
records tested current source on an isolated GitHub branch. **Windows public
release remains deferred.** No release was published and no installed app was replaced.

## Current verification

The native CI target is `44f83d9bfb7e8e2896dc44390c366e4d498be044` on
`codex/windows-ci-durability-20261013`. All five jobs in
[automatic CI](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38652325933)
pass, as does the Mac job in the
[desktop workflow](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/38652359869).
The full Windows suite passes **2,810 tests / 15 existing skips** in 1,880.66
seconds. Windows distribution verification, 20 shutdown unit checks, Ruff/format
and frontend lint/types also pass. The independent Windows native packaging
job built both candidates and passed browser, frozen/vault/settings, window and
real forced-Electron shutdown checks. Installed-upgrade acceptance is blocked.
Attempt 1 timed out installing the historical comparison build (240 seconds).
Diagnostic attempt 2 completed that installation and reached the interruption
checkpoint, then the candidate repair install timed out at the same 240-second
limit. Installed frozen/window, historical data/vault upgrade and uninstall were
not reached after repair. The final desktop workflow remains **failed** for this
verified native blocker. Both artifact hashes and exact logs are retained; the
underlying causes remain unestablished. No Unicode/UAC explanation is inferred.

Local review fixes subsequently correct the unquoted NSIS uninstall tail and
require installed-payload removal plus unchanged separate generated data before
success. Four offline regression cases cover command parsing and false zero exits;
native Windows has not rerun these harness bytes. The stale Mac log hash is corrected,
and all 65 retained raw-evidence hashes match. The verification record separates
this local follow-up from the historical CI target and its unresolved repair failure.
The local follow-up full suite passes **2,820 tests / nine existing skips** in
260.64 seconds; Ruff/format (478 files), repository/whitespace checks and all 20
desktop shutdown unit checks pass.

- Windows Server 2025 Datacenter 10.0.26100 x64 / Python 3.12.10 / NTFS: the
  storage/security/process selection passes, as do the focused regressions. Its
  18 checks comprise 16 using native operations and two mocked Job/bootstrap
  ordering checks. Protected ACLs and actual restricted-token access denial,
  junction/symlink refusal, link collisions, Unicode/paths above 300 characters,
  verified restore, five killed-upgrade boundaries, DELETE/WAL writer recovery,
  unique Credential Manager persistence and owned nested Jobs have native evidence.
- Real defects corrected: Windows private directories followed junction targets;
  saved-research exports relied on ineffective POSIX modes. Portable fixtures,
  escaped-path API normalization, Git executable archive metadata and cancellation
  setup synchronization were corrected while preserving their original assertions.
- Floating automatic CI dependencies had produced 27 failures on each Ubuntu
  Python 3.11/3.12 job. These jobs now use the existing validated constraints,
  as desktop CI already did. No pins or schema fixtures were changed.
- The preceding `e6ed4fa` full Windows suite had two failures / 2,808 passed /
  15 existing skips: an original 30-second CLI deadline and missing expected URL-5
  admission. Both passed focused runs; their intermittent causes remain unproven.
  Earlier cancellation and matching-resume fixture deadlines measured unrelated
  pipeline setup/completion; controlled synchronization preserves the original
  drain/assertion bounds. No historical failure is assumed to persist without a
  current log.
- Generated product diagnostics also reproduce an existing round-four storage
  constraint (`discovery_round BETWEEN 1 AND 3`) for an additional source. The
  contract permits round four, but storage rejects that admission. This separate
  defect is retained as unresolved; it does not explain the missing source-1/5
  test failures, and no schema/evidence policy was changed in this task.
- Local macOS 26.6.2 (25G83) arm64 / Python 3.12.14 provides separate source
  evidence: full suite, Ruff/format, boundaries, generated frontend contracts,
  frontend lint/types/static export, five offline browser smokes, desktop unit
  and native Mac shutdown checks. Exact counts/results are in the verification
  record; Mac success is not Windows validation. Before the local review fixes,
  the full suite passed 2,816 tests / nine skips in 249.45 seconds. Ubuntu branch-coverage suites pass
  2,810 / 15 skips on Python 3.11.17 and 2,814 / 11 skips on Python 3.12.15;
  Mac CI passes 2,815 / ten skips in 281.02 seconds, then the complete desktop packaging path.

Process termination leaves Windows kernel/device caches alive. Physical power-loss
survival and Windows directory-entry flush ordering remain unverified; the record
contains repeatable generated-data fault points and an external-reset protocol.
Consumer Windows clean-desktop, minimum-OS, signing/SmartScreen and ARM64 acceptance
are not established by the Server 2025 runner. Installed repair acceptance remains blocked.

## Git, installed app and release boundary

The parent checkout remains dirty local `master`, HEAD
`94a241b52f9525cab3aff52d1f85026f081b3e85`; remote `master` was checked at
`27aeb95ca0b6c6999ba34b2cfd60c5b84a49200c`. Only the explicitly approved source-only
verification branch was pushed from a disposable clone. Existing staged work is
unchanged (binary-diff SHA-256
`85f8753d0bb6ba7af20c688eab28ad10429ee43329b879d89b8db48071324cf2`).

Current source identity is
`source-sha256:c87e0a2eddcf9d79ea5737a770e9db5c6a7648484352a20f96c5af4dbfd552b6`.
The October 9 app at `/Applications/ResearchAssistant.app` and real user data/cache
were preserved. [Prompt 16](../verification/mac-delivery-gates-2026-10-13.md) retains
its preceding unsigned Mac candidate, DMG/ZIP, native checks and disposable-cache FTS
repair evidence; that candidate does not contain the new private-file source fix.
The real cache was not repaired. Developer ID/notarization, clean-machine/macOS 14
and fresh signed-artifact acceptance remain external gates.

Research/evidence, provenance, admission, budgets, unknown reservations and exact
resume compatibility are unchanged. No paid research occurred. Prompt 14's frozen
$2.48 allowance/zero-spend receipt and the exhausted earlier five-run allowance do
not authorize changed-source paid calls; genuine provider usefulness/human labels
remain separate acceptance work. Authored fixtures provide no live quality evidence.

[Preceding state owners and guides](../archive/2026-10-13-windows-preceding-state/INDEX.md)
are preserved exactly. [HANDOFF](HANDOFF.md) owns the next boundary.
