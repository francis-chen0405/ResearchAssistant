# MVP-2A - Architecture Gate

## Status and Boundary

Status: Complete as a documentation-only architecture decision.

MVP-2A selects the live-provider design. It does not implement adapters, add dependencies,
load secrets, change schemas, make repository network calls, expose a live CLI, or start
MVP-2B. Current provider protocols and fake-provider behavior remain unchanged until a
separately authorized implementation phase migrates them.

## Existing Contracts Inspected

- Synchronous `SearchProvider`, `ScraperProvider`, and `LLMProvider` Protocols with strict
  Pydantic request/result artifacts and explicit failures.
- Six Planner queries, two synchronous Researcher workers, typed checkpoint artifacts,
  atomic model-call reservations, objective retry/fallback metadata, and optional usage.
- Versioned prompts and exact requested Pydantic output schemas for Planner, Extractor,
  Analyst, Reviewer, and Synthesizer.
- Immutable insert-only source snapshots and Ledger records; exact quote offsets are
  rechecked before Analyst and Ledger use.
- Current implemented routing and retrieval assumptions are migration inputs, not the
  approved live design: fixed top-three acquisition, PDF unsupported, and the old MiMo /
  DeepSeek alias route remain in code until MVP-2B.

## Stack A - Approved Primary

### Exact services and models

- Discovery and acquisition: local Wigolo `0.2.1`, bound to `127.0.0.1` and managed by
  ResearchAssistant in the future implementation.
- Search endpoint: `POST /v1/search`, six calls per normal run, with `max_results: 5`,
  `max_fetches: 0`, `include_content: false`, `search_depth: "balanced"`,
  `force_refresh: true`, and `include_full_markdown: false`.
- Fetch endpoint: `POST /v1/fetch`; use `render_js: "never"` first and
  `render_js: "always"` only once after an explicit challenge or JavaScript-required
  result. No browser actions, profiles, authentication, clicks, or typing.
- Search reranker observed and pinned for compatibility: `Xenova/ms-marco-MiniLM-L-6-v2`.
- Wigolo's local fetch cache may lazily embed with `BGE-small-en-v1.5` at 384 dimensions;
  this is local acquisition-cache behavior, not ResearchAssistant evidence scoring.
- LLM gateway: OpenRouter.
- Planner, Extractor, Analyst, Reviewer, Synthesizer primary:
  `xiaomi/mimo-v2.5-pro`.
- Only LLM fallback for all roles: `minimax/minimax-m3`.

### Dependencies and environment

Proposed future Python dependencies, requiring approval in MVP-2B:

- `httpx` for loopback Wigolo and OpenRouter HTTP calls.
- `markdown-it-py` for deterministic Markdown parsing before normalization.

Node.js and pinned `npx -y wigolo@0.2.1` are runtime prerequisites. No LLM SDK is
required. The only required vendor secret is `OPENROUTER_API_KEY`; Wigolo stays on
loopback and receives no LLM key. Future configuration must carry the Wigolo version,
host/port, deadlines, output caps, price caps, budgets, and route identifiers explicitly.

### Calls, cost, and implementation difficulty

- Search: normally 6 calls.
- Acquisition: normally up to 18 successful snapshots; structurally up to 30 ranked URL
  attempts before duplicate and unusable-source handling. A candidate has at most two
  HTTP-level acquisition attempts; Wigolo-internal retries must be disabled.
- Logical LLM operations under the current orchestration are approximately 45-74 for a
  normal run, with a structural maximum around 110. Each logical operation has at most
  four physical calls: primary, primary retry, fallback, fallback retry.
- Expected live cost: approximately USD 0.10-0.25 normally and USD 0.30-0.60 for an
  unusually retry-heavy run, subject to current route prices and actual token use.
- Proposed hard ceiling: USD 1.00, 1,000,000 total tokens, and 160 physical LLM calls per
  run. Search/acquisition are local but still receive explicit zero-cost usage entries.
- Difficulty: medium. It adds a local managed process and Markdown normalization but
  avoids hosting, browser automation logic in ResearchAssistant, and multiple LLM APIs.

### Strengths, limitations, and failures

Strengths are one paid vendor, low cost, strict JSON Schema through OpenRouter,
ResearchAssistant-owned evidence text, two-worker compatibility, local search/fetch,
controlled browser fallback, and no hosting requirement. Expected failures include a
missing or incompatible Node/Wigolo runtime, occupied port, local process startup
failure, degraded search engines, challenge-protected/paywalled sources, JavaScript pages
that still fail after one render, redirect/content ambiguity, bad PDF extraction,
OpenRouter 408/429/5xx/timeouts, strict-schema failures, model retirement, unknown price,
and budget exhaustion.

## Stack B - Concrete Alternative

### Exact services and models

- Discovery: Brave Search API, used only for URLs, titles, snippets, and discovery rank.
- HTML: local Python `httpx` acquisition followed by `trafilatura` extraction.
- PDF: local `pypdf` through the same narrow deterministic PDF policy as Stack A.
- LLM: the same OpenRouter route as Stack A: `xiaomi/mimo-v2.5-pro` primary and
  `minimax/minimax-m3` fallback for all five roles.

### Dependencies, environment, calls, and cost

- Proposed dependencies: `httpx`, `trafilatura`, `pypdf`, and, if Markdown is used as an
  intermediate, `markdown-it-py`.
- Required secrets: `BRAVE_API_KEY` and `OPENROUTER_API_KEY`.
- Normal calls: 6 Brave searches, 18 successful local fetch/extractions, and the same
  LLM call profile as Stack A.
- Brave discovery is approximately USD 0.03 per six-query run at a USD 5/1,000-query
  reference price; pricing must be verified and capped at implementation time. LLM cost
  remains approximately USD 0.10-0.25 normally. The same USD 1 total cap applies.
- Difficulty: medium-high because redirect, content-type, extraction, block handling,
  PDF parsing, and diagnostics become ResearchAssistant responsibilities.

### Strengths, limitations, and failures

This stack removes Node and Wigolo coupling and makes original HTTP metadata easier to
capture. It adds a second paid vendor, more Python dependencies, more adapter code, no
browser-render fallback, and weaker JavaScript-page coverage. Likely failures are Brave
quota/rate limits, fetch blocks, poor article extraction, charset errors, redirect loops,
large responses, unsupported content, and the same OpenRouter/model/budget failures.

## Approved Source Acquisition Policy

- Search output is discovery metadata only. Search snippets, Wigolo evidence fields,
  reranker scores, and provider-generated summaries never substitute for independently
  fetched source snapshots.
- Attempt each query's five ranked results until three usable, unique snapshots exist.
  Preserve Wigolo relevance and component telemetry as discovery metadata only. The
  Analyst alone assigns Evidence Quality and Claim Fit.
- Persist the Planner's original URL and the final redirected URL separately. Preserve
  a source-declared canonical URL as advisory metadata; it never replaces the final URL.
- Preflight content type independently because Wigolo REST fetch output does not expose
  the origin HTTP `Content-Type`. Use headers/final URL and, when ambiguous, a bounded
  byte-range signature check. `%PDF-` selects the PDF path.
- Supported MVP representations: extracted HTML/article text, plain text, and narrowly
  supported digital PDFs. Other types return a typed unsupported-content result.
- Proposed limits: 5 redirects, 10 MiB HTML/text response, and 25 MiB PDF response.
  Streaming enforcement must stop reads that exceed the cap.
- One direct fetch is followed by at most one controlled browser-render fetch only for
  challenge/JavaScript-required outcomes. Paywalls, authentication, persistent bot
  protection, inaccessible content, and failed JavaScript rendering are explicit
  unusable-source results and cause the worker to continue down the ranked list.

## Extraction, Normalization, PDF, and Quotation Contract

PDF decision: **narrow deterministic PDF support is included in the MVP**. Accept only
digitally generated PDFs that are unencrypted, parseable, contain usable extracted text,
and stay within configured size/page/time limits. Reject scanned/image-only, encrypted,
malformed, empty, or unusably extracted PDFs without OCR. Headers, footnotes, and page
markers may remain; no model may silently repair the extraction.

The provider acquisition payload is not the authoritative quote surface. A versioned
ResearchAssistant normalizer must:

1. Decode using declared charset when valid, otherwise a deterministic standards-based
   fallback; reject undecodable or binary payloads rather than using lossy guessing.
2. Parse provider Markdown structurally, retain visible text and link text, discard link
   destinations and formatting syntax, and remove deterministic boilerplate where the
   extractor can identify it reliably.
3. Normalize Unicode to NFC, line endings to `\n`, non-breaking spaces to ordinary
   spaces, horizontal whitespace runs to one space, surrounding line whitespace away,
   and blank-line runs to at most one blank line.
4. Apply the 3,000-word limit after normalization, set `truncated: true` when content is
   omitted, and compute the snapshot word count and SHA-256 from the final stored text.

All segment offsets reference this exact persisted normalized plain text, never raw HTML,
PDF bytes, or provider Markdown. The LLM proposes exact quote strings; deterministic
Python locates segments sequentially and accepts only when
`snapshot.normalized_text[start_char:end_char] == exact_quote`. The immutable snapshot,
its hash, original/final/canonical URLs, source media type, normalization version,
acquisition version, and optional provider-payload hash are persisted before extraction.
A later refetch creates a new attempt/snapshot and never replaces an existing snapshot.

## LLM Structured Output, Pinning, Retry, and Deadlines

- Send strict JSON Schema generated from the requested Pydantic model with
  `response_format`, `strict: true`; locally revalidate the response with that exact
  Pydantic model. Do not use response-healing plugins.
- OpenRouter provider preferences require parameter support and set data collection to
  deny. Application prompt logging remains disabled.
- Persist requested OpenRouter slug, returned exact model identity, upstream provider,
  adapter version, request/response IDs, prompt version/hash, schema version/hash,
  generation settings, usage/cost, and terminal attempt status.
- Pin slugs in configuration and validate the returned identity. A retired/unavailable
  primary may use only the approved fallback. Model replacement requires a new
  architecture decision and version; never silently substitute another model.
- Retry once on the same model, then once on the fallback and once more on that fallback,
  only for objective timeout, 408, 429, retryable 5xx, malformed JSON, schema/Pydantic,
  or deterministic output-validation failure. Never route on semantic disagreement or a
  low Analyst/Reviewer score. Honor `Retry-After` up to 30 seconds with jittered bounded
  backoff.
- Proposed deadlines: health 2s, Wigolo startup 60s, search 15s, HTML fetch 15s, PDF
  fetch 30s, browser fetch 25s, total candidate acquisition 40s; Planner 90s, Extractor
  180s, Analyst 120s, Reviewer 90s, Synthesizer 180s.

## Cost Enforcement and Usage

- Before every physical LLM call, atomically reserve a conservative input-token estimate
  plus the configured maximum output at the route's capped price. Reject the call if the
  remaining call, token, or monetary budget cannot cover it.
- After every response, reconcile the reservation with exact provider usage and cost.
  Persist usage from failed, malformed, and deterministically rejected responses.
- Retries and fallback share the same run-wide limits; they do not receive a fresh
  budget. Do not attempt a fallback that cannot be fully reserved.
- Search and extraction receive usage/cost records even when cost is zero. Stack B's
  Brave charge is reserved and reconciled under the same total monetary budget.
- Estimated usage remains explicitly estimated until exact usage arrives. If current
  pricing or returned route identity cannot be determined reliably, fail closed before
  the call rather than treating it as free.

## Data Handling and Secrets

- Wigolo receives the six public claim-derived queries and public source URLs/content;
  processing and cache/embedding stay local under the Wigolo data directory.
- OpenRouter and its selected upstream provider receive the claim/prompt inputs for each
  role. Extractor and Analyst receive relevant normalized source content; Reviewer
  receives its existing narrow quote/context/draft/Claim Fit input; Synthesizer receives
  Ledger-backed structured content. Search and acquisition vendors never receive the
  full accumulated Ledger or final brief merely for convenience.
- OpenRouter prompt logging is disabled and data collection is denied in route settings,
  but request metadata and accounting records may be retained. Upstream policy can vary,
  so the MVP supports public, non-sensitive research claims only and does not promise a
  sensitive or confidential research mode.
- Persist locally: claims, plans, URLs, acquisition telemetry, immutable snapshots,
  hashes/offsets, typed stage artifacts, prompts/schema/model/version metadata, attempt
  failures, usage/cost, checkpoints, Ledger, and release results. Provider raw Markdown
  may be retained only as a diagnostic payload with its own hash and is never the quote
  authority.
- Load `OPENROUTER_API_KEY` from the process environment or an uncommitted `.env`; never
  persist, log, serialize, echo, or send it to Wigolo. Bind Wigolo to loopback and do not
  expose an unauthenticated network listener.

## Thread Safety, Process Ownership, Persistence, and Restart

- One managed Wigolo process serves both synchronous Researcher workers. The future
  adapter must be thread-safe, cap the application at two researcher requests, and keep
  per-call state local. Workers never share SQLite connections or mutable handoffs.
- On startup, check `/health`; if absent, start the exact pinned command, wait for health,
  and verify an existing port occupant identifies as the expected Wigolo service. Stop
  only the child process ResearchAssistant owns.
- Persist per attempt/checkpoint: provider identity, adapter version, exact model,
  upstream route, prompt version/hash, schema version/hash, normalization version,
  Wigolo/version/config, PDF policy version, retry/budget/pricing policy versions,
  repository revision, artifact IDs, status, timing, and usage/cost.
- Resume only when the complete run fingerprint matches. A changed prompt, model,
  adapter, schema, normalization/PDF policy, Wigolo configuration, budget/pricing policy,
  or repository revision makes the old checkpoint incompatible; refuse resume and
  require a new run. Cross-version silent resume is unsupported.

## Canary Evidence and Acceptance Criteria for MVP-2B

Manual local canaries observed during this gate:

- Balanced discovery-only search completed in about one second, returned reranked
  results, performed no fetch, and exposed per-engine telemetry.
- A digital APA PDF fetched and extracted successfully (about 31,859 characters, 4,618
  words, 12 pages).
- Two ordinary HTML pages extracted successfully (about 20,961 and 63,438 characters).
- Hopkins and AECF pages remained challenge-blocked after the one controlled browser
  retry and returned honest unusable results.

MVP-2B proof of concept must first implement one adapter slice at a time with fake/local
tests, then a deliberately enabled live canary. Acceptance requires six discovery-only
queries, no summary-as-snapshot path, rank-order keep-three behavior, exact original/final
URL persistence, HTML and narrow-PDF fixtures, honest challenge failures, deterministic
normalization and offsets, immutable refetch behavior, two-worker isolation, exact model
and schema provenance, retained failed-attempt usage, enforced USD 1/token/call caps,
restart fingerprint rejection, and unchanged final release gates.

Maximum live proof limits: one public non-sensitive claim, six searches, 30 acquisition
candidates, 18 Extractor snapshots, 160 physical LLM calls, 1,000,000 tokens, and USD
1.00 total. Normal automated tests remain offline.

## Minimum MVP-2B Adapter Surface and Likely Files

The minimum design is concrete rather than a new provider framework:

- `providers/wigolo.py`: thread-safe typed adapter for health, discovery, fetch outcome,
  telemetry, redirect/media-type provenance, and managed-process ownership.
- `providers/openrouter.py`: strict schema request, exact returned route/model capture,
  deadlines, objective error mapping, and exact usage/cost reporting.
- `providers/normalization.py`: versioned Markdown/HTML/PDF-to-plain-text normalization,
  3,000-word truncation, hashes, and source-snapshot construction.
- `providers/pricing.py`: frozen-at-run price table/caps and conservative pre-call cost
  reservations. Keep it small and OpenRouter-specific unless another implemented vendor
  is later approved.

Likely existing files to change are `providers/search.py`, `providers/scraper.py`,
`providers/llm.py`, `models.py`, `store.py`, `orchestrator.py`, `cli.py`,
`.env.example`, `pyproject.toml`/`requirements.txt`, focused provider and orchestration
tests, and the status/handoff/phase documents. Change only files required by the accepted
MVP-2B plan; do not pre-approve every listed change.

The future configuration schema must be a strict Pydantic model and include:

- Wigolo executable/version, loopback host/port, startup/health ownership, search/fetch
  settings, redirect/size/deadline limits, reranker identity, and browser-fallback rule.
- OpenRouter base URL, environment key name, per-role primary/fallback slugs, strict
  structured-output and data-collection settings, provider price caps, generation
  controls, and per-stage deadlines.
- Global call/token/cost ceilings; retry counts/backoff/Retry-After cap; normalization,
  PDF, prompt, schema, adapter, pricing, and restart-fingerprint versions.

The approved future alias mapping is:

| Application alias | OpenRouter primary | Only fallback |
|---|---|---|
| `planner` | `xiaomi/mimo-v2.5-pro` | `minimax/minimax-m3` |
| `extractor` | `xiaomi/mimo-v2.5-pro` | `minimax/minimax-m3` |
| `analyst` | `xiaomi/mimo-v2.5-pro` | `minimax/minimax-m3` |
| `reviewer` | `xiaomi/mimo-v2.5-pro` | `minimax/minimax-m3` |
| `synthesizer` | `xiaomi/mimo-v2.5-pro` | `minimax/minimax-m3` |

## Decisions Requiring User Approval Before MVP-2B

- Approve adding `httpx` and `markdown-it-py` and requiring Node.js/Wigolo `0.2.1`.
- Approve the proposed response-size limits and all request deadlines.
- Approve the USD 1.00, 1,000,000-token, and 160-call hard ceilings.
- Approve `.env.example` additions and the exact operator-facing live-run command/UI.
- Approve any SQLite migration needed for acquisition, normalization, route, pricing,
  and restart-fingerprint provenance.

No implementation may infer these approvals from completion of this gate.
