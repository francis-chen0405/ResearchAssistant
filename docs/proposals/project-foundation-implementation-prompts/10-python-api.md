# Prompt 10 — split the Python API by responsibility

You are powered by GPT 6.1 Sol XHigh. Usage goes very fast. Keep doing some hands-on Sol work. But, use `gpt-6-luna` helpers with task-appropriate effort when suitable, preferably only for simple tasks, such as for searching in general! Retain Sol for hard reasoning.

Split the 1,431-line Python `frontend/api.py` (or its post-migration owner) into reviewable backend modules after the folder move. Read AGENTS/conventions/status, current architecture, existing API/security/race tests, and the current diff. Check graph freshness, search route declarations and callers with the graph, then verify live code. Preserve all existing HTTP paths, methods, request/response schemas, status codes, authentication, same-origin boundaries, redaction and read-only inspection semantics.

Move routes into small owners for research start/status/cancel, history/import, evidence/trail/diagnostics, preferences/settings, provider credentials and service controls. Keep shared application assembly, authentication and lifecycle coordination centralized. Move result/diagnostic projection out of route handlers into application services while preserving one validated read snapshot per request. Keep `create_app` and the public API import as compatibility facades, with no duplicated route registration or global side effects. Preserve the atomic service-stop/start repair from prompt 05 and the rejected-resume behavior from prompt 04.

Make this a structural change: avoid mixing new business rules or policy changes into the module move. Use an API route/schema inventory before and after; compare OpenAPI output or equivalent canonical route metadata and offline responses. Run focused API, security, read-consistency, lifecycle and browser-smoke checks; full Python tests, Ruff/format and whitespace checks. Verify frozen backend startup. Deliver a file/route ownership map, compatibility imports, and any deliberately changed contract with its regression evidence.

Acceptance: every existing route remains registered exactly once with equivalent contracts/security and the API owner has small, clear route/application modules.
