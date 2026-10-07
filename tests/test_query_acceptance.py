from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from test_discovery_store import _init_run

from providers.config import ExaConfig, OpenAlexConfig
from providers.exa import ExaSearchAdapter
from providers.openalex import OpenAlexSearchAdapter
from providers.search import SearchProviderError
from researchassistant.contracts.discovery_v2 import (
    V2ConceptGroup,
    V2ConceptualQuery,
    V2DiscoveryProviderBudget,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import ResearchDirection, ResearchDirections
from researchassistant.research.query_compiler import compile_query
from researchassistant.research.query_execution import execute_query, freeze_query_execution
from researchassistant.storage.discovery_store import provider_attempt_audit, read_discovery_binding

NOW = datetime(2026, 10, 6, tzinfo=UTC)
CLAIM = "The intervention changes the outcome."
DIRECTIONS = ResearchDirections(support_enabled=True, challenge_enabled=True)


def _clock() -> Callable[[], datetime]:
    tick = 0

    def now() -> datetime:
        nonlocal tick
        value = NOW + timedelta(seconds=tick)
        tick += 1
        return value

    return now


def _concept(
    run_id: UUID,
    provider: DiscoveryProvider,
    groups: tuple[V2ConceptGroup, ...],
    *,
    identity: str,
    direction: ResearchDirection = ResearchDirection.SUPPORT,
) -> V2ConceptualQuery:
    return V2ConceptualQuery(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2ConceptualQuery", identity),
        identity_key=identity,
        required_concepts=groups,
        purpose="broad",
        direction=direction,
        provider=provider,
        round_number=1,
    )


def test_alpr_crime_and_discrimination_remain_distinct_broad_lanes() -> None:
    run_id = uuid4()
    alpr = V2ConceptGroup(
        concept="automated license plate readers",
        synonyms=("ALPR", "license plate recognition"),
    )
    crime = compile_query(
        _concept(
            run_id,
            DiscoveryProvider.OPENALEX,
            (alpr, V2ConceptGroup(concept="crime investigation")),
            identity="alpr-crime",
        )
    )
    discrimination = compile_query(
        _concept(
            run_id,
            DiscoveryProvider.OPENALEX,
            (alpr, V2ConceptGroup(concept="racial discrimination", synonyms=("disparate impact",))),
            identity="alpr-discrimination",
        )
    )

    assert crime.conceptual_query.purpose == discrimination.conceptual_query.purpose == "broad"
    assert '"automated license plate readers"' in crime.query_text
    assert '"crime investigation"' in crime.query_text
    assert '"racial discrimination"' in discrimination.query_text
    assert '"disparate impact"' in discrimination.query_text
    assert crime.query_text != discrimination.query_text
    assert "AND" in crime.query_text and "AND" in discrimination.query_text


def test_biomedical_aliases_compile_to_pubmed_title_abstract_terms() -> None:
    query = compile_query(
        _concept(
            uuid4(),
            DiscoveryProvider.PUBMED,
            (
                V2ConceptGroup(
                    concept="maternal health", synonyms=("pregnancy care", "obstetric care")
                ),
                V2ConceptGroup(concept="hypertension"),
            ),
            identity="maternal-health",
        )
    )

    assert '"maternal health"[tiab]' in query.query_text
    assert '"pregnancy care"[tiab]' in query.query_text
    assert '"obstetric care"[tiab]' in query.query_text
    assert '"hypertension"[tiab]' in query.query_text
    assert " AND " in query.query_text
    assert query.parameters[0].name == "term"


def test_normative_nonacademic_concepts_stay_natural_for_exa_and_serp() -> None:
    run_id = uuid4()
    groups = (
        V2ConceptGroup(concept="school zoning policy", synonyms=("school attendance boundaries",)),
        V2ConceptGroup(concept="community debate", synonyms=("local public discussion",)),
    )
    exa = compile_query(_concept(run_id, DiscoveryProvider.EXA, groups, identity="zoning-exa"))
    serp = compile_query(
        _concept(run_id, DiscoveryProvider.SERPSEARCH, groups, identity="zoning-serp")
    )

    assert exa.parameters[0].value == exa.query_text
    assert "school zoning policy" in exa.query_text
    assert "school attendance boundaries" in exa.query_text
    assert "community debate" in exa.query_text
    assert all(token not in exa.query_text.lower() for token in ("site:", "intitle:", "filetype:"))
    assert '"school zoning policy"' in serp.query_text
    assert '"school attendance boundaries"' in serp.query_text
    assert '"community debate"' in serp.query_text
    assert all(token not in serp.query_text.lower() for token in ("site:", "intitle:", "filetype:"))


def test_tighter_openalex_budget_is_frozen_and_enforced_across_operations(tmp_path: Path) -> None:
    path = tmp_path / "tight-openalex.sqlite"
    run_id = uuid4()
    _init_run(path, run_id)
    configured = V2DiscoveryProviderBudget(
        provider=DiscoveryProvider.OPENALEX,
        max_requests=1,
        max_cost_usd=Decimal("0.001"),
        cost_policy_identity="query-openalex-lexical-2026-10-06-v2",
        reservation_per_request_usd=Decimal("0.001"),
        cost_basis="configured_upper_bound",
    )
    binding = freeze_query_execution(
        str(path),
        run_id,
        CLAIM,
        DIRECTIONS,
        (DiscoveryProvider.OPENALEX,),
        _clock(),
        provider_budgets=(configured,),
    )
    assert read_discovery_binding(str(path), run_id).provider_budgets == (configured,)
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(
            200,
            json={
                "meta": {"cost_usd": "0.001"},
                "results": [{"id": "https://openalex.org/W1", "title": "Policy study"}],
            },
        )

    adapter = OpenAlexSearchAdapter(
        OpenAlexConfig(api_key="test-secret"),
        client=httpx.Client(
            base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
        ),
    )
    providers = {DiscoveryProvider.OPENALEX: adapter}
    first = compile_query(
        _concept(
            run_id,
            DiscoveryProvider.OPENALEX,
            (V2ConceptGroup(concept="school zoning policy"),),
            identity="first-zoning-search",
        )
    )
    second = compile_query(
        _concept(
            run_id,
            DiscoveryProvider.OPENALEX,
            (V2ConceptGroup(concept="school attendance boundaries"),),
            identity="second-zoning-search",
        )
    )

    execute_query(
        path=str(path),
        run_id=run_id,
        provider=DiscoveryProvider.OPENALEX,
        query_text=first.query_text,
        compiled_query=first,
        providers=providers,
        clock=_clock(),
    )
    with pytest.raises(SearchProviderError, match="budget"):
        execute_query(
            path=str(path),
            run_id=run_id,
            provider=DiscoveryProvider.OPENALEX,
            query_text=second.query_text,
            compiled_query=second,
            providers=providers,
            clock=_clock(),
        )

    audit = provider_attempt_audit(str(path), run_id)
    assert len(sent) == 1
    assert len(audit.starts) == len(audit.completions) == 1
    assert audit.starts[0].reserved_cost_usd == configured.reservation_per_request_usd
    assert audit.completions[0].actual_cost_usd == Decimal("0.001")
    assert binding.provider_budgets[0].max_cost_usd == Decimal("0.001")


def test_exa_reported_cost_is_persisted_as_actual_cost(tmp_path: Path) -> None:
    path = tmp_path / "exa-cost.sqlite"
    run_id = uuid4()
    _init_run(path, run_id)
    freeze_query_execution(str(path), run_id, CLAIM, DIRECTIONS, (DiscoveryProvider.EXA,), _clock())
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "results": [{"url": "https://example.test/policy", "title": "Local policy debate"}],
                "costDollars": {"total": "0.0042"},
            },
        )

    adapter = ExaSearchAdapter(
        ExaConfig(api_key="test-secret"),
        client=httpx.Client(base_url="https://api.exa.ai", transport=httpx.MockTransport(handler)),
    )
    action = compile_query(
        _concept(
            run_id,
            DiscoveryProvider.EXA,
            (
                V2ConceptGroup(
                    concept="local housing policy", synonyms=("municipal housing rules",)
                ),
            ),
            identity="local-housing-exa",
        )
    )
    result = execute_query(
        path=str(path),
        run_id=run_id,
        provider=DiscoveryProvider.EXA,
        query_text=action.query_text,
        compiled_query=action,
        providers={DiscoveryProvider.EXA: adapter},
        clock=_clock(),
    )

    audit = provider_attempt_audit(str(path), run_id)
    assert len(result.results) == 1
    assert "local housing policy" in seen[0].read().decode()
    assert len(audit.starts) == len(audit.completions) == 1
    assert audit.completions[0].actual_cost_usd == Decimal("0.0042")
    assert audit.completions[0].cost_basis == "reported"
