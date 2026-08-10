# MVP-7 — Direct MiMo Consolidation

## Authority and Boundary

The user explicitly authorized MVP-7 on 2026-08-10. Its purpose is to make direct
Xiaomi MiMo the sole executable LLM integration. Dated records may retain accurate
OpenRouter history, but no active runtime, configuration, smoke tool, test, or
current-facing operator guidance may require or describe OpenRouter.

## Scope

- Replace the legacy boundary smoke with a direct-MiMo, one-search/one-acquisition/
  one-LLM smoke using `MIMO_API_KEY`.
- Remove the OpenRouter configuration, adapter, factory, routes, price caps, and
  executable test coverage.
- Move shared injectable HTTP-client contracts to provider-neutral ownership.
- Make direct MiMo the only live factory, pricing, and orchestration policy.
- Update active documentation, environment examples, and current architecture wording.
- Preserve historical decisions, handoffs, and status records without rewriting them.

## Compatibility

Existing persisted runs remain inspectable through their stored contracts and artifacts.
They cannot resume under the new direct-MiMo-only executable identity. New fingerprints
must identify the MVP-7 policy.

## Verification

Completion requires direct-MiMo smoke construction without network execution, focused
provider/orchestration/configuration regression coverage, the complete offline test suite,
offline evaluations, Ruff lint and format checks, and `git diff --check`.
