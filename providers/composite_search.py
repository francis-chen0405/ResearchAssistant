"""Provider-specific MLP-4 discovery routing with bounded OpenAlex fallback."""

from __future__ import annotations

import re

from models import DiscoveryProvider
from providers.exa import ExaSearchAdapter
from providers.openalex import OpenAlexSearchAdapter
from providers.search import (
    SearchFailureCode,
    SearchProvider,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
)
from providers.serpsearch import SerpSearchAdapter

_DEGRADABLE_OPENALEX_FAILURES = frozenset(
    {
        SearchFailureCode.CONNECTION,
        SearchFailureCode.TIMEOUT,
        SearchFailureCode.RATE_LIMIT,
        SearchFailureCode.TRANSIENT_OUTAGE,
        SearchFailureCode.EMPTY_RESULTS,
    }
)


class CompositeSearchProvider:
    """Route each typed query to its declared provider, never by query text."""

    def __init__(
        self,
        *,
        exa: ExaSearchAdapter | None = None,
        openalex: OpenAlexSearchAdapter | None = None,
        serpsearch: SerpSearchAdapter | None = None,
        arxiv: SearchProvider | None = None,
        pubmed: SearchProvider | None = None,
        serper: SearchProvider | None = None,
    ) -> None:
        self._exa = exa
        self._openalex = openalex
        self._serpsearch = serpsearch
        self._arxiv = arxiv
        self._pubmed = pubmed
        self._serper = serper

    def search(self, request: SearchRequest) -> SearchResponse:
        if request.provider is DiscoveryProvider.EXA:
            if self._exa is None:
                raise SearchProviderError(
                    SearchFailureCode.MISSING_CONFIGURATION, "Exa is disabled"
                )
            return self._exa.search(request)
        if request.provider is DiscoveryProvider.SERPSEARCH:
            if self._serpsearch is None:
                raise SearchProviderError(
                    SearchFailureCode.MISSING_CONFIGURATION, "SERP Search is disabled"
                )
            return self._serpsearch.search(request)
        if request.provider is DiscoveryProvider.ARXIV:
            return self._require_optional_provider(self._arxiv, "arXiv").search(request)
        if request.provider is DiscoveryProvider.PUBMED:
            return self._require_optional_provider(self._pubmed, "PubMed").search(request)
        if request.provider is DiscoveryProvider.SERPER:
            return self._require_optional_provider(self._serper, "Serper").search(request)
        if self._openalex is None:
            raise SearchProviderError(
                SearchFailureCode.MISSING_CONFIGURATION, "OpenAlex is disabled"
            )
        try:
            normal = self._openalex.search(request)
        except SearchProviderError as normal_error:
            if normal_error.code not in _DEGRADABLE_OPENALEX_FAILURES:
                raise
            if not request.semantic:
                try:
                    return self._openalex.search(request.model_copy(update={"semantic": True}))
                except SearchProviderError as semantic_error:
                    if semantic_error.code not in _DEGRADABLE_OPENALEX_FAILURES:
                        raise
                    normal_error = semantic_error
            return SearchResponse(
                results=[],
                provider_name="openalex",
                provider_version="works-api",
                adapter_version="mlp4-openalex-works-v1",
                degraded_pool=True,
                warnings=(
                    "OpenAlex was temporarily unavailable; this query continued with Exa.",
                    f"openalex_failure:{normal_error.code.value}",
                ),
            )
        if request.semantic or not _weak_openalex_response(request, normal):
            return normal
        try:
            return self._openalex.search(request.model_copy(update={"semantic": True}))
        except SearchProviderError as semantic_error:
            if semantic_error.code not in _DEGRADABLE_OPENALEX_FAILURES:
                raise
            return normal.model_copy(
                update={
                    "warnings": (
                        *normal.warnings,
                        "OpenAlex semantic fallback was unavailable; normal results were kept.",
                    )
                }
            )

    @staticmethod
    def _require_optional_provider(provider: SearchProvider | None, name: str) -> SearchProvider:
        if provider is None:
            raise SearchProviderError(
                SearchFailureCode.MISSING_CONFIGURATION,
                f"{name} is disabled",
            )
        return provider


def _weak_openalex_response(request: SearchRequest, response: SearchResponse) -> bool:
    query_tokens = set(re.findall(r"[a-z0-9]+", request.query_text.lower()))
    for result in response.results:
        if result.relevance_score is not None and result.relevance_score >= 20:
            return False
        title_tokens = set(re.findall(r"[a-z0-9]+", result.title.lower()))
        if len(query_tokens & title_tokens) >= 2:
            return False
    return True
