# Phase MVP-3B - Full Live-Canary Stabilization

## Completion Record - 2026-07-31

MVP-3B is complete. The approved positive direct-MiMo canary released with a valid
deterministic final result and persistence-stable SHA-256
`4f17c54f0b2d475552266026d5b6c0dd84b91a0044c1e60970dfc2e9526551ba`; the controlled
negative canary reached its expected typed failed state and persisted its bounded reason.
Exact claims, run IDs, usage, costs, incompatibilities, fixes, verification, limitations,
and CLI suitability are recorded at the top of `STATUS.md` and `HANDOFF.md`. Changes remain
uncommitted. Stop here; MVP-4 requires separate explicit approval.

## Authorized Direct MiMo Amendment - 2026-07-29

The user explicitly replaced OpenRouter with Xiaomi's direct MiMo platform for MVP-3B.
Use direct `mimo-v2.5-pro` as the sole LLM route for all five roles. Preserve the
historical MVP-2B/MVP-3A OpenRouter implementation and tests, but an MVP-3B run must make
no OpenRouter or MiniMax call. Xiaomi JSON mode is followed by exact local Pydantic
validation; there is no response healing and no cross-provider fallback. Direct MiMo
cost is calculated conservatively from a frozen dated price cap and labeled estimated.
All other phase scope and safety limits below remain binding.

## Prerequisite and Purpose

Begin only after MVP-3A passes with realistic mocked provider responses. This phase is
limited to tightly controlled live validation and narrow fixes demonstrated by actual
Wigolo/OpenRouter incompatibilities. Do not add the live CLI, modify Streamlit, redesign
orchestration, or begin MVP-4.

## Live Safety Gate

Credentials alone never trigger execution. Every live run requires an explicit enable
flag, explicit user approval, a dedicated test database, public/non-sensitive claim,
strict deadlines, limited retries, secret redaction, fail-closed pricing, and explicit
maximums for Search calls, acquisition candidates, snapshots/Extractor calls, physical
LLM calls, tokens, and USD cost. Never exceed the approved MVP-2A/MVP-2B limits.

## Required Canaries

Run two cases only when all configuration and approvals are present:

- Positive: an easy, narrow, well-documented public claim. It must complete the whole
  provider-backed pipeline, release at least one brief, pass deterministic final
  validation, produce a hash, reconstruct from persistence, and remain within limits.
- Negative: a controlled public case expected to block or fail safely. It must reach the
  expected typed terminal state with correct persistence, redaction, and reason.

A blocked positive canary is insufficient. At least one approved live claim must release
before MVP-3B can be declared complete.

## Permitted Fixes

Only make narrow changes justified by observed behavior: response normalization, strict
schema handling, deadlines, error mapping, provider-required prompt compatibility,
capability declarations, returned identity handling, usage/cost parsing, or deterministic
extraction normalization. Do not add speculative abstractions or another provider.

## Verification and Report

Rerun focused provider tests, all mocked integration/restart/cancellation tests, full
offline suite, offline evaluation, Ruff, both live canaries, persisted positive-result
reconstruction, `git diff --check`, and Git status.

Report exact files, both exact claims and terminal states, actual Search/acquisition/LLM
counts, tokens, estimated/confirmed cost, incompatibilities, narrow fixes, final
validation/hash, suitability for the CLI MVP, and limitations. Leave changes uncommitted.
