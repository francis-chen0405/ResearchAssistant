# Storage, evidence, and contract audit

Date: 2026-10-01

## Scope and coverage

Read the assigned runtime modules in full: `store.py`, `store_schema.py`,
`model_contracts.py`, `model_research.py`, `model_evidence.py`, `models.py`,
`provider_contract.py`, `pipeline_artifacts.py`, `pipeline_compatibility.py`,
`evidence_core.py`, `evidence_analysis.py`, `evidence_portfolio.py`,
`evidence_browser.py`, `history_import.py`, `brief_export.py`, `money.py`,
`utils.py`, and `fixture_pipeline.py`. Also reviewed the schema-integrity,
transaction, research-governor, portfolio, read-only, type-contract, evidence,
admission, accounting, and export tests. Checked the current source and callers
for each reported issue. The codebase graph was advisory; its index-status
operation was unavailable, so conclusions below rely on current files and tests.

No live database, application data, credentials, provider, or external service
was accessed. The pre-existing Reviewer-route/UI work was left intact.

## Confirmed defects and repairs

### Research-round terminal timestamp invariant

Before the change, `ResearchRoundRecord` required `completed_at` on terminal
statuses but accepted a completion timestamp on `PLANNED` or `RUNNING`. The
store API only checked that a timestamp existed, so an invalid in-memory record
could be persisted. Repository runtime callers write completed/terminal round
records; no fixture or caller found depended on persisting a nonterminal round.

`model_contracts.py` now rejects completion timestamps for nonterminal statuses,
and `store.py` independently rejects nonterminal records even if model
validation was bypassed. Added model tests for both nonterminal states and a
store-boundary test using `model_construct`. Before the fix these states were
accepted; after the fix `tests/test_mvp11_research_governor.py` passes (21 tests).

### Evidence candidate provenance binding

Before the change, `verify_candidate_against_snapshot` checked snapshot
identity/hash and quote offsets but accepted candidate records with a different
run ID, retrieval attempt, source URL, retrieval timestamp, or snapshot
creation time. A quote ID could be recomputed over a forged URL, so quote-ID
integrity alone did not bind the URL to the retrieved snapshot. The Phase-9
analyst input contract also omitted those snapshot metadata comparisons.

The central verifier in `evidence_core.py` now checks those five provenance
fields. `model_evidence.py` applies the corresponding checks at the analyst
input boundary. The comparison uses the snapshot's `source_url`, the URL of
the actual captured snapshot; redirect provenance remains represented by the
existing `original_url` and `canonical_url` fields. New constructed regressions
cover foreign run and retrieval IDs, forged URL with a recomputed quote ID,
retrieval and snapshot timestamps, analyst-input rejection, and Ledger
admission through the central verifier. Before the fix the forged verifier
cases were accepted; after the fix the focused quote, analyst, and admission
suites pass (116 tests).

### Exact USD addition across exponent ranges

Before the change, `add_usd` sized Decimal precision from coefficient lengths
alone. Under a precision-2 ambient context, adding `1` and `1e-60` returned `1`
and adding `1e50` and `1` lost the unit. The first regression run failed on
those two cases and passed the five other cases.

`money.py` now sizes precision after aligning nonzero coefficients to the
smallest exponent, with additional room for carries across addends. The new
tests also cover ordinary fractional sums, scaled and widely-exponented zero,
large-plus-subunit addition under altered ambient precision, and rejection of
negative values and signed zero. Negative amounts are outside the validated
USD domain, so cancellation between positive and negative inputs is not a
supported operation; exact preservation is tested for all accepted inputs.
After the fix, all assigned focused tests pass: **176 passed** across money,
research-governor, evidence provenance, quote/analyst/admission, portfolio,
and accounting suites.

## Assessed, not changed

`RunManifest.validate_completion` requires `completed_at` for `COMPLETED`, but
does not require it for `BLOCKED`, `FAILED`, or `CANCELLED`, and does not reject
a timestamp on `RUNNING`. Current terminal writers set completion times, and
some tests construct terminal manifests with those timestamps, but that does
not establish the persisted-history contract for older records. Since this
audit has no evidence that older terminal rows always have `completed_at`, I
left the lifecycle hypothesis unchanged rather than tightening a persisted
record validator without compatibility evidence.

## Verification

- Before money repair: `tests/test_audit_money.py` — 2 failed, 5 passed; both
  failures demonstrated lost low-order values from exponent alignment.
- After repair: focused assigned test set — 176 passed.
- Research-round focused suite — 21 passed.
- Evidence focused quote/analyst/admission suite — 116 passed.
- No schema change, migration, dependency, provider call, or live-data access.
