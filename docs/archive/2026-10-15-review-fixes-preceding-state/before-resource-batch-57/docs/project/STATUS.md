# Current status

All user-approved R01–R55 fixes in the [full review](../audits/2026-10-15/full-code-review.md)
are implemented and verified. The latest repairs preserve query directions, recover
interrupted stage/admission prefixes, retain exact fresh quote context and selected
occurrences, correct methods headings and approval wording, tolerate optional author
metadata, verify native source evidence, repair retained deduplication/accounting,
and protect evaluation inputs and benchmark fixtures.
[Verification](../verification/full-review-fixes-2026-10-15.md) retains exact evidence.

R53–R55 retain exact Scout/Gap inputs and bounded attempt outcomes, reuse known
results, and stop on unknown outcomes without repeating calls. Fresh Strong finding
labels follow validated relationships; indirect qualifications and recorded historical
rendering remain. All 39 new regressions and final source/distribution/frozen checks pass.

R56 is reproduced and awaiting approval: Source Selection independently repeats
the same completed request across interruptions before its queue/status commit.
Its two-attempt cap resets; accounting stays correct.
R57 also repeats completed initial Planner requests before the first plan write.
R58 confirms an unbounded checkout-launcher readiness request. R59 records stale
current security/schema/link-policy guidance. R56–R59 await approval; none is repaired.

The literal every-file/every-line review remains incomplete. The [manual ledger](../audits/2026-10-15/manual-coverage.json)
records 629 current files / 160,794 lines, including reviewed updates and added tests.
Canonical backend modules, compatibility facades, evaluation/tooling and desktop code
have full reads. Remaining tests and non-code records stay in scope. Automated
checks and hashes do not establish manual completion.

## Current verification

The complete Python suite passes **3,151 tests / nine existing skips** in 400.22
seconds, including all 39 R53–R55 regressions. Ruff lint/format (515 files), repository
boundaries, generated API types, frontend lint/types and staged/unstaged whitespace
checks pass. Focused historical compatibility and resume checks pass.

The exact 304-file wheel audit and fresh wheel/editable installs pass from unrelated
directories, including prompts/fonts, fixture release/blocking, fresh/replayed bindings
and DNS/PDF helpers. A separate frozen Mac candidate passes authentication,
smoke-only vault cleanup, settings restart, acquisition lifecycle and DNS/PDF dispatch
with an empty PATH. The installed app and preceding candidate are preserved.

Renderer/Node bytes remain unchanged from R29. Its exact static export, 17 hook
checks, six offline browser smokes, 38 desktop/acquisition units and nine native
shutdown scenarios are retained; those unchanged checks were not rerun for R53–R55.

Current verified source identity: `source-sha256:9f1c3e19607ed1d9b393457dcb629ccebb290be11cb6d4db0e76c2798c181189`.

Schema 18 and existing research budgets/scoring remain authoritative. Fresh query
provenance v2 retains each lane's own direction; quotation context filter v2 preserves
exact selected offsets; fresh synthesis v2 / renderer validator v4 use relationship-aware admission wording. Explicit
old dispatch/serialization preserves historical records and released hashes. An older
ranking-only checkpoint has no saved Scout decisions: versioned recovery discloses
that loss and uses the existing ranking fallback without another Scout call. Original
charges and unknown reservations remain unchanged. Source/executable changes require
fresh research under the exact compatibility gate.

## Windows and release boundary

[Prompt 17](../verification/windows-ci-durability-2026-10-13.md) retains historical CI
target `44f83d9bfb7e8e2896dc44390c366e4d498be044` on
`codex/windows-ci-durability-20261013`. Automatic CI and Mac packaging passed there;
Windows Python passed 2,810 / 15 skips. Packaging remains blocked by the 240-second
repair-install timeout after interrupted upgrade; installed acceptance was not reached.
The latest uninstall harness and these runtime changes have no native Windows rerun.

Physical power loss, Windows directory-entry flush ordering, clean/minimum-OS
acceptance, Windows ARM64, signing/SmartScreen and Mac signing/notarization remain
unverified. No new Electron installer acceptance is claimed. Public release is deferred.

## Preservation

The checkout remains dirty local `master`, HEAD
`94a241b52f9525cab3aff52d1f85026f081b3e85`. The original staged binary diff remains
`85f8753d0bb6ba7af20c688eab28ad10429ee43329b879d89b8db48071324cf2`.
Approved repairs update owned working files; unrelated staged/unstaged work is retained.
The October 9 installed app, real databases/cache/credentials, prompt bytes,
historical research policies, release hashes and accounting were preserved.
No paid research, installed-app replacement, commit, push or release occurred.

[Exact preceding records](../archive/2026-10-15-review-fixes-preceding-state/INDEX.md)
are archived. [HANDOFF](HANDOFF.md) owns the next boundary.
