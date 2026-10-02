# Audited Mac app installation and cleanup — 2026-10-01

The user explicitly authorized installation of the latest app and removal of all
old local ResearchAssistant copies, including mac-arm64 packaging folders. This
supersedes earlier generated-artifact retention; source, saved research, credentials,
and verification records are preserved. No release was published or paid research
started. The latest build was already local; the older public download was not fetched.

## Installed artifact

- Installed and opened: `/Applications/ResearchAssistant.app`.
- Origin: verified `desktop/dist/comprehensive-audit-20261001/mac-arm64/ResearchAssistant.app`
  from the [completed audit](../audits/2026-10-01/README.md).
- Bundle identifier: `org.researchassistant.desktop`; Apple Silicon, unsigned local
  build on macOS 26.6.2. Developer ID signing/notarization is not claimed.
- Backend SHA-256: `2fbffbb0e524a1cd769ac11e37769325044290193707735b771363bf557cd9bd`.
- Source-only identity:
  `source-sha256:7f9e05142129e7124cae130c4bc8feba32c49b193b8ca15237130e463c87f551`.

The app was staged in Applications and compared against the verified candidate:
**30,928 payload files and symlinks matched**, including file modes. The old installed
copy was kept for rollback until the new installed bundle's checks passed, then
removed with the other obsolete copies. No quarantine attribute was present on the
local candidate; no quarantine or Keychain ACL workaround was applied. Strict
`codesign` verification reports an incomplete inherited Electron signature, consistent
with this unsigned local packaging; it does not establish a signed-release gate.
The complete payload comparison passed again after cleanup and normal launch.

## Installed checks

- `desktop/smoke.py /Applications/ResearchAssistant.app/Contents/Resources`: passed
  frozen UI/backend, authentication, isolated native-vault cleanup, durable settings,
  and owned Wigolo lifecycle. Log:
  `desktop/build/comprehensive-installed-native-smoke-20261001.log`.
- `desktop/ui-smoke.cjs /Applications/ResearchAssistant.app/Contents/MacOS/ResearchAssistant`:
  passed actual window and authenticated requests, seven empty password fields,
  no renderer Node/browser storage, duplicate-launch exclusion, and normal shutdown.
  Log: `desktop/build/comprehensive-installed-window-smoke-20261001.log`.
- Real app-data metadata before installation and after isolated checks/cleanup
  matched: **38 files**, unchanged sizes and modification times. These checks
  precede normal launch; ordinary launch may update its own caches. No saved research
  or real credential was edited or removed.
- Registered the new app with Launch Services and opened it normally. The app and
  bundled backend were running from Applications. Its loopback backend returned
  HTTP 401 to an unauthenticated health request, as required. The first listener
  diagnostic used name-resolved `localhost` output while looking for a numeric IP;
  the corrected `lsof -nP` diagnostic passed. This was a diagnostic mismatch, not
  an application startup failure.

Exact payload manifest, cleanup paths, user-data metadata digests, and normal-launch
evidence are local JSON records under `desktop/build/` with the
`comprehensive-installed-*`, `obsolete-app-cleanup-inventory-*`, and
`installation-user-data-metadata-*` prefixes. The prior audit's full source gates
remain the applicable source verification; this phase changed documentation and
installed/generated artifacts, not runtime code.

## Cleanup result

Removed **24 old or redundant app bundles**, **22 DMG/ZIP archives**, **6 blockmaps**,
**4 obsolete generated resource backups**, and **22 residual temporary packaging,
cache, or backend-intermediate directories**. This includes the old Applications
copy, prior Reviewer-route and first-candidate apps, all repository `desktop/dist`
copies, old temporary apps, and their mac-arm64 folders. The latest source candidate
was also removed after successful installation, leaving one installed app.

Preserved **19 text/hash/package records** under
`desktop/build/retired-package-records-20261001/`, along with the original verification
reports/logs and current development resources. Runtime source and dependencies,
real app data, and credentials were not cleanup targets. The previous candidate and
local published-installer paths in older reports are historical evidence; their
binaries were deleted under this new authorization. Published GitHub assets remain.

A Luna helper independently scanned Applications, the home directory (including
Downloads, Desktop, Applications, Trash, and CloudStorage), and `/private/tmp`.
**Only `/Applications/ResearchAssistant.app` remains as a standalone app**; no
ResearchAssistant installer or old mac-arm64 folder remains in those locations.
Nested Electron helper apps belong to this one bundle; unrelated vendor apps and
mounted Chrome media were excluded. Empty/cache remnants reported in the first
rescan were subsequently removed and recorded.
Final cleanup-inventory and documentation-link checks passed; Ruff lint, formatting
(170 files), and whitespace checks passed on the unchanged runtime source.

## Next boundary

The new app is installed and open for manual testing. Preserve historical runs and
costs; updated executable identity requires a fresh run rather than bypassing resume
checks. No new paid allowance was granted. Live quality, clean-machine/minimum
macOS 14, native Windows, signing, and notarization remain separate verification
limits. Do not infer those gates from this local installation.
