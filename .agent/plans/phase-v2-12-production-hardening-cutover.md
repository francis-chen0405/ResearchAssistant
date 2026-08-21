# ResearchAssistant v2 — Phase 12: Production Hardening and Cutover

Status: Complete and verified.

## Authorized scope

- Join the completed Phase 1–11 v2 stage boundaries into one restart-safe production
  coordinator for fresh product runs.
- Enforce one run-wide maximum of 160 physical LLM calls and 300,000 total tokens,
  including retries and every configured model route, while supporting lower ceilings.
- Protect mandatory downstream analysis, review, Ledger, synthesis, and release work
  before optional continuation or queue expansion.
- Preserve compatible completed artifacts across restart and degrade ordinary provider or
  stage failures without weakening direction isolation, immutable evidence, Ledger
  admission, final validation, or rendered-output hashing.
- Cut fresh website and CLI execution over to v2 only after the mocked production gates
  pass. Keep historical inspection, rendering, export, and immutable records under their
  original contracts.
- Add mocked end-to-end, restart, failure-matrix, direction-adversarial, budget, fingerprint,
  API/export/render, and release-integrity tests. Make no paid provider call.

## Hard boundaries

- No new product feature, frontend redesign, dependency, hidden live call, Round 4,
  historical evidence migration, raw-source synthesis, unreviewed Ledger entry, or release
  validator bypass.
- Every internal handoff remains a strict Pydantic model. JSON remains limited to
  persistence, API, logging, and export boundaries.
- Historical direct-MiMo runs remain readable and are never silently reinterpreted as v2.

## Completion gates

- Mocked Runs A–H reach the expected v2 terminal result or fail closed.
- Complete Python and deterministic evaluation suites pass with exact counts recorded.
- Ruff lint/format, `git diff --check`, frontend lint/build, and launcher/syntax checks pass,
  or an exact environmental limitation is recorded without changing dependency manifests.
- README, architecture, decisions, status, handoff, and canonical plan index match the
  verified production implementation.

## Implemented result

- `v2_orchestrator.py` is the fresh-run coordinator and preserves every Phase 3–11
  append-only checkpoint.
- `providers/v2_budget.py` enforces the cumulative call/token/cost boundary and
  `providers/v2_factory.py` constructs the exact three-alias production route.
- `agents/v2_extraction.py` bridges the deep-analysis queue to exact immutable candidates;
  failures remain per-source status rather than silently dropping survivors.
- Website and CLI defaults use v2. Historical inspection/render/export and explicit legacy
  test injection remain available without cross-version migration.
- Mocked production, lower-limit, restart, direction, fingerprint, Phase 4–11 degradation,
  Governor, release, API, export, and hash regressions pass without paid calls.
- Final verification: 772 Python tests passed and 2 expected opt-in tests skipped; the 10
  focused Phase 12 tests include mocked Runs A–H. Ruff lint/format, diff check, Python
  compilation, launcher syntax, frontend ESLint, and the
  Next.js production build passed.
