# Current status

The user-approved R01–R18 repair set from the [full review](../audits/2026-10-15/full-code-review.md)
is implemented. Settings wait for saved preferences before editing/start and offer
retry on read failure. History import preserves intervening edits and owns late
completion; credential actions protect pending inputs and refresh current models.
[Verification](../verification/full-review-fixes-2026-10-15.md) records the
source, transport, migration, UI and packaging checks. The literal every-line manual
review remains incomplete. All eighteen reported fixes are approved and implemented;
no fix approval is currently pending.

## Current verification

The backend complete suite passed **2,868 tests / nine skips** in 322.97 seconds,
including the last standalone shutdown regression and stronger PDF timeout
assertions. Ruff lint/format (487 files), repository
boundaries, generated API contracts and staged/unstaged whitespace checks pass.
The later UI-only R15–R18 changes pass 20 focused integration tests; backend source
identity is unchanged. Frontend lint/types/static export and all six offline browser
smokes pass. Seventeen actual-hook/component regressions, 24 JavaScript syntax checks,
21 desktop shutdown/link regressions and 17 acquisition
cache/network/proxy unit checks pass. Chromium uses an owned public-destination
HTTP/HTTPS proxy, including worker paths outside the context router. Generated
public dedicated/shared-worker content loads; private HTTP, WebSocket and secure
WebSocket attempts make zero connections to the private sentinel. Service-worker
activation and peer transports remain blocked. All nine native POSIX shutdown scenarios pass
with normal process inspection; the sandbox sentinel result is retained separately.

The exact 300-file wheel audit and fresh wheel/editable installs pass from unrelated
directories. Dependency checks, all 18 prompt identities, embedded-font identity,
fixture release/blocking and fresh/replayed discovery binding pass. Both installed
forms also run the actual PDF subprocess successfully.

Current source identity:
`source-sha256:0cd486b049ee8d5192ba6e5bc318cb4eb195302530a7aaa21f688c54039a0835`.

Schema 18 admits v2 round-four evidence; read-only schemas 7–18 remain supported.
Historical migration declarations, rows, triggers, indexes, output hashes, policies
and unknown reservations retain their meaning. New behavior uses acquisition
provenance v4, PDF policy v2 and metadata ranking v3; explicit v2 ranking dispatch
preserves old scores. Exact source compatibility requires a fresh run.

The existing httpcore 1.0.9 dependency is explicitly declared. Already locked
ipaddr.js 1.9.1 and Playwright 1.60.0 are explicit acquisition dependencies; no
version was upgraded. Protected Node acquisition is required for HTML refetch.
A fresh disposable Mac frozen-resource candidate passes UI/backend authentication,
temporary-vault cleanup, settings/restart persistence, owned acquisition lifecycle,
frozen PDF-worker dispatch, and bundled Node/Chromium proxy checks. Node/Chromium
bytes are copied from the earlier candidate; backend/acquisition/frontend resources
are current. This is resource-level acceptance, without a new Electron installer,
installed-app replacement or native Windows acceptance.

## Windows and release boundary

[Prompt 17](../verification/windows-ci-durability-2026-10-13.md) retains the historical
CI target `44f83d9bfb7e8e2896dc44390c366e4d498be044` on
`codex/windows-ci-durability-20261013`. Automatic CI and Mac packaging passed there;
Windows Python passed 2,810 / 15 skips. Windows packaging remains blocked by the
240-second repair-install timeout after interrupted upgrade. Installed checks after
repair were not reached. The latest uninstall harness and these approved runtime
changes have not been rerun natively on Windows.

Physical power loss, Windows directory-entry flush ordering, consumer clean-machine
and minimum-OS acceptance, Windows ARM64, signing/SmartScreen and Mac
signing/notarization remain unverified. Public release remains deferred.

## Preservation

The checkout remains dirty local `master`, HEAD
`94a241b52f9525cab3aff52d1f85026f081b3e85`. The original staged binary diff remains
unchanged: `85f8753d0bb6ba7af20c688eab28ad10429ee43329b879d89b8db48071324cf2`.
Approved repairs update their owned working files; unrelated prior work is retained.
No commit, push or release occurred.

The October 9 installed Mac app and real databases/cache/credentials were preserved.
[Prompt 16](../verification/mac-delivery-gates-2026-10-13.md) retains its older
unsigned candidate and native acceptance evidence. No paid research occurred.
Historical allowances do not authorize changed-source calls; live usefulness and
human judgments remain separate from authored offline fixtures.

[Exact preceding records](../archive/2026-10-15-review-fixes-preceding-state/INDEX.md)
are archived. [HANDOFF](HANDOFF.md) owns the next boundary.
