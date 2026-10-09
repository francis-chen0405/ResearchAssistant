# Phase 10 Evaluations

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
