"""Provider-specific MLP-4 discovery routing with bounded OpenAlex fallback."""

from __future__ import annotations

import re

from models import DiscoveryProvider
from providers.exa import ExaSearchAdapter
from providers.openalex import OpenAlexSearchAdapter
from providers.search import (
    SearchFailureCode,
    SearchProviderError,
    SearchRequest,
    SearchResponse,
)

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
        exa: ExaSearchAdapter,
        openalex: OpenAlexSearchAdapter,
    ) -> None:
        self._exa = exa
        self._openalex = openalex

    def search(self, request: SearchRequest) -> SearchResponse:
        if request.provider is DiscoveryProvider.EXA:
            return self._exa.search(request)
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


def _weak_openalex_response(request: SearchRequest, response: SearchResponse) -> bool:
    query_tokens = set(re.findall(r"[a-z0-9]+", request.query_text.lower()))
    for result in response.results:
        if result.relevance_score is not None and result.relevance_score >= 20:
            return False
        title_tokens = set(re.findall(r"[a-z0-9]+", result.title.lower()))
        if len(query_tokens & title_tokens) >= 2:
            return False
    return True
