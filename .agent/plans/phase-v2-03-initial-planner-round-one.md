# ResearchAssistant v2 — Phase 3: Initial Planner and Broad Round 1

Status: Complete and verified on 2026-08-20.

## Scope

- Add the fresh-v2 startup Initial Planner, using the v2 MiMo-v2.5-Pro Planner route.
- Preserve the submitted claim byte-for-byte, retain only material scope interpretations,
  and generate only broad discovery queries for Round 1.
- Centralize enabled-provider and Round-1 lane eligibility in one application-owned v2
  policy. The policy keeps the established two SERP Search, three Exa, and one OpenAlex
  broad-query ceilings for each enabled direction; no provider ceiling increases.
- Persist an append-only initial-plan record and Round-1 query rows with run, direction,
  provider, round, strategy, query text, timestamps, and policy identity.
- Retain v2 generic artifact persistence and historical/pre-v2 planner and pipeline readers.

## Explicitly out of scope

- Round 2 or Round 3 generation, targeted replanning, objectives, importance scoring,
  discovery execution, provider calls, Scout, Gap Analysis, source selection, Luna
  transport, evidence analysis, or user-interface changes.

## Completion signal

Offline tests prove support-only, challenge-only, both-direction isolation, provider
toggles, disabled/invalid provider rejection, invalid rounds, duplicate IDs/text,
Round-1-only planning, no future search plan, append-only persistence/restart, and
contract-fingerprint mismatch. Existing historical Planner and v2 Phase 1–2 tests remain
green. No live provider call is made during verification.
