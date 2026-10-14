# Prompt 12 — neutralize contracts and isolate historical execution

You are powered by GPT 6.1 Sol XHigh. Usage goes very fast. Keep doing some hands-on Sol work. But, use `gpt-6-luna` helpers with task-appropriate effort when suitable, preferably only for simple tasks, such as for searching in general! Retain Sol for hard reasoning.

Improve backend ownership after folder consolidation. Read AGENTS/conventions/status, `docs/research-invariants.md`, architecture and historical-read/export tests. Check Git/graph status. Use graph tracing for dependencies, then verify imports and call-time behavior in live source. The last review confirmed `researchassistant.contracts.query_retrieval` imports provider-owned `SearchResponse`, `contracts.neighborhood` imports `ResolvedOpenAlexWork`/`SearchResult`, and storage discovery code calls research/agent helpers. It found no direct top-level runtime import cycles, so treat these as maintainability seams, not startup failures.

Place stable request/result data shapes in a neutral contract owner consumed by providers, research and storage. Ratchet import-layer checks down only after actual call sites migrate; avoid a global rule that fails existing code. Keep Pydantic validation, frozen fields, enum values and old serialized meanings exactly compatible. Preserve public imports with thin re-exports where callers still use them.

Separate historical read/inspection/export from historical execution so those paths do not need the 4,241-line old orchestrator for ordinary inspection. Verify `agents.researcher`/`analyst` are already facades and `agents.renderer`/`synthesizer` still serve current v2 before moving them. Keep the explicit `legacy_runner` execution path and historical artifacts intact. Do not move a shared helper into `legacy/` solely by filename, and do not change prompt bytes or released text.

Work in small steps: neutral data contracts, call-site migration, historical inspection extraction, dependency guard. For each, run targeted import/serialization/history/export tests; then full Python tests, Ruff/format, whitespace checks and packaged resource checks if imports change. Compare old/new public objects, historical release hashes and incompatible-resume behavior. Deliver a dependency map and explain remaining exceptions.

Acceptance: contract ownership no longer requires the identified provider imports, ordinary historical inspection no longer imports executable orchestration, and public/historical behavior remains byte- and shape-compatible.
