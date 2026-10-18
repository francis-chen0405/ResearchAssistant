# Install the current Mac app — 2026-10-18

The user explicitly requested deletion of the current Mac app and installation of
its replacement. Package the locally verified R01–R59 build, install and verify it,
then remove the obsolete app bundle. Keep one local installer copy. Preserve actual
research databases, cache, preferences and native credentials; use isolated generated
data and temporary native credential namespaces for checks. No paid research,
public publication, source changes, staging, commit or push is authorized.

## Work

- [x] Verify current source, frozen resources, renderer and pinned shell inputs.
- [x] Package the current unsigned Apple Silicon app and DMG in a separate directory.
- [x] Exercise packaged backend/window and duplicate-launch/normal shutdown checks.
- [x] Snapshot saved-data hashes, stage and verify replacement; retain rollback until installed checks pass.
- [x] Verify installed backend/window and payload parity, remove the old bundle, keep the installer in Downloads and open the app.
- [x] Record exact identities, checks, data preservation and remaining distribution limits.

Source identity is `source-sha256:fe0cc617eaba0753c9895d0a5f4a983f07946c594c7054d9696775250dcf937c`.
Existing frozen backend is `source-sha256:721663605cbebb699899af04610598f4f137748125952f5f8c1a3fc0a22a7d6a`.
The prior 3,195-test source validation remains applicable only while executable source
bytes remain unchanged. Local replacement is authorized; signing/notarization,
minimum-OS/clean-machine, Windows and public-release acceptance remain separate.

## Completion

Installed and opened build `20261018.59`; old app removed. Candidate, DMG parity, installed backend/window and generated schema-17 upgrade checks pass. All 38 saved-data entries matched through isolated checks; normal launch changed only ordinary Electron logs/instance links. Verified DMG is in Downloads. [Exact record](../../docs/verification/current-app-install-2026-10-18.md) retains source/artifact identities and remaining distribution boundaries.
