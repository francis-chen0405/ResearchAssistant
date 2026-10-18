# Current status

User-approved R01–R36 fixes in the [full review](../audits/2026-10-15/full-code-review.md)
are implemented and verified. The latest repairs commit evidence admission and its
source checkpoint together, recover validated older partial admissions, support up
to 100 retained sources under fresh selection/shortlist v3, and redact CLI
configuration validation input. Historical selection v1/v2 keep their 75-source
limit. Research allowances, prompt bytes, scoring and length policies are unchanged.
[Verification](../verification/full-review-fixes-2026-10-15.md) retains exact evidence.

R37–R52 await approval: cross-direction discovery provenance; discovery/acquisition
and Round-4 completion prefixes; historical Reviewer admission; fresh quotation
context, selected occurrences and methods-heading recognition; optional seed author
metadata, compatible approval wording, native snapshot integrity and retained same-family
duplicate outcomes, native Reviewer resume, retained URL deduplication and duplicate
rate derivation; and the query-scaling benchmark's schema downgrade and older evaluation output collisions. Their offline reproductions and
proposed fixes are in the review report. These defects remain unfixed.

The literal every-file/every-line review is incomplete: the [manual ledger](../audits/2026-10-15/manual-coverage.json)
records 393 current files / 93,970 lines, including small facades and added tests.
Every canonical `backend/src/researchassistant/` Python module has a full read.
The desktop launcher/smoke code and remaining build/tooling files now have full reads. All evaluation Python modules now have full reads. Remaining tests and non-code records are still in scope. Automated
checks and hashes do not establish manual completion.

## Current verification

The complete Python suite passes **3,049 tests / nine existing skips** in 340.94
seconds. All 17 new regressions pass; focused checks pass 143, integration 130 and
contract compatibility 178. Ruff lint/format (501 files), repository boundaries,
generated API types and staged/unstaged whitespace checks pass.

Current frontend lint/types pass. Renderer and Node bytes are unchanged from R29;
that exact snapshot retains static export, 17 hook/component checks, six offline
browser smokes, 38 desktop/acquisition units and nine native shutdown scenarios.
Those unchanged browser/Node checks were not rerun for R34–R36.

The exact 303-file wheel audit and fresh wheel/editable installs pass from unrelated
directories, including dependency/prompt/font identities, fixture release/blocking,
fresh/replayed bindings and owned DNS/PDF helpers. Disposable frozen Mac resources
also pass authentication, smoke-only vault cleanup, settings restart, acquisition
lifecycle and DNS/PDF dispatch with an empty PATH. The installed app is unchanged.

Current verified source identity:
`source-sha256:eaec364bbc727aa3e101bf5948392458c1169c494c825bf2fccd1a5afb8fa61d`.

Schema 18, acquisition provenance v5, PDF policy v2, metadata ranking v4, URL identity
v2 and fresh selection/shortlist v3 govern current behavior. Explicit older policy
handling preserves history. Read-only schemas 7–18 remain supported. Saved rows,
released hashes and unknown reservations are immutable; exact resume compatibility
requires fresh research after source/executable changes.

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
