# Provider and model-routing audit — 2026-10-01

Status: provider pass complete; one confirmed budget defect fixed and covered
offline. The desktop packaging/CI pass and service-manager lifecycle follow-up
are recorded separately.

## Scope reviewed

Read every `providers/*.py` runtime module: `acquisition.py`, `arxiv.py`,
`clients.py`, `composite_search.py`, `config.py`, `crossref.py`, `exa.py`,
`firecrawl.py`, `llm.py`, `mimo.py`, `mimo_factory.py`, `model_choices.py`,
`model_profiles.py`, `normalization.py`, `openalex.py`, `pricing.py`, `pubmed.py`,
`ranking.py`, `scraper.py`, `search.py`, `serpsearch.py`, `v2_budget.py`,
`v2_factory.py`, `v2_routing.py`, and `wigolo.py`. Also read
`frontend/profile_preflight.py` and `frontend/provider_connections.py`.

Reviewed cross-module routing from selected stage choice through the immutable
route, provider factory, exact request prompt, budget reservation, attempt
completion, and restart audit. Reviewed strict provider response parsing, retry
classification, credential/end-point selection, price-cap and cache accounting,
discovery limits, acquisition redirects/provenance, and the relevant offline
tests. The code knowledge graph was refreshed in fast mode after the fix
(5,934 nodes; 37,178 edges); graph relationships were checked against the live
files. An `index_status` operation was not exposed.

## Confirmed finding and fix

Before the fix, `BudgetedV2LLMProvider.generate` in `providers/v2_budget.py`
reserved input bytes from `request.rendered_prompt`. The physical adapter in
`providers/mimo.py` sends `_direct_mimo_prompt(request)`, which adds the semantic
output contract and stage-specific instructions. For the default Extractor
request, an isolated offline comparison measured 4,041 bytes for the rendered
prompt and 5,691 bytes for the physical prompt. Both use the established
one-token-per-UTF-8-byte conservative estimate. The outer reservation therefore
understated that call by 1,650 tokens and its route price cap by the corresponding
input cost.

An offline temporary-database reproduction seeded 487,767 tokens of exposure
under the 500,000-token run ceiling. The old preflight reserved 12,233 tokens for
the next Extractor attempt; the physical-prompt estimate was 13,883. The budget
wrapper accepted the old reservation, then a provider-reported usage value of
13,883 produced 501,650 tokens of total exposure, 1,650 above the ceiling. The
production adapter's own check did not prevent that case because its per-call
limit is the full run ceiling, not the remaining aggregate allowance.

`XiaomiMimoAdapter.conservative_input_tokens` now estimates the exact prompt it
sends. `RoutedV2LLMProvider` delegates to the stage-selected adapter and returns
the larger of that estimate and the existing rendered-prompt estimate.
`BudgetedV2LLMProvider` reserves tokens and cost from that conservative maximum
before writing a physical-call start or dispatching transport. The direct adapter
uses the same estimator for its per-call check. Providers without this optional
estimator retain the existing standard-prompt fallback.

`tests/test_audit_provider_budget.py` uses a real Xiaomi adapter with mocked
HTTPX transports and verifies both near-exhausted token and cost ceilings reject
before any transport request. It also retains conservative reservations when
usage is unknown. The restart regression in
`tests/test_model_cache_pricing.py` now computes the reservation from the same
selected adapter estimate while preserving its exposure and restart-equality
assertions.

An integration follow-up checked direct construction of
`BudgetedV2LLMProvider(provider=XiaomiMimoAdapter(...))`, which is supported by
the wrapper's `LLMProvider` type even though the production factory normally
uses `RoutedV2LLMProvider`. The first estimator version accepted only the
request, while the wrapper invokes the optional estimator with the request and
its minimum bound. `XiaomiMimoAdapter.conservative_input_tokens` now accepts that
minimum and returns the maximum of both bounds. A dedicated regression verifies
the direct adapter rejects before HTTP transport, and the test input artifact
uses the repository's strict `StrictModel` handoff base.

## Checks

- The initial pre-fix offline reproduction is recorded above; it used only a
  temporary SQLite database and a fake provider, with no network or key access.
- Provider-budget, reconciliation, routing, stage-choice, model-cache/pricing,
  and provider-setup tests: **173 passed**.
- Discovery adapters, v2 Scout/acquisition, acquisition security, acquisition
  configuration/provenance, provider selection, and adaptive reliability tests:
  **83 passed**.
- Focused Ruff check and format check for changed Python files passed; `git diff
  --check` passed.
- No paid, live, external web, or real-data calls were made. The full suite and
  application build are outside this area-pass report.

## Review disposition

The reviewed routes keep the selected logical model and physical endpoint aligned
through the factory and stage dispatch. Reservations are serialized under the
budget lock before transport; missing or unknown usage continues to retain its
reservation. Discovery adapters enforce typed provider selection and bounded
result counts; OpenAlex and SERP attempts reserve their per-run call allowance
before transport. LLM provider errors and malformed outputs are converted to
typed failures, and usage prices use route-specific cache metadata only when
the route and usage evidence support it.

The acquisition code resolves and checks every explicit redirect hop, enforces
byte/page/word bounds in the local preflight and normalizer, and separately
validates Firecrawl source and canonical provenance. The documented
DNS-rebinding/time-of-check limitation in the MVP-6.3 plan remains a known
limitation, not a newly introduced finding. Provider connection checks use
sanitized results and do not generate text; start preflight computes the real
initial planning reservation without contacting a provider.

No additional confirmed defect was established in the assigned provider and
frontend files. This conclusion is limited to the source and offline evidence
reviewed here; it does not verify external provider pricing/access, live
endpoints, installed-app behavior, or untested platform configurations.

## Adjacent runtime integration cross-check

An independent follow-up checked the live budget/accounting projection, API
input failures, candidate-to-snapshot provenance, exact USD aggregation, CLI
inspection of fresh-v2 artifacts, stage-selected adaptive budget protection,
and concurrent same-URL acquisition. The live presentation keeps token and cost
completeness independent, shows known subtotals separately from conservative
exposure, and retains reservations for incomplete usage. Read-only snapshot
construction reuses the validated connection, and early results stay pollable
when a database exists but the run is not yet persisted; the historical one-shot
behavior remains for missing-database startup outcomes.

After the CLI and snapshot instrumentation were aligned with their new read
boundaries, the adjacent API, evidence, live service, money, CLI, retrieval,
research-governor, and v2 production tests passed with warnings treated as
errors: **118 passed**. The review found no additional confirmed integration
defect. The only interactions exercised were offline temporary-database,
MockTransport, and local subprocess tests.
