# Prompt 05 — make service stop and research admission atomic

You are powered by GPT 6.1 Sol XHigh. Usage goes very fast. Keep doing some hands-on Sol work. But, use `gpt-6-luna` helpers with task-appropriate effort when suitable, preferably only for simple tasks, such as for searching in general! Retain Sol for hard reasoning.

Fix the confirmed check-then-act race in `frontend/api.py` near `/api/service/stop`. It checks `controller.has_active_runs()` and then separately calls `services.stop()`. The saved deterministic interleaving probe `/private/tmp/researchassistant-runtime-audit-94a241b-probes.py` forced a research admission between those actions; the endpoint returned 200 and stopped acquisition after research became active. Rerun/rebuild the probe against current source. Read AGENTS, conventions and runtime lifecycle tests; check Git/graph freshness, then trace all research start, stop, credential/configuration changes, controller registration and native service ownership.

Introduce one short-lived lifecycle coordination point so stop and research admission have an atomic order. A stop must complete before research admission or return a clear conflict while an admitted run owns the service. Do not hold a global lock across ordinary paid requests, SQLite waits or shutdown draining. Review nearby credential/save/import guards for the same race and fix only confirmed equivalent hazards while preserving native-vault rules, API response contracts and concurrent-run behavior.

Add barrier-based tests covering both operation orders, duplicate start/stop, cancellation, failed service start, and a run that finishes as stop begins. Verify no service kill after successful admission, no deadlock, and no provider replay or reservation loss. Run focused/full Python tests, Ruff/format, whitespace checks, and affected API/desktop offline smokes. Report lock scope and measured contention behavior. Use fake services and temporary data only.

Acceptance: the forced interleaving no longer allows HTTP 200 service stop after research has been admitted, and both legitimate operation orders remain available.
