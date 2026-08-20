# ResearchAssistant v2 — Phase 5: Acquisition Routing, Snapshots, Probe, and Survivor Pool

Status: Complete and verified on 2026-08-20.

## Scope

- Reuse the existing Wigolo acquisition boundary as the primary route and permit Firecrawl
  only as its optional, verified-preflight fallback.
- Order conservative source clusters by Scout `retrieve`, deterministic discovery rank, and
  Scout `maybe`; Scout `skip` records are never normally acquired.
- Attempt a cluster's preferred URL first, then its retained alternate URLs only after an
  eligible failure. Do not reacquire an equivalent cluster after success.
- Preserve each successful normalized response as a strict, hash-verified `SourceSnapshot`
  inside an append-only v2 Phase-5 artifact, with source identity and acquisition provenance.
- Add deterministic sentence-level Probe windows with exact offsets, snapshot IDs/hashes,
  opening/conclusion/evidence-density/citation signals, and no LLM invocation.
- Persist every successful, usable Probe source as a survivor; preserve snapshots and an
  explicit failed Probe audit without inventing passages or making that source available to
  later Gap Analysis.

## Explicitly out of scope

- New provider transports, live calls, dependency changes, Claim Fit or Evidence Quality
  scoring, factual claims, Claim Ledger admission, Gap Analysis, source recommendation,
  deep analysis, later rounds, or UI work.

## Completion signal

Offline tests cover Wigolo success, verified Firecrawl fallback, provider ordering,
preferred/alternate URL behavior, Scout skips, immutable snapshot hashes, deterministic
2–5 passage Probe behavior and exact offsets, low-overlap fallback, survivor persistence,
Probe failure, and restart reuse. Existing safety regressions remain green.
