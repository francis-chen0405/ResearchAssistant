# Handoff

Phase 3 was developed on `codex/phase-3-frontend-settings`, from clean completed
Phase 2, and delivered to local `master` by fast-forward at the user’s request.
The user explicitly authorized this phase. No push, public release, paid call or
dependency addition was performed. Stop at the Phase 3 boundary.

Read [architecture](ARCHITECTURE.md), [configuration](docs/model-settings.md),
[active plan](.agent/plans/phase-3-frontend-settings.md) and
[verification](docs/verification/phase-3.md) for actual checks and artifact locations.
The UI now shares reusable workspace/progress/dialog components; demo data is isolated
from live APIs. Standard model selection resolves a copied environment before worker
startup and preserves existing immutable configuration, accounting and release checks.

Outstanding: rebuild and test Windows on an authorized native runner; verify credential
access across signed versions, clean-machine install, minimum OS and signing/notarization.
The user denied an isolated old-to-new Keychain test after entering a provider API key
into the macOS password prompt. Different ad hoc executable identities explain the
system access request; cancellation returned -128. Do not rerun that cross-version prompt
without new authorization. Do not weaken native ACLs. Settings and API errors now explain
the distinction. Same-build native vault round-trip/persistence remains separately tested.

Rebuild, restart and start a new run after updating. The source/executable fingerprint
changes; incompatible resume must still fail explicitly. Historical inspection/export
must remain read-only and preserve exact validated output.

Use `.venv/bin/python -m pytest` / `-m ruff`: launcher shebangs reference the older
checkout. Local DMG output must use a temporary directory because the synced checkout
rejects disk-image creation; this is not an application runtime path.

This replaces the prior handoff while preserving its exact text in the
[Phase 2 handoff](docs/archive/phase-2-handoff/HANDOFF.md) and the
[earlier archive](docs/archive/pre-phase-2/HANDOFF.md).

## 2026-09-08 authorized upgrade verification

The user explicitly authorized another isolated test. The unchanged
`desktop/upgrade-smoke.py` passed against the preceding Phase 2 frozen app and the new
Phase 3 resources: native credential persistence, migrated preferences, identical
validated historical brief and byte-identical history database, with distinct executable
identities. This supersedes the earlier unverified credential result after cancellation;
no assertions, timeouts or vault access controls were weakened. Signed distribution and
Windows verification remain separate outstanding gates.

Inspection also confirmed `/Applications/ResearchAssistant.app` still contained the old
frontend. The new Phase 3 DMG was opened for the user to replace the installed application.
Installation/replacement by the user has not yet been verified.

## 2026-09-08 visual refinement

The user requested warmer, more varied colors, automatic preview playback, a smaller
side-by-side desktop home layout and removal of repetitive explanatory/footer copy.
The initial viewport of https://nomu.store/ was inspected without scrolling or exploring
lower sections. Coral, apricot, green and plum now distinguish actions, workspace,
supporting and challenging evidence. The hero and preview share the desktop viewport;
narrow windows retain readable stacking and scrolling.

The isolated example automatically advances through preparation, evidence, completion,
interruption and recovery. Hover and keyboard inspection pause it; hidden documents do
not advance. Reduced-motion mode shows a static completed example. A compact Example
badge and fictional source labels preserve its distinction from actual research. No
provider calls, engine changes, new dependencies or storage changes were introduced.
This supersedes the earlier manual example controls and dark workspace styling.

Verification: 942 tests passed, 2 existing skips; Ruff, frontend lint/types/build,
offline browser acceptance, archive validation and packaged Mac window test passed.
Updated installer and screenshots: `desktop/dist/phase3-colors/`. Replace the installed
app to see this refinement. See the Phase 3 verification record for retry details
and unchanged Windows/public-release gates.

## 2026-09-09 orange/green and sourced evidence refinement

At the user's request, orange and green are the only accent families; neutral surfaces
replace saturated background panels. Four real-source cards replace the fictional pair
and takeaway box. Source-type labels were removed; source links, years and expandable
context remain. Automatic playback, reduced motion, side-by-side desktop layout and
all actual research functionality remain. See [preview source audit](docs/preview-sources.md)
for provenance and the distinction between curated example material and live-run output.

Verification passed: 942 Python tests (2 existing skips), Ruff, frontend lint/types/build,
offline browser interaction/desktop-fit checks, DMG/ZIP integrity and packaged Mac
window/security/shutdown checks. Updated installer: `desktop/dist/phase3-evidence/`.

## 2026-09-12 preview tempo and orange hue

The requested fivefold speedup conflicts with the above-10-second full-loop minimum:
28.8 / 5 = 5.76 seconds. The loop is now 10.4 seconds (8 × 1.3 seconds), with its first
completed result at 3.9 seconds. This replaces the prior 3.6-second stage timing.
Hover/focus pause and static reduced-motion behavior remain. Orange accents shift toward
amber-orange; green and neutral surfaces remain. Browser timing measured 10,496 ms.
942 tests passed (2 existing skips), plus Ruff, frontend lint/types/build and offline
browser acceptance. New Mac installer location: `desktop/dist/phase3-tempo/`.

Final Mac artifact checks passed: DMG checksum, ZIP integrity and packaged window
load/authentication/renderer isolation/duplicate exclusion/normal shutdown.
