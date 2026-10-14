# Prompt 16 — Mac distribution and installed-cache verification

Verified October 13, 2026 on macOS 26.6.2 (25G83), Apple Silicon arm64.
The current dirty working tree at `94a241b52f9525cab3aff52d1f85026f081b3e85`
produced a complete **unsigned local distribution candidate**. It is not a public
release. The installed October 9 app was preserved. No paid provider calls,
real-cache repairs, research migrations, credential replacement, staging/commit,
fetch/push or public upload occurred.

The [exact JSON record](mac-delivery-gates-2026-10-13.json) owns full identities,
artifact sizes/hashes, cache results and evidence-log hashes. Local logs/helpers are
under `desktop/build/prompt16-20261013/`; scratch build/install resources remain
under `/private/tmp/researchassistant-prompt16-20261013/`. Deliverable files are
retained in `desktop/dist/prompt16-20261013/`, separately from historical artifacts.
The [October 9 installation record](current-app-install-2026-10-09.md) and
[database review](database-phase4-review.md) remain unchanged historical evidence.

## Exact identities and build provenance

| Surface | Identity / SHA-256 |
| --- | --- |
| Installed app | `/Applications/ResearchAssistant.app`, version `0.1.0`, `org.researchassistant.desktop` |
| Installed backend bytes | `12e1705b6790b2532e8284ce5baa32e25f09b83de701dd15ce6d0415945c03f5` |
| Installed source-only identity | `source-sha256:c8a3543a1f77f20586586e8487fb22130c6fe71f50ad3c3c582cfbfb1ba2805f` |
| Installed observed frozen identity | `source-sha256:66a5233ff2ffa535e7061b8cd28be65b2dcf5c4eec399ef50e34c76d04597b90` |
| Current and packaged source-only identity | `source-sha256:49db1858f558ba58234ea4509ecce80266df22bda4887cf6feda6d4c9d09bf41` |
| Candidate backend bytes | `ca47831babcb685626f01a088327544e9c092daac52a2c130ce458c195365db5` |
| Candidate observed frozen identity | `source-sha256:5b57457e0c9f3771a02907e764e2548ebff72535bef0ad70ce6d3aa49d1da128` |
| Candidate app | `0.1.0`, bundle build `20261013.16`, Apple Silicon, `org.researchassistant.desktop` |
| Packaged Electron main, identical to source | `89ff592b55f70834d4480dc5d54078dadd13056a0d51c0ad22435fe12d67fdf6` |
| Cache integration policy | `bef371fc054733c6e26a7af810facfdcd4fb83b2c13329c0cc19520f286817a8` |
| Patched packaged Wigolo database module | `6cabc7847b07413ead1b1a9cc5e92f2ac01cfa3f320d3048250b7cb2d9a19261` |

Both backends' reported identities were compared with the calculated exact frozen
identities during authenticated isolated launches. Source-only identity covers the
backend distribution surface; frozen identity also includes its executable bytes.
The separately hashed acquisition policy is an external-cache integration input,
not part of that backend-only source hash. The installed backend still matches the
October 9 record before and after this work; newer backend/renderer work and this
cache policy have not been installed over it. Historical identities are not converted.

Python 3.12.14 / PyInstaller 6.22.2 (hooks 2026.7), Node 24.18.0, Next.js 16.3.1,
Electron 44.2.0 and electron-builder 26.15.3 were used. Locked Wigolo is 0.2.1,
better-sqlite3 reports SQLite 3.53.0, and sqlite-vec is 0.1.9. No dependency versions
were added or changed. Backend resources were built with `--clean` into a new
scratch destination; the existing builder's staging logic was used with scratch
output paths and a byte-identical `desktop/backend.py`. The renderer was freshly
exported with webpack. Exact pinned Node/Chromium resources were reused unchanged;
acquisition was freshly staged from the locked source with the reviewed policy.
No runtime data, real cache or vault values were build inputs.

Parity covers 290 backend source/prompt/font/document files plus backend configuration,
all 31 exported renderer files, acquisition package/lock bytes, and the main process
extracted from `app.asar`. Wheel verification audits the exact 296-file backend
inventory and exercises wheel/editable CLI/API/resource installs. The standalone
source archive contains 632 owned source/build/test/evaluation/workflow files and
locks; `SOURCE-MANIFEST.json` binds every supplied path/byte. It excludes developer
runtimes, generated bundles, native credentials and runtime databases.

Earlier staged work is unchanged: binary-diff SHA-256
`85f8753d0bb6ba7af20c688eab28ad10429ee43329b879d89b8db48071324cf2`.
The original pre-task status/handoff/index were copied byte-for-byte to the
[archive](../archive/2026-10-13-mac-delivery-preceding-state/README.md).
Graph freshness was checked and the advisory index refreshed without persistence
(12,391 nodes / 76,120 edges); identity/staging findings were verified against live
source, package bytes, the diff and focused tests.

## Installed cache: access, findings and confirmed repair

The inspected cache is
`~/Library/Application Support/ResearchAssistant/acquisition/wigolo.db`, owned by
UID 501 / GID 20, mode 0600; its application-data and acquisition parents are 0700.
Model-resource subdirectories are traversable only through those private parents.
No process had the cache open and no WAL/SHM sidecars existed at the inspection
boundary. Its unchanged SHA-256 is
`8b493db7055402e10c34d614e2623564d2a2abd23fb603d51eaf0fafc24e8a6f`.

The installed app's own Node/native vector extension could load the database
connection, but the first direct read-only query returned **`unable to open database
file`** in the restricted inspection context. No permissions, ACLs or sidecars were
changed to bypass that limit. Instead, the quiescent file was copied byte-for-byte
into a mode-0700 disposable directory. The installed runtime opened that copy
read-only, loaded its exact extension and used SQLite backup to create a second
private disposable database. FTS write commands and deeper checks ran only there.
Copies were removed in `finally` blocks. Cache hash, mode, owner, size, mtime and
absence of sidecars were rechecked after inspection and after disposable repair.

| Installed-cache copy check | Actual result |
| --- | --- |
| SQLite core integrity / foreign keys | `ok` / zero violations; journal mode `wal` |
| Recorded migrations | All nine, `001-sqlite-vec` through `009-content-completeness` |
| URL / search / feed counts | 93 / 0 / 0 |
| Vectors / ID map / metadata | 93 / 93 / 93; vector bytes 1536 = 384 float32 values |
| Vector/map/metadata references | No missing or orphaned row IDs; metadata URLs match map IDs |
| URL ownership references | All resolve through upstream exact-or-normalized lookup; 54 lack an exact literal match but **zero** lack a normalized cache owner |
| Feed external-content FTS integrity | Pass |
| URL external-content FTS integrity | **Fails `SQLITE_CORRUPT_VTAB`: database disk image is malformed** |

This differs from the earlier repository-build cache result (39 rows / valid FTS).
That pass was not evidence for the installed cache. Core database integrity remains
valid; the failure is a stale derived URL full-text index, not evidence that saved
research is corrupted.

A synthetic test using the exact pinned upstream database reproduces the defect:
`cacheContent` uses `INSERT OR REPLACE`, while SQLite's default disabled recursive
triggers omit the old row's FTS delete trigger. Repeated captures leave stale index
entries. The integration policy is applied only during packaging; installed files
and checkout `node_modules` remain untouched. Staging refuses upstream `db.js`
unless its hash is exactly
`3fbee2a93d4424d2174fd758141b945d54aa198e24a030482c7101ce485385f1`.

`desktop/acquisition/cache-policy.mjs` enables recursive triggers on the actual
Wigolo connection, then validates URL FTS against external content. Only a recognized
FTS corruption error with passing core integrity permits a transactional derived
index rebuild/recheck. Core corruption and unrelated errors fail; content, vectors
and migrations are never discarded. Four native regressions cover reproduction,
repair/preservation/future replacement writes, healthy repeated initialization,
and refusal cases. Two Python staging checks cover exact reviewed bytes and refusal
without replacing existing resources. CI invokes the native tests after staging.

Invoking the **candidate's patched initialization** on the disposable installed-cache
backup passes FTS and reports recursive triggers enabled. Exact content/vector/map/
metadata/migration rows remain unchanged. The user's real cache still has its original
FTS inconsistency: this task intentionally did not modify it or replace the installed
app. Future adoption of the candidate applies the tested policy on ordinary owned
Wigolo startup. No user credentials, URLs or page bodies were printed in the report.

## Local distribution and saved-data checks

- Full source suite: **2,797 passed / five existing skips**, 306.43 seconds.
  Focused Python: 16 passed; native cache: four passed; desktop unit: 20 passed.
- Ruff lint and format: pass, 469 files. Repository/import boundaries, generated
  API contract parity and working/staged whitespace: pass. Frontend lint/types,
  static export and all five offline browser/API/race checks: pass.
- Frozen check, with empty developer-tool PATH and unrelated working directory:
  authentication/origin boundary, static UI, preferences, native vault round-trip,
  restart persistence/cleanup, owned Wigolo health/start/stop and shutdown pass.
- Real packaged window: authenticated renderer, seven empty password inputs,
  no renderer Node/browser storage, duplicate exclusion and normal shutdown pass.
  Native process-ownership and accelerated real-Electron failure/deadline tests pass.
- October 9 installed backend to current candidate: both authenticate; native test
  credentials and configurable preferences persist; validated historical brief is
  identical and history database is byte-identical; executable identities differ.
  The stock upgrade harness passed without fixture conversion or assertion changes.
- DMG checksum verification and ZIP compressed-data integrity pass. The DMG was
  mounted read-only, copied with `ditto` to an isolated local installation directory,
  then detached. **31,127 files/symlinks and their modes** match between the original
  bundle, DMG-installed copy and ZIP. Its copied backend and window repeat frozen/
  native-vault/acquisition and UI checks. This is a current-host local installation
  check, not a clean-machine test.
- Real application data: all 60 manifested entries (30 content-hashed files,
  remaining directories/symlinks and sensitive-file metadata) are identical before
  and after isolated checks. Token/credential-file contents were not read for that
  manifest. Original cache and installed backend remain unchanged. Real vault
  entries were not replaced/deleted; test-only namespaces were cleaned up. No real
  research DB was opened for writable migration, and unknown reservations remain.
- Fresh offline evaluations retain 38 integrity cases, six synthetic discovery
  scenarios, two authored held-out visibility cases, zero-observation quality replay
  and one authored arithmetic observation. No live research/quality claim follows.

Initial restricted browser binding and process-ownership checks failed under the
sandbox; unchanged checks passed with authorized local execution. Initial wheel
build dependency lookup failed because network DNS was unavailable; the existing
pinned offline wheelhouse then passed exact wheel/editable verification. Packaging
first rejected a CLI array override; a complete scratch JSON configuration passed.
These failures and successful reruns are retained in logs, not hidden as passes.
No app/cache defect was inferred from those harness/environment failures.

## Exact unsigned candidate artifacts

All paths below are relative to `desktop/dist/prompt16-20261013/`.

| Artifact | SHA-256 |
| --- | --- |
| `ResearchAssistant-0.1.0-prompt16-20261013-arm64.dmg` | `db5cfd0b722cc0b58ff6be7c8e970fe0d87681130ec7a80f16356789a5a0bc3a` |
| `ResearchAssistant-0.1.0-prompt16-20261013-arm64.zip` | `f69c8b00afd852ade1169eb150a7e0d9dea5ba6bdf621faaf8cb86045c699965` |
| `ResearchAssistant-prompt16-20261013-source.tar.gz` | `c0bf6240188d0a0e71d26ef9debd154e80b5f73b144b2cebb42cb4e4e58a3a01` |
| `SOURCE-MANIFEST.json` | `bb43cb1c2c4587810de990b6d036f314221e08d6e68f50753226b59978f847f1` |

`SHA256SUMS`, `RELEASE-NOTES.md` and the exact verification JSON accompany these
artifacts. Existing ignored installers and historical logs were preserved.

## Minimum OS, signing inputs and precise remaining gates

Bundle metadata declares **macOS 14.0**. Every one of 111 arm64 Mach-O payloads
was inspected successfully; none declares a load-command minimum above 14.0.
`otool` interprets parentheses in helper filenames as archive syntax, so those files
were inspected through temporary neutral-name symlinks. This resolves a tool-path
error without changing bytes. Actual macOS 14 execution and clean-machine behavior
remain unverified because no suitable external test Mac/VM is available here.

`security find-identity -v -p codesigning` reports **zero valid identities**. The
candidate has linker/ad-hoc binary signatures, no TeamIdentifier and no sealed
Developer ID app resource signature. Gatekeeper rejects it with `code has no
resources but signature indicates they must be present`; the DMG has no stapled
notarization ticket. The prior record states no Apple Developer membership/certificate.
No certificate/private key, Apple account password or notary credentials were read,
exported, requested in chat or uploaded. `notarytool` 1.1.3 (42) is available.

Prepared inputs: `desktop/release-signing.cjs` and `release-entitlements.plist` pass
the pinned electron-builder 26.15.3 configuration/plist checks. They require a local
certificate name and notary-profile name, refuse unsigned fallback, request hardened
runtime/JIT and notarization. No existing repository signing/notarization mechanism
was found; these inputs use supported local Keychain identity/profile handling.
Their signed-runtime behavior cannot be validated without the missing identity.
See [Apple Developer ID](https://developer.apple.com/developer-id/),
[Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
and [Electron notarization's Keychain support](https://github.com/electron/notarize).

When the prerequisites exist, create/use the notary profile interactively in the
local terminal, with secrets entered only through its secure prompt:

```sh
xcrun notarytool store-credentials ResearchAssistant-notary
```

After rebuilding current resources and running their checks, use the local
Developer ID certificate's name and the existing profile. The variables below
contain names only; their private key/password remain in Keychain:

```sh
CSC_IDENTITY_AUTO_DISCOVERY=true CSC_NAME="$RESEARCHASSISTANT_SIGNING_IDENTITY" \
APPLE_KEYCHAIN_PROFILE=ResearchAssistant-notary \
npm run package --prefix desktop -- --arm64 --config=release-signing.cjs \
  --config.directories.output=/private/tmp/researchassistant-signed-successor
```

The unsigned candidate must be retained. Signing changes executable bytes: recompute
source/artifact hashes and reported frozen identity, then repeat vault/runtime/UI/
upgrade/installer checks. Inspect every nested signature and Apple notary results;
configuration alone is not signed acceptance. After the signed app is notarized,
submit/staple/validate the final DMG through the same local profile and retain the
receipt, then verify Gatekeeper without overrides. Recreate ZIP from the final
stapled app if any app bytes change; issue new checksums for signed artifacts.

The only remaining delivery prerequisites are **Developer ID/Apple notarization
access through local Keychain**, and **a clean Apple Silicon Mac plus actual macOS
14 execution** for signed install, credential-backed launch, acquisition lifecycle
and old-to-new saved-data testing. No quarantine removal, ACL weakening or Gatekeeper
bypass counts as acceptance. **Publishing/uploading a public release requires
explicit final authorization after those gates pass.** Current installed-cache
inspection is documented, including the exact direct-access failure and successful
supported disposable-copy route; it is not left inferred from repository cache tests.
