# Folders-only root — October 18

The user explicitly selected only folders and README at the GitHub repository root.
Keep ten existing folder owners plus README (11 entries), preserve stable archived
records and actual runtime data, and update GitHub after validation. No application
feature/policy, installed app replacement, paid research or public release is included.

## Changes

- Move instructions to `.agent/AGENTS.md`, with README navigation and corrected links.
- Move workspace configuration to `tests/pyproject.toml`; preserve full test discovery,
  explicit lint configuration, coverage paths and CI commands.
- Move the executable Mac checkout launcher into `desktop/`, resolving the repository
  parent, and reuse the identical existing backend CLI facade instead of a root copy.
- Give all ten owners their own private/generated-file exclusions and LF rules.
  Preserve existing checkout-only root exclusions locally before removing root rules.
- Tighten the root guard to README only, require nested settings/rules in source
  archives, and update launcher/CLI/clean-checkout regressions and maintained guides.

## Verification

Initial relocated-launcher checks passed 113 / one existing skip. Nested configuration
and source/archive checks passed 27 tests before the fresh-checkout regression was added.
Ruff explicit paths retain the existing import classification without changing runtime
source. The complete suite passes **3,196 / nine existing skips** in 415.65 seconds.
Explicit-config Ruff lint/format pass (517 files); repository boundaries and both
whitespace checks pass. The coverage-config smoke passes three tests. A real source
archive contains 2,151 files under exactly 11 top-level entries, with README the
only root file, and requires all ten folders’ Git rules. The new clean-repository
regression verifies private/generated-file exclusions and LF attributes without
using this checkout’s local exclusions. The Mac launcher retains executable mode.

The complete layout is staged for the user-authorized GitHub update. Final local/
remote SHA equality and clean-tree state are reported after the normal master push.

Source identity remains
`source-sha256:fe0cc617eaba0753c9895d0a5f4a983f07946c594c7054d9696775250dcf937c`.
The installed Mac app, packaged backend metadata/resources and real data are untouched.
Preceding current-state/configuration bytes are retained with hashes in
`docs/archive/2026-10-18-root-layout-preceding-state/`.
