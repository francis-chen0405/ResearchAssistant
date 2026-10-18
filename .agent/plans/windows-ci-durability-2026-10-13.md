# Prompt 17 — Windows CI and native durability

Windows release remains deferred. Preserve the installed Mac app, real databases,
vault entries, earlier staged work, research/evidence policy and exact resume gate.

1. Verify remote workflow/job/log provenance against dirty local HEAD `94a241b`.
2. Upload only the reviewed source archive to an isolated verification branch;
   reproduce current Windows failures before correcting their root causes.
3. Exercise isolated native NTFS privacy/publication, recovery after killed
   processes, Unicode/long paths, native vault/process ownership and packaged smoke.
   Explicitly distinguish fault-injected boundaries from physical power loss.
4. Run complete Python/quality/frontend/desktop checks at the final source revision;
   retain OS/filesystem, exact failures, artifact hashes and remaining release gates.

The user explicitly approved the 1,001-file source snapshot upload to
`francis-chen0405/ResearchAssistant`, branch `codex/windows-ci-durability-20261013`,
and CI dispatch. Parent checkout/index are untouched; a disposable clone owns CI
commits. No master update or release publication is authorized.

Evidence: `desktop/build/prompt17-evidence/` retains manifests, snapshots and raw
GitHub logs. Current-state owners are STATUS/HANDOFF; final results belong in the
Windows verification record. The preceding owners are saved byte-for-byte in
`docs/archive/2026-10-13-windows-preceding-state/`.

Outcome at `44f83d9`: full Windows Python (2,810 passed / 15 skips), Windows
quality/frontend, automatic Python 3.11/3.12 and the native storage/security/process
selection pass. Both native packaging attempts pass through NSIS construction.
Installed acceptance retains a verified blocker: first comparison installation,
then candidate repair after the observed interruption checkpoint, time out at
240 seconds. Exact evidence, artifact hashes and unverified properties are in
[the verification record](../../docs/verification/windows-ci-durability-2026-10-13.md).
Windows release remains deferred; the next boundary is HANDOFF.

Review follow-up: correct the NSIS unquoted uninstall tail and reject a successful
exit that leaves installed payload. Add isolated offline regressions, verify
separate generated data survives, and correct the retained Mac log's stale hash.
Keep these local harness changes separate from `44f83d9` native evidence; the
repair timeout remains unresolved and no new Windows execution is claimed.
Validation: local full suite 2,820 passed / nine skips; focused installer/type/build
selection eight passed; Ruff/format, repository/whitespace checks and 20 desktop
shutdown units pass. The existing verification supplement retains the exact
follow-up log hash and all 65 corrected original evidence hashes.
