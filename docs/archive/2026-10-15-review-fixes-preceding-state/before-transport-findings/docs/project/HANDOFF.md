# Handoff

Continue the requested literal every-file/every-line manual code review. The
[starting inventory](../audits/2026-10-15/review-inventory.json) contains 527 code
files / 147,198 lines. Record actually inspected ranges and bytes. Automated tests,
hashes and namespace-normalized AST equality do not establish manual completion.
The [review report](../audits/2026-10-15/full-code-review.md) preserves the original
eighteen findings; their user-approved fixes are implemented. [STATUS](STATUS.md)
owns current verification and the [repair record](../verification/full-review-fixes-2026-10-15.md)
describes implementation and remaining platform limits.

R15–R18 are approved and implemented, with seventeen hook/component regressions
and all six offline browser smokes passing. Continue beyond this inspected frontend
area using the current manual-coverage ledger; no reported fix is awaiting approval.
New confirmed findings should include a reproduction and a concrete proposed fix
for user approval before implementation.

Keep the protected Node acquisition preload with its locked runtime. Future changes
to reviewed upstream sources need hash review, transport/browser checks and a new
identity as appropriate. The explicitly declared httpcore and Node dependencies
retain their existing locked versions. PDF workers need fresh frozen/native process
checks on each target platform, including nested Windows Jobs and frozen dispatch.
Keep the owned Chromium proxy and its loopback-bypass/direct-DNS restrictions:
context WebSocket routing alone misses worker sockets. Dedicated/shared workers
remain enabled behind the proxy; peer transports and service workers stay blocked.
The real private-sentinel smoke checks both successful public worker content and
zero private HTTP/WebSocket/secure-WebSocket connections. New frozen Mac resources
pass local smoke/PDF/proxy checks; Electron installer and Windows acceptance remain
separate. Source-only unpatched-cache reproduction tests do not apply unchanged
to the already-patched staged cache module; retain that diagnostic distinction.

The next delivery task remains the native Windows interrupted-upgrade repair
failure at the historical exact target
`44f83d9bfb7e8e2896dc44390c366e4d498be044`; see
[retained evidence](../verification/windows-ci-durability-2026-10-13.md). Preserve the
original 240-second acceptance deadline. Retain the root's nonzero exit, partial
tree and exact owned descendant-handle exits before claiming interruption recovery.
Use a disposable NTFS runner, phase journals, installer/control text and created-path
progress. Establish a cause before changing the harness. After repair, complete the
previously unreached installed frozen/window, generated-history/vault upgrade and
uninstall checks with the corrected uninstall quoting and payload/data assertions.

Rerun full quality/native checks at the final source/artifact revision. Local Mac
checks do not close Windows packaging acceptance. Physical power-loss durability
needs a disposable VM/device and an external controller. Consumer clean-machine,
minimum-OS, Windows ARM64, native vault/process behavior and signing remain separate
gates. Mac release still requires Developer ID/notarization and actual
clean-machine/macOS 14 acceptance.

Preserve the installed October 9 Mac app, real databases/cache/credentials,
historical policies and hashes, unknown reservations and all prior staged/unstaged
work. Changed source/executable identity requires fresh research. No paid research,
new allowance, public release, installed-app replacement, commit or push is
authorized by this repair approval.
