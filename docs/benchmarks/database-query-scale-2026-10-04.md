# Database query scale benchmark — 2026-10-04

The reproducible benchmark is [scripts/benchmark_database_query_scale.py](../../scripts/benchmark_database_query_scale.py); its complete JSON output is [database-query-scale-2026-10-04.json](database-query-scale-2026-10-04.json). It compares the committed schema-16 evidence browser at `b25df1d` with the current schema-17 reader using disposable SQLite databases. No repository, build, or user database was used as a benchmark target.

Each size uses 501 total runs, including 500 unrelated history rows with running, completed, failed, and cancelled states. The target released run has 2, 10, 40, or 1,000 candidates. Every candidate has one Analyst decision, statement draft, Reviewer decision, and Ledger row; each references one of two shared snapshots with 65,536 bytes of synthetic source text and a matching SHA-256. The 1,000-candidate case crosses the browser's 500-key query chunk boundary. The benchmark compares the complete typed browser output, including filtering inputs, provenance, source text, release traces, and metadata.

| Candidates | Schema 16 SELECTs | Schema 17 SELECTs | Schema 16 related-table queries | Schema 17 related-table queries | Output |
| ---: | ---: | ---: | ---: | ---: | --- |
| 2 | 21 | 15 | 11 | 6 | Equal |
| 10 | 69 | 15 | 51 | 6 | Equal |
| 40 | 249 | 15 | 201 | 6 | Equal |
| 1,000 | 6,009 | 19 | 6,001 | 10 | Equal |

At 1,000 candidates, the extra four SELECTs are the second bounded batch for each candidate-related child table. The snapshot set has only two unique IDs, so it is fetched once. Empty runs are covered by a regression that confirms no child-table queries run; pending and terminal/released behavior remains covered by the existing browser decision and evidence-browser tests.

## Plans and indexes

Schema 16 plans full scans plus a temporary sort for history, candidates, and drafts. Reviewer reads use an index on `run_id` alone and sort into a temporary B-tree; Ledger reads scan the primary-key index. Schema 17 removes the sort for history and uses direct lookups that satisfy each evidence ordering:

- `runs(updated_at DESC, run_id ASC)` supports the public history order and stable tie-break.
- `candidates(run_id, extracted_at, quote_block_id)` supports candidate selection and display order.
- `statement_drafts(run_id, quote_block_id, drafted_at)` supports per-candidate draft reads.
- `statement_review_attempts(run_id, quote_block_id, reviewed_at, statement_draft_id)` supports the existing review order and preserves the prior tie order from its `(run_id, statement_draft_id)` key.
- `ledger_records(run_id, quote_block_id, ledger_claim_id)` supports candidate Ledger lookup and explicit Ledger ordering.

The Analyst table already has a unique `(run_id, quote_block_id)` index, so migration 17 adds none. The query indexes are strict schema objects introduced atomically with migration record 17. The migration reuses matching pending indexes and rolls back index creation when ledger insertion fails.

## Timing and memory

The benchmark reports one first call and a median of the next three calls; the filesystem cache was uncontrolled, so the first sample is not a cold-cache result. Each timed call includes schema validation, database open/close, typed reconstruction, and Python object allocation. The table shows measured milliseconds and traced peak Python allocation:

| Candidates | Schema 16 first / warm median | Schema 17 first / warm median | Peak Python MiB, schema 16 → 17 |
| ---: | ---: | ---: | ---: |
| 2 | 4.68 / 4.37 | 4.47 / 4.61 | 0.19 → 0.20 |
| 10 | 7.80 / 7.94 | 6.68 / 6.64 | 0.86 → 0.36 |
| 40 | 22.04 / 21.68 | 15.29 / 18.96 | 3.34 → 1.01 |
| 1,000 | 1,379.87 / 1,410.57 | 388.37 / 416.32 | 82.27 → 20.92 |

Small-run timings are similar and should not be read as a user-interface benchmark. The larger measurements show reduced repeated-query and duplicate source-text reconstruction work in this synthetic workload. SQLite's native allocator and operating-system cache are not included in `tracemalloc`'s memory figure. `list_runs(limit=100)` returned 100 rows from the 501-run database in 1.36 ms on this run; that is one local measurement, not a latency guarantee.

The operation-count regression asserts six related-table queries at 40 candidates and bounded chunk counts at 1,000 candidates. It does not use wall-clock thresholds.
