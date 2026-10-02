# Approved ALPR fixes — 2026-10-01

The user approved findings A–G from the [read-only run review](alpr-run-review-2026-10-01.md). The [active plan](../../.agent/plans/alpr-run-fixes-2026-10-01.md) bounds implementation and verification. Three Luna High helpers implemented presentation/provenance, stopping disclosures, and usage telemetry; the primary agent handled conservative lineage notices, integration, and replacement verification.

Status: A–G implemented and offline verification complete. The verified replacement is installed at `/Applications/ResearchAssistant.app`; the superseded app and redundant build copies have been removed.

## Changes

| Finding | Result |
| --- | --- |
| A: unadmitted Evidence cards | Projection requires an admitted evidence/Ledger record and shows its approved factual statement. Rejected/failed sources remain in the trail/source outcomes. |
| B: misleading Supporting labels | Cards distinguish the selected research direction from the Analyst’s evidence relationship. Scoring and admission policy are unchanged. |
| C: stale stopping/zero-gaps wording | Future reconciliation carries the authoritative Round-4 decision. No productive new search is distinct from complete coverage. A separate read-only display supplements historical releases using persisted governor/gap facts; frozen exports are preserved. |
| D: missing visible citations | Findings link by exact Ledger claim ID to the admitted source and verbatim quote. Ordinary source cards no longer expose internal family UUIDs. |
| E: hidden outcomes | Source cards distinguish selection history from final disposition. Acquisition and evidence analysis failures/rejections are shown alongside successful outcomes. |
| F: incomplete usage records | Future physical completions retain optional input/output/cache splits, with strict sums and unknown values preserved. Semantic Analyst failures retain usage returned by the completed invocation. |
| G: possible duplicate-study mirrors | Read-only notices identify shared DOI metadata or possible matching study titles. The Exa/PubPub pair is flagged; no source-family ID, independence count, selection, or historical evidence is merged or rewritten. Conflicting DOIs defeat title-only hints. |

These repairs do not prove the ALPR claim. The source’s narrower vehicle-theft association, disabled challenge direction, incomplete coverage, inaccessible sources, and bounded analysis failures remain material qualifications. Budgets, fail-closed validators, prompts, persisted schema, real credentials, and immutable artifacts are preserved. No paid/provider/retrieval calls or new dependencies are used.

## Cost and historical usage

At the user-supplied $0.10 input/$0.50 output per million rates, 250,000 input plus 70,000 output costs **$0.06**. The saved run records $0.057952460 across 268,135 tokens. Its missing full input/output/cache breakdown cannot be reconstructed; the 320,000-token scope difference remains unresolved. New telemetry improves future diagnosis without inventing historical values.

## Verification

All final product-source gates passed on the rebuilt source:

| Check | Evidence/result |
| --- | --- |
| Full Python suite, warnings as errors | **1,283 passed, 2 unchanged skips**, 147.06 seconds; `desktop/build/alpr-fixes-pytest-final-20261001.log` |
| Ruff lint/format and whitespace | Passed; 174 Python files already formatted; final lint/format logs under `desktop/build/` |
| Frontend lint, types, desktop export | Passed; final export uses same-origin API requests, including when an invalid fixed-origin environment value is supplied |
| Offline evaluation and API/config smoke | Passed; no live provider requests |
| Browser checks | Citation binding, actual relationships, final dispositions, lineage notice, copy/download, polling, configuration and history races passed |
| Frozen, packaged and installed app | Backend/native checks and actual Electron-window checks passed with isolated data and test-only credential namespaces |
| Advisory graph | Refreshed after final code changes: 5,212 nodes / 34,930 edges; important conclusions checked against live source and tests |

The final browser screenshot was visually checked at `desktop/build/phase3-screenshots/research-evidence.png`. Browser race smokes preceded the last cosmetic aggregate-outcome sentence; the final full browser smoke and packaged/installed window checks ran on the final export. Logs use the `alpr-fixes-` prefix under `desktop/build/`; the final backend build used a workspace-local PyInstaller cache.

Historical run `daf3e186-eb9c-42ec-b9ec-d992334a5428` was checked through SQLite read-only access before and after installation. **All 233 artifact payload hashes match**, and deterministic revalidation reproduces release hash `74b9c1da7bb4386c931a108c96898b1da417bad4c2554a387860af1645c4a600`. The new display contains **12 admitted cards, 12 unique Ledger-bound citations, one possible mirror notice, three partial and one unavailable coverage dimensions**. Its derived stopping display reports no productive new search; the old rendered brief/export and its original hard-round-limit enum remain immutable. This is a presentation correction using persisted facts, not a regenerated historical result.

## Installed replacement

The verified installed app is `/Applications/ResearchAssistant.app` on macOS 26.6.2 arm64. Exact source and generated frontend parity passed:

- Backend SHA-256: `d561b04e95a2745792e8d76143e30cb4fefe0a9f314e2d74286b85fed302480c`.
- Runtime identity (source plus frozen executable): `source-sha256:7466fee71fd74c1fb2fb660d4646d6c2d14edff0f6c84fc95c3357203c0f9499`.
- Source-only identity: `source-sha256:3a647ec07198f6ab682cbda09e8948872e01dea152ce684957dafde5c1b44d27`.
- All **101 source inputs** and **22 exported frontend files / 27 entries** match the tested source/export, including bytes, modes and symlinks.
- Staged and installed copies match all **30,929 payload files/symlinks** before and after installed native/window checks and cleanup.

The first strict frontend parity check exposed an empty generated export directory omitted by packaging, with no file mismatch. The empty directory was removed from the generated export, resources were refreshed and the app was repackaged; final strict parity passed. The first record remains preserved as `alpr-fixes-source-parity-first-20261001.json`.

After the installed checks passed, the superseded Applications rollback app, redundant `mac-arm64` candidate directory, and three backend build/cache directories were removed. Package text records were archived under `desktop/build/retired-package-records-20261001/alpr-fixes`; current resources, source and verification logs remain. Installation and cleanup records are `alpr-fixes-install-20261001.json` and `alpr-fixes-cleanup-20261001.json`. The 38 real-user-data file metadata records matched across installation and isolated checks; saved research and credentials were preserved. At the verification point, changes remained uncommitted and no publication or push had occurred. The user subsequently authorized committing and pushing all pending changes; Git history records that repository delivery. No installer release publication is included.

## Normal launch

The installed app was reopened through LaunchServices and observed running from Applications with its own backend; unauthenticated health returned 401. A separate normal-mode backend check (`self_test=false`) passed authenticated health, continued running and recorded the runtime identity above. See `alpr-fixes-normal-launch-final-20261001.log` and `alpr-fixes-normal-backend-retry-20261001.log`. Neither check started research or changed credentials.

The initial normal-backend probe missed its 10-second health deadline; a retry with a bounded 40-second allowance passed. Its secondary cleanup error came from a nonexistent method in the generated diagnostic helper and was corrected there. A separate process observer initially expected numeric addresses while its socket utility returned hostnames; numeric-address observation then passed. No product source was changed for these diagnostic errors. Earlier short-lived windows were explained by the user's confirmation that they closed them; no app crash report was found. Strict signature verification retains the known unsigned-test-build limitation; normal launch and local checks do not establish signing/notarization acceptance.

## Remaining boundary

No new paid-run allowance or release publication is included. Local checks do not establish clean-machine/macOS 14, live-provider research quality, Developer ID signing, or notarization acceptance. A new research run must obey the existing source/executable identity gate; historical research is inspected/exported without regeneration.

## Subsequent authorized repository delivery

At the user’s request, installed parity and normal launch passed again. A Luna
name-only rescan found only the installed Applications app and no named installers
or mac-arm64 directories in accessible locations. An obsolete backend build cache
in Codex worktree 3020 was removed while preserving source and seven text records.
One Google Drive CloudStorage location was unreadable and remains unchecked.
The user explicitly authorized committing and pushing all pending source, tests
and documentation; no real credentials, saved research or generated binaries are
included. The precommit lint/format/whitespace checks passed, and Git history records
this delivery. The existing full source and installed-app verification remains
applicable; no product source changed during final cleanup/delivery.
