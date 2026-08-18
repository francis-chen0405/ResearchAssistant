"""Deterministic MLP-4 discovery ranking before source acquisition."""

from __future__ import annotations

import re
from collections import Counter
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from models import (
    DiscoveryProvider,
    RetrievalRecord,
    SearchIntent,
    SearchQuery,
    SourceSnapshot,
    StrictModel,
)
from providers.search import SearchResult

DISCOVERY_POLICY_VERSION = "mlp4-expanded-retrieval-yield-v1"
DISCARD_SCORE_FLOOR = 5
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "with",
        "without",
    }
)
_TRACKING_PARAMETERS = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "source",
        "utm_campaign",
        "utm_content",
        "utm_medium",
        "utm_source",
        "utm_term",
    }
)
_MARKETING_HOSTS = frozenset(
    {
        "monday.com",
        "www.monday.com",
        "genesys.com",
        "www.genesys.com",
    }
)
_MARKETING_TERMS = frozenset(
    {
        "blog",
        "community",
        "customer story",
        "customer success",
        "marketing",
        "our product",
        "press release",
        "productivity tools",
        "sponsored",
    }
)
_EMPIRICAL_TERMS = frozenset(
    {
        "analysis",
        "effect",
        "evidence",
        "impact",
        "improve",
        "output",
        "productivity",
        "research",
        "study",
    }
)


class DiscoveryDecision(StrEnum):
    SELECTED = "selected"
    DEFERRED = "deferred"
    DISCARDED = "discarded"


class DiscoveryScoreComponents(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relevance: int = Field(ge=0, le=35)
    intent_match: int = Field(ge=0, le=20)
    directness: int = Field(ge=0, le=15)
    metadata_completeness: int = Field(ge=0, le=10)
    likely_accessibility: int = Field(ge=0, le=10)
    source_novelty: int = Field(ge=0, le=10)
    generic_homepage_penalty: int = Field(default=0, ge=-15, le=0)
    marketing_or_community_penalty: int = Field(default=0, ge=-20, le=0)
    unrelated_title_penalty: int = Field(default=0, ge=-10, le=0)

    @property
    def total(self) -> int:
        return max(
            0,
            self.relevance
            + self.intent_match
            + self.directness
            + self.metadata_completeness
            + self.likely_accessibility
            + self.source_novelty
            + self.generic_homepage_penalty
            + self.marketing_or_community_penalty
            + self.unrelated_title_penalty,
        )


class RankedDiscoveryResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: SearchQuery
    result: SearchResult
    canonical_url: str = Field(min_length=1)
    components: DiscoveryScoreComponents
    score: int = Field(ge=0, le=100)
    decision: DiscoveryDecision
    selection_rank: int | None = Field(default=None, ge=1, le=10)

    @model_validator(mode="after")
    def validate_score_and_selection(self) -> RankedDiscoveryResult:
        if self.score != self.components.total:
            raise ValueError("discovery score must equal its deterministic components")
        if (self.decision is DiscoveryDecision.SELECTED) != (self.selection_rank is not None):
            raise ValueError("only selected discovery results may have a selection rank")
        if self.decision is DiscoveryDecision.DISCARDED and self.score >= DISCARD_SCORE_FLOOR:
            raise ValueError("only scores below the discard floor may be discarded")
        return self


class AcquiredSourceScoreComponents(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    readability: int = Field(ge=0, le=25)
    claim_term_coverage: int = Field(ge=0, le=35)
    document_specificity: int = Field(ge=0, le=25)
    evidence_language: int = Field(ge=0, le=15)
    generic_or_promotional_penalty: int = Field(default=0, ge=-20, le=0)

    @property
    def total(self) -> int:
        return max(
            0,
            self.readability
            + self.claim_term_coverage
            + self.document_specificity
            + self.evidence_language
            + self.generic_or_promotional_penalty,
        )


class RankedAcquiredSource(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: UUID
    retrieval_attempt_id: UUID
    components: AcquiredSourceScoreComponents
    score: int = Field(ge=0, le=100)
    extraction_rank: int = Field(ge=1, le=10)

    @model_validator(mode="after")
    def validate_score(self) -> RankedAcquiredSource:
        if self.score != self.components.total:
            raise ValueError("acquired-source score must equal its deterministic components")
        return self


def rank_discovery_pool(
    *,
    claim_text: str,
    claim_facets: tuple[str, ...] = (),
    query_results: tuple[tuple[SearchQuery, SearchResult], ...],
    source_target: int,
) -> tuple[RankedDiscoveryResult, ...]:
    """Collapse exact canonical URLs, score the pool, and select only the top N."""
    if source_target not in {5, 7, 10, 15, 20}:
        raise ValueError("source target must be one of 5, 10, 15, or 20")
    host_counts = Counter(
        (urlsplit(result.original_url).hostname or "").lower() for _, result in query_results
    )
    scored = [
        _score_result(
            claim_text=claim_text,
            claim_facets=claim_facets,
            query=query,
            result=result,
            repeated_host=host_counts[(urlsplit(result.original_url).hostname or "").lower()] > 1,
        )
        for query, result in query_results
    ]
    best_by_url: dict[str, RankedDiscoveryResult] = {}
    for item in scored:
        current = best_by_url.get(item.canonical_url)
        if current is None or _sort_key(item) < _sort_key(current):
            best_by_url[item.canonical_url] = item
    ordered = sorted(best_by_url.values(), key=_sort_key)
    selected_count = 0
    final: list[RankedDiscoveryResult] = []
    for item in ordered:
        if item.score < DISCARD_SCORE_FLOOR:
            decision = DiscoveryDecision.DISCARDED
            selection_rank = None
        elif selected_count < source_target:
            selected_count += 1
            decision = DiscoveryDecision.SELECTED
            selection_rank = selected_count
        else:
            decision = DiscoveryDecision.DEFERRED
            selection_rank = None
        final.append(
            item.model_copy(
                update={"decision": decision, "selection_rank": selection_rank},
            )
        )
    return tuple(final)


def canonical_discovery_url(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = host if port is None else f"{host}:{port}"
    path = parsed.path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in _TRACKING_PARAMETERS
        )
    )
    return urlunsplit((parsed.scheme.lower(), netloc, path, query, ""))


def rank_acquired_sources(
    *,
    claim_text: str,
    claim_facets: tuple[str, ...] = (),
    snapshots: tuple[SourceSnapshot, ...],
    retrievals: tuple[RetrievalRecord, ...],
) -> tuple[RankedAcquiredSource, ...]:
    """Order acquired text for extraction without discarding an otherwise usable source."""
    retrieval_by_id = {item.retrieval_attempt_id: item for item in retrievals}
    claim_tokens = _tokens(claim_text)
    facet_tokens = _facet_tokens(claim_facets, claim_tokens)
    scored: list[tuple[SourceSnapshot, AcquiredSourceScoreComponents]] = []
    for snapshot in snapshots:
        retrieval = retrieval_by_id.get(snapshot.retrieval_attempt_id)
        if retrieval is None:
            raise ValueError("acquired-source ranking requires matching retrieval provenance")
        text = snapshot.normalized_text
        text_tokens = _tokens(text)
        word_count = len(_TOKEN_RE.findall(text))
        readability = 25 if word_count >= 150 else 18 if word_count >= 75 else 8
        base_coverage = round(20 * len(claim_tokens & text_tokens) / max(len(claim_tokens), 1))
        facet_coverage = (
            round(15 * len(facet_tokens & text_tokens) / len(facet_tokens)) if facet_tokens else 0
        )
        claim_term_coverage = min(35, base_coverage + facet_coverage)
        path = urlsplit(retrieval.resolved_url).path
        document_specificity = (15 if path not in {"", "/"} else 3) + (
            10 if word_count >= 250 else 5
        )
        lowered = text.casefold()
        empirical_matches = sum(term in lowered for term in _EMPIRICAL_TERMS)
        evidence_language = min(15, empirical_matches * 3)
        promotional_matches = sum(term in lowered for term in _MARKETING_TERMS)
        components = AcquiredSourceScoreComponents(
            readability=readability,
            claim_term_coverage=claim_term_coverage,
            document_specificity=document_specificity,
            evidence_language=evidence_language,
            generic_or_promotional_penalty=-20 if promotional_matches >= 2 else 0,
        )
        scored.append((snapshot, components))
    ordered = sorted(
        scored,
        key=lambda item: (-item[1].total, item[0].source_url, str(item[0].snapshot_id)),
    )
    return tuple(
        RankedAcquiredSource(
            snapshot_id=snapshot.snapshot_id,
            retrieval_attempt_id=snapshot.retrieval_attempt_id,
            components=components,
            score=components.total,
            extraction_rank=index,
        )
        for index, (snapshot, components) in enumerate(ordered, start=1)
    )


def _score_result(
    *,
    claim_text: str,
    claim_facets: tuple[str, ...],
    query: SearchQuery,
    result: SearchResult,
    repeated_host: bool,
) -> RankedDiscoveryResult:
    claim_tokens = _tokens(f"{claim_text} {query.query_text}")
    facet_tokens = _facet_tokens(claim_facets, claim_tokens)
    result_tokens = _tokens(f"{result.title} {result.snippet or ''}")
    overlap = len(claim_tokens & result_tokens)
    base_relevance = round(20 * overlap / max(len(claim_tokens), 1))
    facet_relevance = (
        round(15 * len(facet_tokens & result_tokens) / len(facet_tokens)) if facet_tokens else 0
    )
    relevance = min(35, base_relevance + facet_relevance)
    if result.relevance_score is not None:
        relevance = min(35, relevance + min(round(max(result.relevance_score, 0) / 20), 5))
    intent_match = _intent_score(query, result)
    parsed = urlsplit(result.original_url)
    directness = (10 if result.title else 5) + 5 if parsed.path not in {"", "/"} else 0
    metadata = result.metadata
    metadata_completeness = min(
        10,
        (3 if result.title else 0)
        + (3 if metadata.published_at else 0)
        + (1 if metadata.author else 0)
        + (3 if metadata.doi else 0),
    )
    likely_accessibility = 10 if parsed.scheme in {"http", "https"} and parsed.netloc else 0
    source_novelty = 5 if repeated_host else 10
    generic = parsed.path in {"", "/"}
    unrelated = bool(result.title) and overlap == 0
    empirical = bool(_tokens(f"{claim_text} {query.query_text}") & _EMPIRICAL_TERMS)
    marketing = empirical and _is_marketing_page(result)
    components = DiscoveryScoreComponents(
        relevance=relevance,
        intent_match=intent_match,
        directness=directness,
        metadata_completeness=metadata_completeness,
        likely_accessibility=likely_accessibility,
        source_novelty=source_novelty,
        generic_homepage_penalty=-15 if generic else 0,
        marketing_or_community_penalty=-20 if marketing else 0,
        unrelated_title_penalty=-10 if unrelated else 0,
    )
    return RankedDiscoveryResult(
        query=query,
        result=result,
        canonical_url=canonical_discovery_url(result.original_url),
        components=components,
        score=components.total,
        decision=(
            DiscoveryDecision.DISCARDED
            if components.total < DISCARD_SCORE_FLOOR
            else DiscoveryDecision.DEFERRED
        ),
    )


def _intent_score(query: SearchQuery, result: SearchResult) -> int:
    engine = (result.metadata.engine or "").lower()
    if query.provider is DiscoveryProvider.OPENALEX:
        return 20 if engine == "openalex" and query.intent is SearchIntent.ACADEMIC_STUDY else 5
    if engine == "exa":
        return 20
    return 10


def _is_marketing_page(result: SearchResult) -> bool:
    parsed = urlsplit(result.original_url)
    host = (parsed.hostname or "").lower()
    surface = f"{parsed.path} {result.title}".lower().replace("-", " ").replace("_", " ")
    return host in _MARKETING_HOSTS or any(term in surface for term in _MARKETING_TERMS)


def _tokens(value: str) -> frozenset[str]:
    return frozenset(
        token for token in _TOKEN_RE.findall(value.lower()) if token not in _STOP_WORDS
    )


def _facet_tokens(claim_facets: tuple[str, ...], claim_tokens: frozenset[str]) -> frozenset[str]:
    """Return optional, claim-specific terms without imposing a gate on broad claims."""
    tokens = frozenset().union(*(_tokens(facet) for facet in claim_facets if facet.strip()))
    # A Planner can use broad boilerplate such as "all people"; only terms already
    # present in the claim are safe as ranking bonuses.
    return tokens & claim_tokens


def _sort_key(item: RankedDiscoveryResult) -> tuple[int, str, int, str]:
    return (-item.score, item.query.provider.value, item.result.rank, item.canonical_url)
