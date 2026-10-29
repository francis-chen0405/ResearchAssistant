"""Offline selection coverage, confirmed mirror identity and guarded-dispatch regressions."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from test_preview_selection_bounds import (
    BoundedSourceSelector,
    _audit,
    _large_selection_input,
    _render_full_input,
    _run,
)
from test_query_execution import DIRECTIONS, NOW, _action, _clock, _freeze, _persist_round_one_gap
from test_query_retrieval_depth import _body, _serp_adapter
from test_seed_expansion_runtime import _candidate as paper_candidate

from researchassistant.agents.adaptive_execution import (
    _execute_searches,
    search_failure_explanation,
)
from researchassistant.agents.adaptive_summary import _merge_survivors
from researchassistant.api.discovery_diagnostics import enrich_discovery_diagnostics
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import (
    V2AcquisitionProbeOutput,
    V2AdaptiveRoundPlan,
    V2AdaptiveSearchQuery,
    V2DiscoveryScoutOutput,
)
from researchassistant.contracts.selection_view import selection_model_view
from researchassistant.evidence.paper_identity import confirmed_paper_anchor
from researchassistant.providers.config import OpenAlexConfig
from researchassistant.providers.llm import LLMRequest
from researchassistant.providers.mimo import _direct_mimo_prompt
from researchassistant.providers.openalex import OpenAlexSearchAdapter
from researchassistant.providers.pricing import conservative_token_estimate
from researchassistant.research.query_compiler import compile_query
from researchassistant.research.v2_orchestrator import build_v2_run_diagnostics
from researchassistant.storage.discovery_store import provider_attempt_audit
from researchassistant.storage.query_dispatch import query_dispatch_states
from researchassistant.storage.store import open_read_only_store

TITLE = (
    "An ecological network approach to predict ecosystem service vulnerability to species losses"
)
DOI = "10.1038/s41467-021-21824-x"


class NativeSizedSelector(BoundedSourceSelector):
    def conservative_input_tokens(self, request: LLMRequest, minimum: int) -> int:
        return max(minimum, conservative_token_estimate(_direct_mimo_prompt(request)))


def test_compact_selection_considers_twenty_sources_and_replays_without_calls(
    tmp_path: Path,
) -> None:
    original = _large_selection_input(source_count=20)
    assert conservative_token_estimate(_render_full_input(original)) > 24_000
    compact = original.model_copy(update={"model_view_policy": "compact-selection-v1"})
    model = NativeSizedSelector(output_source_id=compact.survivors[-1].source_id)
    result, path = _run(tmp_path, compact, model)
    audit = _audit(path, compact.run_id)
    assert len(audit.included_source_ids) == 20
    assert not audit.omitted
    assert audit.rendered_input_tokens <= 24_000
    assert result.recommended_source_ids == (compact.survivors[-1].source_id,)
    assert result.input == compact  # Complete local provenance was not projected away.
    native = _direct_mimo_prompt(model.requests[0])
    assert '"metadata_ranks"' not in native
    assert all(str(source.source_id) in native for source in compact.survivors)
    from test_v2_phase8_source_selection import NOW as SELECT_AT
    from test_v2_phase8_source_selection import _budget, _routing

    from researchassistant.agents.v2_source_selection import run_v2_source_selection_and_queue

    replay = run_v2_source_selection_and_queue(
        db_path=path,
        selection_input=compact,
        llm_provider=model,
        routing_config=_routing(),
        budget=_budget(tokens_remaining=2_000_000),
        clock=lambda: SELECT_AT,
    )
    assert replay.resumed and replay.result == result.result
    assert len(model.requests) == 1


def _mirror_pair(
    *,
    other_doi: str = DOI,
    reference_only: bool = False,
) -> tuple[V2DiscoveryScoutOutput, V2AcquisitionProbeOutput]:
    items, clusters, acquisitions, probes, survivors = [], [], [], [], []
    for index, url in enumerate(
        (
            "https://www.nature.com/articles/s41467-021-21824-x",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC7952599/",
        )
    ):
        item, cluster, (source, probe, survivor), _ = paper_candidate(
            f"mirror-{index}",
            doi=None,
            title=TITLE,
        )
        header = f"Nat Commun\n. 2021 Mar 11;12:1586. doi: {other_doi}\n\n{TITLE}\n"
        if reference_only:
            header = f"{TITLE}\nReferences\n1. Another paper doi: {other_doi}\n"
        text = (
            (header if index else TITLE + "\n")
            + ("Reported methods and results. " * (20 + index))
            + source.snapshot.normalized_text
        )
        snapshot = source.snapshot.model_copy(
            update={
                "source_url": url,
                "normalized_text": text,
                "snapshot_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "word_count": len(text.split()),
            }
        )
        acquisitions.append(source.model_copy(update={"snapshot": snapshot}))
        survivors.append(survivor.model_copy(update={"snapshot_sha256": snapshot.snapshot_sha256}))
        items.append(item.model_copy(update={"source_url": url, "canonical_url": url}))
        clusters.append(cluster.model_copy(update={"preferred_url": url, "canonical_url": url}))
        probes.append(
            probe.model_copy(
                update={
                    "snapshot_sha256": snapshot.snapshot_sha256,
                    "preview": None,
                    "passages": tuple(
                        passage.model_copy(
                            update={
                                "snapshot_sha256": snapshot.snapshot_sha256,
                                "start_char": text.index(passage.text),
                                "end_char": text.index(passage.text) + len(passage.text),
                            }
                        )
                        for passage in probe.passages
                    ),
                }
            )
        )
    return (
        V2DiscoveryScoutOutput(
            run_id=items[0].run_id,
            directions=DIRECTIONS,
            items=tuple(items),
            clusters=tuple(clusters),
            scout_batches=(),
            scout_audits=(),
            completed_at=NOW,
        ),
        V2AcquisitionProbeOutput(
            run_id=items[0].run_id,
            directions=DIRECTIONS,
            acquisitions=tuple(acquisitions),
            attempts=(),
            probes=tuple(probes),
            survivors=tuple(survivors),
            completed_at=NOW,
        ),
    )


def test_confirmed_mirrors_keep_both_snapshots_and_one_analysis_identity() -> None:
    discovery, acquisition = _mirror_pair()
    before = acquisition.model_dump_json()
    pool = _merge_survivors(
        discovery.run_id, ((1, discovery, acquisition),), deduplicate_papers=True
    )
    assert len(pool.sources) == 1
    canonical = pool.sources[0]
    assert len(canonical.paper_locations) == 2
    assert {location.snapshot_hash for location in canonical.paper_locations} == {
        source.snapshot.snapshot_sha256 for source in acquisition.acquisitions
    }
    assert {location.source_url for location in canonical.paper_locations} == {
        source.snapshot.source_url for source in acquisition.acquisitions
    }
    assert all(location.doi == DOI for location in canonical.paper_locations)
    assert acquisition.model_dump_json() == before
    assert len(_merge_survivors(discovery.run_id, ((1, discovery, acquisition),)).sources) == 2


@pytest.mark.parametrize("reference_only,other_doi", ((True, DOI), (False, "10.1038/other")))
def test_title_matches_or_reference_dois_do_not_merge_papers(
    reference_only: bool, other_doi: str
) -> None:
    discovery, acquisition = _mirror_pair(reference_only=reference_only, other_doi=other_doi)
    pool = _merge_survivors(
        discovery.run_id, ((1, discovery, acquisition),), deduplicate_papers=True
    )
    assert len(pool.sources) == 2
    assert all(not source.paper_locations for source in pool.sources)


def test_conflicting_doi_or_changed_snapshot_cannot_establish_paper_identity() -> None:
    _, acquisition = _mirror_pair()
    source = acquisition.acquisitions[0].snapshot
    assert confirmed_paper_anchor(source, TITLE, ("10.1038/conflicting",)) is None
    with pytest.raises(ValueError, match="snapshot hash"):
        confirmed_paper_anchor(source.model_copy(update={"normalized_text": "Changed."}), TITLE, ())


def test_later_mirror_keeps_early_assessment_identity_and_validates_locations() -> None:
    from pydantic import ValidationError

    from researchassistant.agents.adaptive_handoffs import V2MergedSurvivor

    discovery, acquisition = _mirror_pair()

    def acquired_at(index: int) -> V2AcquisitionProbeOutput:
        return V2AcquisitionProbeOutput(
            run_id=acquisition.run_id,
            directions=acquisition.directions,
            acquisitions=(acquisition.acquisitions[index],),
            probes=(acquisition.probes[index],),
            survivors=(acquisition.survivors[index],),
            attempts=(),
            completed_at=NOW,
        )

    initial = _merge_survivors(
        discovery.run_id, ((1, discovery, acquired_at(0)),), deduplicate_papers=True
    )
    final = _merge_survivors(
        discovery.run_id,
        ((1, discovery, acquired_at(0)), (2, discovery, acquired_at(1))),
        deduplicate_papers=True,
    )
    assert final.sources[0].survivor == initial.sources[0].survivor
    assert len(final.sources[0].paper_locations) == 2
    invalid = final.sources[0].model_dump()
    invalid["paper_locations"][0]["snapshot_hash"] = "f" * 64
    with pytest.raises(ValidationError, match="canonical paper location"):
        V2MergedSurvivor.model_validate(invalid)


def test_compact_preview_preserves_exact_unicode_offsets_and_omission_flags() -> None:
    from researchassistant.contracts.discovery_v2 import (
        V2PreviewRequest,
        V2PreviewResult,
        V2PreviewSpan,
        discovery_id,
    )

    original = _large_selection_input(source_count=1)
    source = original.survivors[0]
    text = "Methods. " + "Écosystème 🌿 resilience varies under disturbance. " * 40
    start = 9
    request = V2PreviewRequest(
        run_id=original.run_id,
        artifact_id=discovery_id(original.run_id, "V2PreviewRequest", "preview-request"),
        identity_key="preview-request",
        exact_claim=original.exact_claim,
        direction=source.direction,
        directions=original.directions,
        source_id=source.source_id,
        snapshot_id=uuid4(),
        snapshot_hash=hashlib.sha256(text.encode()).hexdigest(),
    )
    preview = V2PreviewResult(
        run_id=original.run_id,
        artifact_id=discovery_id(original.run_id, "V2PreviewResult", "view"),
        identity_key="view",
        request=request,
        outcome="completed",
        content_classification="full_text",
        spans=(V2PreviewSpan(start=start, end=len(text), text=text[start:], section="results"),),
        reason="Exact fixture window",
    )
    compact = original.model_copy(
        update={
            "model_view_policy": "compact-selection-v1",
            "survivors": (source.model_copy(update={"preview": preview}),),
        }
    )
    projected = selection_model_view(compact).survivors[0]
    assert projected.preview_omitted
    assert projected.snapshot_hash == preview.request.snapshot_hash
    assert sum(len(span.text.encode()) for span in projected.spans) <= 320
    assert all(text[span.start : span.end] == span.text for span in projected.spans)


def test_dispatch_counts_unknown_call_and_blocked_query_without_reissuing(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.OPENALEX)
    _persist_round_one_gap(path, run_id)
    actions = tuple(
        _action(
            run_id,
            DiscoveryProvider.OPENALEX,
            round_number=2,
            purpose="gap",
            target_gap_ids=("gap-1",),
            term=term,
        )
        for term in ("first community", "independent ecology")
    )
    sent = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        raise httpx.ReadTimeout("offline unknown request outcome")

    client = httpx.Client(
        base_url="https://api.openalex.org", transport=httpx.MockTransport(handler)
    )
    adapter = OpenAlexSearchAdapter(OpenAlexConfig(api_key="offline-test"), client=client)
    plan = V2AdaptiveRoundPlan(
        run_id=run_id,
        round_number=2,
        directions=DIRECTIONS,
        enabled_providers=(DiscoveryProvider.OPENALEX,),
        targeted_gap_ids=("gap-1",),
        discovered_terms=(),
        searches=tuple(
            V2AdaptiveSearchQuery(
                run_id=run_id,
                query_id=uuid4(),
                round_number=2,
                direction="support",
                provider=DiscoveryProvider.OPENALEX,
                targeted_gap_ids=("gap-1",),
                strategy="gap",
                query_text=action.query_text,
                compiled_query=action,
                created_at=NOW,
            )
            for action in actions
        ),
        search_agent_prompt_version="offline-v1",
        planned_at=NOW,
    )
    try:
        result = _execute_searches(
            str(path), plan, {DiscoveryProvider.OPENALEX: adapter}, None, _clock()
        )
    finally:
        client.close()
    assert sent == 1, result
    assert query_dispatch_states(path, run_id) == {
        actions[0].artifact_id: "unknown",
        actions[1].artifact_id: "blocked",
    }, result.model_dump_json()
    before = hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns
    diagnostics = build_v2_run_diagnostics(path, run_id, (DiscoveryProvider.OPENALEX,))
    provider = diagnostics.provider_outcomes[0]
    assert diagnostics.search_attempts == provider.query_attempts == 1
    assert provider.unknown_queries == provider.blocked_queries == 1
    assert provider.failed_queries == 0
    reason = search_failure_explanation(str(path), result)
    assert "1 searches with unknown" in reason and "1 searches blocked before dispatch" in reason
    with open_read_only_store(path) as store:
        enriched = enrich_discovery_diagnostics(store.connection, run_id, diagnostics)
    assert any(
        "1 queries blocked before dispatch" in message for message in enriched.diagnostic_messages
    )
    audit = provider_attempt_audit(path, run_id)
    assert len(audit.starts) == 1 and audit.starts[0].reserved_cost_usd > 0
    assert audit.completions[0].actual_cost_usd is None
    assert _execute_searches(str(path), plan, {}, None, _clock()) == result
    assert sent == 1
    assert before == (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)


def test_partial_query_reports_unknown_page_and_retained_results(tmp_path: Path) -> None:
    path = tmp_path / "partial-unknown-dispatch.sqlite"
    run_id, _ = _freeze(path, DiscoveryProvider.SERPSEARCH)
    _persist_round_one_gap(path, run_id)
    actions = tuple(
        compile_query(
            _action(
                run_id,
                DiscoveryProvider.SERPSEARCH,
                round_number=2,
                purpose="gap",
                target_gap_ids=("gap-1",),
                term=term,
            ).conceptual_query,
            requested_depth=20,
        )
        for term in ("first community", "independent ecology")
    )
    sent: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        sent.append(page)
        if page == 2:
            raise httpx.ReadTimeout("offline unknown later page")
        return httpx.Response(200, json=_body())

    adapter = _serp_adapter(handler)
    plan = V2AdaptiveRoundPlan(
        run_id=run_id,
        round_number=2,
        directions=DIRECTIONS,
        enabled_providers=(DiscoveryProvider.SERPSEARCH,),
        targeted_gap_ids=("gap-1",),
        discovered_terms=(),
        searches=tuple(
            V2AdaptiveSearchQuery(
                run_id=run_id,
                query_id=uuid4(),
                round_number=2,
                direction="support",
                provider=DiscoveryProvider.SERPSEARCH,
                targeted_gap_ids=("gap-1",),
                strategy="gap",
                query_text=action.query_text,
                compiled_query=action,
                created_at=NOW,
            )
            for action in actions
        ),
        search_agent_prompt_version="offline-v1",
        planned_at=NOW,
    )

    result = _execute_searches(
        str(path), plan, {DiscoveryProvider.SERPSEARCH: adapter}, None, _clock()
    )

    assert sent == [1, 2]
    assert result.outcomes[0].succeeded and result.outcomes[0].results
    assert not result.outcomes[1].succeeded
    diagnostics = build_v2_run_diagnostics(path, run_id, (DiscoveryProvider.SERPSEARCH,))
    provider = diagnostics.provider_outcomes[0]
    assert provider.query_attempts == 1
    assert provider.non_empty_queries == 0
    assert provider.search_results == 10
    assert provider.unknown_queries == provider.blocked_queries == 1
    assert provider.failed_queries == 0
    explanation = search_failure_explanation(str(path), result)
    assert "1 searches with unknown request outcomes" in explanation
    assert "including 1 with retained partial results" in explanation
    assert "1 searches blocked before dispatch" in explanation
