# Source discovery implementation prompts

> Historical proposal/prompt pack. All six source-discovery phases and cross-phase review fixes are now implemented and committed locally; see [the shared implementation record](../../../../.agent/plans/source-discovery-v2-2026-10-05.md) and [current STATUS](../../../../STATUS.md). The instructions and observations below retain their original scope; live acceptance and delivery remain pending. Use the current handoff for subsequent work; implementation prompts below describe completed scope.

## Original October 5 proposal text

Prepared October 5, 2026 for the current ResearchAssistant repository. These documents are implementation instructions to use in order, not a claim that the features have been implemented. Creating this pack does not alter active application behavior or the repository's verified implementation status.

The approved scope is three changes: **engine-specific queries**, **deeper metadata retrieval and ranking with better exact source previews**, and **expansion from strong seed papers**. The pack covers supporting contracts, budgets, persistence, identity, old-client/history compatibility, provider execution, API/CLI/desktop UI, tests, and acceptance. Automatic full-text recovery, OCR, specialist catalog providers, and a new generic research-round system are excluded.

Each phase repeats the requested GPT 6.1 Sol High / `gpt-6-luna` helper directive and the shared invariants so it can be pasted into a new coding chat. Select the intended main model separately in the app; text in a prompt does not change the actual selected model. Helpers must review actual available capabilities rather than claim a model/tool exists when it does not. These coding-team directions do not change ResearchAssistant's own research-model choices.

## Run order

1. [Foundations and contracts](01-foundations-and-contracts.md): versioned policy, strict typed handoffs, budgets, persistence, identity, and compatibility.
2. [Engine-specific queries](02-engine-specific-queries.md): conceptual planning, provider syntax compilation, lexical/semantic modes, adapters, and initial/adaptive wiring.
3. [Deeper retrieval and ranking](03-deeper-retrieval-and-ranking.md): real depth/pagination, per-page accounting, fair ranking, bounded Scout, and acquisition shortlist.
4. [Claim-aware source previews](04-claim-aware-source-previews.md): exact methods/results windows, section/context signals, and actual Source Selection integration.
5. [Expand from strong papers](05-expand-from-strong-papers.md): seed identity, references/citing/related-work requests, bounded expansion, provenance, and normal evidence handoff.
6. [Integration, UI, and acceptance](06-integration-ui-and-acceptance.md): ordinary product entry points, settings/diagnostics/history/export, whole-suite checks, ablations, and completion matrix.

[All six prompts in one document](all-six-prompts.md) contains the complete repeated instructions. [The source audit](source-audit.md) records the observed ALPR cases and distinguishes historical capture failures from current source behavior.

## Suggested ownership and model effort

Sol owns contract/policy design, run identity, budget and trust-boundary decisions, critical integration, and final acceptance, and performs some of that implementation itself. Luna helpers should take most scoped discovery, primary-documentation research, call-site inventories, adapters, fixtures, UI plumbing, focused tests, and independent review. Start with low effort for simple lookup, medium for ordinary implementation, and high for complex bounded review; increase based on the task rather than sending every helper the maximum effort. Give independent helpers non-overlapping edits and require evidence-based handoff.

## Completion criteria

- All existing enabled engines receive appropriate compiled queries; supported semantic requests really reach the provider and carry the correct accounting.
- Deeper metadata retrieval/pagination works within actual provider limits, with no free pages or hidden requests; a useful below-five candidate can reach the acquisition shortlist.
- Previews are exact spans of owned immutable snapshots and help identify relevant substantive methods/results without becoming factual evidence.
- Seed-paper neighborhoods reveal additional work through verified provider metadata and stay within existing authorized rounds, lane slots, physical request budgets, and one-hop/run caps.
- No discovery path bypasses acquisition/extraction/assessment/admission; no historical release, cost, source family, or artifact is rewritten.
- API, CLI, desktop, diagnostics, history, trail, export, fingerprints, and package identity work together; offline evidence supports the claimed fixture improvements.
- Required checks pass and limitations are honestly recorded. Live quality, paid research, real-data mutation, app replacement, commit/push, and publication remain separate actions.

## Execution notes

Before each phase, inspect the previous phases' actual diffs/tests instead of assuming completion. Keep one shared implementation plan. Proposed initial defaults are ceilings subordinated to tighter provider/run budgets, not a promise of additional spending. Do not raise current hard ceilings to make the feature pass. A provider's unsupported capability gets an explicit bounded fallback/skip; it must not be silently advertised as present.

As official endpoints, capabilities, and pricing change, implementation must recheck current primary documentation and store the actual chosen policy/version. The prompts intentionally require this rather than hardcoding today's external API assumptions into future execution.
