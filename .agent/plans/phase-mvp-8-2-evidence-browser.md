# MVP-8.2 — Evidence Browser

## Authority and Boundary

The user explicitly authorized MVP-8.2 on 2026-08-10 after MVP-8 and MVP-8.1 were
confirmed complete and verified. This plan adds a local, read-only evidence browser for
an existing run. It must reuse the validated SQLite inspection boundary and must never
create, migrate, update, or otherwise mutate a database.

## Scope

- Define frozen strict Pydantic view models for a run-level evidence trail, released
  statement trace, filters, source provenance, stage decisions, and explicit browser
  failures.
- Reconstruct source snapshots, source URL provenance, exact quotations, stance,
  candidate validation, Analyst decisions, Reviewer decisions, Ledger records, and
  final validation through the existing read-only store session.
- Let an operator select a released factual statement and trace it to its Ledger record,
  Reviewer approval, quotation, trusted snapshot, and source provenance.
- Support deterministic filtering by stance, stage, source URL, approval/rejection
  state, and release status.
- Clearly label trusted snapshot text, provider metadata, and untrusted source text;
  label blocked and rejected artifacts without representing them as released.
- Add the browser as a separate local Streamlit surface or through established safe
  read-only live-service boundaries, while keeping the fixture UI separate.

## Non-Negotiable Invariants

- Every browser artifact is a strict Pydantic model using
  `ConfigDict(extra="forbid")`; internal boundaries use models rather than raw
  dictionaries.
- The browser uses only the validated `ReadOnlyStore`/read-only inspection path. It
  never calls `init_db()`, applies a migration, opens a writable fallback, or changes
  database bytes.
- Browser content is inspection-only: no editing, approval, revalidation, release,
  or artifact mutation action exists.
- Browser view models and UI must not expose secrets, credentials, authorization values,
  or provider request headers. Provider metadata remains explicitly non-authoritative.
- Existing evidence, Reviewer, Ledger, synthesis, and release-validator policy is
  unchanged. Historical records remain readable under their existing compatibility
  rules.
- No dependency, account, collaboration feature, cloud storage, web retrieval, provider
  behavior, multi-claim comparison, or change-evidence feature is introduced.

## Likely Implementation Surfaces

- `models.py`, `store.py`, and a narrow read-only browser service for typed
  reconstruction and explicit compatibility/corruption failures.
- `frontend/live_service.py` and a dedicated local browser page for display only.
- A focused `tests/test_mvp8_2_evidence_browser.py` module and narrow updates to
  existing inspection/UI tests where needed.

## Verification

- Add regression tests before implementation for released-statement navigation,
  filtering, rejected/blocked labeling, redaction, missing/corrupt/incompatible
  databases, and byte-for-byte non-mutation.
- Run focused browser coverage, then full `pytest`, `ruff check .`,
  `ruff format --check .`, deterministic evaluation, and `git diff --check`.
- Confirm no generated databases, reports, credentials, caches, new dependencies, or
  live calls are added. Update `STATUS.md` and `HANDOFF.md` only after successful
  completion.

## Out of Scope

- User accounts, collaboration, cloud or remote persistence, web retrieval, provider
  changes, artifact editing, multi-claim comparison, change evidence, Reviewer/Ledger
  policy changes, synthesis changes, release-validator changes, and dependency changes.
