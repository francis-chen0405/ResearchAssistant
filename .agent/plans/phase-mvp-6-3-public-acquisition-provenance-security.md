# MVP-6.3 — Public Acquisition and Provenance Security

## Authority and Boundary

MVP-6.2 Batch A is the completed prerequisite documentation/current-stack correction.
The user separately authorized MVP-6.3 to close redirect-time SSRF exposure in local
primary acquisition and to validate untrusted Firecrawl provenance. This phase does not
implement evidence-policy, database, CLI-status, usage-accounting, provider-contract,
or type-hint batches. No phase after MVP-6.3 has started.

## Security Contract

- The source/preflight client never follows redirects automatically. ResearchAssistant
  follows only 301, 302, 303, 307, and 308 through an explicit bounded loop.
- Before every local source request, the current URL must be an absolute,
  credential-free HTTP(S) URL with a valid public hostname or literal global address.
  Hostnames are resolved through the injectable resolver boundary, and every returned
  address must be global. Empty, malformed, local, private, loopback, link-local,
  reserved, multicast, unspecified, mixed-safe/unsafe, and resolution-failure results
  fail closed.
- Relative `Location` values resolve against the current response URL. Missing or
  malformed locations, redirect loops, and chains beyond the exact configured limit
  fail with typed non-retryable redirect/policy errors. Each response stream closes at
  its hop.
- HTML acquisition sends Wigolo only the validated final preflight URL, never the
  original URL after a redirect. Original and final provenance remain distinct.
- Firecrawl direct requests and returned `metadata.sourceURL` are independently checked
  under the same public HTTP(S) policy. An absent `sourceURL` may fall back only to the
  already validated requested URL. Recognized canonical metadata is also validated
  before entering `ScrapeResponse`; malformed, conflicting, or unsafe values fail
  closed.
- Firecrawl remains a narrow fallback only for the existing Wigolo-local connection,
  timeout, malformed-output, extraction, or challenge failures. Authentication,
  paywall, access-denied, source-policy, unsupported-content, size-limit, and redirect-
  policy failures never activate it.

## Identity and Compatibility

- Acquisition identity: `mvp6.3-public-acquisition-v2`.
- Firecrawl adapter identity: `mvp6.3-firecrawl-provenance-v2`.
- Direct-MiMo fingerprint identity:
  `mvp6.3-public-acquisition-fingerprint-v2`.
- Acquisition identity remains embedded in both historical OpenRouter-factory and
  current direct-MiMo fingerprints. A persisted run created under earlier redirect or
  provenance semantics fails exact-fingerprint compatibility and requires a new run ID.
  Historical persisted artifacts remain historical and are not reinterpreted.

## Deterministic Regression Coverage

The offline suite uses only injected `httpx.MockTransport` instances and injected
resolvers. Coverage includes unsafe literal/localhost/credential/scheme redirects,
private and mixed DNS answers, resolver failure, all approved redirect statuses,
relative and multi-hop success, exact redirect limits, malformed locations, loop
detection, proof that forbidden destinations were not requested, response closing,
validated Wigolo final-URL use, unsafe/absent/valid Firecrawl source provenance,
unsafe canonical provenance, direct-request validation, fallback exclusion, secret
absence, and pre-phase fingerprint incompatibility.

## Residual Limitation

The validator resolves each hostname immediately before the application asks `httpx`
to send that hop, but the ordinary HTTP transport performs its own DNS lookup. The
implementation therefore closes automatic-redirect and known-target SSRF exposure but
does not pin the validated address to the socket and does not claim complete DNS-
rebinding protection. Wigolo independently fetches the validated final public URL, so a
destination whose DNS or redirect behavior changes after preflight remains subject to
that same time-of-check/time-of-use limitation.

## Dependencies, Persistence, and Provider Calls

MVP-6.3 adds no dependency and no SQLite migration. Verification is offline; no Exa,
Wigolo, Firecrawl, MiMo, or other provider call or spending is authorized or required.

## Completion Requirements

Before marking MVP-6.3 complete, pass focused acquisition, Firecrawl, provider-factory,
and persistence compatibility tests; the full pytest suite; all offline evaluations;
Ruff lint and format checks; Python compilation; launcher shell syntax; and
`git diff --check`. Inspect the final diff and worktree for unrelated changes,
network-capable tests, generated coverage databases, caches, dependencies, and
migrations. Record exact results in `STATUS.md` and `HANDOFF.md`. Do not commit.

## Completion Record

MVP-6.3 is complete. Focused security/provider/persistence tests passed 159; the full
suite passed 501 with 2 expected opt-in skips; all 38 offline evaluation cases passed;
Ruff lint/format, Python compilation, launcher syntax, and `git diff --check` passed.
No provider call or spending occurred. No dependency or SQLite migration was added, no
generated cache/coverage artifact remains in the repository worktree, no commit was
created, and MVP-6.4 has not started.
