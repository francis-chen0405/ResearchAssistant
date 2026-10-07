"""Versioned capability catalog for fresh-v2 discovery.

This catalog records two different things: documented native API behavior and
the subset represented by today's adapters.  Native support is advisory for
planning; it does not activate transports.  ``executable_*`` values are based
on the live adapters, which currently return one metadata page and execute no
graph-neighbor requests. PubMed requires a separate ESearch and ESummary HTTP
request for that page; both must be reserved by new execution.

Primary documentation consulted (checked 2026-10-06):

* OpenAlex API, search, filters, and paging:
  https://help.openalex.org/api/ ; https://help.openalex.org/api/searching/ ;
  https://help.openalex.org/api/filtering/ ; https://help.openalex.org/api/paging/
* arXiv API User's Manual:
  https://github.com/arXiv/arxiv-docs/blob/develop/source/help/api/user-manual.md
* NCBI E-utilities:
  https://www.ncbi.nlm.nih.gov/books/NBK25497/ ;
  https://www.nlm.nih.gov/dataguide/eutilities/utilities.html
* Exa Search API:
  https://exa.ai/docs/reference/search
* SERP Search API:
  https://serpsearch.com/docs

Limits here are deliberately bounded catalog limits, not promises that an API
will return that many records.  Effective limits are also constrained by the
discovery policy and provider-specific request budgets.  Unsupported structured
filters and graph actions must be rejected; a provider's general query language
does not imply this adapter can compile arbitrary field/operator expressions.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from researchassistant.contracts.discovery_v2 import (
    Relationship,
    SearchMode,
    V2ProviderCapabilities,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider

_CAPABILITIES: tuple[V2ProviderCapabilities, ...] = (
    V2ProviderCapabilities(
        provider=DiscoveryProvider.OPENALEX,
        search_modes=("lexical", "semantic"),
        fields=(
            "works.title",
            "works.abstract",
            "works.fulltext.search",
            "works.doi",
            "works.publication_year",
            "works.publication_date",
            "works.type",
            "works.cited_by_count",
            "works.is_retracted",
            "works.open_access",
            "works.authorships",
            "works.primary_location",
        ),
        operators=("and", "or", "not", "eq", "neq", "gt", "lt", "gte", "lte", "search"),
        max_metadata_per_page=100,
        max_metadata_per_operation=300,
        pagination="cursor",
        identity_lookup=True,
        relationships=("references", "citing", "related"),
        executable_search_modes=("lexical", "semantic"),
        unsupported_features=(
            "adapter does not compile structured field filters or operators",
            "adapter does not follow cursor or request later pages",
            "adapter does not execute identity lookup or graph relationships",
        ),
        documentation_urls=(
            "https://help.openalex.org/api/",
            "https://help.openalex.org/api/searching/",
            "https://help.openalex.org/api/filtering/",
            "https://help.openalex.org/api/paging/",
        ),
        restrictions=(
            "documented maximum per_page is 100",
            "basic page paging is limited to the first 10000 results; cursor supports deep paging",
            "semantic mode is a distinct search.semantic parameter",
            "catalog operation bound is 300 records under the three-page discovery ceiling",
        ),
    ),
    V2ProviderCapabilities(
        provider=DiscoveryProvider.ARXIV,
        search_modes=("lexical",),
        fields=(
            "all",
            "title",
            "author",
            "abstract",
            "comment",
            "journal_ref",
            "category",
            "report_num",
        ),
        operators=("and", "or", "andnot", "field_prefix"),
        max_metadata_per_page=2000,
        max_metadata_per_operation=6000,
        pagination="offset",
        identity_lookup=True,
        executable_search_modes=("lexical",),
        unsupported_features=(
            "adapter emits only all:<query> and does not compile fielded expressions",
            "adapter fixes start=0 and does not follow offset pages",
            "adapter does not execute identity lookup or graph relationships",
            "arXiv API request pacing guidance is outside this capability declaration",
        ),
        documentation_urls=(
            "https://github.com/arXiv/arxiv-docs/blob/develop/source/help/api/user-manual.md",
        ),
        restrictions=(
            "API max_results tops out at 30000 with 2000 per response; "
            "the catalog's three-page bound is 6000",
            "arXiv advises refining searches above 1000 and delaying "
            "three seconds between requests",
            "search query and id_list can be combined by native API",
        ),
    ),
    V2ProviderCapabilities(
        provider=DiscoveryProvider.PUBMED,
        physical_requests_per_page=2,
        search_modes=("lexical",),
        fields=(
            "[all]",
            "[tiab]",
            "[title]",
            "[author]",
            "[journal]",
            "[dp]",
            "[pt]",
            "[mesh]",
            "[ad]",
            "[doi]",
            "[pmid]",
        ),
        operators=("and", "or", "not", "field_tag", "phrase", "date_range"),
        max_metadata_per_page=10000,
        max_metadata_per_operation=10000,
        pagination="offset",
        identity_lookup=True,
        relationships=("references", "citing", "related"),
        executable_search_modes=("lexical",),
        unsupported_features=(
            "adapter forwards a plain Entrez term without compiling a structured query",
            "adapter does not use retstart or page through result sets",
            "adapter does not execute ID lookup or ELink relationships",
        ),
        documentation_urls=(
            "https://www.ncbi.nlm.nih.gov/books/NBK25497/",
            "https://www.nlm.nih.gov/dataguide/eutilities/utilities.html",
        ),
        restrictions=(
            "PubMed ESearch returns at most 10000 matching records for a query",
            "E-utilities request-rate ceilings depend on API-key status",
            "ESearch is UID discovery; bibliographic summaries require a separate ESummary call",
        ),
    ),
    V2ProviderCapabilities(
        provider=DiscoveryProvider.EXA,
        search_modes=("provider_default",),
        fields=(
            "query",
            "includeDomains",
            "excludeDomains",
            "startPublishedDate",
            "endPublishedDate",
            "category",
        ),
        operators=(
            "natural_language_query",
            "domain_include",
            "domain_exclude",
            "date_lower_bound",
            "date_upper_bound",
        ),
        max_metadata_per_page=100,
        max_metadata_per_operation=100,
        pagination="none",
        identity_lookup=False,
        executable_search_modes=("provider_default",),
        unsupported_features=(
            "adapter fixes type=auto and does not expose publication category or date filters",
            "adapter does not expose Exa deep additionalQueries or content controls",
            "adapter maps site: exclusions to excludeDomains and adds default exclusions",
            "no native search pagination or graph relationship action is used by this adapter",
        ),
        documentation_urls=("https://exa.ai/docs/reference/search",),
        restrictions=(
            "public numResults maximum is 100",
            "native filters include publication date bounds and domain allow/deny lists",
            "native search types: instant, fast, auto, deep-lite, deep, deep-reasoning",
            "adapter executes configured auto mode; its lexical or semantic engine is unspecified",
            "Exa search types vary in latency and cost; this catalog does not activate deep search",
        ),
    ),
    V2ProviderCapabilities(
        provider=DiscoveryProvider.SERPSEARCH,
        search_modes=("lexical",),
        fields=("query", "exact_match", "page", "location", "lat", "lng", "gl", "hl"),
        operators=("google_query_syntax", "site", "intitle", "inurl", "quoted_phrase", "or"),
        max_metadata_per_page=10,
        max_metadata_per_operation=30,
        pagination="page",
        identity_lookup=False,
        executable_search_modes=("lexical",),
        unsupported_features=(
            "adapter fixes page=1 and does not expose exact_match, locale, or location controls",
            "adapter passes query text; it does not compile structured fields or operators",
            "adapter only normalizes organic results; special SERP modules are ignored",
            "adapter does not execute identity lookup or graph relationships",
        ),
        documentation_urls=("https://serpsearch.com/docs",),
        restrictions=(
            "documented web search page returns 10 results",
            "page is 1-based; catalog operation bound is 30 records under three pages",
            "upstream Google interprets query syntax; this adapter does not validate it locally",
        ),
    ),
)

PROVIDER_CAPABILITIES: Mapping[DiscoveryProvider, V2ProviderCapabilities] = MappingProxyType(
    {capability.provider: capability for capability in _CAPABILITIES}
)


def get_provider_capabilities(provider: DiscoveryProvider) -> V2ProviderCapabilities:
    """Return the immutable catalog entry, rejecting disabled/legacy providers."""
    try:
        return PROVIDER_CAPABILITIES[provider]
    except KeyError as exc:
        raise ValueError(f"no fresh-v2 discovery capabilities for {provider}") from exc


def validate_search_capability(
    provider: DiscoveryProvider, mode: SearchMode, *, executable: bool = False
) -> None:
    """Reject a mode absent from the native or currently executable catalog."""
    get_provider_capabilities(provider).require_search(mode, executable=executable)


def validate_relationship_capability(
    provider: DiscoveryProvider, relationship: Relationship, *, executable: bool = False
) -> None:
    """Reject unsupported native or currently executable graph operations."""
    get_provider_capabilities(provider).require_relationship(relationship, executable=executable)
