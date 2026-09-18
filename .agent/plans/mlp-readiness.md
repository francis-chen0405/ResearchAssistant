# MLP readiness audit and proposed next steps — 2026-09-17

Status: completed audit. The user subsequently selected Mac first and authorized
researched cache pricing in [the Mac release plan](mac-release-cache-pricing.md).
Pending-decision and proposed-work text below records the original audit, not current authority.
Reviewed local `master` at `8e82c1f`; no paid providers, private history, credentials,
installed application, remote CI or release publication were used or changed.

## Readiness assessment

The core local product exists: claim/direction controls, discovery, bounded adaptive
research, exact evidence/provenance, conservative unresolved gaps, results/export,
history, native credentials and desktop packaging. Named MLP-2 through MLP-5 plans
record completed implementations; MLP-1's remaining-slice notes are historical and
were followed by later product work. MLP-4's planned “MLP-5 visual redesign” name
is historical; actual MLP-5 shipped provider selection, and Phase 3 later shipped
the current interface. Those records are not an active unfinished feature backlog.

Personal Mac use is close to an acceptance milestone, but current evidence does not
establish consistently useful live research or accurate accounting for every route.
A public cross-platform release has additional outstanding installation and signing
gates. A percentage or finish date would imply more certainty than the evidence supports.

| Area | Evidence | Remaining acceptance |
| --- | --- | --- |
| Research integrity/control flow | Current offline regressions pass; adaptive correction shipped on Mac | Live usefulness on representative claims; resolve accounting defect below |
| Desktop experience | Phase 3 and adaptive Mac delivery records | Confirm user can complete real work without assistance |
| Windows | Phase 2 CI/build/runtime matrix passed on `52e8f75` | Rebuild current source; native smoke, actual installation and upgrade |
| Public distribution | Unsigned test installers exist | Clean-machine/minimum-OS checks, production signing and notarization |

## Confirmed contradictions and disposition

1. **Shared usage pricing bypasses route caps when cache metadata exists.**
   `providers/mimo.py::_usage` calls `_cache_aware_cost`, which always uses MiMo Pro
   constants. `providers/v2_factory.py` constructs Scout, Pro and Luna with that same
   adapter. `providers/v2_budget.py::_snapshot` uses the resulting completion cost to
   replace reserved exposure. This conflicts with the selected route's pricing and
   the Standard profile's documented no-discount policy. A local synthetic probe
   (1,000 input, 800 cached, 100 output tokens) returns `$0.000176880` for all three
   models; their configured cap-based totals are respectively `$0.000180000`,
   `$0.000600000`, and `$0.000680000`. These are repository arithmetic comparisons,
   not verified vendor invoices or current market prices. Runtime remains unchanged
   pending the policy decision below. Existing cache-cost regression covers direct
   MiMo Pro only, so the passing suite does not rule out this defect.
2. **Windows completion wording mixes versions.** Clarified current architecture,
   assistant instructions and Phase 3 plan: earlier native matrix success does not
   verify the current build. Historical successful checks remain valid evidence for
   their exact revisions; installation and signing remain distinct gates.
3. **Evaluation README claimed the entire repository has no live adapters/HTTP.**
   Corrected the claim to describe only the offline evaluation harness. Production
   providers remain unchanged.

Previously identified acquisition/error-page filtering and long extraction duration
remain investigations, not newly proven failures. Reproduce them with sanitized
fixtures/timing evidence before changing acquisition or timeout policy. Do not infer
that exact quotation integrity independently proves entailment: the current deliberate
Analyzer Admission policy explicitly retains that limitation.

## Proposed sequence

1. **Resolve accounting first.** Recommended: use each configured route's conservative
   cap for fresh v2 completed usage and retain cache counts as informational metadata.
   Alternatively, introduce explicit model-specific cache pricing only after official
   rate verification and policy approval. Add failing regressions through each real
   routed adapter and persisted budget reconciliation, including failure responses,
   zero/missing/malformed cache counts and unknown usage. Preserve historical stored
   reports and the intentional legacy direct-MiMo contract; do not weaken its test.
   Require full Python/Ruff checks and applicable packaging verification before delivery.
2. **Reproduce acquisition and latency concerns.** Use offline success/error/challenge
   page fixtures and stage timing evidence. Separate transport success from useful
   source text. Only change policy for demonstrated defects; no speculative timeout
   reduction or broad source rejection.
3. **Rebuild and evaluate the chosen target.** Verify the corrected packaged Mac build
   before assessing it. For a Windows pilot, rebuild current source on native Windows,
   then test install, upgrade, vault persistence, history/export and shutdown.
4. **Run a small, explicitly budgeted live acceptance set.** Proposed five fresh runs:
   two supporting-only (including the previous failure shape), one challenging-only,
   one both-direction claim and one scarce-evidence claim. Agree exact claims, enabled
   paid services and total spending ceiling before execution. Record useful admitted
   evidence, exact source context, unresolved gaps, rejection/repair behavior, total
   exposure and wall time. Human review judges usefulness and entailment; a release
   hash alone does not. No requirement that every claim produce support or trigger
   a repair. Supplement uncovered repair/cancellation paths with offline tests.
5. **Close the milestone against the selected target.** Personal Mac acceptance requires
   useful research, trustworthy budget handling and an unaided start→result→history→export
   workflow. A private pilot additionally requires clean-machine checks on its actual
   targets. A public release additionally requires declared minimum-OS checks and
   production signing/notarization. Do not expand features until these results identify
   a concrete need.

## Decisions to make with the user

- First target: personal Mac use, private Mac/Windows pilot, or public cross-platform
  release. Recommend personal Mac acceptance first, then widen distribution.
- Accounting: configured conservative caps (recommended) versus separately verified
  model-specific cache rates. No response is treated as approval.
- Before future live evaluation: exact claims, provider permissions and total budget.
  The current audit authorizes no paid acceptance runs.

## Verification performed during this audit

- Full Python suite: **959 passed, 2 existing skips**, one existing Starlette warning.
- Ruff lint and format: passed, **146 files**.
- Deterministic offline evaluation: **38 cases passed**; optional live comparison skipped.
- Frontend ESLint and TypeScript: passed using existing local binaries. The pnpm wrapper
  attempted registry/dependency preparation and failed; no dependency update was made.
- Git whitespace and current audit/status/handoff documentation link checks passed.
- Synthetic usage probe reproduced the route-pricing mismatch above without network calls.
- Knowledge graph was refreshed without a repository artifact; live source was authoritative.
  No `index_status` tool was exposed in this session.
- No new desktop build, native smoke, browser acceptance or current Windows run was performed
  for this documentation-only audit. Earlier results are attributed to their delivery records.
