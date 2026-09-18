# Current status

## 2026-09-17 — Authorized reliability follow-up

The user prioritized reliable research and explicitly chose larger responses within
the same total budget. Fresh initial-planner responses now have a narrow valid-default
claim-component schema, unchanged strict rejection and clearer duplicate diagnostics.
Scout uses batches of 20 with corrected Round-4 call reservations. Standard profile
allowances are 4,096 Scout / 8,192 Pro / 16,384 Luna High; request payloads, reservations
and configuration identity agree. Historical generic schemas and data remain unchanged.

992 Python tests pass (2 existing skips), Ruff and frozen offline evaluation pass.
The backend rebuild, native runtime/vault/settings/service smoke, packaging, archive
integrity, upgrade and packaged/installed window checks pass. The updated app is installed;
downloads are in `desktop/dist/mac-reliability/`. Original live acceptance uses the preceding frozen
build and cannot establish these fixes' live effectiveness. See
[reliability verification](docs/verification/planner-scout-reliability.md).

All five submissions are consumed: one harness cancellation, one rejected overlap, one
planner failure and two 20-minute cancellations during deep analysis. No final report
was released; recorded model exposure totals $0.178617536, excluding source-service fees.
The test backend stopped. Further paid acceptance needs a new explicit allowance.
The five-submission cap must not be reset. Public distribution remains
deferred pending live reliability, signing/notarization and clean-machine/minimum-OS checks.

## 2026-09-17 — Mac-first cache-pricing delivery

The user selected Mac first, deferred Windows, and authorized researched cache accounting.
Model-specific tariffs now replace the shared Pro-only calculation; Luna cache writes,
long-context multipliers and explicit High effort are covered. Reservations and unknown
usage remain conservative; historical data and schema 13 are unchanged.

984 Python tests pass (2 existing skips), along with Ruff, offline evaluation, frontend
checks, rebuilt backend, offline browser acceptance, native runtime, packaged/installed
window and cross-version upgrade checks. The new unsigned Mac build is installed;
downloadable DMG/ZIP and checksums are in `desktop/dist/mac-cache-pricing/`.
See [verification](docs/verification/mac-cache-pricing.md).

The authorized live acceptance is bounded to five submissions, including an initial
harness interruption and rejected overlap. A live initial-planner schema rejection
prevented claiming dependable MLP research quality; final outcomes are in verification.
No Apple Developer certificate is available. Public signing/notarization and actual
clean-machine/minimum-OS acceptance remain open; Windows is not a Mac release gate.

## 2026-09-17 — Repository audit and MLP readiness

The core local MLP is implemented; acceptance for reliable live use and public distribution
is not complete. The [readiness audit](.agent/plans/mlp-readiness.md) separates current
Mac delivery from the earlier successful Phase 2 Windows matrix and the outstanding
current-version Windows/install/signing gates. Misleading completion wording and the
evaluation README's repository-wide no-network claim were clarified.

A synthetic offline probe confirmed that cached-token usage in the shared model adapter
uses hard-coded MiMo Pro prices for every route, bypassing configured model caps. The
result flows into remaining-budget calculations. Runtime is unchanged pending the user's
choice of conservative cap accounting or verified model-specific cache pricing.
Acquisition quality and long timeouts remain separate evidence-gathering follow-ups.

Fresh checks: 959 Python tests passed, 2 existing skips; Ruff lint/format, 38-case offline
evaluation, frontend ESLint and TypeScript passed. No paid calls or new packaged build.
The readiness plan records scope, limitations, proposed acceptance and pending decisions.

## 2026-09-14 — Adaptive-search reliability

The user authorized and implementation completed the
[corrective plan](.agent/plans/adaptive-search-reliability.md): exact-claim coverage defaults
and restart persistence, round-aware gap checks, one audited/budgeted Round-2/3 planning
repair, and conservative unresolved-gap reporting. Supporting-only remains fully supported.
Historical reports, Round-4 authorization, budgets and evidence validators are preserved.

Verification: 959 Python tests passed, 2 existing skips; Ruff lint/format, frontend
lint/types/build, offline browser acceptance, visual review and frozen native smoke passed.
No dependencies, database migrations, paid research or remote publication. Packaged Mac
delivery is tracked in [verification](docs/verification/adaptive-search-reliability.md).
The verified update is installed in `/Applications/ResearchAssistant.app`; DMG/ZIP artifacts
are in `desktop/dist/adaptive-reliability/`. Installed window checks and archive integrity passed.
The Phase 3 record below remains the preceding implementation/platform history.

## Preceding Phase 3 implementation record

Phase 3 frontend and provider/model settings were developed on
`codex/phase-3-frontend-settings` and delivered to local `master` at the user’s request. Verification and release limits are recorded in
[Phase 3 verification](docs/verification/phase-3.md). The authorized 2026-09-08 macOS
upgrade test passed for native credentials, preferences and research history. Windows
rebuilding remains outstanding; Phase 3 is not fully verified.

The redesigned welcome, interactive curated-source preview, research workspace, evidence,
history and settings share one visual system. Provider credentials stay in the native
vault; non-secret preferences and the supported Standard model profile are separate
from frozen per-run configuration. Existing research behavior and database schema remain.
No new dependencies, paid calls, public publishing or next-phase work were introduced.

macOS unsigned test artifacts and screenshots are listed in the verification record.
Signing/notarization, clean-machine installation and minimum-OS checks remain release gates.
The Keychain upgrade prompt expects a Mac login/keychain password, not a provider API key;
its cancellation does not establish that the provider rejected a key.

[Phase 3 plan](.agent/plans/phase-3-frontend-settings.md) · [Handoff](HANDOFF.md) ·
[Architecture](ARCHITECTURE.md). This replaces the previous current-state summary;
the exact [Phase 2 status](docs/archive/phase-2-handoff/STATUS.md) and
[earlier history](docs/archive/pre-phase-2/STATUS.md) are preserved.

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
