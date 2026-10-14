# Phase 10 Evaluations

## Current research-quality benchmark (Prompt 14)

The [bounded protocol](cases/research_quality/PROTOCOL.md),
[exact current baseline/topics](cases/research_quality/prepared.json),
[comparison requests](cases/research_quality/queries.json),
[strict schema](cases/research_quality/schema.json) and
[result template](cases/research_quality/RESULT_TEMPLATE.md) prepare current quality
acceptance without changing production defaults. Run locally:

```sh
.venv/bin/python -m evaluations.research_quality --output-dir /private/tmp/prompt14/prepared --replay
.venv/bin/python -m evaluations.research_quality --manifest evaluations/cases/research_quality/fixture_bundle/manifest.json --output-dir /private/tmp/prompt14/fixture --replay
```

The prepared current-pilot manifest contains **zero current live observations**. Human reference sets
are pending, so live denominators remain unknown. The separate arithmetic bundle
is entirely authored fixture data. The harness validates frozen bytes/ownership,
reports per-stage work metrics, human judgment coverage/abstentions, publication
aliases versus study groups, exact quotation checks, final-statement judgments,
physical requests, elapsed time, known costs and conservative exposure. It keeps
fixtures, replayed observations and newly authorized live observations separate.
Production handoff replay runs normalization/ranking only; it does not execute
models, parse raw HTTP anew, or assert evidence admission/entailment. Read-only
native history inspection also found eight September/October saved runs; the
private [saved-history importer](import_saved_research.py) preserves search,
acquisition and model receipts and replays typed metadata with unknown quality
denominators. This historical availability sample is separate from current live
rankings; original HTTP bodies and exact model inputs remain unavailable.

Locked reference evidence must follow the [canonical reference schema](cases/research_quality/reference-schema.json):
topic, claim digest, useful work list, sampling method, reviewer and lock time are
hashed together and must match the scored manifest. Supporting human records remain
separate hashed artifacts. Complete discovery replay maps exact logical handoffs
to successful physical attempts via `discovery_handoff_attempts` and preserves page
results via `search_attempt_result_paths`. Attempt settings record `query_id`;
query/provider identity and result multiplicity are checked per page. Aggregate
handoffs must preserve complete result values from those pages, allowing subsets
and deduplication; later stage retention dispositions are independent. Historical
handoffs without physical receipts remain explicitly incomplete.

Whole-output support bounds require a complete assertion inventory. Recorded-subset
bounds have explicit names/scope. Work usefulness/relevance disagreements remain
unknown across stage filtering; URL capture grades stay separate. Admission behavior
is distinct from human utility evaluation. Repeated URLs and distinct publication
aliases have separate counts; monetary exposure compares Decimal values.

Saved stage exports validate persisted checksums, types and nested run ownership,
reject recognized credentials before writing, and identify the pinned SQLite read
snapshot (including committed WAL) separately from main-file measurements. Failed
exports remove only their own newly created files. These safeguards were repaired
after the [Prompt 14 review](../.agent/plans/research-quality-acceptance-2026-10-11.md#review-repairs--october-12-2026).

No live adapter or credential integration exists in the scoring runner. The prior
paid allowance is exhausted. The human approved the **$2.48** pilot and collection
with human scores pending. The separate local [preflight](research_quality_preflight.py)
binds approval to input/source hashes before optional native-key availability checks,
without provider transport. [Actual pilot result](cases/research_quality/LIVE_RESULT.md):
all four required native keys missing, account terms unverified, collector unavailable;
zero starts/$0.00 exposure. Human references stay pending. Current live rankings, full-text yield, model
value and interpretation quality remain untested. The two older suites below keep
their existing meanings and frozen corpora unchanged.

## Separate source-discovery evaluation

Run `.venv/bin/python -m evaluations.source_discovery --json-output /private/tmp/source-discovery/results.json --summary-output /private/tmp/source-discovery/summary.md`.
The strict `cases/source_discovery/manifest.json` contains author-created metadata/documents
and independent expected-work rationales for ALPR crime, discrimination, biomedical and
non-scholarly claims, plus disabled and neutral cases. It replays frozen query responses
through the production compiler/ranker and runs production seed transport and acquisition/
exact previews with fakes. Rank-12/18 and citation-only cases use explicit shortlist K=18
and a source target of 20, rather than the product default target of 10.

The report separates recall/precision, unresolved independence, DOI duplication, annotated
preview exactness/relevance, actual usable captures and fake physical request counts.
Metadata transport is replayed locally; its network cost is unmeasured. No model stage runs;
model calls/tokens are zero, total monetary cost is unknown and seed reservation exposure
is reported separately. The capture-aware selection ablation is deterministic and neutral
on the usable pool; it does not execute production model selection, Analyst or admission.
Their gates are covered by separate production integration tests. Fixture gains do not
establish live rankings or research quality and do not redefine the historical corpus below.
Graph results are attributed to exact OpenAlex fixture IDs. Identical titles cannot substitute
another work or acquisition URL, and missing or unknown graph IDs fail the evaluation.
Recall and precision count independent DOI work anchors, so choosing a better publication
alias cannot create a false miss or inflate the number of expected works. Record IDs and
acquisition locations remain separate; title equality never establishes a work alias.

Run the normal deterministic evaluation from the repository root:

```bash
python evaluations/run_evaluations.py
```

If this shell does not expose bare `python`, place the existing repository virtual
environment first on `PATH` without setting `PYTHONPATH`:

```bash
PATH="$PWD/.venv/bin:$PATH" python evaluations/run_evaluations.py
```

The default command reads `evaluations/cases/offline-corpus.json` and writes:

- `evaluations/output/results.json` — strict machine-readable result
- `evaluations/output/summary.md` — human-readable summary derived from the same result

The output directory is ignored except for its `.gitignore`; tests normally direct
outputs to a temporary directory.

Regression fixture manifests store strict frozen outcomes separately from corpus case
expectations. The runner checks both against observed gate behavior, so changing a
corpus expectation cannot silently turn a regression into a passing snapshot.

## What the offline corpus measures

- citation, snapshot-hash, and macro-bracket classification
- unsupported-claim, placement, prompt-injection, and final-validator mutation attacks
- Analyst and Reviewer rejection rates and two-axis score separation
- supporting/opposing retrieval parity
- primary success, retry, backup, and third-line fake-provider routes by stage
- per-alias malformed-output and exact-quote failure rates
- fallback safety across Pydantic, snapshot, post-filter, Reviewer, Ledger, and final
  validator gates
- MiMo V2.5 versus MiMo V2.5 Pro quality delta on identical frozen inputs
- offline Extractor comparison between MiMo V2.5 and DeepSeek V4 Flash
- same-model Analyst/Reviewer correlated-error cases
- cost per successful artifact and completed run from recorded tokens and frozen pricing
- completion time from deterministic completed-run cases

Offline quality scores and pricing are frozen corpus observations. They do not claim to
be current vendor benchmarks or prices and do not change routing defaults.

## Optional live comparison

Live comparison is skipped unless explicitly enabled. The Python API accepts a strict
`LiveEvaluationProvider`; when enabled, every call receives the exact frozen input ID,
input text, model alias, and pinned snapshot from the corpus. Returned observations must
match that identity exactly or evaluation fails.

The command-line `--enable-live` flag deliberately fails unless an embedding application
injects a provider. This evaluation harness contains no built-in live vendor adapter or
API-key integration and makes no network calls in its default offline mode. The production
application separately contains live provider adapters and HTTP clients under `providers/`.

## Exit behavior

- `0`: every required offline invariant passed
- `1`: evaluation completed and wrote a clear failing report
- `2`: corpus, configuration, provider, or output execution error
- `3`: unexpected internal evaluation error

No failing case is skipped. Optional live comparison is the only normal skip and is
recorded explicitly in both outputs.

## Source-lead visibility comparison

Run `python -m evaluations.source_leads --output-dir /private/tmp/source-leads`.
The report uses authored source-disposition fixtures on the two Prompt 14 held-out
topic labels, school-start and green-roofs. Each persists five same-run metadata
leads with skip, Scout-budget omission, failed capture, shell and readable outcomes.
Fixture setup uses three fake acquisition attempts and zero model/live provider calls
per topic. Both display arms share the same saved inputs/capacities. Inspection adds
zero calls and preserves database bytes/mtime. The prior brief-gated view exposes zero
leads without a final artifact; the new view exposes all five. This measures saved
record availability, not human readability, useful recall, source truth, admission
utility or a query-policy winner. Those fields stay unknown. Frozen Prompt 14 files
and approval inputs are not regenerated.
