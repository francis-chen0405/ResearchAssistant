# ResearchAssistant implementation prompts

> Historical prompt pack from the October 9 foundation proposal. Its instructions
> describe the proposed work at that time, not current authorization or recordkeeping
> requirements. Use [current STATUS](../../project/STATUS.md) for outcomes and priorities,
> and [current conventions](../../project/CONVENTIONS.md) for how to make changes.

## Original October 9 navigation

Copy one numbered file as a standalone prompt. The numbers group a practical sequence; each prompt requires a fresh source/status check and can run in a separate task. After prompts 01–06, the offline preparation in prompt 14 can proceed while prompts 07–13 clean the repository. Prompt 15 needs the benchmark or must limit itself to independently verifiable UI/adapter work. These are implementation requests, not records of completed work. The [foundation review](../project-foundation-2026-10-09.md) supplies the evidence and target layout.

| Order | Prompt | Outcome |
| --- | --- | --- |
| 01 | [Root cleanup and guardrails](01-root-cleanup-and-guardrails.md) | Finish staged stale-copy removal and prevent regression |
| 02 | [Expansion-limit investigation](02-expansion-limit.md) | Reproduce the pasted claim, fix only if confirmed |
| 03 | [Unusable capture fallback](03-acquisition-fallback.md) | Continue to allowed locations after an unreadable capture |
| 04 | [Rejected resume status](04-resume-status.md) | Show actionable rejection without rewriting the old run |
| 05 | [Atomic service lifecycle](05-service-lifecycle.md) | Eliminate research-start/service-stop race |
| 06 | [Bounded desktop shutdown](06-desktop-shutdown.md) | Exit safely when a child stalls |
| 07 | [Installable backend foundation](07-installable-backend.md) | Make current source installable and prepare resources/identity |
| 08 | [Folder consolidation](08-folder-consolidation.md) | Move installable source into a clear backend/frontend/desktop root |
| 09 | [Current docs and tests](09-docs-and-test-navigation.md) | Remove stale guidance and make tests findable |
| 10 | [Python API decomposition](10-python-api.md) | Split HTTP routes from lifecycle and read projections |
| 11 | [Frontend and fast checks](11-frontend-and-ci.md) | Split UI features, check API types and shorten CI feedback |
| 12 | [Neutral contracts and legacy](12-contracts-and-legacy.md) | Remove reverse dependencies and isolate historical execution |
| 13 | [Remaining monoliths](13-research-storage-decomposition.md) | Split active research, storage and contract hotspots safely |
| 14 | [Real quality benchmark](14-research-quality.md) | Measure actual source and interpretation quality |
| 15 | [Discovery and result usefulness](15-discovery-and-results.md) | Use the benchmark to improve source coverage and user value |
| 16 | [Mac release and cache](16-mac-distribution-and-cache.md) | Close installed-cache and public Mac delivery gates |
| 17 | [Windows verification](17-windows-ci-and-durability.md) | Resolve CI and native durability evidence before Windows release |

Completed since the original pasted critique: a current-source Mac app was built and installed locally on October 9; `reportlab` imports in the virtual environment and the PDF tests passed in the 2,232-test suite. The remaining Mac prompt concerns distribution, not another local replacement. The 17 stale-root deletions are staged but not committed. The expansion-limit claim has no confirmed reproducer. Live research calls need a separate bounded allowance; prompts 14–15 complete all offline preparation first.

Each prompt includes the requested GPT-6.1 Sol XHigh/Luna-helper instruction. Use Luna only for narrow simple discovery; Sol owns design, edits, integration and final judgment. Preserve unrelated work and follow the repository's current AGENTS/conventions. Do not treat historical plans or these proposals as evidence that implementation has occurred.
