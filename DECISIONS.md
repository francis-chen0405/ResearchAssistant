# Current decisions

## 2026-09-17 — Reliability before distribution

The user explicitly selected research reliability as the next milestone. Correct the
demonstrated fresh planner schema/default contradiction and reduce new Scout batches to
20 based on successful smaller live batches. Keep generic historical coverage schemas,
all evidence validators, two-attempt Scout limit and global budgets unchanged. Round 4
must reserve for the smaller batches. This extends the active Mac/cache plan; it does
not replenish the five-submission test allowance. See
[reliability evidence](docs/verification/planner-scout-reliability.md).

## 2026-09-17 — Mac first and verified cache accounting

The user selected macOS as the first delivery target and deferred Windows. They
authorized official pricing research and correction for Luna High/MiMo Pro; the shared
Scout route is included to prevent cross-model accounting. Reservations keep existing
caps. Completed usage uses verified model/endpoint-specific cache rates, including
Luna cache writes and long-context multipliers; uncertain cache metadata stays conservative.
Luna's configured High effort is now explicit in the request, with standard service tier
on the official endpoint. Historical usage/reports remain unchanged; new source requires
new runs. No dependencies or database migrations are introduced.

The user has no Apple Developer membership/certificate. Deliver an unsigned downloadable
Mac test candidate; signing/notarization and clean-machine/minimum-OS acceptance remain
public-release limitations. The package now declares the documented macOS 14 floor.
The user authorized at most five research prompts under the proposed combined $5 model
budget plus existing search/acquisition quotas. Test history is isolated; no remote
publication or account purchase is authorized. See the
[active plan](.agent/plans/mac-release-cache-pricing.md) for evidence and outcome.

## 2026-09-14 — Authorized adaptive-search reliability correction

The user's implementation request extends Phase 3 only for the approved corrective plan.
Fresh plans receive an exact-claim coverage default and atomic full-artifact persistence.
Round-aware gap instructions preserve stable Gap identity. Round 2/3 permit one bounded
repair with persisted diagnostics and physical-call linkage, current budget checks and
unchanged downstream reserves. Unknown attempts are never silently reissued; no automatic
fallback query is added. Round 4 keeps its existing Governor authorization and call limits.

Fresh source-selection handoffs explicitly select conservative gap reporting. Relevant
admitted evidence does not prove gap resolution; latest strategy coverage is distinct from
final proof. Old handoffs retain legacy reporting and stored reports remain unchanged.
No dependency or database migration is introduced. Changed executable/prompt identity still
requires a new run. Acquisition quality, pricing and timeout changes remain separate work.

## 2026-09-06 — Phase 2 code and documentation cleanup

Use coherent implementation modules behind stable public imports. Shared domain
contracts, v2 strategy contracts and v2 evidence/results have one-way dependencies.
Fixture execution is separate from historical provider execution. Schema/migration
code is separate from typed persistence/read-only readers. Live request/view models,
progress projections and history readers are separate from worker and lock ownership.
Shared application identity and exit codes no longer require importing the CLI.

Preserve existing schemas, SQL/migrations, policy identities, prompt bytes, strictness,
immutability, prices/accounting, cancellation and release gates. Source layout changes
naturally change executable fingerprints and require new runs; do not relax resume.
No dependency is added and no historical execution/read/export contract is deleted.
Existing native platform boundaries are retained because Phase 1 already separated
paths, preferences, file locks, credential vaults and process trees.

The old requirement to define every model in `models.py` and every schema in
`store.py:init_db()` is superseded by this explicitly authorized refactor. Public imports
and writable initialization remain compatible. This is an organization change only.

Current documentation replaces accumulated chronological descriptions with architecture,
invariants, operating instructions and concise state. Exact pre-cleanup files remain in
[the archive](docs/archive/README.md); historical phase plans retain stable paths.
`prompts/*.md` remain executable application inputs and are untouched.

## Retained runtime decisions

- [Desktop packaging](docs/archive/pre-phase-2/DECISIONS.md#2026-09-05--phase-1-local-desktop-packaging):
  Electron, static Next.js, PyInstaller backend, separate locked Node/Wigolo/Chromium;
  native vaults and portable data paths. The earlier master-only instruction applied
  to Phase 1; Phase 2 uses the user-requested `codex/` branch.
- [V2 production cutover](docs/archive/pre-phase-2/DECISIONS.md#2026-08-21---researchassistant-v2-phase-12-production-hardening-and-cutover):
  fresh website/CLI execution uses v2; all physical attempts count against one budget.
- [Analyzer Admission](docs/archive/pre-phase-2/DECISIONS.md#2026-08-26---researchassistant-v2-phase-13-analyzer-admission-cutover):
  one Luna assessment/statement call, deterministic admission and synthesis, no fresh
  Reviewer call, explicit reduced semantic-verification disclosure.
- [Conditional Round 4](.agent/plans/phase-v2-14-conditional-round-four.md):
  bounded Governor authority, stable Gap identities and deterministic reconciliation.
- Native vault persistence, immutable evidence, exact quotations/provenance, separate
  score axes, conservative accounting, read-only history/export and exact resume
  remain mandatory as stated in [ARCHITECTURE.md](ARCHITECTURE.md).

Earlier choices and their supersessions remain in the
[complete decision history](docs/archive/pre-phase-2/DECISIONS.md). Historical policy
text describes its original contract; it is not authorization for current changes.

## 2026-09-07 — Phase 3 frontend and provider/model settings

The user's explicit Phase 3 request supersedes the previous prohibition on frontend work.
Use the existing Electron/static Next.js/Python architecture and native credential vault.
The ivory/grid presentation and local interactive preview share real workspace components;
the preview was later refined with curated public report excerpts.
Support only the established MiMo/Luna role combination; expose roles and conservative
maintained caps without claiming arbitrary model compatibility. Profile resolution copies
configuration before startup, and the first planner reservation is validated offline.
For the Phase 3 frontend/settings scope, no dependency or broader research behavior change
was needed. The later adaptive-search correction is recorded above.

A denied old-to-new Keychain smoke exposed confusing password guidance. Both frozen backends
were ad hoc signed with different designated identities; macOS required renewed access and
returned -128 on cancellation. Clarify the system password versus provider API key in Settings
and sanitized errors. Preserve OS vault access controls. Cross-version credentials remain
unverified; stable production signing and user-granted access must be verified separately.

Follow-up 2026-09-08: the explicitly authorized isolated cross-version credential test
passed unchanged. This supersedes the unverified local upgrade result above; production
signing and Windows verification remain separate gates.
