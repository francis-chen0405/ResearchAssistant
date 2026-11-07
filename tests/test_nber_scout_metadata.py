from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from html import escape
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn
from uuid import uuid4

import httpx
import pytest
from test_v2_ranked_scout import NOW, _RecallScout, _routing, _snapshot

from researchassistant.agents import v2_discovery
from researchassistant.agents.discovery_overlap import (
    DiscoveryResponses,
    FirstPass,
    scout_during_search,
)
from researchassistant.agents.v2_discovery import (
    ScoutHandoff,
    V2DiscoveryResponse,
    V2DiscoveryScoutRunResult,
)
from researchassistant.contracts.discovery_v2 import V2MetadataDiscoveryPolicy
from researchassistant.contracts.metadata_ranking import MetadataRank
from researchassistant.contracts.models import (
    CrossrefIdentityMetadata,
    DiscoveryProvider,
    NormalizedDiscoveryItem,
    ResearchDirection,
    ResearchDirections,
    RunManifest,
    RunStatus,
    ScoutBatch,
    Stage,
    StrictModel,
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchQuery,
    V2DiscoveryScoutOutput,
    V2InitialPlannerOutput,
    V2PipelineIdentity,
    V2RoundOneSearchQuery,
)
from researchassistant.contracts.research_discovery import ScoutDecision
from researchassistant.contracts.search import SearchDiscoveryMetadata, SearchResult
from researchassistant.providers.llm import LLMRequest
from researchassistant.providers.nber_metadata import (
    NberPaperMetadata,
    nber_paper_number,
    resolve_nber_metadata,
)
from researchassistant.storage.store import init_db, insert_run, insert_v2_pipeline_identity

Query = V2RoundOneSearchQuery | V2AdaptiveSearchQuery

PAPERS = {
    "31625": (
        "August 2023, Revised September 2025",
        "https://www.nber.org/system/files/working_papers/w31625/w31625.pdf",
        "Supporting Women’s Livelihoods at Scale: Evidence from a Nationwide Multi-Faceted Program",
        "Zambia’s nationwide program produced sustained gains in consumption and earnings.",
    ),
    "33322": (
        "Working Paper 33322",
        "https://www.nber.org/system/files/working_papers/w33322/w33322.pdf",
        "Community Targeting at Scale",
        "Two Indonesian scale-ups tested community targeting of assistance to poor households.",
    ),
}
CLAIM = "Nationwide livelihood programs produce sustained gains in consumption and earnings."


def _record(number: str, *, handle: str | None = None) -> httpx.Response:
    _, _, title, abstract = PAPERS[number]
    return httpx.Response(
        200,
        text=(
            f'<meta name="handle" content="RePEc:nbr:nberwo:{handle or number}">'
            f'<meta name="citation_title" content="{escape(title)}">'
            f'<meta name="citation_abstract" content="{escape(abstract)}">'
        ),
    )


@pytest.fixture
def discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    run_id = uuid4()
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    query = V2RoundOneSearchQuery(
        run_id=run_id,
        query_id=uuid4(),
        provider=DiscoveryProvider.EXA,
        direction=ResearchDirection.SUPPORT,
        strategy="direct_evidence",
        query_text="poverty programs at scale",
        created_at=NOW,
    )
    plan = V2InitialPlannerOutput(
        run_id=run_id,
        raw_claim=CLAIM,
        directions=directions,
        discovery_providers=(query.provider,),
        searches=(query,)
        + tuple(
            query.model_copy(
                update={"query_id": uuid4(), "strategy": strategy, "query_text": strategy}
            )
            for strategy in ("mechanism", "analysis")
        ),
        planner_prompt_version="test-v2",
        planned_at=NOW,
    )
    path = str(tmp_path / "scout.sqlite")
    init_db(path)
    insert_run(
        path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.PLANNED,
            raw_claim=CLAIM,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(path, run_id, V2PipelineIdentity(), NOW)
    binding = SimpleNamespace(
        exact_claim=CLAIM,
        policy=V2MetadataDiscoveryPolicy(),
        ranking_identity=v2_discovery.RANKING_IDENTITY,
    )
    monkeypatch.setattr(v2_discovery, "_fresh_ranked_binding", lambda *_: binding)
    ranked = []
    rank_metadata = v2_discovery.rank_metadata

    def rank(items: tuple[NormalizedDiscoveryItem, ...], **kwargs: Any) -> tuple[MetadataRank, ...]:
        ranked.extend(items)
        return rank_metadata(items, **kwargs)

    monkeypatch.setattr(v2_discovery, "rank_metadata", rank)
    scout = _RecallScout()

    def run(
        responses: DiscoveryResponses,
        *,
        planner: V2InitialPlannerOutput | V2AdaptiveRoundPlan = plan,
        **kwargs: Any,
    ) -> V2DiscoveryScoutRunResult:
        return v2_discovery.run_v2_discovery_and_scout(
            db_path=path,
            planner_output=planner,
            responses=responses,
            llm_provider=scout,
            routing_config=_routing(),
            clock=lambda: NOW,
            budget_snapshot=lambda: _snapshot(100),
            **kwargs,
        )

    return SimpleNamespace(
        run=run,
        query=query,
        plan=plan,
        scout=scout,
        ranked=ranked,
    )


def _response(query: Query, *numbers: str) -> V2DiscoveryResponse:
    return V2DiscoveryResponse(
        query=query,
        results=tuple(
            SearchResult(
                original_url=PAPERS[number][1],
                title=PAPERS[number][0],
                rank=rank,
                metadata=SearchDiscoveryMetadata(engine="exa"),
            )
            for rank, number in enumerate(numbers, start=1)
        ),
    )


def _lookup(
    monkeypatch: pytest.MonkeyPatch, respond: Callable[[str], httpx.Response] = _record
) -> list[str]:
    calls = []

    def send(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "econpapers.repec.org"
        number = request.url.path.removeprefix("/paper/nbrnberwo/").removesuffix(".htm")
        calls.append(number)
        return respond(number)

    def resolve(number: str) -> NberPaperMetadata | None:
        with httpx.Client(transport=httpx.MockTransport(send)) as client:
            return resolve_nber_metadata(number, client=client)

    monkeypatch.setattr(v2_discovery, "resolve_nber_metadata", resolve)
    return calls


def _assert_metadata(
    discovery: SimpleNamespace, output: V2DiscoveryScoutOutput, number: str, query: Query
) -> None:
    _, url, title, abstract = PAPERS[number]
    item = next(item for item in output.items if item.source_url == url)
    assert (item.title, item.abstract) == (title, abstract)
    assert item in discovery.ranked
    assert item.provider == query.provider
    assert item.direction == query.direction
    assert item.query_id == query.query_id
    assert item.provenance_chain[0].original_url == url
    assert item.provenance_chain[0].query_text == query.query_text
    repair = next(entry for entry in item.provider_metadata if entry.key == "nber_metadata_repair")
    assert json.loads(repair.value_json) == {
        "handle": f"RePEc:nbr:nberwo:{number}",
        "source_url": f"https://econpapers.repec.org/paper/nbrnberwo/{number}.htm",
    }
    candidates = [
        candidate
        for request in discovery.scout.requests
        for candidate in request.input_artifact.candidates
        if candidate.item_id == item.item_id
    ]
    assert [(c.title, c.abstract, c.source_url) for c in candidates] == [(title, abstract, url)]
    assert all(request.input_artifact.exact_claim == CLAIM for request in discovery.scout.requests)


def test_initial_progressive_handoff_repairs_before_ranking_and_scout(
    discovery: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _lookup(monkeypatch)
    first = _response(discovery.query, "31625")
    full = _response(discovery.query, "31625", "33322", "31625")
    handoffs = []
    generate = discovery.scout.generate

    def decide(request: LLMRequest) -> ScoutBatch:
        batch = generate(request)
        if request.input_artifact.exact_claim != CLAIM:
            return batch
        return batch.model_copy(
            update={
                "items": tuple(
                    item.model_copy(update={"decision": ScoutDecision.RETRIEVE})
                    if "sustained gains" in (candidate.abstract or "")
                    else item
                    for item, candidate in zip(
                        batch.items, request.input_artifact.candidates, strict=True
                    )
                )
            }
        )

    monkeypatch.setattr(discovery.scout, "generate", decide)

    def execute(publish: FirstPass | None, cancelled: Callable[[], bool]) -> DiscoveryResponses:
        assert publish is not None and not cancelled()
        publish((first,))
        return (full,)

    def scout(
        responses: DiscoveryResponses,
        on_batch: ScoutHandoff | None,
        cancelled: Callable[[], bool],
        first_pass_only: bool,
        first_pass: V2DiscoveryScoutRunResult | None,
    ) -> V2DiscoveryScoutRunResult:
        return discovery.run(
            responses,
            on_batch=on_batch,
            cancellation_requested=cancelled,
            first_pass_only=first_pass_only,
            first_pass=first_pass,
        )

    _, result = scout_during_search(
        execute=execute,
        responses=lambda result: result,
        scout=scout,
        on_batch=lambda output, *_: handoffs.append(output),
        cancelled=lambda: False,
        progressive=True,
    )

    assert calls == ["31625", "33322"]
    assert handoffs[0].items[0].title == PAPERS["31625"][2]
    _assert_metadata(discovery, result.output, "31625", discovery.query)
    _assert_metadata(discovery, result.output, "33322", discovery.query)
    assert [item.title for item in result.output.items].count(PAPERS["31625"][2]) == 2
    decisions = {
        decision.item_id: decision.decision
        for batch in result.output.scout_batches
        for decision in batch.items
    }
    assert {
        item.title: decisions[item.item_id]
        for item in result.output.items
        if item.item_id in decisions
    } == {PAPERS["31625"][2]: "retrieve", PAPERS["33322"][2]: "maybe"}


def test_adaptive_round_repairs_before_scout(
    discovery: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _lookup(monkeypatch)
    discovery.run((_response(discovery.query, "31625"),))
    query = V2AdaptiveSearchQuery(
        run_id=discovery.plan.run_id,
        query_id=uuid4(),
        provider=discovery.query.provider,
        direction=discovery.query.direction,
        round_number=2,
        strategy="targeted_search",
        targeted_gap_ids=("targeting",),
        query_text="community targeting of poor households",
        created_at=NOW,
    )
    plan = V2AdaptiveRoundPlan(
        run_id=query.run_id,
        round_number=2,
        directions=discovery.plan.directions,
        enabled_providers=(query.provider,),
        targeted_gap_ids=query.targeted_gap_ids,
        discovered_terms=(),
        searches=(query,),
        search_agent_prompt_version="test-v2",
        planned_at=NOW,
    )
    result = discovery.run(
        (_response(query, "33322"),), planner=plan, target_gaps=(query.query_text,)
    )
    _assert_metadata(discovery, result.output, "33322", query)
    assert discovery.scout.requests[-1].input_artifact.target_gaps == (query.query_text,)
    assert calls == ["31625", "33322"]


@pytest.mark.parametrize("failure", ["mismatch", "timeout", "denied", "missing"])
def test_failed_repair_and_ineligible_results_still_reach_scout(
    discovery: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    def respond(number: str) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("fixture timeout")
        if failure == "mismatch":
            return _record(number, handle="31625")
        return httpx.Response(403 if failure == "denied" else 404)

    calls = _lookup(monkeypatch, respond)
    response = _response(discovery.query, "33322", "31625", "31625", "33322")
    eligible, valid, foreign, duplicate = response.results
    valid = valid.model_copy(update={"title": "A valid study title"})
    foreign = foreign.model_copy(
        update={"original_url": "https://nber.org.example/papers/w31625.pdf"}
    )
    response = response.model_copy(update={"results": (eligible, valid, foreign, duplicate)})
    result = discovery.run((response,))
    assert calls == ["33322"]
    assert [item.title for item in result.output.items] == [item.title for item in response.results]
    assert all(item.abstract is None for item in result.output.items)
    assert {
        c.title for request in discovery.scout.requests for c in request.input_artifact.candidates
    } == {item.title for item in response.results}


def test_failed_nber_lookup_preserves_doi_recovery(
    discovery: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _lookup(monkeypatch, lambda _: httpx.Response(404))
    response = _response(discovery.query, "31625")
    (original,) = response.results
    doi = "10.3386/w31625"
    candidate = original.model_copy(
        update={"metadata": original.metadata.model_copy(update={"doi": doi})}
    )
    crossref_calls = []

    def resolve_crossref(requested_doi: str) -> CrossrefIdentityMetadata:
        crossref_calls.append(requested_doi)
        return CrossrefIdentityMetadata(
            doi=requested_doi, canonical_title=PAPERS["31625"][2], verified=True
        )

    result = discovery.run(
        (response.model_copy(update={"results": (candidate,)}),),
        crossref_resolver=resolve_crossref,
    )
    assert calls == ["31625"]
    assert crossref_calls == [doi]
    (item,) = result.output.items
    assert item.crossref is not None and item.crossref.verified
    assert item.title == discovery.ranked[0].title == PAPERS["31625"][2]
    (scout_candidate,) = discovery.scout.requests[0].input_artifact.candidates
    assert scout_candidate.title == item.title


@pytest.mark.parametrize("interrupt_at", ["rank_metadata", "_run_scout_batches"])
def test_resume_reuses_outcome_and_preserves_bound_inputs(
    discovery: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, interrupt_at: str
) -> None:
    calls = _lookup(monkeypatch)
    response = _response(discovery.query, "31625")
    original = getattr(v2_discovery, interrupt_at)

    def interrupted(*args: object, **kwargs: object) -> NoReturn:
        raise RuntimeError("interrupted")

    monkeypatch.setattr(v2_discovery, interrupt_at, interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        discovery.run((response,))
    monkeypatch.setattr(v2_discovery, interrupt_at, original)
    result = discovery.run((response,))
    assert calls == ["31625"]
    _assert_metadata(discovery, result.output, "31625", discovery.query)
    assert discovery.run((response,)).resumed
    assert len(discovery.scout.requests) == 1


def test_historical_completed_round_loads_without_repair(
    discovery: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _lookup(monkeypatch)
    response = _response(discovery.query, "31625")
    with monkeypatch.context() as previous_version:
        previous_version.setattr(v2_discovery, "nber_paper_number", lambda _: None)
        historical = discovery.run((response,))
    loaded = discovery.run((response,))
    assert loaded.resumed and loaded.output == historical.output
    assert loaded.output.items[0].title == PAPERS["31625"][0]
    assert calls == []


@pytest.mark.parametrize("title", ["", "   "])
def test_blank_title_repair_preserves_discovery_abstract(
    discovery: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, title: str
) -> None:
    calls = _lookup(monkeypatch)
    response = _response(discovery.query, "31625")
    original = response.results[0]
    metadata = original.metadata.model_copy(update={"abstract": "Discovery abstract"})
    result = original.model_copy(update={"title": title, "metadata": metadata})
    output = discovery.run((response.model_copy(update={"results": (result,)}),)).output
    assert calls == ["31625"]
    assert output.items[0].title == PAPERS["31625"][2]
    assert output.items[0].abstract == "Discovery abstract"


def test_interrupted_lookup_is_not_dispatched_again(
    discovery: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(number: str) -> NoReturn:
        raise RuntimeError("process stopped during lookup")

    monkeypatch.setattr(v2_discovery, "resolve_nber_metadata", interrupted)
    response = _response(discovery.query, "31625")
    with pytest.raises(RuntimeError, match="process stopped"):
        discovery.run((response,))
    calls = _lookup(monkeypatch)
    output = discovery.run((response,)).output
    assert calls == []
    assert output.items[0].title == PAPERS["31625"][0]


@pytest.mark.parametrize(
    ("url", "number"),
    [
        ("https://www.nber.org/papers/w33322.pdf?tracking=1", "33322"),
        ("http://nber.org/papers/w33322", "33322"),
        ("https://www.nber.org/system/files/working_papers/w31625/w33322.pdf", None),
        ("https://www.nber.org@other.example/papers/w33322.pdf", None),
    ],
)
def test_exact_nber_pdf_identity(url: str, number: str | None) -> None:
    assert nber_paper_number(url) == number


def test_historical_ranking_only_checkpoint_keeps_original_inputs(
    discovery: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _lookup(monkeypatch)
    response = _response(discovery.query, "31625")
    insert_artifact = v2_discovery.insert_v2_artifact
    insert_batch = v2_discovery.insert_v2_artifact_batch

    def save_without_scout_checkpoint(
        path: str, key: str, artifact: StrictModel, timestamp: datetime
    ) -> None:
        if not isinstance(artifact, v2_discovery.V2ScoutRoundCheckpoint):
            insert_artifact(path, key, artifact, timestamp)

    def save_ranking_only(
        path: str, artifacts: tuple[tuple[str, StrictModel, datetime], ...]
    ) -> NoReturn:
        insert_batch(path, artifacts[:1])
        raise RuntimeError("interrupted after saving legacy ranking")

    with monkeypatch.context() as previous_version:
        previous_version.setattr(v2_discovery, "nber_paper_number", lambda _: None)
        previous_version.setattr(v2_discovery, "insert_v2_artifact", save_without_scout_checkpoint)
        previous_version.setattr(v2_discovery, "insert_v2_artifact_batch", save_ranking_only)
        with pytest.raises(RuntimeError, match="legacy ranking"):
            discovery.run((response,))

    recovered = discovery.run((response,))
    assert recovered.output.items[0].title == PAPERS["31625"][0]
    assert recovered.output.scout_audits[0].recovery_policy == "partial-ranking-recovery-v1"
    assert len(discovery.scout.requests) == 1
    assert calls == []
