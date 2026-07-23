# Phase MVP-2B - Production Provider Adapters and Boundary Proof

## Implementation Record - 2026-07-22

Status: Complete offline. The user explicitly approved `httpx`, `markdown-it-py`, `pypdf`,
Node.js/Wigolo `0.2.1`, the documented deadlines/size caps, full-run ceilings, environment-template
changes, and the gated smoke path. The user prohibited a SQLite migration and separately withheld
permission to execute live calls.

Implemented the concrete Wigolo Search/acquisition, ResearchAssistant normalization/digital-PDF,
and OpenRouter single-call boundaries. Migrated defaults to MiMo Pro -> MiniMax M3, added frozen
HTML/PDF and mocked HTTP boundary tests, and added an explicitly gated standalone smoke script.
No complete orchestration, live product command, UI, migration, second provider, browser driver, or
later-phase behavior was added.

Verification at completion: 40 focused tests passed; 366 complete offline tests passed with one
pre-existing explicit opt-in skip; all 38 offline evaluation cases passed; Ruff lint/format passed;
the live smoke was not run.

## Prerequisite and Purpose

MVP-2A Architecture Gate is complete. Implement production-intended adapters for only
the approved stack:

- local Wigolo `0.2.1` for discovery and controlled acquisition;
- ResearchAssistant-owned deterministic normalization and narrow PDF handling; and
- OpenRouter using `xiaomi/mimo-v2.5-pro` as primary and
  `minimax/minimax-m3` as the only fallback model identity.

Do not connect the complete orchestration, add a live user-facing CLI command, modify
Streamlit, or begin MVP-3A.

Before changing dependencies, environment templates, persistence, or live-test limits,
confirm the explicit approvals listed at the end of the MVP-2A plan. This phase prompt
does not silently grant approvals that MVP-2A reserved for the user.

## Production Boundary Rule

Adapters created here must be production-intended implementations of the existing
Protocols, not disposable proof-of-concept clients. Keep the existing synchronous typed
boundaries. Extend strict Pydantic contracts only where the approved provenance and
normalized-failure contract requires it. Do not build another general provider
abstraction.

## Wigolo Search Adapter

Implement the approved discovery-only search boundary:

- call pinned Wigolo `0.2.1` on loopback;
- use `POST /v1/search` with `max_results: 5`, `max_fetches: 0`,
  `include_content: false`, `search_depth: "balanced"`, `force_refresh: true`, and
  `include_full_markdown: false`;
- return the existing typed Search result contract in provider rank order;
- preserve provider/version identity, rank, URL, title, relevance metadata, engine
  telemetry, warnings, and degraded-pool state where the typed contract supports them;
- treat snippets, provider evidence, relevance scores, and summaries as discovery
  metadata only; and
- never create a trusted snapshot from Search output.

Use explicit deadlines and normalize missing configuration, connection failure,
authentication failure where applicable, timeout, rate limit, transient outage,
permanent request failure, provider error payloads inside successful HTTP responses,
malformed success responses, empty results, and malformed or missing URLs. Error text
must be secret-safe and must retain an objective retryability classification.

Offline tests must cover empty results, duplicate URLs, missing URLs, unexpected fields,
malformed metadata, provider-error payloads with HTTP success, redirects or unusual
valid URLs, degraded engine pools, and deterministic rank preservation.

## Wigolo Acquisition and ResearchAssistant Normalization

Implement the approved source path without changing full Researcher orchestration:

1. Independently preflight the source to determine original URL, final redirected URL,
   advisory canonical URL where available, and origin media type. Do not infer origin
   `Content-Type` from Wigolo Markdown.
2. Enforce five redirects, a 10 MiB HTML/text ceiling, a 25 MiB PDF ceiling, streaming
   abort on excess size, and the approved request deadlines.
3. Call Wigolo `/v1/fetch` with `render_js: "never"` first. Permit one final
   `render_js: "always"` request only for an explicit challenge or JavaScript-required
   result. This is the sole approved controlled rendering path. Do not write separate
   browser automation, perform actions, authenticate, click, type, or use browser
   profiles.
4. Normalize inaccessible, paywalled, challenge-blocked, unsupported, timeout, size,
   redirect, content-type, malformed-response, and extraction failures into strict typed
   outcomes.
5. Treat provider Markdown as an acquisition representation, never the quote authority.

Implement the versioned ResearchAssistant normalizer exactly as approved by MVP-2A:

- deterministic charset handling;
- Unicode NFC;
- `\n` line endings;
- non-breaking spaces converted to spaces;
- collapsed horizontal whitespace and trimmed line edges;
- at most one blank line between text blocks;
- visible link text retained while Markdown syntax and link destinations are removed;
- deterministic boilerplate removal only;
- 3,000-word truncation after normalization; and
- snapshot hash and word count calculated from the exact final stored text.

All quote offsets refer to the normalized plain text. Frozen-fixture tests must prove
byte-for-byte repeated output, stable hashes, stable truncation, sequential quote
location, and `text[start:end] == exact_quote`.

## PDF Policy

Implement the approved narrow deterministic digital-PDF path. Accept only unencrypted,
parseable PDFs within configured size/page/time limits that contain usable embedded
text. Reject scanned/image-only, encrypted, malformed, empty, or unusably extracted PDFs
without OCR. Headers, footnotes, and page markers may remain. Frozen PDF fixtures, not a
live page, prove deterministic extraction and offsets.

## OpenRouter LLM Adapter

Implement direct OpenRouter HTTP integration without adding an LLM SDK.

- Map every existing application role to primary `xiaomi/mimo-v2.5-pro` and only
  fallback `minimax/minimax-m3`.
- Send strict JSON Schema generated from the exact requested Pydantic output type with
  strict structured output enabled.
- Require parameter support, deny provider data collection, and keep application prompt
  logging disabled.
- Locally validate raw JSON with the exact requested Pydantic model. Do not use response
  healing.
- Record requested slug, returned exact model, upstream provider when available,
  adapter version, request/response identity, timing, usage, and reliable cost.
- Normalize refusal, timeout, 408, 429, retryable 5xx, permanent failure, malformed JSON,
  truncated output, schema failure, capability mismatch, malformed usage, unknown
  pricing, and returned-model mismatch.

Use at least one representative existing schema to prove valid typed output. Tests must
reject unknown fields, missing fields, invalid enums, malformed/truncated JSON, wrapper
text or Markdown fences unless the approved provider demonstrably requires a narrowly
documented compatibility rule, refusals, and malformed usage metadata.

This adapter exposes one physical call and typed metadata. Do not move the orchestration
retry/fallback loop into the adapter. Boundary tests may invoke primary or fallback
explicitly; MVP-3A proves full routing behavior.

## Configuration and Secrets

- Validate required configuration before any network call.
- Read `OPENROUTER_API_KEY` only from the approved process environment or explicitly
  approved uncommitted `.env` path; do not silently discover other credential sources.
- Never print, log, persist, serialize, echo, or send the key to Wigolo.
- Bind Wigolo to loopback and verify health/service identity before use.
- Use strict Pydantic configuration, explicit adapter/version/model identities, and
  redacted representations.
- Support public, non-sensitive test inputs only.

## Opt-In Boundary Smoke

Add one opt-in boundary smoke script or test that performs exactly one Search request,
one acquisition/normalization, and one representative structured LLM request. It must
require all of:

- a dedicated explicit live-enable flag;
- explicit user approval at execution time;
- maximum Search, acquisition, and LLM call counts;
- maximum tokens and monetary cost;
- strict deadlines and limited retries;
- dedicated ignored output or database path;
- non-sensitive data; and
- fail-closed price enforcement and secret redaction.

Credentials alone must never trigger it. Do not run it without separate approval.

## Scope Limits

Do not connect all orchestration stages, run a full research claim, add the live CLI,
modify Streamlit, add another provider stack, add ResearchAssistant-owned browser
automation, add hosting/Docker/accounts, redesign orchestration, or commit automatically.

## Verification and Report

Run focused adapter/normalization tests, the full offline suite, offline evaluation,
Ruff lint, Ruff format check, `git diff --check`, and Git status. Run the opt-in smoke
only with credentials, all limits, and explicit approval.

Report exact files changed; Search boundary result; HTML and PDF determinism/offset
proof; representative structured-output result; observed usage/cost if live smoke was
approved; normalized errors; configuration and secret protections; remaining provider
incompatibilities; and whether the stack is ready for MVP-3A. Leave changes uncommitted.
