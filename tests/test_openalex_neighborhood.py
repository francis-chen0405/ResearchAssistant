from __future__ import annotations

from collections.abc import Callable, Mapping

import httpx
import pytest
from pydantic import SecretStr

from providers.config import OpenAlexConfig
from providers.openalex import OpenAlexSearchAdapter
from providers.openalex_neighborhood import (
    NeighborhoodRelation,
    NeighborhoodStatus,
    OpenAlexNeighborhoodAdapter,
    ResolvedOpenAlexWork,
)
from providers.search import SearchFailureCode, SearchProviderError

API = "https://api.openalex.org"


def _config() -> OpenAlexConfig:
    return OpenAlexConfig(api_key=SecretStr("unused-test-secret"))


def _work(
    work_id: str = "W123",
    *,
    doi: str | None = "https://doi.org/10.1234/seed",
    refs: list[str] | None = None,
    related: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": f"https://openalex.org/{work_id}",
        "doi": doi,
        "title": "Seed study",
        "abstract_inverted_index": {"bounded": [0], "abstract": [1]},
        "publication_year": 2024,
        "type": "article",
        "authorships": [{"author": {"display_name": "A. Researcher"}}],
        "is_retracted": False,
        "referenced_works": refs or [],
        "related_works": related or [],
        "primary_location": {
            "landing_page_url": "https://publisher.example.org/paper",
            "pdf_url": "https://publisher.example.org/paper.pdf",
        },
        "best_oa_location": None,
        "locations": [],
    }


def _adapter(handler: Callable[[httpx.Request], httpx.Response]) -> OpenAlexNeighborhoodAdapter:
    client = httpx.Client(base_url=API, transport=httpx.MockTransport(handler))
    return OpenAlexNeighborhoodAdapter(_config(), client=client)


def _direct_requester(
    captured: list[tuple[Mapping[str, str | int | bool], httpx.Response]],
) -> Callable[[Mapping[str, str | int | bool], Callable[[], httpx.Response]], httpx.Response]:
    def request(
        parameters: Mapping[str, str | int | bool], send: Callable[[], httpx.Response]
    ) -> httpx.Response:
        response = send()
        captured.append((dict(parameters), response))
        return response

    return request


def test_resolve_verified_openalex_id_uses_one_accounted_official_request() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_work(), request=request)

    adapter = _adapter(handler)
    captured: list[tuple[Mapping[str, str | int | bool], httpx.Response]] = []
    result = adapter.resolve("W123", requester=_direct_requester(captured))

    assert result.status is NeighborhoodStatus.RESOLVED
    assert result.work is not None
    assert result.work.openalex_id == "https://openalex.org/W123"
    assert result.work.authors == ("A. Researcher",)
    assert result.work.is_withdrawn is None
    assert result.work.results[0].metadata.author == "A. Researcher"
    assert result.work.results[0].metadata.abstract == "bounded abstract"
    assert len(calls) == len(captured) == 1
    assert calls[0].url.host == "api.openalex.org"
    assert calls[0].url.params["api_key"] == "unused-test-secret"
    assert "api_key" not in captured[0][0]


def test_search_adapter_exposes_one_cached_neighborhood_adapter() -> None:
    client = httpx.Client(base_url=API, transport=httpx.MockTransport(lambda request: None))
    search = OpenAlexSearchAdapter(_config(), client=client)
    assert search.neighborhood_adapter is search.neighborhood_adapter
    assert isinstance(search.neighborhood_adapter, OpenAlexNeighborhoodAdapter)


def test_public_parsers_replay_response_without_transport() -> None:
    resolved = OpenAlexNeighborhoodAdapter.parse_resolution(
        "W123", httpx.Response(200, json=_work(refs=["W100"]))
    )
    assert resolved.status is NeighborhoodStatus.RESOLVED
    assert resolved.work is not None
    expanded = OpenAlexNeighborhoodAdapter.parse_expansion(
        resolved.work,
        NeighborhoodRelation.REFERENCES,
        1,
        httpx.Response(200, json={"results": [_work("W100")]}),
    )
    assert expanded.status is NeighborhoodStatus.RESOLVED
    assert expanded.results[0].metadata.external_id == "https://openalex.org/W100"


def test_resolve_doi_verifies_exact_doi_and_never_matches_by_title() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"results": [_work(doi="https://doi.org/10.1234/other")]},
            request=request,
        )

    result = _adapter(handler).resolve("doi:10.1234/seed", requester=lambda _params, send: send())
    assert result.status is NeighborhoodStatus.EMPTY
    assert len(seen) == 1
    assert seen[0].url.params["filter"] == "doi:https://doi.org/10.1234/seed"


def test_doi_normalization_preserves_legitimate_trailing_period() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"results": [_work(doi="https://doi.org/10.1234/seed.")]},
            request=request,
        )

    result = _adapter(handler).resolve("10.1234/seed.", requester=lambda _params, send: send())
    assert result.status is NeighborhoodStatus.RESOLVED
    assert seen[0].url.params["filter"] == "doi:https://doi.org/10.1234/seed."


@pytest.mark.parametrize(
    "identifier", ["Seed study", "W12?x=1", "10.1234/a#frag", "https://evil.example/W123"]
)
def test_unsupported_identifier_causes_no_request(identifier: str) -> None:
    adapter = _adapter(lambda request: pytest.fail(f"unexpected request: {request.url}"))
    result = adapter.resolve(identifier, requester=lambda _params, send: send())
    assert result.status is NeighborhoodStatus.UNSUPPORTED


def test_resolve_truncates_both_neighborhood_id_lists_at_ten() -> None:
    ids = [f"https://openalex.org/W{n}" for n in range(100, 115)]
    result = _adapter(
        lambda request: httpx.Response(200, json=_work(refs=ids, related=ids), request=request)
    ).resolve("W123", requester=lambda _params, send: send())
    assert result.work is not None
    assert len(result.work.referenced_work_ids) == 10
    assert len(result.work.related_work_ids) == 10


def test_search_results_drop_credential_bearing_location_urls() -> None:
    unsafe = _work()
    unsafe["primary_location"] = {"landing_page_url": "https://publisher.example/?token=secret"}
    result = _adapter(lambda request: httpx.Response(200, json=unsafe, request=request)).resolve(
        "W123", requester=lambda _params, send: send()
    )
    assert result.work is not None
    assert result.work.results[0].original_url == "https://doi.org/10.1234/seed"


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://127.0.0.1/paper",
        "http://[::1]/paper",
        "http://2130706433/paper",
        "http://0x7f000001/paper",
        "https://publisher.example/paper",
        "https://publisher.test/paper",
        "https://publisher.internal/paper",
    ],
)
def test_search_results_drop_non_public_or_reserved_location_hosts(unsafe_url: str) -> None:
    unsafe = _work()
    unsafe["primary_location"] = {"landing_page_url": unsafe_url}
    result = _adapter(lambda request: httpx.Response(200, json=unsafe, request=request)).resolve(
        "W123", requester=lambda _params, send: send()
    )
    assert result.work is not None
    assert result.work.results[0].original_url == "https://doi.org/10.1234/seed"


def test_neighborhood_send_uses_persistable_response_cap() -> None:
    from providers.openalex_neighborhood import MAX_NEIGHBOR_RESPONSE_BYTES

    assert MAX_NEIGHBOR_RESPONSE_BYTES == 262_144
    client = httpx.Client(
        base_url=API,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b" " * (MAX_NEIGHBOR_RESPONSE_BYTES + 1),
                request=request,
            )
        ),
    )
    with pytest.raises(SearchProviderError):
        OpenAlexNeighborhoodAdapter(_config(), client=client).resolve(
            "W123", requester=lambda _params, send: send()
        )


def test_expand_references_batches_at_most_ten_verified_ids_once() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [_work("W100")]}, request=request)

    seed = ResolvedOpenAlexWork.model_validate(
        {
            "openalex_id": "https://openalex.org/W123",
            "title": "Seed",
            "referenced_work_ids": tuple(f"W{i}" for i in range(100, 110)),
            "related_work_ids": (),
            "results": (),
        }
    )
    captured: list[tuple[Mapping[str, str | int | bool], httpx.Response]] = []
    result = _adapter(handler).expand(
        seed,
        NeighborhoodRelation.REFERENCES,
        requester=_direct_requester(captured),
    )
    assert result.status is NeighborhoodStatus.RESOLVED
    assert len(requests) == len(captured) == 1
    assert requests[0].url.params["per_page"] == "10"
    assert requests[0].url.params["filter"] == "openalex:" + "|".join(
        f"W{i}" for i in range(100, 110)
    )
    assert result.results[0].metadata.external_id == "https://openalex.org/W100"


def test_expand_related_uses_documented_related_ids_and_no_request_for_empty() -> None:
    seed = ResolvedOpenAlexWork.model_validate(
        {
            "openalex_id": "https://openalex.org/W123",
            "title": "Seed",
            "referenced_work_ids": (),
            "related_work_ids": ("W456",),
            "results": (),
        }
    )
    captured: list[tuple[Mapping[str, str | int | bool], httpx.Response]] = []
    adapter = _adapter(lambda request: httpx.Response(200, json={"results": []}, request=request))
    empty = adapter.expand(
        seed, NeighborhoodRelation.REFERENCES, requester=_direct_requester(captured)
    )
    assert empty.status is NeighborhoodStatus.EMPTY
    assert not captured
    related = adapter.expand(
        seed, NeighborhoodRelation.RELATED, requester=_direct_requester(captured)
    )
    assert related.status is NeighborhoodStatus.EMPTY
    assert len(captured) == 1
    assert captured[0][0]["filter"] == "openalex:W456"


def test_missing_related_ids_are_unsupported_not_empty() -> None:
    seed = ResolvedOpenAlexWork.model_validate(
        {
            "openalex_id": "https://openalex.org/W123",
            "title": "Seed",
            "referenced_work_ids": (),
            "results": (),
        }
    )
    result = _adapter(lambda request: pytest.fail("unexpected transport")).expand(
        seed, NeighborhoodRelation.RELATED, requester=lambda _params, send: send()
    )
    assert result.status is NeighborhoodStatus.UNSUPPORTED


def test_batch_response_cannot_introduce_unrequested_work() -> None:
    seed = ResolvedOpenAlexWork.model_validate(
        {
            "openalex_id": "https://openalex.org/W123",
            "title": "Seed",
            "referenced_work_ids": ("W456",),
            "related_work_ids": (),
            "results": (),
        }
    )
    result = _adapter(
        lambda request: httpx.Response(200, json={"results": [_work("W999")]}, request=request)
    ).expand(seed, NeighborhoodRelation.REFERENCES, requester=lambda _params, send: send())
    assert result.status is NeighborhoodStatus.MALFORMED


@pytest.mark.parametrize("relation", [NeighborhoodRelation.REFERENCES, NeighborhoodRelation.CITING])
def test_expansion_deduplicates_work_ids_at_first_provider_rank(
    relation: NeighborhoodRelation,
) -> None:
    first = _work("W456")
    duplicate = _work("W456")
    first["title"] = "First provider record"
    duplicate["title"] = "Later duplicate"
    if relation is NeighborhoodRelation.CITING:
        first["referenced_works"] = ["W123"]
        duplicate["referenced_works"] = ["W123"]
    seed = ResolvedOpenAlexWork.model_validate(
        {
            "openalex_id": "https://openalex.org/W123",
            "title": "Seed",
            "referenced_work_ids": ("W456",),
            "related_work_ids": (),
            "results": (),
        }
    )
    parsed = OpenAlexNeighborhoodAdapter.parse_expansion(
        seed,
        relation,
        10,
        httpx.Response(200, json={"results": [first, duplicate]}),
    )
    assert parsed.status is NeighborhoodStatus.RESOLVED
    assert len(parsed.results) == 1
    assert parsed.results[0].title == "First provider record"
    assert parsed.results[0].rank == 1


def test_expand_citing_uses_single_bounded_cites_filter_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json={"results": [_work("W444", refs=["W123"])]}, request=request
        )

    seed = ResolvedOpenAlexWork.model_validate(
        {
            "openalex_id": "https://openalex.org/W123",
            "title": "Seed",
            "referenced_work_ids": (),
            "related_work_ids": (),
            "results": (),
        }
    )
    result = _adapter(handler).expand(
        seed, NeighborhoodRelation.CITING, requester=lambda _params, send: send(), limit=3
    )
    assert result.status is NeighborhoodStatus.RESOLVED
    assert len(requests) == 1
    assert requests[0].url.params["filter"] == "cites:W123"
    assert requests[0].url.params["per_page"] == "3"


def test_citing_response_must_reference_the_seed() -> None:
    seed = ResolvedOpenAlexWork.model_validate(
        {
            "openalex_id": "https://openalex.org/W123",
            "title": "Seed",
            "referenced_work_ids": (),
            "related_work_ids": (),
            "results": (),
        }
    )
    result = _adapter(
        lambda request: httpx.Response(200, json={"results": [_work("W444")]}, request=request)
    ).expand(seed, NeighborhoodRelation.CITING, requester=lambda _params, send: send())
    assert result.status is NeighborhoodStatus.MALFORMED


def test_malformed_success_and_http_failures_have_typed_outcomes() -> None:
    malformed = _adapter(
        lambda request: httpx.Response(200, json={"unexpected": []}, request=request)
    )
    result = malformed.expand(
        ResolvedOpenAlexWork.model_validate(
            {
                "openalex_id": "https://openalex.org/W123",
                "title": "Seed",
                "referenced_work_ids": ("W456",),
                "related_work_ids": (),
                "results": (),
            }
        ),
        NeighborhoodRelation.REFERENCES,
        requester=lambda _params, send: send(),
    )
    assert result.status is NeighborhoodStatus.MALFORMED

    failed = _adapter(lambda request: httpx.Response(429, request=request))
    with pytest.raises(SearchProviderError) as error:
        failed.resolve("W123", requester=lambda _params, send: send())
    assert error.value.code is SearchFailureCode.RATE_LIMIT


def test_redirects_are_not_followed() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"Location": f"{API}/works/W999"}, request=request)

    with pytest.raises(SearchProviderError):
        _adapter(handler).resolve("W123", requester=lambda _params, send: send())
    assert len(requests) == 1
