"""Read-only live diagnostics remain tied to one immutable request snapshot."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from test_discovery_integration import _compiled_setup, _complete, _page
from test_seed_expansion_runtime import (
    RUN,
    _adapter,
    _binding,
    _clock,
    _identity,
    _install_round_one,
    _json_response,
    _manual_action,
    _openalex_work,
)

from frontend.discovery_diagnostics import enrich_discovery_diagnostics
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_evidence import (
    V2ProviderRunDiagnostics,
    V2RunDiagnostics,
)
from researchassistant.research.seed_expansion import execute_expansion
from researchassistant.storage.discovery_store import reserve_provider_attempt
from researchassistant.storage.store import open_read_only_store, read_snapshot_connection


def _base_diagnostics(provider: DiscoveryProvider) -> V2RunDiagnostics:
    outcome = V2ProviderRunDiagnostics(
        provider=provider,
        query_attempts=0,
        non_empty_queries=0,
        empty_queries=0,
        timeout_queries=0,
        failed_queries=0,
        search_results=0,
        surviving_sources=0,
    )
    return V2RunDiagnostics(
        configured_providers=(provider,),
        provider_outcomes=(outcome,),
    )


def test_discovery_counts_are_derived_read_only_and_unknown_values_stay_unknown(
    tmp_path: Path,
) -> None:
    legacy_shape = _base_diagnostics(DiscoveryProvider.OPENALEX).model_dump(mode="json")
    assert "logical_discovery_operations" not in legacy_shape
    assert "diagnostic_messages" not in legacy_shape

    path = tmp_path / "diagnostics.sqlite"
    operation = _compiled_setup(path)
    start = reserve_provider_attempt(str(path), _page(operation, 1, 1, 20))
    _complete(path, start)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    with open_read_only_store(path) as store:
        with read_snapshot_connection(store.connection):
            result = enrich_discovery_diagnostics(
                store.connection,
                operation.run_id,
                _base_diagnostics(DiscoveryProvider.OPENALEX),
            )

    assert result.logical_discovery_operations == 1
    assert result.physical_search_requests == 1
    assert result.retained_metadata_records is None
    assert result.deduplicated_work_candidates == 0
    assert result.seed_derived_candidates == 0
    assert result.shortlist_candidates is None
    assert result.diagnostic_messages == (
        "Citation graph expansion is unavailable with the selected provider capability.",
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_unselected_openalex_is_reported_as_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "provider-off.sqlite"
    operation = _compiled_setup(path, provider=DiscoveryProvider.EXA)

    with open_read_only_store(path) as store:
        with read_snapshot_connection(store.connection):
            result = enrich_discovery_diagnostics(
                store.connection,
                operation.run_id,
                _base_diagnostics(DiscoveryProvider.EXA),
            )

    assert result.diagnostic_messages == (
        "OpenAlex was not selected; citation graph expansion was unavailable.",
    )


def test_actual_fresh_query_fixture_reports_retained_records_and_requests(
    tmp_path: Path,
) -> None:
    import test_query_production as production
    import test_v2_phase12_production as phase12

    path = tmp_path / "production-diagnostics.sqlite"
    run_id = uuid4()
    result = production._run_fresh(
        path,
        model=production._ConceptModel(completed_rounds=4),
        search=phase12._Search(unique_results=True),
        scraper=phase12._Scraper(),
        run_id=run_id,
    )
    assert result.diagnostics is not None

    with open_read_only_store(path) as store:
        with read_snapshot_connection(store.connection):
            enriched = enrich_discovery_diagnostics(store.connection, run_id, result.diagnostics)

    assert enriched.logical_discovery_operations > 0
    assert enriched.physical_search_requests > 0
    assert enriched.retained_metadata_records is not None
    assert enriched.retained_metadata_records > 0
    assert enriched.deduplicated_work_candidates > 0


@pytest.mark.parametrize("rejected_kind", ("self_cycle", "doi_alias", "retracted", "only_self"))
def test_seed_candidate_counts_exclude_rejected_raw_hits(
    tmp_path: Path, rejected_kind: str
) -> None:
    path = tmp_path / "graph-diagnostics.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    action = _manual_action(path)
    rejected = _openalex_work("W1", doi=None, title="Seed study")
    if rejected_kind == "doi_alias":
        rejected = _openalex_work("W3", doi="10.5555/neighbor", title="Neighbor mirror")
    elif rejected_kind == "retracted":
        rejected = _openalex_work("W3", doi="10.5555/retracted", title="Retracted study")
        rejected["is_retracted"] = True
    records = [rejected]
    expected = 0 if rejected_kind == "only_self" else 1
    if expected:
        records.insert(0, _openalex_work("W2", doi="10.5555/neighbor", title="Neighbor"))
    refs = tuple(record["id"].rsplit("/", 1)[-1] for record in records)

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            request,
            _identity(action.seed, refs=refs)
            if request.url.path.endswith("/W1")
            else {"results": records},
        )

    adapter, client = _adapter(handler)
    try:
        results = execute_expansion(path=str(path), action=action, adapter=adapter, clock=_clock)
    finally:
        client.close()
    assert len(results) == expected
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    for _ in range(2):
        with open_read_only_store(path) as store:
            with read_snapshot_connection(store.connection):
                diagnostics = enrich_discovery_diagnostics(
                    store.connection, RUN, _base_diagnostics(DiscoveryProvider.OPENALEX)
                )
        assert diagnostics.seed_derived_candidates == expected
        assert diagnostics.retained_metadata_records == len(records)
        assert diagnostics.physical_search_requests == 2
    assert path.read_bytes() == before and path.stat().st_mtime_ns == mtime


def test_seed_counts_keep_accepted_identity_when_rejected_hit_gains_doi(tmp_path: Path) -> None:
    path = tmp_path / "graph-alias-diagnostics.sqlite"
    _binding(path)
    _install_round_one(path, ({"score": 85},))
    first = _manual_action(path)
    second = _manual_action(path, relationship="related")
    responses = [
        _identity(first.seed, refs=("W2",), related=("W2",)),
        {"results": [_openalex_work("W2", doi=None, title="Neighbor")]},
        {"results": [_openalex_work("W2", doi="10.5555/late", title="Neighbor")]},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(request, responses.pop(0))

    adapter, client = _adapter(handler)
    try:
        assert (
            len(execute_expansion(path=str(path), action=first, adapter=adapter, clock=_clock)) == 1
        )
        assert execute_expansion(path=str(path), action=second, adapter=adapter, clock=_clock) == ()
    finally:
        client.close()
    with open_read_only_store(path) as store:
        with read_snapshot_connection(store.connection):
            diagnostics = enrich_discovery_diagnostics(
                store.connection, RUN, _base_diagnostics(DiscoveryProvider.OPENALEX)
            )
    assert diagnostics.seed_derived_candidates == 1
    assert diagnostics.retained_metadata_records == 2
    assert diagnostics.physical_search_requests == 3
