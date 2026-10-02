# Approved private-surveillance run fixes — 2026-10-02

Status: implementation and final offline/native verification complete; installed delivery verified.

The user approved all findings with “Fix all issues.” This supersedes the preceding manual-testing boundary for these repairs. The [read-only review](../../docs/verification/private-surveillance-run-review-2026-10-02.md) identified four confirmed defects and related research-quality limits.

## Scope and decisions

1. New versioned Analyst/admission policy separates search direction from evidence relationship. Opposite relationships are permitted in the enabled search lane; wrong source identity, disabled search provenance, quotation, quality and Claim Fit gates remain enforced. Historical policies retain their meanings. Preserve the prior prompt and add a new prompt version.
2. Valid unrelated decisions become typed relevance rejections without retrying; malformed and invalid outputs retain clear failures and bounded retry rules.
3. Fresh sentence segmentation preserves decimals, abbreviations and URLs, exact offsets and complete immutable source text. Preserve historical quotation/context validation. Prefer substantive probes to page controls or links.
4. Derive stopping labels from typed status, not model prose. Reassess evidence sufficiency after analysis deterministically, distinguish strategy coverage from admitted-evidence coverage, and disclose failures or qualified-only findings without inventing proof or closing gaps.
5. Preserve legal scope/conditions in new statements, disclose repeated publishers without merging families, and flag unverified legal assertions from secondary sources. Historical statements and exports remain unchanged.

Three Luna helpers own Analyst/admission, segmentation/probes and result presentation. The primary agent owns integration, post-analysis assessment, docs, aggregate verification and rebuilt Mac delivery. No dependencies, SQL migration, paid calls, real-data mutation or public release are authorized. The user's standing installed-app replacement/obsolete-copy preference applies after the new build is verified. Commit/push remains outside this new phase.

## Verification

Prefer failing regressions for integrity/validator fixes; retain all legacy assertions under explicit legacy policy. Run focused tests, full pytest with warnings as errors, Ruff check/format and whitespace checks, frontend lint/types/static export, offline evaluation and API/browser checks. Verify saved runs read-only with unchanged payload/release hashes. Rebuild and verify frozen/packaged/installed backend and actual window; compare installed/source/export parity before retiring the old bundle. Update STATUS, HANDOFF and a dated verification record with actual evidence. Clean-machine/macOS 14, signing/notarization and live-quality gates remain open.

## Completion — 2026-10-02

All approved defects and safeguards are implemented. Final checks passed 1,346 tests with 2 existing skips, Ruff lint/format (178 files), frontend lint/types/export, offline evaluation, API/browser checks and frozen/packaged/installed native/window checks. All six historical releases and 1,111 artifact payload hashes remain valid. The new installed app matches 30,931 payload entries, 103 source inputs and 27 frontend tree entries. The final [verification record](../../docs/verification/private-surveillance-run-fixes-2026-10-02.md) records hashes, installation and known release boundaries. Stop at manual testing; source is uncommitted and no automatic commit/push or paid run follows.

## Commit and installer redelivery authorization — 2026-10-02

The user requested “commit, redownload the new app.” This authorizes committing all verified pending review/fix changes and supplying a fresh local installer/reinstallation of the corrected bundle. The known published September download predates these repairs; it is not the replacement candidate. Preserve exact source/export/payload parity and existing saved data. No new paid run, signing or public release is included; push is not part of this request. Prior uncommitted/manual-testing statements above are historical.

## Commit and installer redelivery completion — 2026-10-02

The fresh local installer is in Downloads and passed checksum, CRC and exact 30,931-entry payload comparison. Reinstallation, source/export parity, actual window and normal launch passed; verified temporary copies are retired. [Delivery verification](../../docs/verification/committed-app-redelivery-2026-10-02.md) records the installer checksum and preserved boundaries. All verified pending changes are included in this local commit. The new app is open for manual testing. No push or publication follows.
