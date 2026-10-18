# Prompt 11 — split the renderer and give it fast checks

You are powered by GPT 6.1 Sol XHigh. Usage goes very fast. Keep doing some hands-on Sol work. But, use `gpt-6-luna` helpers with task-appropriate effort when suitable, preferably only for simple tasks, such as for searching in general! Retain Sol for hard reasoning.

Refactor the Next.js UI after the folder migration (current source: `web/app/page.tsx`, 783 lines/78 KB, 23 state hooks; the folder should become root `frontend/`). Read web/AGENTS.md or its moved equivalent and the installed Next.js guides there, plus repository AGENTS/conventions/status. Check Git/graph status; verify current UI and API behavior in source and existing browser smokes. Keep the same visible workflow and settings, support/challenge controls, cost disclosures, provenance and accessibility behavior.

Extract research start/poll/cancel, history, preferences/configuration and result/trail state into focused hooks or controllers; extract corresponding feature components. Break very long JSX lines so reviews are feasible. Preserve request-id/abort protections against stale configuration, history and polling responses. Ensure modal focus/keyboard handling and reduced-motion paths still work. Keep source leads separate from admitted evidence; do not change research policy here.

The TypeScript API client currently casts successful JSON as `T`. Mechanically generate or check its types against backend response schemas and add representative offline contract checks; do not assert an existing mismatch without evidence. Add an independent fast frontend CI job for lint/typecheck and reusable offline browser smokes. Five browser smokes already exist behind the desktop build; reuse them or extract shared fixtures without dropping native packaging CI. Keep the locked dependencies and generated files under their owning folder.

Run frontend lint/types, static export and all relevant offline smokes, plus affected backend API tests and full required repository checks. Report the feature/module map, before/after route contracts, race-test results and which checks are fast versus native. Do not claim local static export verifies a signed installer.

Acceptance: the page is divided by feature with unchanged user behavior, API types are mechanically checked, and frontend feedback runs independently before native packaging.
