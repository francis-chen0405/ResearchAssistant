# MVP-8 — Briefs, Export & Performance

## Authority and Boundary

The user explicitly authorized MVP-8 on 2026-08-10. MVP-7.1 is complete; this plan is
the canonical active phase plan. MVP-8 improves released-brief presentation, adds local
traceable export, and makes persisted progress and restart reuse clearer without changing
evidence, Reviewer, Ledger, validation, provider, or release policy.

## Scope

- Build strict typed export request/result/metadata artifacts.
- Export only a read-only reconstructed RELEASED run whose final validation is valid and
  whose rendered brief re-hashes to the persisted `rendered_brief_hash`.
- Generate local Markdown, PDF, and Word `.docx` reports. Every report records run ID,
  rendered-brief hash, format, exporter version, and timezone-aware generation time.
- Keep Markdown byte-deterministic for the same released artifact and supplied generation
  timestamp; use only standard-library document containers/encodings so no dependency is
  added.
- Improve the readable released-brief layout using application-owned headings, citations,
  approved connective text, and required warnings only. Exact Reviewer-approved factual
  statements remain byte-for-byte unchanged.
- Add explicit persisted-progress summaries and ensure a failed compatible restart skips
  completed, valid checkpoints rather than repeating their work.
- Expose local CLI export and improve inspection/live-status progress wording.
- Add regression coverage for all successful formats, rejection of blocked/failed/
  cancelled/running runs, metadata integrity, deterministic Markdown, readable output,
  progress reporting, and valid checkpoint reuse.

## Non-Negotiable Invariants

- Internal handoffs are strict Pydantic models with `ConfigDict(extra="forbid")`; raw
  dictionaries appear only at serialization/export boundaries.
- Exports never create a release, repair a validation result, mutate the run, or hide
  one-sided-evidence or human-review warnings.
- A report cannot alter, paraphrase, merge, omit, or add to an approved factual sentence.
- Exports are local files only. No accounts, cloud sharing, external storage, live calls,
  provider changes, or dependency additions are permitted.
- Exact claim/fingerprint compatibility, immutable artifacts, Ledger admission, Reviewer
  approval, and final validation remain the authority for release eligibility.

## Out of Scope

- Comparing multiple claims, user accounts, cloud sharing, provider changes, live calls,
  evidence/release-policy changes, schema migration, or new dependencies.

## Verification

- Run the full offline pytest suite, `ruff check .`, `ruff format --check .`, the
  deterministic evaluation, and `git diff --check`.
- Confirm all new export paths remain local and that no generated report, database,
  credential, or cache artifact is tracked.

## Completion Record

Complete on 2026-08-10. The full offline suite passed 557 tests with two expected
opt-in skips. Ruff lint/format, deterministic evaluation, and `git diff --check`
passed. No dependency, live call, cloud export, external storage, or schema migration
was added.
