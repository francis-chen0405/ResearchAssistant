# Mac-first cache-pricing delivery — 2026-09-17

This candidate is superseded by the subsequent
[planner/Scout reliability build](planner-scout-reliability.md), which is now installed.
The live acceptance below deliberately used this original frozen candidate; it does not
establish the effectiveness of later fixes. Source identity below was checked at build time.

User authorized Mac-first delivery, official cache pricing research, and at most five
research prompts under the proposed combined $5 model budget plus existing source-service
quotas. Windows is deferred. No Apple Developer membership or Developer ID certificate is
available, so these are unsigned downloadable test artifacts, not a signed public release.

## Changes and source evidence

The shared adapter previously applied MiMo Pro rates to every response with cache metadata.
Verified rates now select by exact official endpoint and model, covering Scout, Pro and
Luna. Luna's disjoint cache-write counts and whole-request long-context multipliers are
included; invalid/missing cache metadata stays conservative. Custom routes use configured
caps. Physical failures use the same rules; unknown usage keeps its reservation. Historical
rows and reports are not recalculated. See [pricing rules and sources](../model-settings.md).

The Luna High route now explicitly requests High reasoning and standard service tier.
This corrects a second mismatch between the advertised role and the outgoing request.
The Mac package declares the documented minimum macOS 14.0 instead of inheriting 13.0.
No model selection, research rounds, database migration or dependency version changed.

## Offline and native checks

| Check | Result |
| --- | --- |
| New regressions before implementation | Six failures reproduced Scout/Luna pricing and missing High effort; seven baseline cases passed |
| Focused pricing/adapter/routing suite | 54 passed |
| Full Python suite | 984 passed, 2 existing opt-in skips; one existing Starlette warning |
| Profile/desktop checks after metadata update | 25 passed |
| Ruff lint and format | Passed; 147 Python files |
| Frozen offline evaluation | 38 cases passed |
| Frontend lint, TypeScript and desktop static export | Passed |
| Frozen backend build | Passed |
| Native backend smoke | Passed: authenticated local API/UI, isolated vault round-trip/cleanup, durable settings, owned Wigolo lifecycle |
| Offline browser acceptance | Passed, including repair/coverage, cancellation, history/export, dialogs, responsive layout and reduced motion |
| Packaged actual-window smoke | Passed: renderer isolation, authentication, seven empty credential fields, duplicate exclusion, normal shutdown |
| Installed actual-window smoke | Same checks passed against `/Applications/ResearchAssistant.app`; closed normally |
| Upgrade from installed adaptive build | Passed: isolated cross-executable credentials, preferences, identical validated historical brief and unchanged fixture database |
| Packaged identity | 97 source/prompt/manifest files match checkout byte-for-byte; frontend matches; minimum OS is 14.0 |
| DMG and ZIP | DMG checksum valid; ZIP integrity passed |

Package verification used macOS 26.6.2 arm64. This is not a clean machine or a macOS 14
test. The old backend/frontend resource folders were moved to temporary backup before
staging replacements, avoiding stale copied application source. Bundled locked Node,
Wigolo and Chromium resources were retained. Local loopback/native-vault checks and
packaging required expanded sandbox access; no assertion or timeout was weakened.
The packaged provider-setup screenshot was visually inspected; password fields were empty.

## Artifacts

In `desktop/dist/mac-cache-pricing/`:

- `ResearchAssistant-0.1.0-arm64.dmg` — SHA-256
  `057c9f685af1edb240d01021b2906dbd3aaeeeefe784035fe9c90e0c54a5749d`
- `ResearchAssistant-0.1.0-arm64-mac.zip` — SHA-256
  `7d741008d722303f2ab7177995e7250195467504cf401d4356b6eaf5067f01a3`
- `SHA256SUMS.txt` and `READ-ME-FIRST.txt`.

Original packaging output is `/private/tmp/researchassistant-mac-cache-release/`.
These locations are delivery evidence only, never application runtime defaults.
The verified app was installed with staged copying while closed. The previous bundle
is backed up at `/private/tmp/ResearchAssistant-before-cache-xir5br61/ResearchAssistant.app`.
Installed executable, pricing source and frontend match the packaged candidate. Real
history/preferences/credentials were not replaced; acceptance history is separate.

## Live acceptance

Acceptance runs use the packaged backend and isolated history under
`desktop/build/mac-cache-live-acceptance/`. The persistent `attempts.json` ledger consumes
a slot before every research-start submission; failed/rejected submissions count against
the five-submission maximum. Each actual run has at most $1 model exposure, 500,000 tokens
and 160 physical model attempts. Existing source-service limits remain unchanged.
Credentials remain in the native vault/backend; no secret is copied into reports.

An initial harness error used non-null `exit_code` as a completion signal, even though
running snapshots can have code 13. The backend's cooperative shutdown cancelled the
first run after one model call; a second overlapping request was rejected. The harness
was corrected to use terminal classification. Both submissions consume slots. This was
a harness defect, not an application validation failure. Three subsequent submissions
completed the allowance; it is now exhausted and the backend shut down normally.

One completed live attempt already exposed a real initial-planner reliability limitation:
MiMo returned `claim_coverage_focus` rejected by the semantic response contract. The app
failed closed after one call; no validation was relaxed.

| Submission | Outcome | Physical model calls | Recorded model cost |
| --- | --- | ---: | ---: |
| 1 — spaced practice | Harness shutdown cancelled after initial call | 1 | $0.002595467 |
| 2 — genetic enhancement | Overlapping start rejected; no research started | 0 | $0 |
| 3 — spaced practice | Initial planner claim-coverage contract rejection | 1 | $0.001250882 |
| 4 — later school start times | Reached deep analysis; cancelled at 20-minute acceptance cutoff | 19 | $0.076356733 |
| 5 — blue paper and physics retention | Reached deep analysis; cancelled at 20-minute acceptance cutoff | 24 | $0.098414454 |

Total recorded model exposure: **$0.178617536**, across 45 physical calls and five
submissions. This is estimated model usage, not an invoice or search/acquisition cost.
Cooperative cancellation finished at approximately 1,212 seconds for both long runs;
no final released report was produced. Five submissions is not five successful tests.

Run 4 exposed three Scout truncations, two Luna gap truncations and two Pro selection
truncations. Smaller later Scout batches completed, and two extraction/Analyst pairs
succeeded before cancellation. Run 5 included a Luna timeout and additional truncations.
Completed physical outcomes and failed-call costs persisted correctly. The later
[reliability fixes](planner-scout-reliability.md) address demonstrated schema/batching
issues and increase response headroom; their live effectiveness remains unverified.

## Remaining release limitations

The user selected reliability before distribution; the linked follow-up implements
offline-tested corrections and a new Mac build. Next acceptance should exercise that
exact build, capture stage timings and distinguish truncation from transport latency.
Preserve evidence validators, budgets, retry limits and historical artifacts. Further
paid acceptance needs a new explicit allowance; this five-submission ledger is exhausted.

- Initial-planner live schema rejection requires follow-up; a passing offline suite does
  not establish dependable live research or factual entailment.
- Signing/notarization are unavailable. Apple's [Developer ID guide](https://developer.apple.com/developer-id/)
  explains why downloaded apps outside the App Store also use these checks. Unsigned
  test downloads may be blocked by Gatekeeper; no global security bypass is introduced.
- Clean-machine installation and actual macOS 14 acceptance remain unverified.
- The package still uses the default Electron icon. Windows acceptance is deferred.
- Nothing has been published remotely. The installed app contains this verified test build.
