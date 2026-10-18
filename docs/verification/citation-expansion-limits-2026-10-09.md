# Citation-expansion limit investigation — 2026-10-09

## Result and scope

Prompt 02 authorized offline investigation and correction only for reproduced defects.
The pasted claim had no traceback; the later 63 passing targeted tests did not confirm it.
This investigation reproduced two specific failures, without establishing which case the
original reviewer intended.

Checkout: `master` at `94a241b52f9525cab3aff52d1f85026f081b3e85`, one commit ahead of
the local tracking reference. The 34 pre-existing staged root-cleanup paths and untracked
foundation proposal/prompt pack are preserved. No branch switch, fetch, staging, commit,
push, installation, credential read, paid call or real research database write occurred.
Every new case uses temporary SQLite databases and fake transport.

Read current AGENTS, conventions, architecture, decisions, status, handoff and the
[discovery plan](../../.agent/plans/source-discovery-v2-2026-10-05.md). The earlier graph
retained obsolete paths. Fast indexing refreshed the checkout and correction: **9,541 nodes /
65,649 edges**, ready at the same branch/HEAD under project
`Users-francischen-Library-CloudStorage-OneDrive2-EastsidePreparatorySchool-GitHub-ResearchAssistant`.
Graph discovery/traces were verified against live source and both diffs; no graph artifact
was written to the repository. A Luna Medium helper searched documents; Sol retained
policy analysis, reproduction and implementation.

## Reproduced before production edits

The initial three parameters in [the regression matrix](../../tests/test_seed_expansion_limits.py)
failed before the correction: **3 failed in 7.09 seconds**. Tracebacks remain in
`/private/tmp/ra-expansion-regression-before.txt`.

1. **Graph responses omitted from shared retention.** With valid retention caps of 25,
   three ten-neighbor actions authorized ten each. The third wrote five raw candidates before
   `insert_raw_candidate` raised `ValueError: run raw-candidate cap is exhausted` (or the
   round equivalent). `retention_headroom` counted text pages only.
2. **Replay changed the parser limit.** Persist ten reference records, interrupt before
   their parser checkpoint, then accept three records from another relationship for that
   seed. Replay recomputed seven and persisted a seven-record parser. Raw validation reparsed
   at the immutable physical start's original ten-record limit and raised
   `ValueError: Parser checkpoint differs from exact provider response`.

The actual round caller catches either exception as a failed search; execution degrades.
The replay regression now also consumes all ten seed slots before replay. Both seven-remaining
and zero-remaining cases pass. Re-run the corrected policy with:

```sh
.venv/bin/python -m pytest tests/test_seed_expansion_limits.py tests/test_seed_expansion_review.py -q
```

## Correction and invariants

Fresh bindings freeze **`source-seed-expansion-v3`** through the existing seed identity and
prompt/schema fingerprint. Version catalogs admit v3 while historical defaults stay unchanged.
Prior v1/v2 serialization and dispatch retain their meanings. An existing binding cannot be
relabeled v3; changed source/settings require a fresh run under the exact compatibility gate.

V3 charges completed graph primary responses once toward shared round/run retention, even
before parser/candidate checkpoints. Identity requests consume physical budget but do not
count as retained neighbors. Returned records are charged conservatively, including duplicates
and exclusions. Current acceptance excludes its own already charged response from headroom.

A prior primary start supplies its original `requested_records` for replay. The requester
returns owned completed bytes or rejects failed/unknown starts without another send. Exact
parser/body/hash, seed/action and raw/edge checks stay intact. Acceptance separately applies
current seed/run/retention limits; rejected parsed neighbors retain explicit dispositions.

Exhaustion returns empty results and preserves an immutable **pending** boundary when partial
state may resume, following the discovery plan. It does not fail the caller. Exhausted offers
disappear; completed results replay without transport. Unknown outcomes retain exposure and
stop transport; graph failures do not retry.

Physical reservation/completion logic is unchanged: atomic reservation precedes each send,
counts text/identity/graph/retry starts, charges the greater of reservation and reported actual
cost, and rejects request/cost exhaustion or unknown outcomes. No refund, increased quota,
new request, migration, model stage, evidence gate, source-family change, executable prompt
edit or dependency was introduced.

## Boundary matrix

The dedicated file contains **37 offline cases**, supplemented by existing integrity,
integration, race and historical tests. All sends and exposure below are simulated.

| Boundary | Case and acceptance result |
| --- | --- |
| 3 seeds | Four eligible distinct papers select three; alias regressions preserve distinct capacity. |
| 10 neighbors/seed, 30/run | Three seeds return ten each across Rounds 2/3: six sends, $0.006 reservations. Exhausted offers disappear; a planned exhausted action returns empty without another send. Aggregate case covers v2/v3. |
| Depth 1–10 | Every valid integer bounds over-return and replays without a send. Actions reject 0, 11, bool and fractional values before reservation; adapter 0/11 reject before its requester. |
| Lower round/run retention | Under cap 25, actions retain 10/10/5 without partial failing insertion. Run-cap case spans Rounds 2/3, limiting the later round despite its independent round headroom. |
| Shared text/graph retention | Cap 25: text 20 then graph 5, or graph 10 then text 15. Three sends; zero headroom; next search sends nothing. |
| Default round retention 300 | Graph 10 + OpenAlex text 100 + arXiv 120 + SERP Search 70 = 300: 17 sends inside provider ceilings. Next OpenAlex search is empty with no send despite physical headroom. Round 3 retains its own 300 slots. |
| Shared 10-request/$0.01 ceiling | After 8/9/10 zero-cost-reported text sends, graph completes with two sends / retains identity with one / sends nothing. Starts never exceed ten; reservations remain $0.01; replay adds no send. |
| Cost ceiling before call ceiling | Two reported $0.005 completions exhaust $0.01; graph sends nothing despite only two starts. |
| Retries/unknowns | After eight text starts, known-cost 503s use only two remaining starts; unknown-cost failure stops at nine. Exposure remains $0.01/$0.009. Graph 429/timeout sends once, never retries; timeout retains $0.001 and blocks another later action. |
| Replay after headroom changes | A ten-record response followed by 3 or 10 other accepted neighbors yields 7 or 0 accepted records on replay. Parser retains original ten; starts/completions stay immutable; total sends remain three. |
| Seed revisited in allowed rounds | Six references in Round 2 plus another relation in Round 3 or authorized Round 4 retain four more. Identity reused, three sends. Further relation sends nothing; Round 5 offers nothing. |
| Round 2–4 callers | Identity-only capacity yields successful empty outcomes through actual `_execute_searches` in every round. Round 4 uses typed policy and persisted Governor permission. Existing authorization/lane/terminal tests pass. |
| History/provenance/resume | Race, parser/raw/body forgery, evidence-chain, historical-read/build/identity checks pass. Relabeling prior binding to v3 rejects without changing serialized bytes. |

## Changed files

- `researchassistant/research/seed_expansion.py`: version dispatch, exact physical-limit replay and current acceptance limits.
- `researchassistant/storage/query_retrieval_store.py`: shared text/graph retention.
- `researchassistant/research/query_execution.py`: fresh v3 binding/fingerprint.
- `researchassistant/contracts/discovery_v2.py`, `researchassistant/contracts/neighborhood.py`: version catalogs; historical defaults preserved.
- `researchassistant/storage/discovery_store.py`, `agents/v2_round_four.py`: existing strict checks/planning gates also accept v3.
- `tests/test_seed_expansion_limits.py`: deterministic reproducer and matrix.
- `tests/test_seed_expansion_runtime.py`: configurable fixture policy and binding-derived action identity.
- `tests/test_seed_expansion_review.py`: aggregate caps for both policies, exhausted continuation.
- This record, discovery plan navigation, history and concise current guidance.

## Verification

macOS arm64, Python 3.12.14, Node 24.18.0:

- Initial targeted baseline: **68 passed in 8.58 seconds**; missing boundaries remained uncovered.
- Focused expansion/neighborhood/query/store/race/build/desktop/historical/type checks: **188 passed in 50.14 seconds**.
- Full Python suite: **2,281 passed, 3 existing skips in 198.14 seconds**.
- Ruff lint/format, fast root/import guard and working/staged whitespace: pass; **298 Python files** formatted.
- Web ESLint/TypeScript and desktop shell syntax: pass with installed tools. An initial ESLint invocation used the root directory; rerunning in `web` corrected the command, without a code/config change.
- Offline evaluation: **38 cases pass**; discovery evaluation: **six scenarios pass**, unchanged manifest `bc1038d52ae027ed4e131a77257b29e8c9a81bd3cd522b9393127ebe58a42c67`.
- Logs/results use `/private/tmp/ra-expansion-*`. No live-quality claim or new installed artifact.

Acceptance rests on the reproduced failures, passing regressions and quota matrix. The
installed app remains the `27aeb95` build; this local source correction needs separately
authorized delivery and a fresh research run.
