"""Review regressions for graph trust and aggregate runtime ceilings."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from test_seed_expansion_runtime import (
    NOW,
    RUN,
    _adapter,
    _binding,
    _clock,
    _identity,
    _install_gap_analysis,
    _install_round_one,
    _json_response,
    _manual_action,
    _openalex_work,
)

from researchassistant.contracts.discovery_v2 import (
    V2CandidateDisposition,
    V2ExpansionEdge,
    V2ExpansionResult,
    V2GraphNeighborAction,
    V2RawDiscoveryCandidate,
    V2SeedEligibility,
    discovery_id,
)
from researchassistant.contracts.model_research import (
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
)
from researchassistant.research.seed_expansion import (
    execute_expansion,
    pipeline_work_identity,
    select_seeds,
)
from researchassistant.storage.discovery_store import (
    insert_expansion_result,
    insert_pipeline_seed,
    insert_raw_candidate,
    provider_attempt_audit,
    read_discovery_artifacts,
)
from researchassistant.storage.store import read_v2_artifact


@pytest.mark.parametrize("alias_kind", ("provider_id", "doi"))
def test_seed_aliases_leave_capacity_for_distinct_papers(tmp_path: Path, alias_kind: str) -> None:
    path = tmp_path / "seed-aliases.sqlite"
    _binding(path)
    alias = {"doi": None} if alias_kind == "provider_id" else {"external_id": None}
    _install_round_one(
        path,
        (
            {**alias, "score": 95},
            {"score": 90},
            {"doi": "10.5555/second", "external_id": "W2", "score": 85},
            {"doi": "10.5555/third", "external_id": "W3", "score": 80},
        ),
    )
    selection = select_seeds(str(path), RUN, 1, _clock)
    assert len(selection.seeds) == 3
    assert [seed.work.doi for seed in selection.seeds[1:]] == [
        "10.5555/second",
        "10.5555/third",
    ]
    assert select_seeds(str(path), RUN, 1, _clock) == selection
    # A different owned candidate for the same work cannot bypass selection.
    discovery = V2DiscoveryScoutOutput.model_validate_json(
        read_v2_artifact(str(path), RUN, "phase-4-discovery-scout").payload_json
    )
    acquisition = V2AcquisitionProbeOutput.model_validate_json(
        read_v2_artifact(str(path), RUN, "phase-5-acquisition-probe").payload_json
    )
    candidate = discovery.items[1]
    survivor = acquisition.survivors[1]
    key = f"seed/{candidate.item_id}"
    duplicate = selection.seeds[0].model_copy(
        update={
            "artifact_id": discovery_id(RUN, "V2SeedEligibility", key),
            "identity_key": key,
            "candidate_id": candidate.item_id,
            "source_id": survivor.cluster_id,
            "snapshot_id": survivor.snapshot_id,
            "work": pipeline_work_identity(candidate),
        }
    )
    with pytest.raises(ValueError, match="known work alias"):
        insert_pipeline_seed(
            str(path), duplicate, "phase-4-discovery-scout", "phase-5-acquisition-probe", NOW
        )
    # The existing seed itself remains an idempotent write.
    assert (
        insert_pipeline_seed(
            str(path),
            selection.seeds[0],
            "phase-4-discovery-scout",
            "phase-5-acquisition-probe",
            NOW,
        )
        == selection.seeds[0]
    )


def test_doi_only_seed_resolution_prevents_self_cycle_and_replay(tmp_path: Path) -> None:
    path = tmp_path / "resolved-cycle.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85, "external_id": None},))
    action = _manual_action(path)
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        return _json_response(
            request,
            {"results": [_identity(action.seed, refs=("W1",))]}
            if request.url.params["filter"].startswith("doi:")
            else {"results": [_openalex_work("W1", doi=None, title="Seed study")]},
        )

    adapter, client = _adapter(handler)
    try:
        assert execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock) == ()
        assert execute_expansion(path=str(path), action=action, adapter=None, clock=_clock) == ()
    finally:
        client.close()
    assert len(sends) == 2
    artifacts = read_discovery_artifacts(str(path), RUN)
    raw = next(item for item in artifacts if isinstance(item, V2RawDiscoveryCandidate))
    assert any(
        isinstance(item, V2CandidateDisposition)
        and item.candidate_id == raw.artifact_id
        and item.disposition == "duplicate"
        for item in artifacts
    )
    result = next(item for item in artifacts if isinstance(item, V2ExpansionResult))
    key = f"edge/{raw.artifact_id}"
    edge = V2ExpansionEdge(
        run_id=RUN,
        artifact_id=discovery_id(RUN, "V2ExpansionEdge", key),
        identity_key=key,
        action=action,
        candidate=raw,
        edge_verification="provider_reported",
    )
    # Even an exact owned response cannot admit the resolved seed as a neighbor.
    with pytest.raises(ValueError, match="visited provider work or DOI alias"):
        insert_expansion_result(str(path), result.model_copy(update={"edges": (edge,)}), NOW)


@pytest.mark.parametrize(
    ("observed", "resolved", "accepted"),
    (
        (("A. Researcher",), ("A. Researcher", "B. Researcher"), True),
        (("A. Researcher", "B. Researcher"), ("A. Researcher",), True),
        (("A. Researcher",), ("Different Author",), False),
        (("A. Researcher", "B. Researcher"), ("A. Researcher", "Different Author"), False),
    ),
)
def test_partial_author_lists_are_compatible_but_conflicts_are_not(
    tmp_path: Path, observed: tuple[str, ...], resolved: tuple[str, ...], accepted: bool
) -> None:
    path = tmp_path / "authors.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85, "authors": observed},))
    action = _manual_action(path)
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        if request.url.path.endswith("/W1"):
            body = _identity(action.seed)
            body["authorships"] = [{"author": {"display_name": name}} for name in resolved]
            return _json_response(request, body)
        return _json_response(
            request, {"results": [_openalex_work("W2", doi="10.5555/neighbor", title="Neighbor")]}
        )

    adapter, client = _adapter(handler)
    try:
        results = execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock)
        assert bool(results) is accepted
        assert (
            execute_expansion(path=str(path), action=action, adapter=None, clock=_clock) == results
        )
    finally:
        client.close()
    assert len(sends) == (2 if accepted else 1)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("id", "https://openalex.org/W999"),
        ("doi", "https://doi.org/10.5555/other"),
        ("title", "An unrelated paper"),
        ("publication_year", 2020),
    ),
)
def test_partial_authors_do_not_waive_exact_seed_identity_conflicts(
    tmp_path: Path, field: str, value: Any
) -> None:
    path = tmp_path / "identity-conflict.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    action = _manual_action(path)
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        body = _identity(action.seed)
        body["authorships"].append({"author": {"display_name": "B. Researcher"}})
        body[field] = value
        return _json_response(request, body)

    adapter, client = _adapter(handler)
    try:
        assert execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock) == ()
    finally:
        client.close()
    assert len(sends) == 1


def test_three_seeds_ten_neighbors_each_and_thirty_run_bound(tmp_path: Path) -> None:
    path = tmp_path / "aggregate.sqlite"
    _binding(path)
    _install_round_one(
        path,
        tuple(
            {
                "doi": f"10.5555/seed-{index}",
                "external_id": f"https://openalex.org/W{index}",
                "title": f"Seed study {index}",
                "score": 90 - index,
            }
            for index in range(1, 5)
        ),
    )
    seeds = select_seeds(str(path), RUN, 1, _clock).seeds
    assert len(seeds) == 3
    base = _manual_action(path)
    sends: list[httpx.Request] = []
    for index, seed in enumerate(seeds):
        round_number = 2 if index < 2 else 3
        if round_number == 3:
            _install_gap_analysis(path, 2)
        key = f"review-seed-{index}"
        action = V2GraphNeighborAction.model_validate(
            base.model_copy(
                update={
                    "identity_key": key,
                    "artifact_id": discovery_id(RUN, "V2GraphNeighborAction", key),
                    "seed": seed,
                    "round_number": round_number,
                    "requested_depth": 10,
                }
            ).model_dump()
        )
        ids = tuple(f"W{100 + index * 20 + value}" for value in range(15))

        def handler(
            request: httpx.Request,
            seed: V2SeedEligibility = seed,
            ids: tuple[str, ...] = ids,
        ) -> httpx.Response:
            sends.append(request)
            if request.url.path.endswith(seed.work.provider_work_id.rsplit("/", 1)[-1]):
                return _json_response(request, _identity(seed, refs=ids))
            assert request.url.params["per_page"] == "10"
            filtered = request.url.params["filter"].split(":", 1)[1].split("|")
            assert len(filtered) == 10
            return _json_response(
                request,
                {
                    "results": [
                        _openalex_work(wid, doi=f"10.5555/{wid}", title=f"Work {wid}")
                        for wid in filtered
                    ]
                },
            )

        adapter, client = _adapter(handler)
        try:
            results = execute_expansion(
                path=str(path), action=action, adapter=adapter, clock=_clock
            )
            assert len(results) == 10
            assert (
                execute_expansion(path=str(path), action=action, adapter=None, clock=_clock)
                == results
            )
        finally:
            client.close()
    assert len(sends) == 6
    audit = provider_attempt_audit(str(path), RUN)
    assert len(audit.starts) == 6
    assert sum(attempt.reserved_cost_usd for attempt in audit.starts) == Decimal("0.006")
    expansions = [
        item
        for item in read_discovery_artifacts(str(path), RUN)
        if isinstance(item, V2ExpansionResult)
    ]
    assert (
        len({edge.candidate.work.grouping_key for item in expansions for edge in item.edges}) == 30
    )


def test_raw_neighbor_metadata_cannot_be_forged_with_owned_response_hash(tmp_path: Path) -> None:
    path = tmp_path / "raw-forgery.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    action = _manual_action(path)

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            request,
            _identity(action.seed)
            if request.url.path.endswith("/W1")
            else {"results": [_openalex_work("W2", doi="10.5555/neighbor", title="Actual title")]},
        )

    adapter, client = _adapter(handler)
    try:
        assert execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock)
    finally:
        client.close()
    result = next(
        item
        for item in read_discovery_artifacts(str(path), RUN)
        if isinstance(item, V2ExpansionResult)
    )
    raw = result.edges[0].candidate
    forged = raw.model_copy(update={"work": raw.work.model_copy(update={"title": "Forged title"})})
    with pytest.raises(ValueError, match="exact provider response"):
        insert_raw_candidate(str(path), forged, NOW)


def test_rehashed_exact_response_must_still_match_physical_completion(tmp_path: Path) -> None:
    import json
    import sqlite3
    from hashlib import sha256

    from researchassistant.contracts.neighborhood import V2NeighborhoodResponse
    from researchassistant.storage.store import canonical_v2_artifact_json, v2_payload_fingerprint

    path = tmp_path / "response-forgery.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    action = _manual_action(path)

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            request,
            _identity(action.seed)
            if request.url.path.endswith("/W1")
            else {"results": [_openalex_work("W2", doi="10.5555/neighbor", title="Actual title")]},
        )

    adapter, client = _adapter(handler)
    try:
        assert execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock)
    finally:
        client.close()
    responses = [
        item
        for item in read_discovery_artifacts(str(path), RUN)
        if isinstance(item, V2NeighborhoodResponse)
    ]
    original = next(item for item in responses if '"results"' in item.content)
    content = json.dumps({**json.loads(original.content), "fixture_altered": True})
    forged = original.model_copy(
        update={"content": content, "response_hash": sha256(content.encode()).hexdigest()}
    )
    payload = canonical_v2_artifact_json(forged)
    # Simulate a checksum-valid rewrite in this disposable database; production
    # immutability stays intact, and the real physical completion remains untouched.
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER v2_artifacts_immutable_update")
        connection.execute(
            "UPDATE v2_artifacts SET payload_json = ?, payload_sha256 = ? "
            "WHERE run_id = ? AND artifact_key = ?",
            (
                payload,
                v2_payload_fingerprint(payload),
                str(RUN),
                f"source-discovery-v1:V2NeighborhoodResponse:{original.identity_key}",
            ),
        )
    with pytest.raises(ValueError, match="Exact provider body differs"):
        execute_expansion(path=str(path), action=action, adapter=None, clock=_clock)


def test_prior_provider_work_id_stays_visited_when_doi_metadata_appears(tmp_path: Path) -> None:
    path = tmp_path / "late-doi-alias.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    first = _manual_action(path)
    second = _manual_action(path, relationship="related")
    responses = [
        _identity(first.seed, refs=("W2",), related=("W2",)),
        {"results": [_openalex_work("W2", doi=None, title="Same work")]},
        {"results": [_openalex_work("W2", doi="10.5555/late-doi", title="Same work")]},
    ]
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        return _json_response(request, responses.pop(0))

    adapter, client = _adapter(handler)
    try:
        assert (
            len(execute_expansion(path=str(path), action=first, adapter=adapter, clock=_clock)) == 1
        )
        assert execute_expansion(path=str(path), action=second, adapter=adapter, clock=_clock) == ()
    finally:
        client.close()
    assert len(sends) == 3  # Shared seed identity was not fetched again.


def test_known_failed_seed_resolution_is_not_offered_as_another_relationship(
    tmp_path: Path,
) -> None:
    from test_seed_expansion_runtime import _lane

    from researchassistant.research.query_execution import available_query_budgets
    from researchassistant.research.seed_expansion import offer_expansions

    path = tmp_path / "failed-seed.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    action = _manual_action(path)
    sends: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request)
        return _json_response(
            request, {"error": "rate limit", "meta": {"cost_usd": "0.001"}}, status=429
        )

    adapter, client = _adapter(handler)
    try:
        assert execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock) == ()
    finally:
        client.close()
    _install_gap_analysis(path, 2)
    assert available_query_budgets(str(path), RUN)[0].remaining_calls == 9
    assert offer_expansions(str(path), RUN, 3, (_lane(),), _clock) == ()
    assert len(sends) == 1
