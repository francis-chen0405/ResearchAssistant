# Windows packaging trigger — October 18

The user requested diagnosis of the failed GitHub check and removal from automatic
checks if it was the Windows verifier again. At source `25860279d6351c68865d421d547642cf80b9f94c`,
[Windows packaging and native desktop](https://github.com/francis-chen0405/ResearchAssistant/actions/runs/39152698037/job/117749415340)
failed during `Exercise frozen bundle without developer tools`. The downloaded job
log reports `Packaged acquisition failed: Owned Wigolo exited with code 1.` at
`desktop/smoke.py:97`. The installer stage was not reached: this is an earlier
failure than the historical repair-install timeout, and its deeper Windows service
startup cause is not established by that message. The local raw log is
`/tmp/ra-github-windows-frozen-2586027.log`.

The independent Windows regressions/native-storage job passed. Frontend, Ruff and
offline evaluation also passed at inspection; Python 3.11/3.12 and desktop matrices
were still running. Do not present incomplete jobs as passing.

## Authorized change and verification

Guard only `windows-package` with `github.event_name == 'workflow_dispatch'` and
label it manual. Push/PR checks skip that verifier; a deliberate manual workflow run
can still reproduce its real failure. Keep all other job definitions unchanged,
including Windows native regressions and Mac packaging. No release is authorized.

YAML parsing, exact dispatch guard and equality of all unaffected job bodies/triggers
pass. Repository boundaries, Ruff lint/format (517 files) and whitespace pass. Retain the
preceding complete offline result (3,196 / nine skips): no runtime/test source changes
are made, so no new native or full-runtime acceptance is claimed. Verify the new
remote automatic job is skipped after the normal master push. Existing Windows
release blockers remain open; installed app, real data and source identity are preserved.

## Windows desktop matrix removal

The user subsequently explicitly requested removal of `Desktop windows-2025` after
another failure. Remove `windows-2025` from the desktop matrix, retaining `macos-15`.
The separate Windows native-storage regressions remain enabled and the packaging
verifier remains manual-only. This supersedes the earlier instruction to leave the
desktop matrix unchanged. No application code or installed data changes.
