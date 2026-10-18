# Prompt 06 — bound desktop shutdown safely

You are powered by GPT 6.1 Sol XHigh. Usage goes very fast. Keep doing some hands-on Sol work. But, use `gpt-6-luna` helpers with task-appropriate effort when suitable, preferably only for simple tasks, such as for searching in general! Retain Sol for hard reasoning.

Fix the missing desktop shutdown deadline in `desktop/main.cjs` near `before-quit`. The current handler prevents every quit, closes backend stdin, and waits only for child exit. The saved handler probe `/private/tmp/researchassistant-runtime-audit-94a241b-quit.cjs` showed two prevented quit attempts, no deadline and no escalation when the child never exits. Read AGENTS/conventions, `desktop/backend.py` shutdown behavior and native smoke tests; check Git and graph status. Reproduce with a stub child before editing; do not use a real user database.

Keep cooperative Python cancellation/draining as the first path. Add one documented outer deadline covering startup and shutdown stalls, longer than the current 90-second controller drain plus a defensible margin. Escalate only against the owned backend/process group using platform-appropriate behavior. Handle repeated quit, backend exit during timeout setup, late child exit, startup failure and multiple owned acquisition children without killing unrelated processes. Preserve recoverable SQLite state and conservative unknown-call reservations; do not convert forced termination into a claim of completed work.

Add deterministic handler tests with fake timers/child events and native offline smoke coverage where feasible. Verify normal quit, stuck child, repeated quit, startup timeout, Windows handling, resource cleanup and process ownership. Run relevant Python and desktop checks, full Python suite, Ruff/format, whitespace checks. Report the exact maximum shutdown window and the platform behavior verified locally versus still pending on native Windows/macOS builds.

Acceptance: every owned shutdown path exits within the documented limit without truncating normal graceful drain or terminating an unrelated process.
