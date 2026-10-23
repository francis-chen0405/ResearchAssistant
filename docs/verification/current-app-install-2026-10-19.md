# Current Mac app replacement — 2026-10-19

The user requested a fresh local app install and new research defaults. Build
`20261019.1` was installed at `/Applications/ResearchAssistant.app`; the prior bundle
was deleted after the installed backend and window checks passed. The app was
registered, opened normally, and left open. This was an unsigned local Apple
Silicon build. Later replacements are recorded below; this is a historical install record.

## Research settings and fixes

- New app and API defaults: metadata search depth 50 and 20 candidate sources per
  enabled direction per round. The UI offers 5, 10, 20, and 30; saved 15-source
  settings remain readable for historical compatibility.
- Fresh product runs can acquire up to 30 per enabled direction, with a 60-cluster
  round ceiling. Final selection can disposition up to 240 survivors over four
  rounds without changing its 24,000-token rendered input cap.
- The installed build includes the Round-2 source provenance fix, clearer discovery
  failure reporting, and candidate-source wording from the run investigation.
- The saved preferences already contained depth 50, target 20, support on and
  challenge off at replacement time. They remained byte-identical through install
  and normal opening. No real research was started or charged.

## Exact build and checks

- Live, staged, and packaged backend source identity:
  `source-sha256:a55a1ad8acaaedab245b66bc1c5c917fb0c979b5ca6c31c7e4aca444791770f6`.
- Frozen backend executable SHA-256:
  `3c369c5c5c5167ebe976548202965cf544986486f1e29a774df04bd6fd99acc3`.
  Backend, exported frontend and patched acquisition hashes match between tested
  resources and packaged app.
- Historical local app archive (removed in the 2026-10-20 cleanup): `desktop/build/current-install-20261019/release/ResearchAssistant-0.1.0-20261019-local-arm64.zip`,
  SHA-256 `b47f5638a2b725a491b0e8c7f0a2251669e7fd6278b317ad32767747cbcd6577`.
  Disk-image creation failed with `hdiutil: create failed - Device not configured`;
  installation used the verified local app bundle directly.
- Focused product/compatibility tests: 107 passed. Full Python suite: 3,201 passed,
  nine skipped, one outdated frozen-benchmark capacity expectation. That test was
  corrected without changing benchmark data; its 172-case focused compatibility
  group then passed. The full suite was not rerun after this test-only correction.
- Generated API types, frontend TypeScript, frontend lint, Python lint, and diff
  whitespace checks passed. Tested resources, packaged candidate, and installed
  bundle each passed isolated backend/authentication/native-vault/settings/Wigolo
  smoke and actual window/renderer/normal-shutdown smoke. No paid provider calls.

## Data and installation

The installer staged and compared all 31,133 candidate payload entries, confirmed
that no prior main process was running, hashed the 40 saved-data entries, swapped the
app with a rollback copy, and verified the installed payload and saved data. The
installed smoke passed before the old rollback bundle was deleted. Normal opening
exposed authenticated backend readiness (unauthenticated health returned HTTP 401).
After opening, the research databases and preferences still matched the pre-install
hashes. Only Electron's LevelDB logs and three running-instance links changed.
Installation state, payload/data manifests, and checks are retained under
`desktop/build/current-install-20261019/`; its old app package was removed.

## Run 1 follow-up and rank fix

The first new run (`437cc6f6-b63b-401d-8bec-e14c1992b35e`) completed on
2026-10-19 after 157 search results and 49 acquisition attempts. It retained
14 sources, including eight from Round 2, and recommended ten. Its post-analysis
assessment was still `incomplete_coverage`: eight sources entered deep analysis,
but only one produced admitted evidence. The source execution record includes
two OpenAI connection failures, three source token-cap blocks, one total-token
ceiling block, and one extraction validation failure because a provider rank of
30 exceeded an older 25-rank contract bound.

The three carried search-rank contracts now accept ranks through 100, matching
the existing provider-rank range. The focused phase 3, production, and evidence
analysis suites passed (116 tests). A new backend was built into app version
`20261019.2`, tested in an isolated app smoke, installed over `20261019.1`, and
tested again from `/Applications/ResearchAssistant.app`. The 40 saved-data entries
matched before and after replacement; the prior bundle was removed. Its frozen
backend SHA-256 is
`1d6d1356a3c05d29289ce338e13a4e5dca119a86fe9cc90c857e0cf9e5d2efdd`.
The app is open with backend health responding on loopback. Build and installation
records are under `desktop/build/rankfix-20261019/`.

## Run 2 follow-up and adaptive search fix

The second new run (`e9a97839-0178-443f-8af2-8c3c3b10e2e5`), on the claim
"Species extinctions make ecosystems less resilient to disturbances," completed
on 2026-10-20. Seven search queries returned 177 results; 30 acquisition attempts
retained 12 sources. All 12 entered deep analysis and seven produced admitted
evidence, but the report recommended only one source and marked claim coverage
incomplete.

The run stopped after Round 1 because an application-owned adaptive search lane
copied an unbounded gap `search_focus` into a 240-character `strategy` field.
The resulting validation error was reported as `no_materially_new_query`, so
Round 2 never searched even though 317,187 of 500,000 tokens remained. The lane
now normalizes and bounds its short strategy while the complete material gap
remains in the Search Agent input. All 35 adaptive search tests passed, including
a regression for overlong gap advice. Version `20261020.3` was built and passed
isolated and installed backend/authentication/native-vault/settings/Wigolo smoke.
The installed `/Applications/ResearchAssistant.app` contains frozen backend
SHA-256 `243ca6a934545cddc02dc7e32973a0c972146fdada7802dd3dba74d7eb6f008b`.
All 40 saved-data entries matched before and after replacement, and the prior
bundle was removed. Build and installation records are under
`desktop/build/lanefix-20261020/`.

On 2026-10-20, at the user's request, the older and duplicate packaged app
bundles, older app ZIP/DMG installers, their blockmaps, and one unfinished
Electron build bundle were deleted. The sole retained ResearchAssistant app is
version `20261020.3` at `/Applications/ResearchAssistant.app` as of that cleanup. Saved runs and
preferences were not part of the cleanup. The removed-path inventory is saved
at `desktop/build/older-app-cleanup-20261020.json`.
