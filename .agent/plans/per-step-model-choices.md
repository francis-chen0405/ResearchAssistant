# Per-step model choices and codebase audit

Authorized 2026-09-23. This plan supersedes the completed neutral evidence ownership
phase for this bounded implementation. Mac-first release gates, prior paid-test limits,
evidence policy, database schema and historical run data stay in force.

## Scope

Fresh v2 Planner, Scout, Gap Analysis, Search Agent, Source Selection, exact Extractor
and Evidence Analyst each choose independently from GPT-6 Luna High/XHigh, MiMo v2.6
Pro/Flash, GPT-6 Sol High and GPT-5.6 Terra High. Scout and Extractor default to Luna
High; the other stages default to Luna XHigh. Deterministic stages have no selector.

Desktop preferences, research-start API and ordinary CLI runs use the same typed
defaults. The CLI accepts repeated `--model STAGE=CHOICE` overrides. A model-options
API exposes the six choices; a selection-aware setup check validates only selected
provider credentials and enabled search providers. Saved desktop preferences migrate
on read to the new `configurable-2026-09` profile. The prior `standard-2026-09` profile
and historical run inspection/resume checks remain available.

Every selected call uses its frozen official endpoint, provider model ID, reasoning
or thinking setting, stage output allowance, key and conservative price cap. Selected
choices enter the run fingerprint, so a changed choice requires a new run. The default
model budget is $0.20, explicitly selectable up to $20. Existing call/token limits,
strict typed output validation, evidence rules and conservative accounting stay intact.
No paid provider calls or new dependencies are authorized by this plan.

## Verification and audit

Mocked offline tests cover all 42 stage/choice combinations, outbound settings,
mixed credentials, pricing, budget limits, preference migration and route identity.
Run the full Python, Ruff, frontend and offline desktop checks. After implementation,
a GPT-5.6 Luna High helper scans code, tests, configuration and documentation read-only
for related contradictions or bugs. A GPT-5.6 Luna XHigh helper fixes confirmed findings;
review those changes and rerun affected and required full checks. Record actual results,
remaining limits and next phase guidance in `STATUS.md` and `HANDOFF.md`.

## Outcome

Implemented and audited on 2026-09-23. The Luna High read-only audit confirmed five
related issues: old desktop smoke mocks, old-model-only connection checks, an upgrade
assertion predating preference migration, credential-save readiness without selections,
and stale current authority documentation. Luna XHigh fixed each issue. The final full
suite passed 1,122 Python tests with two existing skips, Ruff lint/format, frontend
TypeScript/ESLint/export, the interaction and polling browser smokes, and rebuilt
native backend/window self-tests. The isolated upgrade smoke passed once during the
fix pass; two reruns after the final backend rebuild timed out waiting for a startup
line, while both backends passed separate self-tests. No paid provider calls, schema
migration, dependency additions, installer, push or publication occurred.

## 2026-09-25 GPT-6 Luna selection update

The user requested replacing the two active GPT-5.6 Luna choices with GPT-6 Luna High
and XHigh while keeping the other four choices. New runs route both choices to
`gpt-6-luna` with the selected reasoning effort. Fresh desktop, API and CLI defaults
continue using High for Scout and exact extraction and XHigh for the other active steps.
The model options catalog, conservative route caps and current documentation are updated.
Saved stage selections migrate GPT-5.6 Luna IDs to matching GPT-6 Luna IDs on read while
preserving other selections; historical Standard routes, the low-level no-selection v2
compatibility route, and saved run identities remain compatible.

Verification passed: 1,124 Python tests, with two existing skips; Ruff lint and format;
diff whitespace checks; frontend ESLint, TypeScript and desktop static export; the offline
interaction and status-polling browser checks; and all 42 stage/choice routes through
mocked provider APIs. The final GPT-5.6 Luna High audit found no confirmed active-route
issues. No provider API calls or credits were used. The refreshed arm64 app is installed
at `/Applications/ResearchAssistant.app`; artifact integrity, bundle contents, checksums
and the local frozen-smoke limitation are recorded in `HANDOFF.md`.
