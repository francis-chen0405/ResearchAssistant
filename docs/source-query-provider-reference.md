# Source query provider reference

Checked against primary provider documentation on 2026-10-06; OpenAlex semantic
limits/pricing, SERP pagination/exact-match behavior, and Exa pricing rechecked on 2026-10-07. This reference records
the provider behavior used by the bounded query compiler and adapters. It is not a
claim that every documented operation is enabled in this application.

## OpenAlex Works API

- The endpoint is `GET /works`; query text uses exactly one of `search`,
  `search.exact`, or `search.semantic` per request. Semantic search cannot be combined
  with another search parameter. See [Search](https://help.openalex.org/api/searching/)
  and [Semantic Search](https://help.openalex.org/api/semantic-search/).
- Ordinary `per_page` is supported from 1 to 100; semantic search allows at most 50
  results and query text up to 2,000 characters. Fresh executable metadata uses
  bounded 20-result pages for lexical search (up to 50 across three physical pages)
  and one request for up to 50 semantic results. See [paging](https://help.openalex.org/api/paging/)
  and [Semantic Search limits](https://help.openalex.org/api/semantic-search/).
- Semantic search is limited to one request per second. The adapter serializes and
  spaces actual semantic send starts, including retries, with cancellation checked
  before durable reservation. The limiter covers one adapter instance; separate
  adapters or processes sharing an account need coordination outside this limiter.
  See [Semantic Search rate limit](https://help.openalex.org/api/semantic-search/).
- The current endpoint price is $1 per 1,000 search calls ($0.001 each) for both
  lexical and semantic search. Direct API reranking is disabled by this adapter; if
  enabled separately, rerank adds another $0.001. The adapter reports the response's
  `meta.cost_usd` when present and leaves cost unknown when the provider omits it.
  See [OpenAlex example costs](https://help.openalex.org/access/example-costs/).

## arXiv API

- `GET /api/query` accepts `search_query`, `start`, `max_results`, `sortBy`, and
  `sortOrder`. It returns Atom metadata. `search_query` supports field prefixes such
  as `ti:` (title), `au:` (author), and `abs:` (abstract); fielded expressions are
  preferable to broad `all:` when the concepts can be restricted to title/abstract.
- Sorting accepts `relevance`, `lastUpdatedDate`, or `submittedDate`; sort order is
  ascending or descending. The documented API maximum is 30,000 results total, in
  slices up to 2,000, while this adapter issues one bounded page and compiler policy
  caps it far below that. See the [arXiv API User's Manual](https://github.com/arXiv/arxiv-docs/blob/develop/source/help/api/user-manual.md).
- Legacy free-text input is wrapped with `all:` only when it does not already begin
  with `all:`. Compiled queries use the fielded `search_query` unchanged, avoiding a
  duplicate `all:` prefix.

## PubMed E-utilities

- ESearch uses `/entrez/eutils/esearch.fcgi` with `db=pubmed`, `term`, `retmax`, and
  `retmode=json`; ESummary then fetches bibliographic records by PMID. ESearch accepts
  at most 10,000 PubMed identifiers, and this adapter makes one tightly bounded
  metadata page. See [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/).
- PubMed supports the `[tiab]` (Title/Abstract) search tag. Each concept and alias is
  explicitly scoped to Title/Abstract by the compiler, so compiled queries do not
  depend on automatic term mapping across other fields. NCBI also documents the
  equivalent long form `[Title/Abstract]`. See [PubMed search help](https://pubmed.ncbi.nlm.nih.gov/help/).

## Exa Search API

- Search is `POST https://api.exa.ai/search` with a natural-language `query`, `type`,
  and `numResults`. Compiled default-mode requests explicitly set `type: "auto"`,
  letting Exa select the search route. The adapter sends the compiler's query string
  directly and reports `costDollars.total` only when the response supplies it. See
  [Exa Search API](https://exa.ai/docs/reference/search).
- The API request supports `numResults`; the application currently caps executable
  auto-search at 25 pending enterprise entitlement. The [Exa pricing page](https://exa.ai/pricing)
  prices Auto Search at $7 per 1,000 requests for up to 10 results and $1 per 1,000
  requests per additional result. To preserve the existing $0.18 / 18-request run
  ceiling, this implementation reserves $0.02 per default depth-20 operation and
  $0.03 at policy depth 50 (effective result cap 25). These are conservative policy
  reservations, not guarantees about future provider pricing or returned result count.

## SERP Search

- The Google organic search endpoint is `GET /api/v1/search` with `query` and a
  1-based `page`. Results are ten per page; fresh retrieval follows up to three
  pages under the three-physical-request operation ceiling. Empty later pages are
  retained as completed results, and page checkpoints prevent replay of completed
  pages after interruption. See [SERP Search pagination examples](https://serpsearch.com/examples).
- For compiled queries with phrases or Boolean operators, `exact_match=true` requests
  Google's verbatim interpretation, suppressing spelling corrections and preserving
  quotes, Unicode, parentheses, and `OR`. See [SERP Search API documentation](https://serpsearch.com/docs).

## Serper

No Serper adapter or Serper configuration is present in `providers/`; the configured
Google-style adapter is SERP Search above. No Serper requests or credentials were used.
