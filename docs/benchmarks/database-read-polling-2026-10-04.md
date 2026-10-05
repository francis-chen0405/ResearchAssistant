# Validated status polling benchmark

Run with:

```sh
PYTHONPATH=. .venv/bin/python scripts/benchmark_read_polling.py \
  --rows 10,1000,20000 --journal-modes DELETE,WAL \
  --payload-bytes 4096 --polls 5 \
  --output docs/benchmarks/database-read-polling-2026-10-04.json
```

The script creates and removes isolated databases. Each poll opens a fresh
`ReadOnlyStore`, performs the full physical and semantic schema validation,
reads one run, and closes the store. “First” is the first application-level
poll; all cases share the OS page cache, so it is not a disk-cold measurement.
The warm number is the median of the following five polls. The writer scenario
updates one run and commits every 2 ms while polling proceeds. Memory is peak
Python allocation tracked by `tracemalloc` for the poll sequence, not SQLite
page cache or total process resident memory. WAL file sizes include remaining
`-wal` and `-shm` files after the connections close; no explicit checkpoint is
run by the benchmark.

| Runs × claim | Mode | Main + sidecars | First poll, quiet/writer | Warm median, quiet/writer | Writer commits (median wait) | Poll errors | Peak Python allocation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 × 4 KiB | DELETE | 436 KiB | 3.43 / 3.94 ms | 3.11 / 4.36 ms | 11 (0.98 ms) | 0 | 100 KiB |
| 10 × 4 KiB | WAL | 597 KiB | 3.23 / 3.08 ms | 3.10 / 3.29 ms | 14 (0.13 ms) | 0 | 100 KiB |
| 1,000 × 4 KiB | DELETE | 4.90 MiB | 5.11 / 4.18 ms | 4.54 / 6.03 ms | 13 (1.04 ms) | 0 | 100 KiB |
| 1,000 × 4 KiB | WAL | 9.48 MiB | 6.06 / 4.52 ms | 4.39 / 5.41 ms | 17 (0.12 ms) | 0 | 100 KiB |
| 20,000 × 4 KiB | DELETE | 90.75 MiB | 29.60 / 29.23 ms | 32.44 / 53.42 ms | 22 (0.61 ms) | 0 | 101 KiB |
| 20,000 × 4 KiB | WAL | 181.8 MiB | 30.31 / 31.80 ms | 30.67 / 31.51 ms | 68 (0.11 ms) | 0 | 113 KiB |

The exact samples and byte counts are in
[database-read-polling-2026-10-04.json](database-read-polling-2026-10-04.json).
The 20,000-row WAL database retained a 95.3 MiB WAL file plus its shared-memory
file after the benchmark workload, while the main database was also about 90.8
MiB. This disk footprint and the untested checkpoint lifecycle are reasons
these timing results alone do not justify enabling WAL in production. The
rollback-journal cases had no busy polls or writer busy retries in these runs;
the large rollback-journal case did show higher poll latency with writes.

This benchmark uses a status-read proxy (`read_run`) rather than a full desktop
controller snapshot, so it measures validation and one point read only. Its
results do not represent desktop UI cadence or the installed research database.
