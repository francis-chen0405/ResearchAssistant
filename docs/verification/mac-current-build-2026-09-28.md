# Current Mac build verification — 2026-09-28

Source: clean `master` at `ac49404` before this verification-only harness/documentation
update. Target: Apple Silicon macOS 26.6.2, Python 3.12.14 and Node 24.18.0. The
package declares macOS 14.0 as its minimum. No paid provider call, real-data
migration, installed-app replacement, or remote publication occurred during the build
verification. The verified artifacts were published afterward as described below.

## Source and bundled runtime

| Check | Result |
| --- | --- |
| Full Python suite, warnings as errors | 1,204 passed, 2 existing skips |
| Ruff lint/format and diff whitespace | Passed |
| Frontend ESLint and TypeScript | Passed using installed local binaries |
| Deterministic offline evaluation | Passed |
| Fresh static export and PyInstaller backend | Passed |
| Offline interaction, polling, configuration-race browser smokes | All passed |
| Frozen backend smoke, native vault/settings and Wigolo lifecycle | Passed |
| Actual Electron window smoke | Passed |
| Packaged backend and packaged window smokes | Passed |
| Packaged source identity inputs | All 100 current files match byte for byte |
| DMG and ZIP integrity | `hdiutil verify` and `unzip -tq` passed |

The first offline browser attempt could not bind localhost inside the restricted
sandbox; the unchanged smoke passed with localhost execution permitted. The normal
build first could not resolve Node's official checksum host inside that sandbox;
the unchanged builder then completed with network access. The pnpm wrapper attempted
an unnecessary registry check; installed local ESLint and TypeScript binaries passed.

The initial old-to-new upgrade attempt generated schema 14, which the preceding
schema-13 executable cannot read; its first historical-read request returned 400.
The harness now accepts `--previous-schema13`, which removes only the two null
cache-token columns and migration-14 record from the isolated generated fixture. It
rejects any populated cache usage before doing so. With that option, the old and new
executables passed authenticated health, native credential persistence, configurable
model-choice preference migration, identical historical brief, byte-identical
history database, and distinct executable identity. The old and new backend SHA-256
values were respectively `4ef52d66f6c8ee5f80ca26371689c1ac02d4cc8addc5163acd40ff6c5e76f810`
and `945a80542a95cbbb6a02659c3cf9cc1fe4d8c8b13324aa9e8e43b6dee4c39b7f`.

## Artifacts and installation boundary

The OneDrive checkout cannot reliably create disk images in place, so the unchanged
packager built under `/private/tmp` and the verified outputs were copied to
`desktop/dist/mac-current-20260928/`. Both copied files retain these hashes:

- `ResearchAssistant-0.1.0-arm64.dmg`: SHA-256
  `c73d1f93013eeaa91d2c4f79670fcf4a088bbddc03bbe5288eaeeb47cc5042ba`.
- `ResearchAssistant-0.1.0-arm64-mac.zip`: SHA-256
  `ceb13ecef96c2bb0dd7436077b8b183e0b23740c65315cbcf7e17f41d27481e4`.

The DMG mounted successfully. A copied app launched with isolated data and passed
the actual-window smoke on this macOS 26.6.2 host; the copied main executable matched
the packaged one byte for byte. The existing app under `/Applications` was untouched.
This does not simulate a downloaded app's Gatekeeper quarantine or a clean Mac.

`security find-identity -v -p codesigning` found zero valid identities. The bundle
has no Developer ID team signature; strict code-signature verification did not pass.
Signing/notarization cannot be completed on this host. No macOS 14 machine or local
macOS 14 virtual machine was available. The verified DMG/ZIP are still ready locally
as an unsigned downloadable test build. Clean-machine and actual minimum-OS checks
remain open for a broader signed release. The verified files were subsequently published
at the [unsigned Mac test release](https://github.com/francis-chen0405/ResearchAssistant/releases/tag/v0.1.0-mac-test.20260928),
tagged at `ac49404`. The DMG and ZIP are directly downloadable there, along with
`SHA256SUMS.txt` and `READ-ME-FIRST.txt`. GitHub reports the same SHA-256 digests as
the local files and matching sizes for all four uploaded assets. The release is marked
as a pre-release and explicitly describes the unsigned and unnotarized limitations.
The five-submission live allowance remains exhausted; this verification makes no new
live-quality claim.
