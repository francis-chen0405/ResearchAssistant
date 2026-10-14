# Handoff

Prompt 16's local Mac delivery checks, candidate and source-archive review repair
are complete. Read
[STATUS](STATUS.md), the [verification/secure signing procedure](../verification/mac-delivery-gates-2026-10-13.md)
and [exact machine-readable evidence](../verification/mac-delivery-gates-2026-10-13.json).
Reviewable DMG/ZIP, checksums, source archive and release notes are under
`desktop/dist/prompt16-20261013/`. The source archive now includes all required
launchers/guidance/template inputs and passes isolated extraction verification;
use the final companion verification/checksums for acceptance, as archived guidance
freezes at source packaging time. Keep the October 9 installed app and real cache
in place unless adoption is requested. Its URL FTS remains inconsistent; the candidate
repair was verified exclusively on disposable data.

Next delivery boundary requires a Developer ID Application identity/private key in
the local Keychain, Apple Developer/notarization access and a locally stored notary
profile. Use the opt-in pinned `desktop/release-signing.cjs`; never put credentials
in chat, source or logs. Rebuild/sign in a new output folder, retain the unsigned
candidate, recompute hashes and observed frozen identity (signing changes executable
bytes), and repeat native-vault/runtime/window/upgrade/installer checks. A native
vault ACL prompt requires the normal OS response; do not weaken ACLs.

Then test the signed/stapled DMG/ZIP on a clean Apple Silicon Mac with default
Gatekeeper and actual macOS 14. Verify install, launch, authenticated API, provider
setup, owned acquisition lifecycle, saved-history/preferences/credential upgrade
and unchanged real data. Static minimum-OS metadata does not substitute for this.
No suitable external test Mac was available in this session. Public release/upload
is a final action requiring explicit authorization after these gates pass.

Preserve historical runs, native vault contents, unknown reservations and all earlier
staged/unstaged work. Current source changes require fresh research under the exact
identity gate; historical inspection/export remains supported. Prompt 14's old
allowance/inputs/zero-spend receipt cannot authorize changed source or a new paid
comparison. Genuine provider responses and human usefulness labels remain a separate
research-quality boundary; authored fixtures do not establish a query-policy winner.
