# Handoff

[Prompt 08 and its review fixes](../verification/folder-consolidation-2026-10-10.md#review-fixes)
are complete and verified locally. Next is source review/commit, or separately authorized native delivery. Preserve
all earlier staged/unstaged repairs; the migration is unstaged and the original staged
binary diff is unchanged. [STATUS](STATUS.md) owns current verification and provenance.

Keep backend package/data manifests, installed historical aliases, the exact configuration
identity resource and explicit clean frozen source data. `scripts/build_distribution.py`
remains a workspace facade for the backend build hook. Root `cli.py` and the Mac command
file are transition launchers after backend installation; `.agents/PLANS/` is the retained
historical-path exception. Current code uses canonical `researchassistant.*` imports.

The current backend identity requires fresh runs. Preserve read-only historical inspection/
export, exact old hashes, prompt/font bytes, conservative reservations and incompatible
resume rejection. The installed app remains the previous build; local frozen resources
and their Mac smoke results do not authorize replacement or publication.

Remaining platform/delivery checks: Python 3.11 and Linux execution, native Windows/Jobs,
current installers, clean-machine/minimum-OS acceptance and signing/notarization. New live
quality collection requires a separate bounded allowance. All logs/artifacts for this
migration are under `/private/tmp/researchassistant-prompt08/`; review-fix logs and rebuilt
artifacts are under `/private/tmp/researchassistant-prompt08-review-fixes/`.
