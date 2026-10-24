# Current status

Renderer work adds recoverable progress polling: ten-second snapshot deadlines,
three consecutive failures before automatic reads pause, same-run reconnect, last-confirmed
receipt times, and History/cancellation controls on both starting and progress screens.
Cancellation is shown as requested only after backend confirmation. Navigation/unmount
aborts progress reads and suppresses late results. The [task record](../../.agent/plans/recoverable-progress-polling-2026-10-23.md)
owns verification and limitations. Current checks pass **3,239 Python tests / nine
skips**, all **31 renderer tests**, frontend lint/types/static webpack export, Ruff,
repository boundaries and whitespace checks. Review verified all six offline browser
checks, including the added recovery scenarios, and repaired the API-client VM harness
for its new browser abort-controller/timer requirements. An additional 22 focused
API-contract/boundary tests pass. The user authorized commit/push after review.
The installed app has not received this renderer change.

The reviewed e359 worktree changes are integrated into master.
They add early assessed evidence feedback, bounded post-analysis follow-up, later-page
PDF capture with exact omission boundaries, replacement acquisition, selection coverage,
confirmed paper identity and truthful provider dispatch diagnostics. The current CLI
20-source/50-depth defaults are retained. The preceding integration verification passed **3,239 Python tests / nine skips**, Ruff lint/format
(531 files), repository boundaries, generated API contracts, frontend lint/types/static
build, 20 renderer tests, 22 desktop units and all six offline browser checks. Exact
314-file wheel audit and fresh wheel/editable installs pass. The real Electron UI
smoke passes. Backend execution identity:
`source-sha256:f1c92eba7445253b21658a1eff21960223fc4eff24df69f01001d18389e45e4b`.

The integrated backend freezes successfully, but packaged acquisition acceptance is
blocked: the owned Wigolo daemon starts its HTTP server while the backend health
probe reports `[Errno 2] No such file or directory`; the original smoke exceeds its
unchanged health deadline. The missing path/root cause is unresolved. Initial startup
and subsequent health failures are retained in the integration task record.

The [offline evaluation](../verification/offline-evidence-loop-2026-10-23.md) records
3,235 passing Python tests / 12 skips on the preceding e359 source, plus controlled
capture, feedback, accounting and replay checks. These historical checks do not
establish live quality on the integrated source. [The integration task](../../.agent/plans/source-loss-recovery-2026-10-19.md)
records current verification and the packaged delivery blocker.

Installed Mac build `20261020.6` predates the bounded PDF/post-analysis changes and
the final CLI correction. [Its delivery record](../verification/selection-coverage-repairs-2026-10-21.md)
retains the exact checks. This integration does not establish installation or live
research acceptance. Saved data, credentials, historical policies and reservations
retain their existing meaning. Schema 18 and the exact resume identity gate remain.

Windows packaging remains manual-only. Its recorded Wigolo startup failure and
interrupted-upgrade repair acceptance are open. Public release, Mac signing/notarization,
clean-machine/minimum-OS acceptance and physical power-loss durability remain unverified.

[Preceding master and e359 summaries](https://github.com/francis-chen0405/ResearchAssistant/tree/archive-2026-10-23-docs-baseline/docs/archive/2026-10-23-integration-preceding-state)
preserve exact earlier results and boundaries. R01–R59 remain implemented; the
[active review inventory](../audits/2026-10-15/remaining-file-review.json) retains
20 current assets outside the completed source review.
