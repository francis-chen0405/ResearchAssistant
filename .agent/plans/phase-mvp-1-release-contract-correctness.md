# Phase MVP-1 - Release-Contract Correctness

## Purpose

Close three verified post-Phase-10 release-contract defects without starting provider,
network, frontend, live CLI, dependency, extraction-candidate, deduplication, or database
redesign work.

## Scope

- Make brief title, displayed-claim label and text, structural headings, and structural
  order application-owned.
- Remove title, displayed claim, and arbitrary headings from the model-facing
  Synthesizer schema.
- Add deterministic validation for allowed section types, canonical section order, and
  model-supplied framing fields before release hashing.
- Add a strict model-facing Reviewer decision that cannot carry an approval ID.
- Validate the exact reviewed statement and decision shape before deriving an
  application-owned `rappr_v1_<digest>` approval ID.
- Preserve the existing persisted/domain `StatementReviewResult` shape and readability
  of legacy UUID approval IDs where practical.
- Persist validation-blocked fixture runs as `RunStatus.BLOCKED`.

## Canonical Reviewer Approval ID

The `rappr_v1` SHA-256 input is canonical JSON with sorted keys and compact separators.
It contains only:

- `derivation_version`: `rappr_v1`
- `reviewer_schema_version`: `reviewer-decision-v1`
- `statement_draft_id`
- `quote_block_id`
- `reviewed_statement` (exact text)
- `decision`: `approved`

Timestamps, provider request IDs, response formatting, route metadata, token usage, and
other unstable invocation metadata are excluded.

## Files Expected to Change

- `models.py`
- `agents/reviewer.py`
- `agents/synthesizer.py`
- `agents/renderer.py`
- `orchestrator.py`
- `store.py`
- `prompts/reviewer.md`
- `prompts/synthesizer.md`
- relevant Phase 1, 2, 4, 5, 6, 8, 9, and 10 tests and fixtures
- focused `tests/test_mvp1.py`
- `DECISIONS.md`
- `STATUS.md`
- `HANDOFF.md`
- `.agent/PLANS.md`
- this plan

## Compatibility Strategy

- Keep `StatementReviewResult` as the persisted/domain result produced after application
  approval-ID derivation.
- Accept legacy UUID reviewer approval IDs when reading existing persisted review,
  Ledger, synthesis, and fixture artifacts.
- Write new application-generated IDs in the `rappr_v1_<digest>` format.
- Keep the existing SQLite synthesis framing columns for schema compatibility, write
  only application constants into them, and ignore their legacy contents when
  reconstructing the framing-free `SynthesisOutput` domain artifact.
- Update checked-in synthesis fixtures to the framing-free schema; keep checked-in
  legacy Reviewer-result fixtures readable.
- A completed synthesis checkpoint backed by a legacy SQLite synthesis row remains
  readable because framing columns are ignored. A pre-MVP-1 serialized `SynthesisOutput`
  cached before synthesis-row/checkpoint completion is rejected on restart and requires
  a fresh run; it is not silently migrated or accepted as a current checkpoint artifact.

## Acceptance Criteria

- Model-authored title, claim text, headings, and other framing prose are rejected.
- Rendering always uses `Research Brief`, the fixed claim label, the authoritative
  submitted claim, and application-defined headings.
- Unexpected, duplicate, or reordered sections block release and receive no hash.
- The Reviewer LLM schema rejects `reviewer_approval_id` and altered reviewed text is
  rejected before any ID is created.
- Approved decisions receive stable application IDs; rejected decisions receive none.
- Revision, persistence, restart, and checkpoint behavior remains deterministic.
- Valid fixture persistence is completed/released and validation-blocked fixture
  persistence is `RunStatus.BLOCKED` after reopening SQLite.
- Focused and relevant phase tests, the full suite, offline evaluation, fixture CLI
  smoke tests, persisted-status checks, Ruff, `git diff --check`, and final Git status
  pass.

## Explicitly Out of Scope

- Live providers, SDKs, network calls, `.env` loading, dependencies, or live CLI work
- Streamlit or other frontend changes
- Multi-candidate extraction or cross-stance deduplication
- Database triggers or unrelated schema redesign
- Automatic commits
