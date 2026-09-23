# Neutral evidence ownership

Status: complete; explicitly authorized by the user's 2026-09-23 request after the
completed explicit pipeline-selection phase.

## Scope and design

Move source-snapshot, quotation, untrusted-source, Analyst scoring, drafting and Ledger
admission helpers to neutral root modules. Fresh v2 stages must import those neutral
modules directly and must not reach them through the historical researcher, analyst or
supporting-researcher modules.

Retain the existing `agents.researcher`, `agents.analyst` and
`agents.supportingresearcher` import paths as explicit compatibility facades or historical
retrieval owners. Preserve model fields, validation behavior, public names, persisted
contracts and historical execution. No database, prompt, provider, budget or policy
semantics change is in scope.

## Acceptance

- Fresh v2 modules have no imports from the historical researcher, analyst or supporting
  researcher modules.
- Historical imports resolve to the neutral implementations without changing public
  behavior or model identity within a process.
- A regression test protects the fresh-v2 import boundary.
- Full pytest, Ruff lint/format and diff-whitespace checks pass.
- No dependency, database, prompt, provider, packaging, installation, live call, push or
  publication change occurs.

## Delivery record

`evidence_core.py` now owns source snapshots, quote parsing/selection, deterministic
filtering, candidate verification and the untrusted-source envelope. `evidence_analysis.py`
owns Analyst inputs, score-pair policy, drafting, qualification and Ledger admission.
Historical agent modules re-export these contracts and helpers, while fresh v2 modules
import neutral ownership directly. The existing renderer/synthesizer modules remain
shared final-output owners and were not part of the historical evidence-helper seam.

Verification passed: 1,027 Python tests with two existing skips; Ruff lint/format; and
`git diff --check`. No dependency, schema, prompt, provider, budget, packaging,
installation, live call, push or publication changed. The source identity surface changed,
so exact resume requires new runs; historical inspection and export remain readable.

## Remaining boundary

`orchestrator.py` remains the explicit historical provider-execution boundary and is not
selected by ordinary CLI/controller construction. `models.py` remains the stable public
export facade over the contract implementation modules. Further removal of historical
execution requires a separate explicit compatibility/deprecation decision.
