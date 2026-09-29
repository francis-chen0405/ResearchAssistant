# Documentation audit — 2026-09-28

Status: completed 2026-09-28 as a documentation-only pass authorized by the user.

## Scope and outcome

Reviewed current plan navigation, root documentation, developer/research guidance,
desktop operations, and dated verification records against the live source, schema 14,
and current repository paths. Corrected current schema compatibility wording to say
read-only inspection supports schemas 7–14. Corrected credential transport wording:
OpenAlex and optional PubMed keys go to their respective upstream HTTPS query
parameters. Updated the active-plan pointers and clarified that older package tests,
source-byte comparisons, and installed-app descriptions apply to their dated builds.
The historical verification results and hashes remain intact. The model-guide prices
were rechecked against current official OpenAI and Xiaomi model pages on 2026-09-28.

No source, prompt, archive content, product behavior, installer, or release evidence
changed. Public-release gates remain open.

## Checks

Checked the model catalog, defaults, completion allowances, and configurable profile in
`providers/model_choices.py` and `providers/model_profiles.py`; schema 14 ownership and
read-only schema compatibility in `store_schema.py` and `store.py`; and API-key handling
in `providers/openalex.py` and `providers/pubmed.py`. Checked Markdown links in the
current plan index/current plan set, root documents, `docs/*.md`, `desktop/README.md`,
and the edited verification records for local path and section-anchor resolution:
104 local Markdown targets in 93 tracked/current files resolved. The full pytest run,
with warnings treated as errors, passed with 1,204 tests and 2 existing skips.
`.venv/bin/ruff check .`,
`.venv/bin/ruff format --check .` (162 files), and `git diff --check` passed.
The externally sourced factual claims in `docs/preview-sources.md` were not rechecked;
only its local path and role as a non-pipeline preview fixture were considered.
