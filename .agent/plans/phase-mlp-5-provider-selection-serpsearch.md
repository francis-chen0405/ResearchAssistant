# MLP-5 — Provider Selection & SERP Search

Status: Complete and verified on 2026-08-17.

## Delivered behavior

- Added SERP Search (`https://api.serpsearch.com`) as a typed Google-style discovery
  provider. Only normalized organic HTTP(S) results enter the discovery pool; snippets
  remain metadata and never evidence.
- New website runs select SERP Search, Exa, and OpenAlex independently. All three are
  enabled by default, at least one is required, and the choice is frozen in canonical
  controls and the provider-run fingerprint.
- The Planner creates two SERP Search, three Exa, and one OpenAlex query per active
  stance only for selected providers. SERP Search is conservatively limited to twelve
  attempted calls per run; its subscription-backed cost is not fabricated as per-call USD.
- An enabled source without a saved key blocks the run before work starts. Disabled
  sources require no key and create no query, call, or trail failure. Existing CLI and
  programmatic legacy defaults retain the former Exa/OpenAlex selection for compatibility.
- Advanced contains the three required source switches and concise provider guidance.
- Source switches persist automatically in browser local storage, so closing Advanced or
  refreshing the page keeps the user's last selection.

## Safeguards retained

Provider results remain discovery-only, merge into the existing duplicate-collapse and
deterministic two-stage ranking path, and preserve all acquisition, snapshot, quotation,
Reviewer, Ledger, and final-validation rules. Historical contracts remain readable; a
new provider selection or adapter identity requires a new run.

## Verification

- Full offline suite: 655 passed, 2 expected opt-in skips.
- Ruff lint and formatting checks passed; `git diff --check` passed.
- Frontend lint/build could not run in this workspace because the package manager attempted
  an unavailable registry install despite an existing incomplete `web/node_modules` tree.
