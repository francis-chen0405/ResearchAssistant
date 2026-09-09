# Current decisions

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
The ivory/grid presentation and fictional interactive preview share real workspace components.
Support only the established MiMo/Luna role combination; expose roles and conservative
maintained caps without claiming arbitrary model compatibility. Profile resolution copies
configuration before startup, and the first planner reservation is validated offline.
No dependency or broader research behavior change was needed.

A denied old-to-new Keychain smoke exposed confusing password guidance. Both frozen backends
were ad hoc signed with different designated identities; macOS required renewed access and
returned -128 on cancellation. Clarify the system password versus provider API key in Settings
and sanitized errors. Preserve OS vault access controls. Cross-version credentials remain
unverified; stable production signing and user-granted access must be verified separately.

Follow-up 2026-09-08: the explicitly authorized isolated cross-version credential test
passed unchanged. This supersedes the unverified local upgrade result above; production
signing and Windows verification remain separate gates.
