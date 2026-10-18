# Handoff

[Prompt 12 neutral contracts and historical inspection](../verification/contract-ownership-2026-10-10.md)
is complete locally. Next is source review/commit, or separately authorized native
app delivery. Preserve all earlier staged/unstaged work; the pre-task staged binary
diff is unchanged. [STATUS](STATUS.md) owns current verification and provenance.

Review the dependency map and remaining seams in the Prompt 12 record. Contract
ownership is neutral; old provider/agent/orchestrator import paths re-export the
same public objects. Historical reads belong to `storage.provider_history` and
`historical_decode`; saved neighborhood replay belongs to `storage.neighborhood_store`.
Keep metadata projections shared in `common.discovery_identity` and persisted keys
in `contracts.artifact_keys`. All six restricted import exceptions are removed.
Do not add agent/research imports to storage or provider/agent/research imports to
contracts. The two provider URL/parser helpers in storage remain deliberately allowed.

Preserve explicit `legacy_runner` execution and the older controller `runner` alias.
The historical orchestrator retains execution and re-exports its former read/data
APIs. Ordinary CLI inspection does not resolve its lazy legacy execution symbol.
Current v2 still uses shared evidence renderer/synthesizer; Researcher/Analyst are
already evidence facades. Keep recognized historical decoding, per-record corruption
results, immutable release hashes, read-only snapshots and exact incompatible-resume
behavior. Changed source identity requires fresh runs; stored fingerprints are never
converted. Prompt/font and released-text bytes remain unchanged.

The full Python suite, four focused stages, lint/format/whitespace and fresh exact
wheel/editable-install/resource checks pass. The original source snapshots, staged
diff, identity comparison, wheel inventory and logs are under
`/private/tmp/researchassistant-prompt12/`. Use [the test map](../../tests/README.md)
for ownership, history/export, replay and broader integration regressions.

The installed app remains the unsigned October 9 build recorded in STATUS. This task
created no installer or public release and made no paid provider call. Remaining
platform/delivery gates are Python 3.11/Linux, native Windows/Jobs, current installers,
clean-machine/minimum-OS acceptance, signing/notarization and live research quality
under a separately authorized allowance. Prior API/renderer and native shutdown
records retain their existing verification scope and stable paths.
