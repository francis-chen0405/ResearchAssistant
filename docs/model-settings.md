# Provider connections and supported model settings

Connections authenticate provider accounts. The configurable research profile selects
models and conservative budget caps; it is stored separately from secret credentials.
API keys remain in the unchanged macOS Keychain/Windows Credential Manager namespace.
Password fields are transient and cleared after save attempts. Stored secrets are never
returned to the renderer. All credentials remain excluded from preferences, SQLite,
URLs, exports and logs.

## Configurable research profile

`configurable-2026-09` is the default for fresh desktop, research-start API and ordinary
CLI runs. Each of the seven active model steps has one frozen choice from the six options
below. Scout and exact Extractor default to Luna High; Planner, Gap Analysis, Search Agent,
Source Selection and Evidence Analyst default to Luna XHigh. Reviewer and synthesis are
deterministic in fresh runs, so they have no selector. The model-options API returns the
same catalog and defaults as the desktop. The selection-aware configuration check asks
only for keys used by the chosen model steps and enabled search providers.

| Choice | Provider model | Reasoning | Published input / cached / output per million | Conservative input / output cap per million |
| --- | --- | --- | ---: | ---: |
| GPT-6 Luna High | `gpt-6-luna` | high | $0.10 / $0.01 / $0.50 | $0.25 / $0.75 |
| GPT-6 Luna XHigh | `gpt-6-luna` | xhigh | $0.10 / $0.01 / $0.50 | $0.25 / $0.75 |
| MiMo v2.6 Pro | `mimo-v2.6-pro` | thinking | $0.435 / $0.0036 / $0.87 | $0.50 / $1.00 |
| MiMo v2.6 Flash | `mimo-v2.6-flash` | thinking | $0.14 / $0.0028 / $0.28 | $0.15 / $0.30 |
| GPT-6 Sol High | `gpt-6-sol` | high | $2.00 / $0.20 / $10.00 | $5.00 / $15.00 |
| GPT-5.6 Terra High | `gpt-5.6-terra` | high | $2.00 / $0.20 / $12.00 | $5.00 / $18.00 |

The selected route uses the official provider endpoint, the model ID and reasoning
setting shown above, and the stage's 4,096 Scout, 8,192 standard, or 16,384 Gap/Analyst
completion allowance. The selected provider's API key is required only if one or more
stages use it. The default whole-run model budget remains $0.20; users may explicitly
choose up to $20. The 160-call and 500,000-token ceilings, strict output validation,
evidence rules and conservative per-call reservations are unchanged. Search and
acquisition service charges remain separate. CLI overrides use repeated
`--model STAGE=CHOICE` values with stage and choice IDs from `/api/model-options`.

Pricing and capabilities were reviewed against [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Sol](https://developers.openai.com/api/docs/models/gpt-6-sol),
[Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra),
[MiMo API and thinking mode](https://mimo.mi.com/docs/en-US/api/chat/openai-api), and
[MiMo pricing](https://mimo.mi.com/docs/en-US/price/pay-as-you-go). OpenAI caps cover
cache-write and long-context multipliers without assuming any cache discount. MiMo
caps round above published miss and output prices. Completed usage uses exact official
endpoint/model cache rates when usage metadata permits; unknown usage keeps the
reservation. These are estimates, not provider invoices. No paid calls were used to
verify this profile.

GPT-6 Luna's $0.25 input and $0.75 output caps cover the published 2x long-context
input multiplier, 1.25x possible cache-write input charge and 1.5x long-context output
multiplier. Reservations do not assume cached-input discounts.

## Historical Standard profile

`standard-2026-09` retains its earlier fixed three-model routing for historical
compatibility. Its original roles, reservations and saved run identities remain readable.

The low-level v2 compatibility path also retains the original fixed routes when callers
omit `StageModelSelections`, including GPT-5.6 Luna High. New desktop, API and CLI runs
always resolve and freeze explicit stage selections from the current catalog; the
no-selection path remains for older direct-v2 configurations and their run fingerprints.

| Model | Roles | Input cap / million | Output cap / million |
| --- | --- | ---: | ---: |
| MiMo v2.5 | Scout | $0.15 | $0.30 |
| MiMo v2.5 Pro | Planner, Search, Selection, exact Extractor | $0.50 | $1.00 |
| GPT-5.6 Luna High | Gap Analysis, Evidence Analyst | $0.50 | $1.80 |

Reviewed 2026-09-17 against [Xiaomi overseas pricing](https://mimo.mi.com/docs/en-US/price/pay-as-you-go)
and [the official Luna model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna).
MiMo published cache-miss/output prices are $0.14/$0.28 and $0.435/$0.87 per million.
Luna base prices are $0.20/$1.20; the maintained caps include its published long-context
multipliers and cache-write input exposure. These caps are reservations, not a quote
for the provider bill; reservations assume no cache discount or subscription conversion.
Search/acquisition services retain their separate existing limits and charges.

Completed usage now uses model-specific published cache rates only for the exact
official endpoint and supported model. Custom endpoints/model names fall back to their
configured caps. Missing or invalid cached-token counts also retain cap-based estimates.

| Model | Ordinary input / million | Cache read / million | Output / million |
| --- | ---: | ---: | ---: |
| MiMo v2.5 | $0.14 | $0.0028 | $0.28 |
| MiMo v2.5 Pro | $0.435 | $0.0036 | $0.87 |
| GPT-5.6 Luna | $0.20 | $0.02 | $1.20 |

For Luna, `prompt_tokens_details.cache_write_tokens` is separate from `cached_tokens`:
ordinary input is total input minus cache reads minus cache writes. Cache writes use
1.25 times the ordinary input price. Missing/invalid write counts conservatively treat
all noncached tokens as possible writes. Above 272,000 total input tokens, the entire
request uses 2 times all input rates and 1.5 times the output rate. Completion tokens
already include reasoning tokens; they are not added a second time. See
[usage fields](https://developers.openai.com/api/reference/resources/completions#completionusage)
and [cache accounting](https://developers.openai.com/api/docs/guides/prompt-caching).
MiMo charges cache misses at its published input rate, with no additional write fee
under the current limited-time policy. These are usage-based estimates, not invoices.
Valid failure-response usage uses the same accounting; unknown usage retains reservation.
Historical persisted usage is not recalculated.

The Standard profile now allows 4,096 completion tokens for Scout, 8,192 for MiMo Pro,
and 16,384 for Luna High, following observed truncation and the user's explicit choice
of larger responses within the same run budget. Preflight and every physical attempt
reserve the complete route allowance; configuration fingerprints include it. Legacy
callers without a profile retain the 4,096 default. Typed JSON adapter checks remain.
Luna explicitly requests `reasoning_effort: high` and the official endpoint's
standard (`default`) service tier; fresh synthesis remains deterministic. The earlier
Standard profile used a $1 configured maximum; configurable runs now permit an explicit
budget up to $20 while keeping the $0.20 default and the same call/token limits.
Before a profile worker starts, the real initial-planner prompt/schema/input are rendered
locally and conservatively reserved; an insufficient token or dollar budget is rejected.
This is a first-call affordability check, not a promise that the complete run fits.
Every subsequent physical attempt retains its original reservation and validation gates.

## Persistence and compatibility

`preferences.json` remains version 1. Older desktop preferences migrate to the new
configurable profile on read. Saved GPT-5.6 Luna High/XHigh stage choices migrate to
their GPT-6 Luna counterparts; other saved stage choices and settings are preserved.
Legacy non-secret
route/price preferences remain readable and are never overwritten by merely selecting
the new profile. A profile resolves a separate environment snapshot for each new run.
The existing frozen provider configuration captures exact routes/prices, budget and
source/prompt/executable identity. Changed settings cannot alter active or saved runs.
Existing historical read/export and exact resume rejection stay unchanged.

Desktop requests explicitly carry a supported profile ID and seven selections. New
research-start API requests default to the configurable profile and choices. Ordinary
CLI requests also use these choices; they pin official provider endpoints instead of
following old custom endpoint variables. Internal historical callers may still use the
old profile and routing. The seven choices and exact route parameters enter the new
run fingerprint, so a changed choice requires a new run. Historical SQLite rows are
inspected without rewriting them. Custom endpoint/model overrides are rejected by
the configurable desktop profile instead of forwarding keys to another host. The
settings dialog can explicitly restore the standard Luna route. An externally
configured nonstandard MiMo deployment must be corrected by its operator.

## Connection checks

Check connection is an explicit action; it is never run automatically. MiMo and OpenAI
checks only GET the fixed official `/v1/models` endpoint, with a short timeout and no
redirects. They verify authentication and listed model access without generating text.
Source providers without a configured free authentication endpoint report saved-key
presence explicitly; paid searching is never used as a connection check. Listed models
alone do not prove account quota, output compatibility or successful research.

Credential writes/removals are blocked while research is active. Existing native vault
storage, loopback authentication, renderer isolation and per-run immutable snapshots
are unchanged. No new dependency, provider, account system, database migration or cloud
service was introduced.
