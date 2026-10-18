# Current status

[Prompt 15 source dispositions](../../.agent/plans/source-leads-quality-2026-10-13.md)
adds inspectable same-run source leads even without a released brief. Saved URLs/work
IDs, ranking/Scout omissions, capture/readability, selection, analysis and admission
reasons are visible with explicit unknowns. Titles and search directions remain
metadata; snippets are never verified evidence. Rendering starts no provider calls.

## Verified current source

October 13, 2026, macOS 26.6.2 arm64 / Python 3.12.14:

- Full Python suite: **2,778 passed / five existing skips in 232.89 seconds**.
  Focused view/API/adapter/acquisition/product/type/preflight regressions: **88 passed**;
  broader safety/benchmark/resume integration: **290 passed** before final refinements,
  also covered by the final complete suite. No assertion or timeout was weakened.
- Two **authored held-out visibility fixtures** expose **5/5 saved leads per topic**
  without a final brief, versus zero in the earlier brief-gated view. Both arms share
  saved inputs/capacities. Setup uses three fake acquisition attempts and zero model/
  live provider calls per topic; inspection adds zero calls and preserves bytes/mtime.
  [Report](../../evaluations/cases/source_leads/offline_results.json) keeps useful
  recall, human readability and query-policy effects unknown.
- Existing evaluations pass: **38 historical integrity cases**, **six synthetic
  discovery scenarios**, prepared quality replay (zero observations) and the authored
  arithmetic bundle (one fixture observation). Reports are in `/private/tmp/prompt15/`.
- Ruff lint/format passes **467 Python files**; repository boundaries, generated API
  contract parity and working/staged whitespace pass. Frontend lint/types and the
  desktop static build pass. All five offline browser smokes pass, including source
  leads without a brief, bounded pagination, history expansion, snippet/quote exclusion
  and read-only requests. Desktop unit tests pass **20 cases**; native shutdown smokes
  pass with approved local process access. Sandbox-only process/loopback attempts
  initially failed because those capabilities were denied; no check was weakened.
- The API reads a bounded inventory from one validated read-only snapshot, closes
  it before projection, validates saved ownership/checksums/physical page receipts,
  preserves individual capture outcomes, and rejects overflow/corruption. Existing
  release, quotation, source-family, budget/checkpoint and exact resume tests pass.
- Advisory graph refreshed without persistence: **12,351 nodes / 75,692 edges**.
  HEAD stays `94a241b52f9525cab3aff52d1f85026f081b3e85` on dirty local `master`.
  Earlier staged binary-diff hash remains
  `85f8753d0bb6ba7af20c688eab28ad10429ee43329b879d89b8db48071324cf2`.
  No staging, commit, branch switch, fetch, push, real-history/vault access or app
  replacement occurred. Current backend identity is
  `source-sha256:0d0b1c93c8528b9c096e1160defd06f7dcea8013df26ffe4ef7deec2c86eda74`.

## Quality and authorization boundary

No current live provider responses or human usefulness/entailment labels became
available. SERP quoting/verbatim behavior and narrow OpenAlex groups remain verified
implementation facts with **unmeasured useful-recall effects**. Compiler/discovery v3,
Probe v4, prompts, model routing and budgets are unchanged; no query winner is chosen.
There is no new provider or autonomous search loop, and no paid comparison was run.

Prompt 14's frozen [allowance](../../evaluations/cases/research_quality/allowance.json),
inputs and [zero-spend preflight receipt](../../evaluations/cases/research_quality/preflight.json)
remain unchanged. Its $2.48 cap was approved for the exact old inputs/runtime, but
current source drift rejects that pilot before credential access. New comparisons
require their own bounded authorization and genuine captured responses/human labels;
fixture visibility does not satisfy live policy acceptance. The old five-submission
allowance remains exhausted. Historical released records remain readable and immutable.

The installed app is still the [October 9 build from `27aeb95`](../verification/current-app-install-2026-10-09.md)
at `/Applications/ResearchAssistant.app`; it does not contain these changes. No installer,
clean-machine, Python 3.11/Linux, native Windows, minimum-OS or signing/notarization
acceptance was added. [HANDOFF](HANDOFF.md) owns the next boundary. The
[exact preceding current-state documents](../archive/2026-10-13-source-leads-preceding-state/README.md)
and prior task records remain at stable paths.
