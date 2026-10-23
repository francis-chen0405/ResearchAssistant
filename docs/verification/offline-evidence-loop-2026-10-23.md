# Offline evidence-loop evaluation — October 23, 2026

Task 6 evaluates the uninstalled e359 worktree, with the reviewed PDF capture
(task 3) and post-analysis evidence round (task 1) present together. Git HEAD is
detached at `131c7924541144d294b3ea265f7c6b9942f679e6`; these changes are
uncommitted. The advisory code graph was ready at that HEAD. Live source and tests
confirmed the orchestrator calls the post-analysis round after initial admission;
the live acquisition adapter calls the bounded PDF normalizer. The graph missed the
normalizer's acquisition caller, so it was not used as proof of that edge.

## Read-only historical baseline

The real `live-runs.sqlite3` was opened only with SQLite `mode=ro&immutable=1` and
`query_only=ON`. Three saved diagnostic runs were inspected without replaying or
rewriting them. Every stored v2 artifact payload matched its saved SHA-256: **251/251**
for `4fa0dcb5-b7f2-4167-b627-2a9eae710ff3`, **377/377** for
`437cc6f6-b63b-401d-8bec-e14c1992b35e`, and **324/324** for
`e9a97839-0178-443f-8af2-8c3c3b10e2e5`. The database main-file SHA-256 was
`870f75c0b5befc4de91f4af8f3a812bcf882e2a5d7c3efd6d6249766a137c65e`
before and after inspection; its size and modification time were unchanged. No
historical judgments, quotes, citations, fingerprints, charges or reservations were
changed. The [earlier saved-run review](extinction-risk-retry-review-2026-10-21.md)
records the actual IPBES capture as 3,054 words through page 8, ending in
acknowledgements. That old capture was not regenerated here.

## Controlled observations

| Check | Observed result | Boundary |
| --- | --- | --- |
| PDF capture | A generated 30-page PDF retained numbered pages 1–30 under the 12,000-word cap. A finding on page 25 remained an exact 94-character snapshot slice at offsets 100550–100644; normalized-text SHA-256 matched. The crowded 100-page fixture also retained a finding beyond page 25's opening. | Generated documents, not the IPBES report. |
| Preview and quotation | The late finding reached claim preview and the bounded extraction view; tests checked source-owned offsets and rejected a quotation crossing `[PDF text omitted]`. | Exact quotation and provenance, not claim truth. |
| Assessed feedback | The disposable production run persisted a gap input containing an assessed source finding, then selected Round 2 with one new source. The original admission remained the prefix of the combined admission and read-only evidence inspection accepted it. | The fixture model supplied the gap judgment. |
| One-round bound | The full disposable run completed Round 2 only; adequate coverage, no useful novel action, duplicate source, degraded follow-up, exhausted budget, cancellation, unknown request and Round-4 timing cases passed. | No open-ended controller or live search. |
| Accounting and replay | Four fake search requests and 11 fake model requests yielded 11 durable physical starts and 11 completions; `physical_calls_used=11`, below the 160-call ceiling. A released-run replay made zero model or search calls, kept the audit identical and left the disposable database byte-for-byte unchanged. Separate unknown-attempt tests kept reserved token/cost exposure and prevented duplicate dispatch. | Costs and usefulness of actual providers remain unknown. |

The focused task 3/1/recovery suite passed **29/29**; the physical-reservation,
replay and PDF-deadline selection passed **10/10**. The existing frozen integrity
evaluation passed **38 cases**, with optional live comparison skipped. The source
discovery evaluation completed all **six synthetic scenarios**. That discovery
runner does not execute Analyst or admission, so its recall and preview scores are
not evidence-loop quality measurements. The full Python suite was rerun for this
evaluation: **3,235 passed, 12 skipped in 472.14 seconds**. Ruff lint and format
(531 files), repository boundaries, and staged/unstaged whitespace checks passed.

The first focused attempt used a shared virtual environment without this worktree
on the PDF subprocess import path; two worker tests failed before PDF parsing. The
same selection passed 29/29 after setting `PYTHONPATH` to this worktree's root and
`backend/src`. Test databases were disposable files under pytest `tmp_path` or a
`/private/tmp/ra-task6-disposable-*` directory; the latter was removed at exit.
Offline evaluation outputs were written under `/private/tmp/ra-task6-e359-*`.

## Conclusion and remaining decision

The offline controls passed for the constructed cases. There is no joint fixture
that feeds a generated PDF finding through the entire model assessment and
post-analysis search loop; capture-to-preview/quote and assessment-to-follow-up were
tested separately. No new live IPBES capture or human evidence judgment was made.
Consequently this does **not** establish better live research quality. The installed
build remains `20261020.6`; no app installation, paid research, dependency install,
commit or push occurred. A fresh installed build and a separately authorized live
run are the next possible quality check. Provider/page scheduling and truthful
partial-unknown reporting remain separate open issues.
