# Install audited Mac app and remove obsolete copies — 2026-10-01

Status: complete; latest audited app installed, checked, and opened; obsolete local
copies removed 2026-10-01.

The user explicitly requested the new app be installed and every old
ResearchAssistant app/installer copy removed, including the mac-arm64 copies.
This supersedes prior instructions to keep old generated app artifacts. Keep source,
saved research, preferences, OS-vault credentials, and text/hash/log verification
history. It does not authorize new paid research or release publication.

## Procedure

1. Inventory ResearchAssistant app bundles and installers in Applications, user
   Downloads/Desktop/Applications, repository dist, and temporary packaging folders;
   cross-check Spotlight and remaining user locations. Exclude vendor applications,
   source, saved data, and unrelated mounted volumes.
2. Use the already-local verified comprehensive-audit app rather than fetching the
   older published download. Backend SHA-256 must be
   `2fbffbb0e524a1cd769ac11e37769325044290193707735b771363bf557cd9bd`.
   Stage in Applications and compare every payload file/mode and symlink before
   replacing the old app. Retain a temporary rollback copy until installed checks pass.
3. Stop only ResearchAssistant instances/owned descendants if present; install at
   `/Applications/ResearchAssistant.app`. Test the installed bundle with isolated
   packaged backend and window smokes, preserving real data and credentials.
4. Once those checks pass, delete obsolete inventoried bundles/installers, redundant
   packaged candidates, and obsolete generated resource backups. Preserve reports,
   checksums/logs, current development inputs, source, and user data. Record removed
   paths and rescan for duplicate apps/installers.
5. Launch the installed new app normally and confirm its process/backend are running.
   Record actual results, unresolved OS prompts, and remaining live/release limits in
   STATUS.md and HANDOFF.md. No Python/runtime source changes require repeating the
   audit's full source suite; installation requires artifact-specific checks instead.

## Boundaries

The app remains unsigned. Existing ad-hoc Electron signature verification is not
Developer ID signing or notarization; these release gates remain open. Do not
change Keychain access control, read API secrets, erase saved history, or bypass
research identity/budget gates. No new provider calls or public download are included.

## Completed result

The [installation verification](../../docs/verification/audited-app-install-2026-10-01.md)
records the exact installed hash, 30,928-file/symlink payload match, installed native
and window checks, unchanged real-data metadata during replacement, and successful
normal launch. Removed 24 redundant/old bundles, 22 archives, 6 blockmaps, 4 old
resource backups, and 22 packaging/cache/intermediate directories; archived 19 text
records. Independent name-only rescan found only the new Applications app and no
remaining installers/mac-arm64 folders. Source, credentials, saved research, current
development resources, and prior verification logs remain. No runtime code changed.
