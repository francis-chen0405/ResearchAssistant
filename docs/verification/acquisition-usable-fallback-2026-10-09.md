# Acquisition after unusable captures — 2026-10-09

## Scope and reproduction

Prompt 03 authorized a bounded offline correction. HEAD was `94a241b52f9525cab3aff52d1f85026f081b3e85`
on `master`. The original `/private/tmp/researchassistant-quality-unusable-capture-94a241b.py`
was rerun before edits: an `OSF` shell caused one scraper request, one acquired shell and
zero usable sources. An empty landing page caused two requests and one usable source.
Both cases used production clustering and acquisition with fake providers and disposable
SQLite storage. The shell's allowed alternate contains substantive methods and null results.

The unrelated staged root cleanup, unstaged citation-expansion correction and untracked
foundation proposal/prompt pack remain preserved. No staging, commit, branch switch,
fetch, push, installation, real research database mutation or live provider call occurred.
AGENTS, conventions, invariants, architecture, decisions, status, handoff, acquisition tests
and current identities were checked. The graph's acquisition signature was stale despite
its ready status at the correct HEAD; fast re-indexing refreshed discovery and traces, which
were verified against live source. A Luna Medium helper performed read-only test/convention
search; Sol retained the reproduction, policy reasoning, implementation and verification.

## Behavior and identities

Fresh production acquisition selects **`researchassistant-v2-phase-5-acquisition-probe-v4`**.
Explicit v1, v2 and v3 retain their original dispatch and serialization. The historical
production fingerprint remains frozen; the fresh compiler-v3 binding's existing schema
fingerprint now names Probe v4 and includes its expanded policy schema. No discovery,
preview, seed, selection, evidence-admission or database version is relabeled by this task.
Changed executable/source identity and binding hashes require a new research run under the
existing exact compatibility gate. Completed historical artifacts remain readable and are
never repaired. Low-level acquisition also binds its exact policy/input controls before
work; attempting to resume a v3 artifact with v4 fails before transport.

V4 tests observable capture usability inside the ordered acquisition loop. It uses the
existing preview capture classification and substantive-text gate, then the existing
claim-independent capture windows and quote-length floor. Claim terms, preview relevance
scores, desired evidence relationship and agreement with the claim cannot trigger a retry.
Readable unrelated and null-result captures stop normally. Acquired text remains separate
from usable survivor status, model selection, Analyst assessment and final evidence admission.

Known provider PDF locations keep their existing preference. URL and method limits,
configured lower cluster/URL bounds, per-request timeouts and provider adapter boundaries
remain authoritative. A second method stays optional and requires an eligible failure
with independently verified preflight; an unusable successful capture may authorize it
only with verified HTML provenance. Bare content-type claims do not authorize fallback.
The current path deduplicates locations actually tried (including actual resolved URLs);
untried alternates are no longer marked acquired merely because another location succeeded.
Source cluster and discovery-direction ownership do not move between captures.

## Durable capture and accounting trail

Each dispatched scraper attempt has immutable `v2_artifacts` entries under
`<stage-key>/captures/<cluster-id>/<requested-url-sha256>/<provider>`:

- `/start`: run, cluster, direction, requested location, provider, policy, timeout,
  independently verified request preflight and original timestamp, committed before invocation.
- `/response`: exact typed response or known failure and original dispatch, committed before
  local snapshot/assessment processing. Exceptions with unknown outcomes retain the start.
- `/completion`: outcome, response, source snapshot when nonempty and usability flag.
  Each location/method owns distinct snapshot/retrieval IDs even for identical text/redirects.

These records distinguish dispatch, nonempty acquisition and usable capture. They make no
admission claim. Empty returned text is preserved exactly in the response record: it cannot
inhabit the historical nonempty `SourceSnapshot` contract. A provider failure without returned
text has no invented snapshot. No cost is synthesized or refunded; existing model/provider
budget and adapter accounting remains authoritative, and unknown physical exposure is retained.

The established aggregate handoff keeps one selected acquired source per cluster; earlier
unusable snapshots remain in the capture journal and can be inspected with validated
`ReadOnlyStore` plus `read_v2_artifact`. All physical scraper outcomes remain in aggregate
attempts after successful stage completion. Cancellation preserves individual records and
prevents a cancelled v4 stage from writing its aggregate output. Restart reuses completed
captures or saved responses without another provider call. A start without returned data
or completion requires a new run, including when the provider is unavailable on restart.
Local assessment after a saved response may resume; historical captures are never reparsed
or silently changed under a successor policy.

## Offline results

| Case | Requests before (v3) | Requests after (v4) | Outcome |
| --- | ---: | ---: | --- |
| OSF shell → allowed study | 1 | 2 | Before: 0 usable. After: 1 usable; shell and study retained separately. |
| Empty landing → allowed study | 2 | 2 | 1 usable; exact empty response retained, study snapshot retained. |
| Both captures unusable | — | 2 | 0 usable; both nonempty snapshots retained with distinct IDs. |
| Lower one-URL cap | — | 1 | 0 usable; alternate prevented by unchanged lower budget. |
| Cancel after shell, then restart | — | 2 total | Shell reused; only the alternate adds a request. |
| Readable null/unrelated first | — | 1 | Usable first capture; no search for a favorable alternate. |

The original probe was loaded unchanged and rerun with the successor identity injected
only into its policy selection. Historical v3 still produces its original shell failure.
The permanent regression file is `tests/test_acquisition_usable_fallback.py`; it additionally
covers known PDF first, duplicate/shared/untried locations, optional verified-HTML fallback,
timeouts, cancellation before dispatch/during a readable call, unknown primary/fallback
attempts with absent providers, restart after local processing interruption, immutable rows
and read-only inspection of earlier snapshots. Existing historical-dispatch, extraction,
preview, source-selection, provenance and budget regressions remain enabled.

Final checks on macOS arm64 / Python 3.12.14:

- **2,304 passed, 3 existing skips in 207.49 seconds**: `.venv/bin/python -m pytest -q`.
  Final log: `/private/tmp/acquisition-final-verified-pytest.log`.
- **23 new cases**; **89 focused integration cases** passed, covering acquisition,
  preview/inspection, source selection, existing agent review, ranking and seed transport.
- Ruff lint and format checks passed across **299 Python files**; repository root/import
  boundaries and staged/unstaged plus new-file whitespace checks passed.
- Historical offline evaluation: **38 cases passed**. Fresh source-discovery evaluation:
  **six synthetic scenarios passed**, using production transport/acquisition with fakes.
  Reports: `/private/tmp/acquisition-verified-evaluation/` and `evaluations/output/`.
- The unchanged historical probe and the successor injection both passed; final comparisons
  are in `/private/tmp/acquisition-historical-probe.json` and
  `/private/tmp/acquisition-successor-probe.json`.
- Final advisory graph refreshed to **9,593 nodes / 66,227 edges** at the same checkout/HEAD.

These results establish offline behavior and accounting/provenance retention. They do not
measure live full-text yield or provider/model quality. No native build or delivery was
required for this backend-only change; the installed app remains unchanged.
