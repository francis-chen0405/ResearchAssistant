# Current status

[Prompt 16 Mac delivery](../verification/mac-delivery-gates-2026-10-13.md) has a
complete local Apple Silicon candidate and documented installed-cache findings.
Developer ID/notarization and actual clean-machine/macOS 14 tests remain external
gates. Nothing was published or installed over the October 9 app.

## Verified current source and candidate

October 13, 2026, macOS 26.6.2 (25G83) arm64 / Python 3.12.14:

- Full suite: **2,797 passed / five existing skips**, 306.43 seconds. Focused
  desktop/staging checks: 16 passed; native cache regressions: four passed;
  desktop unit checks: 20 passed. Ruff lint/format (469 files), boundaries,
  generated API parity and working/staged whitespace pass. Frontend lint/types,
  static build, all five offline browser checks and native shutdown checks pass.
- Clean frozen backend and fresh renderer, 290 packaged source/resource byte
  comparisons plus configuration, exact acquisition locks and packaged main/UI
  parity pass. Offline wheel/editable/CLI/API verification checks the exact
  296-file distribution. Source-only backend identity remains
  `source-sha256:49db1858f558ba58234ea4509ecce80266df22bda4887cf6feda6d4c9d09bf41`.
  Observed candidate frozen identity is
  `source-sha256:5b57457e0c9f3771a02907e764e2548ebff72535bef0ad70ce6d3aa49d1da128`.
- Candidate app **0.1.0 / bundle build 20261013.16** passes isolated frozen
  authentication/vault persistence/settings/owned Wigolo lifecycle and native
  window checks. October 9-to-candidate upgrade preserves native test credentials,
  configurable preferences, identical historical brief and byte-identical history.
  The DMG-installed copy repeats runtime/window checks. Real vault entries and
  saved research are preserved; temporary test namespaces are cleaned up.
- DMG and ZIP integrity pass. All **31,127 files/symlinks and modes** match the
  candidate, the DMG-installed copy and ZIP. Exact hashes, source snapshot,
  signing inputs and release notes are retained under
  `desktop/dist/prompt16-20261013/` and the verification record.
- Bundle declares macOS 14.0; all **111 arm64 Mach-O files** were inspected with
  no load-command minimum above 14.0. This establishes static compatibility only.
  No suitable clean-machine/macOS 14 environment exists in this session.
- Zero valid signing identities were found. Candidate binaries have linker/ad-hoc
  signatures only; Gatekeeper rejects the app and no DMG notarization ticket exists.
  The prepared opt-in signing configuration passes the pinned builder schema and
  refuses missing local certificate-name/notary-profile inputs. Signed hardened
  runtime, notarization and clean-machine acceptance remain unverified.

## Installed app and cache

The [October 9 app](../verification/current-app-install-2026-10-09.md) remains at
`/Applications/ResearchAssistant.app`, version 0.1.0, backend SHA-256
`12e1705b6790b2532e8284ce5baa32e25f09b83de701dd15ce6d0415945c03f5`.
Its exact observed frozen identity and older source identity are in the new record.
It does not contain Prompt 15 or the new cache integration policy.

Direct read-only cache queries fail with `unable to open database file` in the
restricted inspection context. A quiescent byte-identical private copy, inspected
with the installed Node/vector extension and SQLite backup, passes core integrity,
foreign keys, nine migrations and all 93 normalized URL/vector/map/metadata
references. URL FTS external-content integrity fails; feed FTS passes.
The pinned replacement-write regression reproduces that defect. The candidate's
connection policy fires delete triggers and repairs only the derived URL index
when core integrity passes. On the disposable installed-cache backup, repair passes
FTS checks and preserves content/vector/migration bytes. **The real cache was not
repaired or changed.** App-data manifests, original cache bytes/mode/mtime and the
installed backend hash remain unchanged.

## Research and authorization boundary

[Prompt 15](../../.agent/plans/source-leads-quality-2026-10-13.md) remains implemented:
same-run source leads/reasons are visible without a released brief, with historical
formats, source-local admission and linked-URL readability preserved. Metadata and
snippets never become verified evidence. No compiler/discovery, Probe, prompts,
model routing, budget/reservation or resume policy changed in this delivery task.

Fresh offline evaluations pass 38 integrity cases, six synthetic discovery cases,
two authored visibility fixtures and quality replay (zero observations / one authored
fixture observation). They establish no new live useful-recall or human labels.
Prompt 14's frozen $2.48 allowance/zero-spend receipt remains unchanged and rejects
current-source drift before native credential access; the earlier five-run allowance
remains exhausted. No paid research, real-history migration or public upload occurred.

HEAD remains `94a241b52f9525cab3aff52d1f85026f081b3e85` on dirty local `master`.
Earlier staged changes are unchanged (binary-diff SHA-256
`85f8753d0bb6ba7af20c688eab28ad10429ee43329b879d89b8db48071324cf2`).
No staging, commit, branch switch, fetch or push occurred. Advisory graph refreshed
without persistence: 12,391 nodes / 76,120 edges. The
[preceding documents](../archive/2026-10-13-mac-delivery-preceding-state/README.md)
and historical records retain their stable paths. [HANDOFF](HANDOFF.md) owns next gates.
