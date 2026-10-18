# Root cleanup and repository guardrails

Scope: Prompt 01 on October 9, 2026, in the ResearchAssistant checkout on macOS
arm64/Python 3.12.14. Local `master` HEAD is
`94a241b52f9525cab3aff52d1f85026f081b3e85`; local `origin/master` remains
`27aeb95ca0b6c6999ba34b2cfd60c5b84a49200c`. This is a local cleanup, not a backend
relocation or one of the behavior repairs in the foundation proposal.

## Verified deletion inventory

The pre-existing staged diff contains exactly 17 whole-file root deletions,
10,335 lines. Each removed file has a live canonical owner below. None required
a dependency repair before deletion.

| Removed root copy | Canonical owner under `researchassistant/` |
| --- | --- |
| `application_runtime.py` | `runtime/application_runtime.py` |
| `brief_export.py` | `evidence/brief_export.py` |
| `credential_store.py` | `platform_support/credential_store.py` |
| `desktop_settings.py` | `platform_support/desktop_settings.py` |
| `evidence_browser.py` | `evidence/evidence_browser.py` |
| `evidence_portfolio.py` | `evidence/evidence_portfolio.py` |
| `fixture_pipeline.py` | `research/fixture_pipeline.py` |
| `history_import.py` | `storage/history_import.py` |
| `model_contracts.py` | `contracts/model_contracts.py` |
| `model_evidence.py` | `contracts/model_evidence.py` |
| `model_research.py` | `contracts/model_research.py` |
| `money.py` | `common/money.py` |
| `pipeline_artifacts.py` | `research/pipeline_artifacts.py` |
| `research_governor.py` | `research/research_governor.py` |
| `store_schema.py` | `storage/store_schema.py` |
| `utils.py` | `common/utils.py` |
| `v2_orchestrator.py` | `research/v2_orchestrator.py` |

The audit checked staged deletion contents, canonical source, all tracked live
Python imports (including function-local/type-only imports and literal dynamic
imports), and filename/build/identity references. No live bare import of a removed
module remains. The old files are stale implementations rather than required
facades. For example, the old PDF escape helper has already been replaced by the
package PDF renderer; evidence browsing uses the package's bounded read-only
reconstruction; direction types are imported from `contracts/research_directions.py`.

Only `cli.py`, `models.py`, `orchestrator.py`, and `store.py` remain as root Python
files, both on disk and in the Git index. The CLI launcher and three module aliases
retain canonical object identity, as verified by compatibility tests and CLI help.
`desktop/build.py` explicitly stages these four root entries. The runtime identity
explicitly selects the same four plus package/agent/provider/frontend/prompt sources,
dependency metadata and PDF fonts.

An isolated source tree restored all 17 exact HEAD copies alongside the live
identity surface. Identity before and after restoration was identical:
`source-sha256:c8a3543a1f77f20586586e8487fb22130c6fe71f50ad3c3c582cfbfb1ba2805f`.
Existing bundle/fingerprint tests already verify the explicit root selection,
inactive-copy exclusion, canonical sources, fonts/prompts and frozen identity.
They were retained; the missing tracked-root enforcement is covered by the new
guardrail regressions rather than seventeen repetitive bundle tests.

## Guardrail implementation and baseline review

`scripts/check_repository_boundaries.py` uses only the Python standard library
and Git. CI runs it before the full suite; `tests/test_repository_boundaries.py`
also runs it through pytest. The root allowlist is independent of build/runtime
selection so a packaging change cannot silently authorize a root copy. Tests
verify rejection of both staged and committed copies in a disposable repository.

The AST check includes all static imports under contracts/storage, including lazy,
type-only, aliased, relative and nested-package imports. Contracts cannot add
providers/agents; storage cannot add agents. Future canonical provider/agent paths
are covered too. Symbol/source occurrence counts reject additional symbols,
duplicate import declarations and moved exceptions. Removed imports require
baseline removal. Computed/dynamic imports are outside this deliberately small
check; they must not be used to evade it.

The six current exceptions in `scripts/dependency-boundary-baseline.json` were
reviewed against their live consumers:

- Neighborhood contracts embed `ResolvedOpenAlexWork` and `SearchResult`.
- Parsed-page checkpoints embed `SearchResponse`.
- Discovery persistence imports the acquisition artifact key to verify immutable
  preview input.
- Historical decoding subclasses `V2ExactExtractionResult` and
  `ResearcherRetrievalBatch` for explicit historical-policy support.

These exceptions preserve existing behavior; neutralizing their contracts/constants
is a separate focused migration. Each JSON entry records its reason. Maintainer
instructions for intentional changes and ratcheting are in
[CONVENTIONS](../project/CONVENTIONS.md#packaging-and-verification).

The old `ResearchAssistant` graph was ready at this HEAD but retained removed root
paths. A fast refresh produced a fresh map, returned by the tool under project
`Users-francischen-Library-CloudStorage-OneDrive2-EastsidePreparatorySchool-GitHub-ResearchAssistant-researchassistant`.
Search and inbound tracing found the canonical identity owner and CLI/backend,
discovery policy, live controller and tests. Important conclusions were independently
verified against live source; graph output was advisory.

## Verification

- Focused guardrail, cleanup, desktop/build/identity and annotation checks:
  **46 passed in 6.11 seconds**.
- Full Python suite: **2,243 passed, 3 existing skips in 204.63 seconds**.
- Ruff lint: passed. Ruff format: **297 files already formatted**.
- Staged and unstaged whitespace checks: passed, including the final staged review diff.
- Standalone root/import guard: passed in **0.122 seconds**.
- All five prior-document snapshots byte-match HEAD. Existing archived documents
  were preserved; [the new snapshot](../archive/2026-10-09-root-cleanup-state/)
  retains prior STATUS, HANDOFF, ARCHITECTURE, CONVENTIONS and plan index.

Packaging/identity validation here is offline regression coverage and exact source
identity comparison. No new native bundle/installer, installation, paid research,
provider call, user-data modification, remote CI verification or publication occurred.

## Git boundary

The 17 pre-existing staged deletions are preserved. Cleanup checks and documentation
are staged alongside them for one consistent reviewable diff. The pre-existing
untracked `docs/proposals/project-foundation-2026-10-09.md` and
`docs/proposals/project-foundation-implementation-prompts/` remain unchanged and
untracked. No cleanup commit or push was made. Local HEAD is one commit ahead of
the unchanged local tracking reference; no fetch occurred, so current remote state
was not reverified. The cleanup exists only in the local index/working tree. Final state: **34 staged
paths (17 deletions, 8 modifications, 9 additions)**, no tracked unstaged changes,
and the two pre-existing untracked proposal paths listed above.
