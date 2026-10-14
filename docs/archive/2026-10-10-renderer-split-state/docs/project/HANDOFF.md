# Handoff

[Prompt 10 API responsibility split](../verification/api-module-split-2026-10-10.md)
is complete locally, including full Python/browser/frozen/install verification. Next is source review/commit,
or separately authorized native delivery. Preserve earlier staged/unstaged repairs;
the migration and API split remain unstaged, and the original staged binary diff is
unchanged. [STATUS](STATUS.md) owns current verification and provenance.
[The test map](../../tests/README.md) locates owner regressions and full collection.

Keep backend package/data manifests, installed historical aliases, the exact configuration
identity resource and explicit clean frozen source data. `scripts/build_distribution.py`
remains a workspace facade for the backend build hook. Root `cli.py` and the Mac command
file are transition launchers after backend installation; `.agents/PLANS/` is the retained
historical-path exception. Current code uses canonical `researchassistant.*` imports.

Use the API record's file/route map for review. Keep assembly/authentication/lifespan
central and route factories app-local. Preserve request-time compatibility I/O adapters,
one validated read snapshot per inspection, side-effect-free facade imports and the
single explicitly requested lazy `app`/`runtime` pair. The saved pre-split contract fixture
must not be regenerated merely to accept an unintended change.

The current backend identity requires fresh runs. Preserve read-only historical inspection/
export, exact old hashes, prompt/font bytes, conservative reservations and incompatible
resume rejection. The installed app is the October 9 build recorded in STATUS;
it predates the owning-folder source migration. Local frozen resources and their
Mac smoke results do not establish a new installed delivery or public release.

Remaining platform/delivery checks: Python 3.11 and Linux execution, native Windows/Jobs,
current installers, clean-machine/minimum-OS acceptance and signing/notarization. New live
quality collection requires a separate bounded allowance. All logs/artifacts for this
migration are under `/private/tmp/researchassistant-prompt08/`; review-fix logs and rebuilt
artifacts are under `/private/tmp/researchassistant-prompt08-review-fixes/`.

Prompt 09 logs and the detailed link audit are under `/private/tmp/researchassistant-prompt09/`.
Prompt 10 checks, before/after inventory and fresh installs are under
`/private/tmp/researchassistant-prompt10/`. The rebuilt local frozen backend passed its
isolated smoke; the installed app and public delivery remain unchanged.
