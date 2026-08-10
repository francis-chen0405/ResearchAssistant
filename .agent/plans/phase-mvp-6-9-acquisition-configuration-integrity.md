# MVP-6.9 — Acquisition and Configuration Integrity

## Authority and Boundary

MVP-6.8 is the complete prerequisite. The user explicitly authorized MVP-6.9 to make
Firecrawl origin-media provenance truthful, repair the advertised legacy boundary-smoke
configuration, and replace phase-bound package wording. No phase after MVP-6.9 is
authorized.

No dependency, live provider call, provider spending, commit, push, or pull request is
part of this phase. All provider coverage is offline through injected transports and
resolvers.

## Origin Media-Type Provenance

- Origin media type is verified only by ResearchAssistant's bounded public-host source
  preflight, including its supported header parsing and PDF signature check.
- A strict frozen `MediaTypeProvenance` artifact stores the independently verified media
  type and the exact URL at which it was verified separately from an optional sanitized
  Firecrawl declaration.
- Firecrawl Markdown is an acquisition representation, not proof of HTML, PDF, or text
  origin. Without applicable verified preflight evidence its response representation is
  `text/markdown`, including when `metadata.contentType` is absent.
- Only supported, syntactically valid base media types are retained as provider-declared
  metadata. Empty, malformed, parameter-only, unsupported, non-string, or otherwise
  arbitrary values remain unknown and never populate the verified fields.
- The primary adapter returns a typed `VerifiedAcquisitionPreflight`. Approved fallback
  failures carry that strict artifact across `FallbackAcquisitionAdapter`; Firecrawl
  uses its validated final URL and preserves the verified media type only for the exact
  resolved URL to which it applies.
- Conflicting verified and provider-declared values remain visible as distinct fields;
  the verified value is authoritative only at its verified URL.
- URL validation, redirect limits, canonical validation, credentials rejection,
  public-host enforcement, and the documented DNS time-of-check/time-of-use limitation
  remain unchanged.
- Normalization version and provider Markdown representation remain separate from origin
  media-type provenance.

## Persistence and Compatibility

SQLite migration 7 adds nullable snapshot provenance columns without rewriting existing
immutable snapshot rows. Historical rows reconstruct with explicit unknown media-type
provenance. New snapshot writes persist original/final/canonical URLs, normalization and
acquisition identities, provider identity, and canonical media-type provenance. Reopen
and read-only compatibility verify the new columns.

Acquisition identity, Firecrawl adapter identity, and both provider fingerprint versions
are bumped for MVP-6.9. Exact fingerprint matching rejects same-run resumption under
pre-MVP-6.9 acquisition semantics; historical inspection remains readable after the
intentional writable migration.

## Legacy Boundary Smoke

The historical `scripts/mvp2b_live_smoke.py` boundary smoke remains supported as a
deliberately separate one-search/one-acquisition/one-LLM developer tool. `.env.example`
contains a blank `OPENROUTER_API_KEY`, a token ceiling no greater than 25,000, the exact
two enable/approval gates, one-call caps, cost cap, and an absolute unused output path.
Copying the example and supplying secrets plus the documented gates must construct
`LiveSmokeConfig` and `OpenRouterConfig` offline. No provider call occurs unless the
exact `--execute` argument and both runtime gates pass.

## Package Metadata

`pyproject.toml` uses durable phase-neutral wording describing the Debate Research Agent
System. Current-facing README/status summaries advance to MVP-6.9; chronological phase
records are preserved.

## Regression and Verification

Regression tests are added before behavioral fixes for Firecrawl PDF/HTML declarations,
missing/empty/malformed/parameterized/unsupported declarations, verified preflight
preservation, unknown preflight, conflicts, source/canonical URL validation, unsafe URL
classes, redirect boundaries, snapshot persistence/reconstruction, acquisition identity,
resume incompatibility, and offline `.env.example` construction.

Completion requires focused MVP-6.9, MVP-6.3, acquisition/fallback, persistence,
fingerprint/resume, and environment tests; the repository-wide type-contract test; full
offline pytest; all deterministic offline evaluations; Ruff lint and format checks; and
`git diff --check`. The final diff and tracked files must contain no unrelated changes,
secrets, databases, caches, coverage, or evaluation output. Exact results are recorded
in `STATUS.md` and `HANDOFF.md` only after every gate passes.

## Completion Record

Complete on 2026-08-10. The focused required selection passed 122 tests; the full
offline suite passed 622 tests with two expected opt-in skips; all 38 deterministic
evaluation cases passed; the repository-wide type contract, Ruff lint/format, and
`git diff --check` passed. The refreshed code graph contains 2,545 nodes. Final review
found no dependency, live call, secret, generated tracked artifact, or later-phase work.
