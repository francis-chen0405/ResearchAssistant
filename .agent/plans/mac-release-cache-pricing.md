# Mac-first release and model-aware cache accounting

Status: implementation authorized by the user's 2026-09-17 follow-up. macOS is the
first release target; Windows acceptance is deferred and does not block this milestone.
This narrowly extends the completed adaptive-search boundary for pricing correctness,
the configured Luna High request, Mac packaging/verification and release documentation.

Implementation and unsigned Mac delivery are complete, including the user-authorized
reliability extension below: 992 Python tests, Ruff, offline evaluation, native/upgrade/
packaged/installed checks and archive integrity pass. Latest app is installed and downloads
are in `desktop/dist/mac-reliability/`. See
[delivery evidence](../../docs/verification/planner-scout-reliability.md).
Live acceptance remains open: the original five-submission allowance is exhausted,
with no completed final report and $0.178617536 recorded model exposure. Do not run more
paid tests without a new explicit allowance. Public release remains blocked by live
acceptance and the stated signing/clean-machine/minimum-OS requirements.

## Authorized reliability follow-up

After live testing exposed initial-planner contract rejection and repeated Scout
truncation, the user explicitly selected "Fix research reliability first" before
public distribution. This extends this plan to evidence-led planner/Scout corrections,
offline regressions and a rebuilt Mac candidate. Preserve validation, historical data,
existing budget/retry ceilings and provider choices. No new dependencies or speculative
timeout changes. The original five-submission allowance is unchanged; further paid
acceptance requires separate authorization. The completed acceptance used the original
frozen candidate and cannot verify later fixes.

The user also explicitly chose larger responses within the same total run budget after
Gap Analysis and Source Selection truncation. Standard profile output allowances are
4,096 Scout / 8,192 Pro / 16,384 Luna High. Full allowances must reach request payloads,
preflight/physical reservations and frozen configuration identity consistently. Keep
legacy defaults and total run/source/retry ceilings; verify insufficient budgets fail
before transport. No timeout increase is part of this change.

## Deliverables

1. Verify current official Luna and MiMo token/cache rules. Add regressions before
   fixing the shared-adapter pricing defect; account for Scout as well as Pro and Luna.
   Keep conservative pre-call reservations and unknown-usage exposure. Only apply
   published discounts to verified model/provider identities and valid usage metadata.
   Preserve historical artifacts, existing direct-Pro pricing tests and schema 13.
2. Ensure the named Luna High route actually requests High reasoning; verify the
   outbound payload without paid calls. Do not change model selection or stage policy.
3. Run full Python/Ruff checks, offline evaluation, frontend checks and Mac packaging,
   native-vault/runtime/window/upgrade smokes where available. Generate DMG/ZIP and
   verify their integrity and packaged source identity. No dependency additions planned.
4. Document actual release readiness: Developer ID signing/notarization and actual
   clean-machine/minimum-OS evidence remain required for public release. Prepare an
   unsigned test candidate if signing is unavailable; never label it public-ready.
5. Update current authority/status/handoff and exact verification evidence. Preserve
   the earlier audit and phase history. No Windows work, paid research without an
   explicit budget decision, or remote publication is inferred from this plan.

## Pricing evidence and safety

Official sources reviewed during implementation:

- https://developers.openai.com/api/docs/models/gpt-5.6-luna
- https://mimo.mi.com/docs/en-US/price/pay-as-you-go

Luna High is an effort setting on `gpt-5.6-luna`, not a separate tariff. The model
page lists $0.20 input / $0.02 cache read / $1.20 output per million tokens, a 1.25x
cache-write rate and full-request long-context multipliers above 272,000 input tokens.
MiMo overseas Pro lists $0.435 input / $0.0036 cache read / $0.87 output; Scout lists
$0.14 / $0.0028 / $0.28. Cache writes are currently free for MiMo.
Investigate available usage fields before claiming an exact cache-write split. If the
API does not expose it, charge possible writes conservatively and label costs estimates.

## Decisions / external requirements

- User selected Mac first and authorized researched cache pricing; neither is pending.
- User has no Apple Developer membership/certificate: prepare an unsigned downloadable
  Mac test release and explain Gatekeeper limitations; signing/notarization remain open.
- User explicitly approved at most five research prompts under the proposed combined
  $5 model ceiling and existing search/acquisition quotas. Use isolated test history;
  never exceed five new research runs, including failed runs. Do not replay a failed
  prompt outside that allowance. Public sample claims are sufficient.
- Never request private keys/passwords
  in chat or weaken vault permissions, tests or release gates to complete the task.
