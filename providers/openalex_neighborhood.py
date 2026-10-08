"""Bounded identifier resolution and citation-neighborhood reads for OpenAlex."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import ConfigDict, Field, ValidationError

from providers.config import OpenAlexConfig
from providers.discovery_transport import bounded_send
from providers.search import (
    SearchDiscoveryMetadata,
    SearchFailureCode,
    SearchProviderError,
    SearchResult,
    SearchTimeoutError,
)
from researchassistant.contracts.discovery_v2 import safe_location
from researchassistant.contracts.models import StrictModel

OPENALEX_API = "https://api.openalex.org"
MAX_NEIGHBOR_RESULTS = 10
MAX_NEIGHBOR_RESPONSE_BYTES = 262_144
WORK_SELECT = ",".join(
    (
        "id",
        "doi",
        "title",
        "abstract_inverted_index",
        "publication_year",
        "type",
        "authorships",
        "is_retracted",
        "referenced_works",
        "related_works",
        "primary_location",
        "best_oa_location",
        "locations",
    )
)
_OPENALEX_ID = re.compile(r"^W[0-9]{1,20}$", re.IGNORECASE)
_DOI = re.compile(r"^10\.[0-9]{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)
_CANONICAL_WORK_ID = re.compile(r"^https://openalex\.org/(W[0-9]{1,20})$", re.IGNORECASE)


class NeighborhoodStatus(StrEnum):
    RESOLVED = "resolved"
    UNSUPPORTED = "unsupported"
    EMPTY = "empty"
    MALFORMED = "malformed"


class NeighborhoodRelation(StrEnum):
    REFERENCES = "references"
    RELATED = "related"
    CITING = "citing"


class ResolvedOpenAlexWork(StrictModel):
    """Small immutable, verified identity and bounded neighborhood for one work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    openalex_id: str
    doi: str | None = None
    title: str
    authors: tuple[str, ...] = ()
    year: int | None = Field(default=None, ge=1000, le=9999)
    work_type: str | None = None
    is_retracted: bool | None = None
    # OpenAlex documents is_retracted but no is_withdrawn work attribute.
    is_withdrawn: bool | None = None
    referenced_work_ids: tuple[str, ...] | None = Field(
        default=None, max_length=MAX_NEIGHBOR_RESULTS
    )
    related_work_ids: tuple[str, ...] | None = Field(default=None, max_length=MAX_NEIGHBOR_RESULTS)
    results: tuple[SearchResult, ...] = Field(max_length=MAX_NEIGHBOR_RESULTS)


class NeighborhoodResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: NeighborhoodStatus
    relation: NeighborhoodRelation | None = None
    work: ResolvedOpenAlexWork | None = None
    results: tuple[SearchResult, ...] = Field(default=(), max_length=MAX_NEIGHBOR_RESULTS)


class PhysicalRequester(Protocol):
    """Durable owner callback: reserve/persist first, then invoke the send closure."""

    def __call__(
        self,
        parameters: Mapping[str, str | int | bool],
        send: Callable[[], httpx.Response],
    ) -> httpx.Response: ...


class OpenAlexNeighborhoodAdapter:
    """Resolve exact IDs and read one bounded OpenAlex citation neighborhood."""

    def __init__(self, config: OpenAlexConfig, *, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(
            base_url=OPENALEX_API,
            timeout=httpx.Timeout(config.deadlines.search_seconds),
            follow_redirects=False,
        )

    def resolve(self, identifier: str, *, requester: PhysicalRequester) -> NeighborhoodResult:
        """Resolve only an OpenAlex W ID or DOI, then verify the returned identifier."""
        normalized = _normalize_identifier(identifier)
        if normalized is None:
            return NeighborhoodResult(status=NeighborhoodStatus.UNSUPPORTED)
        kind, value = normalized
        params: dict[str, str | int | bool] = {"select": WORK_SELECT}
        if kind == "openalex":
            path = f"/works/{value}"
        else:
            params.update(filter=f"doi:https://doi.org/{value}", per_page=2)
            path = "/works"
        response = self._request(path, params, requester)
        return self.parse_resolution(identifier, response)

    @staticmethod
    def parse_resolution(identifier: str, response: httpx.Response) -> NeighborhoodResult:
        """Parse a cached or fresh exact-identifier response without transport."""
        normalized = _normalize_identifier(identifier)
        if normalized is None:
            return NeighborhoodResult(status=NeighborhoodStatus.UNSUPPORTED)
        kind, value = normalized
        body = _decode_response(response)
        if kind == "openalex":
            if not isinstance(body, dict):
                return NeighborhoodResult(status=NeighborhoodStatus.MALFORMED)
            item = body
            if _openalex_id(item.get("id")) != value:
                return NeighborhoodResult(status=NeighborhoodStatus.EMPTY)
        else:
            items = body.get("results") if isinstance(body, dict) else None
            if not isinstance(items, list):
                return NeighborhoodResult(status=NeighborhoodStatus.MALFORMED)
            exact = [
                item
                for item in items
                if isinstance(item, dict) and _same_doi(item.get("doi"), value)
            ]
            if not exact:
                return NeighborhoodResult(status=NeighborhoodStatus.EMPTY)
            if len(exact) > 1:
                return NeighborhoodResult(status=NeighborhoodStatus.MALFORMED)
            item = exact[0]
        work = _parse_work(item)
        if work is None:
            return NeighborhoodResult(status=NeighborhoodStatus.MALFORMED)
        return NeighborhoodResult(status=NeighborhoodStatus.RESOLVED, work=work)

    def expand(
        self,
        work: ResolvedOpenAlexWork,
        relation: NeighborhoodRelation,
        *,
        requester: PhysicalRequester,
        limit: int = MAX_NEIGHBOR_RESULTS,
    ) -> NeighborhoodResult:
        """Read one batch of references/related works or one page of citing works."""
        params, status = _expansion_parameters(work, relation, limit)
        if params is None:
            return NeighborhoodResult(status=status, relation=relation, work=work)
        response = self._request("/works", params, requester)
        return self.parse_expansion(work, relation, limit, response)

    @staticmethod
    def parse_expansion(
        work: ResolvedOpenAlexWork,
        relation: NeighborhoodRelation,
        limit: int,
        response: httpx.Response,
    ) -> NeighborhoodResult:
        """Parse cached or fresh bounded relationship data without transport."""
        params, status = _expansion_parameters(work, relation, limit)
        if params is None:
            return NeighborhoodResult(status=status, relation=relation, work=work)
        requested_ids = (
            None
            if relation is NeighborhoodRelation.CITING
            else frozenset(
                (
                    work.referenced_work_ids
                    if relation is NeighborhoodRelation.REFERENCES
                    else work.related_work_ids
                )[:limit]
            )
        )
        body = _decode_response(response)
        items = body.get("results") if isinstance(body, dict) else None
        if not isinstance(items, list):
            return NeighborhoodResult(
                status=NeighborhoodStatus.MALFORMED, relation=relation, work=work
            )
        results: list[SearchResult] = []
        seen_ids: set[str] = set()
        for index, item in enumerate(items[:limit]):
            item_id = _openalex_id(item.get("id")) if isinstance(item, dict) else None
            if item_id is None:
                return NeighborhoodResult(
                    status=NeighborhoodStatus.MALFORMED, relation=relation, work=work
                )
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            if requested_ids is not None and item_id not in requested_ids:
                return NeighborhoodResult(
                    status=NeighborhoodStatus.MALFORMED, relation=relation, work=work
                )
            if relation is NeighborhoodRelation.CITING:
                references = item.get("referenced_works") if isinstance(item, dict) else None
                if not isinstance(references, list) or _openalex_id(work.openalex_id) not in {
                    _openalex_id(reference) for reference in references
                }:
                    return NeighborhoodResult(
                        status=NeighborhoodStatus.MALFORMED, relation=relation, work=work
                    )
            # Preserve the first occurrence's provider rank even when duplicates are skipped.
            parsed = _to_search_result(item, index + 1)
            if parsed is not None:
                results.append(parsed)
        if not results:
            return NeighborhoodResult(status=NeighborhoodStatus.EMPTY, relation=relation, work=work)
        return NeighborhoodResult(
            status=NeighborhoodStatus.RESOLVED,
            relation=relation,
            work=work,
            results=tuple(results),
        )

    def _request(
        self,
        path: str,
        params: Mapping[str, str | int | bool],
        requester: PhysicalRequester,
    ) -> httpx.Response:
        request_params = dict(params)

        def send() -> httpx.Response:
            actual_params = {
                **request_params,
                "api_key": self._config.api_key.get_secret_value(),
            }
            return bounded_send(
                self._client,
                "GET",
                f"{OPENALEX_API}{path}",
                expected_base_url=OPENALEX_API,
                max_response_bytes=MAX_NEIGHBOR_RESPONSE_BYTES,
                params=actual_params,
                timeout=self._config.deadlines.search_seconds,
            )

        try:
            response = requester(dict(params), send)
        except httpx.TimeoutException as exc:
            raise SearchTimeoutError(
                SearchFailureCode.TIMEOUT,
                "OpenAlex neighborhood request timed out",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise SearchProviderError(
                SearchFailureCode.CONNECTION,
                "OpenAlex neighborhood connection failed",
                retryable=True,
            ) from exc
        return response


def _expansion_parameters(
    work: ResolvedOpenAlexWork,
    relation: NeighborhoodRelation,
    limit: int,
) -> tuple[dict[str, str | int | bool] | None, NeighborhoodStatus]:
    if not 1 <= limit <= MAX_NEIGHBOR_RESULTS:
        raise ValueError("neighborhood limit must be between 1 and 10")
    seed_id = _openalex_id(work.openalex_id)
    if seed_id is None:
        return None, NeighborhoodStatus.MALFORMED
    if relation is NeighborhoodRelation.CITING:
        return (
            {
                "filter": f"cites:{seed_id}",
                "per_page": limit,
                "select": WORK_SELECT,
            },
            NeighborhoodStatus.RESOLVED,
        )
    if relation is NeighborhoodRelation.REFERENCES:
        available_ids = work.referenced_work_ids
    elif relation is NeighborhoodRelation.RELATED:
        available_ids = work.related_work_ids
    else:
        return None, NeighborhoodStatus.UNSUPPORTED
    if available_ids is None:
        return None, NeighborhoodStatus.UNSUPPORTED
    ids = available_ids[:limit]
    if any(_openalex_id(work_id) is None for work_id in ids):
        return None, NeighborhoodStatus.MALFORMED
    if not ids:
        return None, NeighborhoodStatus.EMPTY
    return (
        {
            "filter": "openalex:" + "|".join(ids),
            "per_page": len(ids),
            "select": WORK_SELECT,
        },
        NeighborhoodStatus.RESOLVED,
    )


def _decode_response(response: httpx.Response) -> object:
    _raise_http_status(response.status_code)
    try:
        return response.json()
    except ValueError as exc:
        raise SearchProviderError(
            SearchFailureCode.MALFORMED_RESPONSE,
            "OpenAlex returned invalid neighborhood JSON",
        ) from exc


def _normalize_identifier(identifier: str) -> tuple[str, str] | None:
    """Accept only a sanitized W ID or DOI token / DOI URL."""
    if not isinstance(identifier, str) or not identifier or len(identifier) > 512:
        return None
    candidate = identifier.strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in candidate) or "\\" in candidate:
        return None
    work_id = _openalex_id(candidate)
    if work_id is not None:
        return "openalex", work_id
    lowered = candidate.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if lowered.startswith(prefix):
            candidate = candidate[len(prefix) :]
            break
    candidate = candidate.strip()
    if "?" in candidate or "#" in candidate or not _DOI.fullmatch(candidate):
        return None
    return "doi", candidate.lower()


def _openalex_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    canonical = _CANONICAL_WORK_ID.fullmatch(value)
    candidate = canonical.group(1) if canonical else value
    match = _OPENALEX_ID.fullmatch(candidate)
    return match.group(0).upper() if match else None


def _same_doi(value: object, expected: str) -> bool:
    normalized = _normalize_identifier(value) if isinstance(value, str) else None
    return normalized == ("doi", expected)


def _parse_work(item: Mapping[str, object]) -> ResolvedOpenAlexWork | None:
    work_id = _openalex_id(item.get("id"))
    if work_id is None:
        return None
    result = _to_search_result(item, 1)
    if result is None:
        return None
    authorships = item.get("authorships")
    authors: list[str] = []
    if isinstance(authorships, list):
        for authorship in authorships[:10]:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author")
            name = author.get("display_name") if isinstance(author, dict) else None
            if isinstance(name, str) and name.strip():
                authors.append(name.strip())
    year = item.get("publication_year")
    if isinstance(year, bool) or not isinstance(year, int) or not 1000 <= year <= 9999:
        year = None
    retracted = item.get("is_retracted")
    if not isinstance(retracted, bool):
        retracted = None
    raw_refs = item.get("referenced_works")
    raw_related = item.get("related_works")
    refs = _work_ids(raw_refs) if isinstance(raw_refs, list) else None
    related = _work_ids(raw_related) if isinstance(raw_related, list) else None
    try:
        return ResolvedOpenAlexWork(
            openalex_id=f"https://openalex.org/{work_id}",
            doi=result.metadata.doi,
            title=result.title,
            authors=tuple(authors),
            year=year,
            work_type=result.metadata.work_type,
            is_retracted=retracted,
            is_withdrawn=None,
            referenced_work_ids=refs,
            related_work_ids=related,
            results=(result,),
        )
    except ValidationError:
        return None


def _work_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    ids: list[str] = []
    for raw in value:
        work_id = _openalex_id(raw)
        if work_id and work_id not in ids:
            ids.append(work_id)
        if len(ids) >= MAX_NEIGHBOR_RESULTS:
            break
    return tuple(ids)


def _to_search_result(item: object, rank: int) -> SearchResult | None:
    if not isinstance(item, dict):
        return None
    work_id = _openalex_id(item.get("id"))
    if work_id is None:
        return None
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        title = ""
    doi = item.get("doi")
    normalized_doi = _normalize_identifier(doi) if isinstance(doi, str) else None
    doi_value = f"https://doi.org/{normalized_doi[1]}" if normalized_doi is not None else None
    year = item.get("publication_year")
    year_value = (
        f"{year}-01-01"
        if isinstance(year, int) and not isinstance(year, bool) and 1000 <= year <= 9999
        else None
    )
    retracted = item.get("is_retracted")
    if not isinstance(retracted, bool):
        retracted = None
    primary = item.get("primary_location")
    best = item.get("best_oa_location")
    locations = item.get("locations")
    urls = _location_urls(locations)
    primary_url = _location_field(primary, "landing_page_url")
    best_url = _location_field(best, "landing_page_url")
    pdf_url = _location_field(primary, "pdf_url") or _location_field(best, "pdf_url")
    original_url = primary_url or best_url or doi_value or f"https://openalex.org/{work_id}"
    try:
        return SearchResult(
            original_url=original_url,
            title=title,
            rank=rank,
            metadata=SearchDiscoveryMetadata(
                published_at=year_value,
                display_url=original_url,
                category="academic",
                author=_authors(item.get("authorships")),
                abstract=_abstract(item.get("abstract_inverted_index")),
                external_id=f"https://openalex.org/{work_id}",
                doi=doi_value,
                work_type=item.get("type") if isinstance(item.get("type"), str) else None,
                is_retracted=retracted,
                pdf_url=pdf_url,
                full_text_url=urls[0] if urls else None,
            ),
        )
    except ValidationError:
        return None


def _location_urls(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    found: list[str] = []
    for location in value:
        url = _location_field(location, "landing_page_url")
        if url and url not in found:
            found.append(url)
    return tuple(found[:MAX_NEIGHBOR_RESULTS])


def _location_field(location: object, key: str) -> str | None:
    if not isinstance(location, dict):
        return None
    value = location.get(key)
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        safe_location(value)
    except ValueError:
        return None
    if not _syntactically_public_location(value):
        return None
    return value


def _syntactically_public_location(value: str) -> bool:
    """Reject obviously private, reserved, or malformed hosts without doing DNS."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or port == 0
        or any(character.isspace() or ord(character) < 32 for character in value)
        or "\\" in value
    ):
        return False
    hostname = parsed.hostname
    if hostname is None:
        return False
    try:
        lowered = hostname.rstrip(".").encode("idna").decode("ascii").casefold()
    except UnicodeError:
        return False
    prohibited_suffixes = (
        ".localhost",
        ".local",
        ".localdomain",
        ".internal",
        ".home",
        ".lan",
        ".example",
        ".test",
        ".invalid",
        ".onion",
    )
    if not lowered or lowered == "localhost" or lowered.endswith(prohibited_suffixes):
        return False
    try:
        literal = ipaddress.ip_address(lowered)
    except ValueError:
        literal = None
    if literal is not None:
        return literal.is_global and not literal.is_multicast
    if re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*", lowered):
        return False
    labels = lowered.split(".")
    label_pattern = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    return (
        len(lowered) <= 253
        and len(labels) >= 2
        and all(label_pattern.fullmatch(label) for label in labels)
    )


def _authors(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    names: list[str] = []
    for authorship in value[:10]:
        author = authorship.get("author") if isinstance(authorship, dict) else None
        name = author.get("display_name") if isinstance(author, dict) else None
        if isinstance(name, str) and name.strip():
            names.append(name.strip()[:200])
    return "; ".join(names)[:1000] or None


def _abstract(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    terms: list[tuple[int, str]] = []
    for token, positions in list(value.items())[:5000]:
        if not isinstance(token, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if (
                isinstance(position, int)
                and not isinstance(position, bool)
                and 0 <= position < 100_000
            ):
                terms.append((position, token[:200]))
    if not terms:
        return None
    terms.sort(key=lambda term: term[0])
    text = " ".join(token for _position, token in terms)
    return text[:5000] or None


def _raise_http_status(status_code: int) -> None:
    if 200 <= status_code < 300:
        return
    if status_code in {401, 403}:
        raise SearchProviderError(
            SearchFailureCode.AUTHENTICATION, "OpenAlex authentication failed"
        )
    if status_code == 429:
        raise SearchProviderError(
            SearchFailureCode.RATE_LIMIT, "OpenAlex rate limit reached", retryable=True
        )
    if status_code >= 500:
        raise SearchProviderError(
            SearchFailureCode.TRANSIENT_OUTAGE,
            "OpenAlex service is temporarily unavailable",
            retryable=True,
        )
    raise SearchProviderError(SearchFailureCode.PERMANENT_FAILURE, "OpenAlex rejected the request")
