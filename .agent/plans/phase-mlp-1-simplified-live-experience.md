# MLP-1 — Simplified Live Experience

## Authority and boundary

The user explicitly authorized MLP-1 on 2026-08-14. MLP-1 improves the local live
website and launcher experience without changing the evidence pipeline, provider
boundaries, budgets, persistence, Reviewer/Ledger admission, or deterministic release
gate.

This first MLP-1 slice removes research depth, presentation tone, report length, and
focus inputs from the live website. New website runs use the existing frozen safe
`DEFAULT_RESEARCH_CONTROLS` (`standard`, `report`, `neutral`, no focus). The typed
controls and their persisted fingerprint representation remain readable for CLI and
historical-run compatibility.

## Required behavior

- The live start form contains no depth, tone, length, or focus controls.
- The live status view does not expose a research-controls metadata dump.
- Website-created runs always use `DEFAULT_RESEARCH_CONTROLS`.
- Existing persisted runs, exact fingerprints, resume checks, exports, CLI controls,
  and internal typed contracts remain compatible.
- No database migration, dependency, provider call, or release-policy change occurs.

## Verification

- Added focused Streamlit regression coverage for the removed controls.
- Focused live-web/control tests passed: 29.
- Complete offline `pytest` passed: 605 with 2 expected opt-in skips.
- `ruff check .`, `ruff format --check .`, and `git diff --check` passed.
- Rendered-browser inspection confirmed that none of the removed controls remain.

## Remaining MLP-1 work

Secure one-time credential storage, easier macOS startup, and the broader visual
redesign remain separately reviewable MLP-1 slices. They are not implemented by this
control-removal slice.
