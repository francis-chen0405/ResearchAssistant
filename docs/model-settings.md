# Provider connections and supported model settings

Connections authenticate provider accounts. The Standard research profile selects
models and conservative budget caps; it is stored separately from secret credentials.
API keys remain in the unchanged macOS Keychain/Windows Credential Manager namespace.
Password fields are transient and cleared after save attempts. Stored secrets are never
returned to the renderer. All credentials remain excluded from preferences, SQLite,
URLs, exports and logs.

## Supported profile

`standard-2026-09` uses the existing adapters and logical roles, with no new research
behavior. Advanced role assignments are inspectable, not arbitrarily editable: accepting
an arbitrary model name is not a compatibility guarantee.

| Model | Roles | Input cap / million | Output cap / million |
| --- | --- | ---: | ---: |
| MiMo v2.5 | Scout | $0.15 | $0.30 |
| MiMo v2.5 Pro | Planner, Search, Selection, exact Extractor | $0.50 | $1.00 |
| GPT-5.6 Luna High | Gap Analysis, Evidence Analyst | $0.50 | $1.80 |

Reviewed 2026-09-07 against [Xiaomi overseas pricing](https://mimo.mi.com/docs/en-US/price/pay-as-you-go)
and [the official Luna model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna).
MiMo published cache-miss/output prices are $0.14/$0.28 and $0.435/$0.87 per million.
Luna base prices are $0.20/$1.20; the maintained caps include its published long-context
multipliers and cache-write input exposure. These caps are reservations, not a quote
for the provider bill; no cache discount or subscription conversion is assumed.
Search/acquisition services retain their separate existing limits and charges.

Every route retains the existing 4,096-completion-token limit and typed JSON adapter
checks. Luna uses High reasoning; fresh synthesis remains deterministic. The existing
160-call/500,000-token/$1 maximums remain, with lower user limits permitted.
Before a profile worker starts, the real initial-planner prompt/schema/input are rendered
locally and conservatively reserved; an insufficient token or dollar budget is rejected.
This is a first-call affordability check, not a promise that the complete run fits.
Every subsequent physical attempt retains its original reservation and validation gates.

## Persistence and compatibility

`preferences.json` remains version 1. Its strict interface model adds a defaulted
`modelProfile` field, so older preference files preserve their values. Legacy non-secret
route/price preferences remain readable and are never overwritten by merely selecting
the new profile. A profile resolves a separate environment snapshot for each new run.
The existing frozen provider configuration captures exact routes/prices, budget and
source/prompt/executable identity. Changed settings cannot alter active or saved runs.
Existing historical read/export and exact resume rejection stay unchanged.

Desktop requests explicitly carry a supported profile ID. Older API/CLI requests which
omit it retain their legacy explicit configuration semantics. Custom endpoint/model
overrides are rejected by the supported profile rather than silently forwarding keys
to another host. The settings dialog can explicitly restore the standard Luna route.
An externally configured nonstandard MiMo deployment must be corrected by its operator.

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
