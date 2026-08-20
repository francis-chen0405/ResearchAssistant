# ResearchAssistant v2 — Phase 4: Discovery Providers, Normalization, Clustering, and Batched Scout

Status: Complete and verified on 2026-08-20.

## Scope

- Extend fresh-v2 Round-1 discovery metadata to OpenAlex, arXiv, PubMed, Exa, and Serper.
- Normalize all provider outputs into strict typed discovery-only artifacts retaining provider,
  query, direction, round, provider rank, title, URL, snippet/abstract, DOI, authors,
  date, type, provider metadata, and immutable provenance.
- Optionally enrich source identity through Crossref DOI metadata. Failure is recorded as
  audit metadata and cannot fail discovery; Crossref data is never evidence.
- Canonicalize URLs, remove tracking parameters, and conservatively cluster only same-source
  candidates by canonical URL, DOI, normalized title, or exact author/year/title identity.
  Retain every alternate URL, provider reference, query reference, and provenance chain.
- Invoke MiMo-v2.5 Scout on batches of at most 30 metadata-only candidates. Scout may decide
  `retrieve`, `maybe`, or `skip`; exact application IDs are required and malformed mappings
  are rejected. It cannot assess evidence or Ledger eligibility.
- Retry each Scout batch once on objective/model-output failure. If it still fails, persist the
  audit failure and retain all items as `maybe` for deterministic ranking.
- Persist the complete Phase-4 artifact through the existing immutable v2 generic artifact
  boundary, allowing restart without another provider or Scout call.

## Explicitly out of scope

- Page retrieval, acquisition, quotation, evidence analysis, Claim Ledger admission, Gap
  Analysis, later research rounds, source recommendation, UI changes, or live verification.
- Treating provider snippets, abstracts, search metadata, or Crossref metadata as evidence.

## Completion signal

Offline tests prove five-provider normalization, Crossref success/failure, canonical and DOI
deduplication, alternate retention, conservative clusters, stable IDs, 30-item batching,
malformed output rejection, bounded retry/fallback, direction isolation, MiMo-v2.5 routing,
audit accounting, and persistence/restart. No live calls are made.
