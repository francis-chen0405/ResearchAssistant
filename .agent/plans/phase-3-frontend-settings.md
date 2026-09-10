# Phase 3 — Frontend overhaul and provider/model settings

Authorized 2026-09-07 by the user's full Phase 3 request. In progress on
`codex/phase-3-frontend-settings`, from clean completed Phase 2.
This replaces the older current-state prohibition on Phase 3, not its historical record.

1. Verify prior handoffs, live contracts and native packaging (read completed).
2. Build an ivory/grid design system, floating navigation, welcome and interactive
   explicitly fictional preview; share workspace/status components with real research.
3. Expose direction, supported model profile, budget and readiness in the composer.
   Cohesively rebuild results, history, provider setup and accessible dialogs.
4. Add strict supported-profile selection, maintained conservative prices and offline
   preflight. Preserve native credentials, old preferences, frozen run contracts and
   all pipeline/release/cancellation behavior. No new provider or dependency planned.
5. Add offline regressions and browser interaction coverage. Run full Python/Ruff,
   frontend lint/types/build, diff and native packaging/smoke checks. Inspect screenshots.
6. Rebuild installers where target tooling is available, record actual verification,
   update current docs and stop at Phase 3. No public release or paid calls.

Visual reference: supplied Nomu image only guides composition/surfaces/spacing.
The earlier product-preview screenshot was not attached here; the user's detailed
floating-panel specification supplies the implementation requirements.

Profile scope: only the established MiMo/Luna role combination is offered. Role
assignments are inspectable; arbitrary role remapping remains unsupported. Maintained
caps cover cache-miss/long-context exposure; official pricing sources and dates will
be recorded in configuration documentation. Legacy explicit configuration remains
available for historical compatibility but is not advertised as tested model support.

## Implementation outcome

Steps 1–5 are implemented: all redesigned surfaces, shared/local-only preview, provider
settings, strict profile defaults, offline preflight and automated interaction coverage.
No new dependency, provider or research behavior was introduced. Current STATUS/HANDOFF
replace their prior summaries, preserved verbatim under `docs/archive/phase-2-handoff/`.

Step 6 is partially verified: the native macOS build is rebuilt; Windows requires an
authorized native runner. The user denied the cross-version Keychain prompt; its separate
credential migration assertion remains unverified, not waived. Old-to-new preferences
and historical brief/database integrity passed a data-only check without sharing a key.
The [verification record](../../docs/verification/phase-3.md) records final checks/artifacts.
Do not declare cross-platform phase acceptance complete or begin another phase.

The user subsequently requested delivery on `master`; local delivery uses a fast-forward
that includes the completed Phase 2 prerequisite commits. Remote publication is not authorized.

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
all actual research functionality remain. See [preview source audit](../../docs/preview-sources.md)
for provenance and the distinction between curated example material and live-run output.

Verification passed: 942 Python tests (2 existing skips), Ruff, frontend lint/types/build,
offline browser interaction/desktop-fit checks, DMG/ZIP integrity and packaged Mac
window/security/shutdown checks. Updated installer: `desktop/dist/phase3-evidence/`.
