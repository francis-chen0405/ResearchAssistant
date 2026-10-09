# Repository review — 2026-10-08

## Scope and method

The user authorized a repository-wide review and fixes, using GPT-6 Luna helpers
for discovery and implementation while retaining Sol for harder reasoning and
integration. Three Luna High helpers reviewed providers/evaluations; storage,
platform support, contracts and evidence; frontend/web/desktop, documentation and
research agents. Additional passes covered query execution, ranking, previews,
seed expansion and test isolation. Sol reviewed runtime/orchestration, integrated
the changes, and repaired packaging and execution identity.

The initial checkout was master at `0841975f0c86c857a1666e84f151c482051acea9`.
It contained seventeen untracked root Python copies and untracked proposal docs.
Those files were preserved; three copies received import-only repairs. Current
production entry points use the canonical package. Inactive root copies are now
excluded from bundled source data and executable fingerprints.

The user subsequently authorized committing the review fixes. The commit includes
the active-source changes, regressions and documentation. Pre-existing untracked
copies and proposal documents remain outside the commit; the three import-only
repairs to those inactive copies remain local.

The advisory graph reported ready at this HEAD but retained old root paths and
omitted current package paths. Automatic approval review rejected a refresh
because of possible repository-content transmission to an unverified service.
Discovery therefore used the existing graph where useful and local files, diffs
and tests as authority. No further refresh was attempted.

Historical Markdown snapshots and dated verification reports retain their original
claims and evidence. Current guidance was checked against executable behavior.
This review does not establish that no undiscovered issue remains.

## Confirmed findings and repairs

| Area | Finding | Result |
| --- | --- | --- |
| Exports | Resolving a dangling symlink bypassed the existing-file check; a concurrent create could be overwritten. | Lexical destination checks and exclusive creation preserve other files; failed writes clean up only the owned partial file. |
| Model retries | Extraction and optional source selection retried explicit terminal provider failures. | Terminal errors stop after one attempt; transient failures retain bounded retries and selection retains its deterministic fallback. |
| Acquisition resume | A skip-only cached result had no preview carrying the claim, so changed inputs could replay. | Persisted input binding covers claim, discovery, policy, components, gaps and exclusions before acquisition. |
| Extraction resume | Only the aggregate result was durable, so interruption could repeat completed sources; replay did not bind all inputs. | Stable input binding and per-source checkpoints reject changed inputs and reuse completed sources. |
| Historical resume | Terminal prior-policy results bypassed exact-claim checking. | Changed claims are rejected without starting provider work. |
| Relocated databases | Resumed terminal results reported the stored original database path. | Returned results use the requested path while stored historical payloads remain unchanged. |
| CLI display | Launch output advertised obsolete MiMo routes regardless of selected models. | Every stage displays its actual configured alias and physical model. |
| Desktop resources | Directory merging and reused Node unpack trees retained obsolete generated files. | Node extraction uses a fresh temporary tree and resource staging replaces complete trees. |
| Source packaging | Every root Python file was bundled and hashed, including inactive untracked prior implementations. | Only the four documented root compatibility entry points are included; canonical package sources remain covered. |
| Evaluation inputs | Duplicate scenario IDs could overweight aggregate metrics; duplicate expected-work IDs were accepted. | Both duplicate forms are rejected by manifest validation. |
| Test isolation | Seven API tests reached the actual application-data folder or preferences. | Default database and preference I/O use temporary test paths; runtime privacy checks remain enforced. |
| Documentation | Grouped history claimed nineteen verification files while its directory contained twenty-one. | The count now matches the retained verification files. |
| Inactive root copies | Three untracked prior modules had imports broken by package moves. | Imports reference canonical package paths without replacing their existing bodies. |

Regressions exercise symlinks, concurrent export creation, interrupted writes,
terminal/transient retries, claim and input mismatch, extraction checkpoint
interruption, relocated databases, selected model display, stale build files and
inactive source exclusion. Existing integrity and integration tests remain intact.

## Verification

Initial full-suite baseline: **2,207 passed, 7 failed, 3 skipped** in 172.57 seconds.
All seven failures were API test isolation defects described above.

Final full-suite verification on macOS arm64/Python **3.12.14**: **2,232 passed,
3 existing skips in 200.51 seconds**. Whole-workspace Ruff lint and format pass
across **312 Python files**, including the import repairs in untracked copies.
Web ESLint, TypeScript, Next.js **16.3.1** webpack desktop static export, desktop
shell syntax and whitespace checks pass. Offline evaluation passes **38 cases**;
strict discovery evaluation completes **six synthetic scenarios**. Web checks
use installed Node tools directly because the pnpm wrapper attempted a registry fetch.

No paid provider calls, application installation, installer publication or native
Windows verification were performed. The changed source has not been built into
a new distributable or installed application. Existing live-quality, Windows,
cache, signing and clean-machine acceptance gates remain in [STATUS](../../STATUS.md).
Source identity changes require a new run under the existing compatibility gate.

Exact preceding current-state files are retained in the
[repository-review archive](../../docs/archive/2026-10-08-repository-review-state/STATUS.md).
