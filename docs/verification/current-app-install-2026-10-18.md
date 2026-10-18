# Current Mac app replacement — 2026-10-18

The user explicitly requested deletion of the current Mac app and installation of
the new app. The verified local R01–R59 build now replaces the October 9 app at
`/Applications/ResearchAssistant.app`; the obsolete bundle was removed after all
installed checks passed. The new app was registered and opened normally, and remains
open for the user. This is an unsigned local Apple Silicon build, not a public release.
[Exact evidence](current-app-install-2026-10-18.json) records hashes and checks.

## Installed build and installer

- Build `20261018.59`, version `0.1.0`, identifier `org.researchassistant.desktop`.
- Source: `source-sha256:fe0cc617eaba0753c9895d0a5f4a983f07946c594c7054d9696775250dcf937c`.
- Frozen backend: `source-sha256:721663605cbebb699899af04610598f4f137748125952f5f8c1a3fc0a22a7d6a`.
- Backend SHA-256: `cc9fcdf881589b016869c238188e2c1ff6582d88f8f42707d9ba6d7e2ac0a75e`.
- Installer: `~/Downloads/ResearchAssistant-0.1.0-20261018-review-arm64.dmg`.
- DMG: 1,025,825,811 bytes, SHA-256 `bbe4751370bbdfb3903644a00387a316ea124c0ee7c806bde717ffd0061b9172`.

The installed app came from a verified read-only-mounted DMG copy. All 31,663
payload files/symlinks and modes matched the tested candidate, the DMG-derived copy,
staging and installed app. Exact current shell bytes and all 299 backend source/resource
payloads match the checkout; current frontend and pinned acquisition files also match.
Existing Electron 44.2.0, Node 24.18.0 and Chromium were retained. Electron Builder
26.15.3 created the separate local DMG with publishing and signing disabled.

## Verification and preservation

Both candidate and installed checks pass: authenticated backend/renderer, isolated
native credential round-trip/persistence/cleanup, durable settings, owned acquisition
lifecycle, actual window, empty password controls, renderer isolation, duplicate
launch exclusion and normal shutdown. Old-to-new upgrade uses a disposable schema-17
fixture generated from the installed version’s source/tests; it preserves native test
credentials, model preferences, the exact validated historical brief and history
file bytes. All upgrade assertions remain intact. No real database is used by tests.

The exact 3,195-pass / nine-existing-skip source suite remains applicable: executable
source is unchanged. Packaging/install checks supplement that source evidence.
Normal launch ran the installed main/backend from Applications; unauthenticated
health returned HTTP 401. No paid research or provider submissions occurred.

All 38 existing saved-data files/symlinks matched contents and modes through
replacement and isolated installed checks. Normal opening changed only Electron’s
`Local Storage/leveldb/LOG` and `LOG.old`, and created its three usual running-instance
links. Actual research databases, acquisition cache and preferences remain unchanged;
no existing files were removed. Real native credentials were not replaced/deleted.
The prior app was retained briefly for rollback, verified again and deleted only
after installed checks passed. The verified installer remains in Downloads.

Local logs, helpers and before/after manifests are under
`desktop/build/current-install-20261018/`. Prior source/build/release evidence remains
at its stable paths. All original staged work is preserved; no source changes,
staging, commit, push, signing/notarization, paid research or public release occurred.
Clean/minimum-OS, Windows packaging and signing/notarization remain separate gates.
