"""Product settings exercise ordinary fresh orchestration and immutable inspection."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
import test_query_production as production
import test_v2_phase12_production as phase12

from frontend.live_history import research_trail
from frontend.live_progress import snapshot_from_v2_result
from researchassistant.contracts.discovery_v2 import V2ProductDiscoveryPolicy
from researchassistant.contracts.models import DiscoveryProvider, ResearchControls
from researchassistant.research.product_discovery import resolve_product_discovery
from researchassistant.research.v2_orchestrator import (
    V2ProductionPipelineResult,
    V2ProductionState,
    run_v2_production_pipeline,
)
from researchassistant.storage.discovery_store import read_discovery_binding


def _run(
    path: Path, controls: ResearchControls, *, run_id: UUID | None = None
) -> tuple[V2ProductionPipelineResult, production._ConceptModel, phase12._Search]:
    model = production._ConceptModel(completed_rounds=4)
    search = phase12._Search(unique_results=True)
    result = run_v2_production_pipeline(
        production.CLAIM,
        db_path=path,
        directions=production.DIRECTIONS,
        discovery_providers=controls.discovery_providers,
        search_providers={provider: search for provider in controls.discovery_providers},
        wigolo_provider=phase12._Scraper(),
        llm_provider=model,
        routing_config=phase12._routing(),
        ceilings=production.CEILINGS,
        research_controls=controls,
        run_id=run_id,
        clock=lambda: phase12.NOW,
    )
    return result, model, search


def test_product_settings_reach_every_round_and_read_only_views(tmp_path: Path) -> None:
    path = tmp_path / "product.sqlite"
    controls = ResearchControls(
        discovery_providers=(DiscoveryProvider.EXA,),
        metadata_depth=50,
        seed_expansion_enabled=False,
        scholarly_search_mode="auto",
    )
    result, model, search = _run(path, controls)
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    binding = read_discovery_binding(path, result.run_id)
    assert isinstance(binding.policy, V2ProductDiscoveryPolicy)
    assert binding.policy.seed_expansion_enabled is False
    assert binding.policy.scholarly_search_mode == "auto"
    assert binding.policy.metadata_depth == 50
    assert {
        request.compiled_query.conceptual_query.round_number for request in search.requests
    } == {1, 2, 3, 4}
    assert all(request.compiled_query.policy == binding.policy for request in search.requests)
    assert all(request.compiled_query.requested_depth == 50 for request in search.requests)
    assert all(request.compiled_query.effective_depth <= 25 for request in search.requests)
    assert len(model.requests) <= 160
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    snapshot = snapshot_from_v2_result(result)
    trail = research_trail(path, result.run_id)
    assert snapshot.research_controls == controls
    assert trail.items
    assert all(item.compiled_query and item.requested_metadata_depth == 50 for item in trail.items)
    assert all(item.effective_metadata_depth <= 25 for item in trail.items)
    assert path.read_bytes() == before and path.stat().st_mtime_ns == mtime
    replay, replay_model, replay_search = _run(path, controls, run_id=result.run_id)
    assert replay == result
    assert not replay_model.requests and not replay_search.requests


@pytest.mark.parametrize(
    "changes",
    [
        {"metadata_depth": 10},
        {"seed_expansion_enabled": False},
        {"scholarly_search_mode": "auto"},
    ],
)
def test_current_product_resume_rejects_changed_frozen_settings(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    path = tmp_path / "resume.sqlite"
    controls = ResearchControls(
        discovery_providers=(DiscoveryProvider.EXA,),
        metadata_depth=20,
        seed_expansion_enabled=True,
        scholarly_search_mode="lexical",
    )
    result, _, _ = _run(path, controls)
    assert result.state is V2ProductionState.RELEASED
    with pytest.raises(ValueError, match="binding|fingerprint|new run|immutable"):
        _run(path, controls.model_copy(update=changes), run_id=result.run_id)


def test_auto_mode_does_one_lexical_attempt_and_semantic_stays_openalex_only() -> None:
    providers = (DiscoveryProvider.OPENALEX, DiscoveryProvider.ARXIV, DiscoveryProvider.PUBMED)
    policy, modes = resolve_product_discovery(
        ResearchControls(
            discovery_providers=providers,
            scholarly_search_mode="auto",
        ),
        providers,
    )
    assert policy.scholarly_search_mode == "auto"
    assert tuple(modes.values()) == ("lexical", "lexical", "lexical")
    _, modes = resolve_product_discovery(
        ResearchControls(
            discovery_providers=providers,
            scholarly_search_mode="semantic",
        ),
        providers,
    )
    assert modes == {
        DiscoveryProvider.OPENALEX: "semantic",
        DiscoveryProvider.ARXIV: "lexical",
        DiscoveryProvider.PUBMED: "lexical",
    }
    with pytest.raises(ValueError, match="requires OpenAlex"):
        resolve_product_discovery(
            ResearchControls(
                discovery_providers=(DiscoveryProvider.EXA,),
                scholarly_search_mode="semantic",
            ),
            (DiscoveryProvider.EXA,),
        )


def test_historical_controls_serialize_without_inventing_new_settings() -> None:
    controls = ResearchControls.model_validate({"sources_per_stance_per_round": 5})
    assert controls.metadata_depth is None and controls.seed_expansion_enabled is None
    payload = json.loads(controls.canonical_json())
    assert "metadata_depth" not in payload and "seed_expansion_enabled" not in payload
    assert "scholarly_search_mode" not in payload


class _WideSearch(phase12._Search):
    def search(self, request: phase12.SearchRequest) -> phase12.SearchResponse:
        self.requests.append(request)
        return phase12.SearchResponse(
            provider_name="offline-wide-search",
            provider_version="v1",
            adapter_version="v1",
            results=[
                phase12.SearchResult(
                    original_url=f"https://example.test/study-{len(self.requests)}-{index}",
                    title=f"Regional program course completion evaluation {index}",
                    snippet="A controlled comparison of program completion outcomes.",
                    rank=index,
                )
                for index in range(1, request.limit + 1)
            ],
        )


def test_source_target_caps_acquisition_independently_of_metadata_depth(tmp_path: Path) -> None:
    from agents.v2_acquisition import V2_ACQUISITION_PROBE_ARTIFACT_KEY
    from researchassistant.contracts.models import V2AcquisitionProbeOutput
    from researchassistant.storage.store import read_v2_artifact

    path = tmp_path / "source-target.sqlite"
    controls = ResearchControls(
        discovery_providers=(DiscoveryProvider.EXA,),
        metadata_depth=20,
        sources_per_stance_per_round=5,
        seed_expansion_enabled=False,
        scholarly_search_mode="lexical",
    )
    search = _WideSearch()
    result = run_v2_production_pipeline(
        production.CLAIM,
        db_path=path,
        directions=production.DIRECTIONS,
        discovery_providers=controls.discovery_providers,
        search_providers={DiscoveryProvider.EXA: search},
        wigolo_provider=phase12._Scraper(),
        llm_provider=production._ConceptModel(completed_rounds=1),
        routing_config=phase12._routing(),
        ceilings=production.CEILINGS,
        research_controls=controls,
        clock=lambda: phase12.NOW,
    )
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    acquisition = V2AcquisitionProbeOutput.model_validate_json(
        read_v2_artifact(
            path,
            result.run_id,
            V2_ACQUISITION_PROBE_ARTIFACT_KEY,
        ).payload_json
    )
    assert len(acquisition.acquisitions) == 5
    assert all(request.compiled_query.requested_depth == 20 for request in search.requests)
    assert sum(request.limit for request in search.requests) > 5


def test_live_controller_uses_product_controls_in_real_fresh_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from frontend.live_contracts import LiveRunRequest
    from frontend.live_service import LiveResearchController
    from providers.config import ExaConfig
    from providers.v2_factory import V2ProductionFactoryConfig

    controls = ResearchControls(
        discovery_providers=(DiscoveryProvider.EXA,),
        metadata_depth=10,
        seed_expansion_enabled=False,
        scholarly_search_mode="auto",
    )
    seen: list[ResearchControls] = []

    def config_factory(
        cls: type[V2ProductionFactoryConfig],
        environment: object,
        **kwargs: object,
    ) -> V2ProductionFactoryConfig:
        seen.append(kwargs["research_controls"])
        return cls(
            routing=phase12._routing(),
            ceilings=production.CEILINGS,
            discovery_providers=controls.discovery_providers,
            research_controls=controls,
            exa=ExaConfig(api_key="offline-fixture-key"),
        )

    model = production._ConceptModel(completed_rounds=1)
    search = phase12._Search(unique_results=True)
    bundle = SimpleNamespace(
        search_providers={DiscoveryProvider.EXA: search},
        wigolo=phase12._Scraper(),
        firecrawl=None,
        crossref_resolver=None,
        llm=model,
    )
    monkeypatch.setattr(V2ProductionFactoryConfig, "from_environment", classmethod(config_factory))
    monkeypatch.setattr("frontend.live_service.build_v2_production_bundle", lambda config: bundle)
    controller = LiveResearchController(environment={})
    path = tmp_path / "ordinary-desktop.sqlite"
    try:
        started = controller.start(
            LiveRunRequest(
                raw_claim=production.CLAIM,
                db_path=str(path),
                max_tokens=500_000,
                max_cost_usd=5,
                research_controls=controls,
            )
        )
        assert started.started, started.message
        controller._executor.shutdown(wait=True)
        snapshot = controller.snapshot(path, started.run_id)
        assert snapshot.classification == "released", snapshot.message
        assert snapshot.research_controls == controls
        assert seen == [controls]
        assert all(request.compiled_query.requested_depth == 10 for request in search.requests)
        assert snapshot.v2_diagnostics.physical_search_requests == len(search.requests)
    finally:
        controller.shutdown(timeout=20)


def test_disabled_expansion_cannot_bypass_offer_execution_or_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import test_seed_expansion_runtime as seeds

    from researchassistant.contracts.discovery_v2 import (
        V2DiscoveryBinding,
        V2DiscoveryOperation,
        discovery_id,
    )
    from researchassistant.research.seed_expansion import execute_expansion, offer_expansions
    from researchassistant.storage.discovery_store import (
        bind_discovery_run,
        insert_discovery_operation,
        provider_attempt_audit,
    )

    def disabled_binding(path: str, binding: V2DiscoveryBinding, now: object) -> str:
        return bind_discovery_run(
            path,
            binding.model_copy(
                update={
                    "policy": V2ProductDiscoveryPolicy(seed_expansion_enabled=False),
                }
            ),
            now,
        )

    monkeypatch.setattr(seeds, "bind_discovery_run", disabled_binding)
    path = tmp_path / "expansion-off.sqlite"
    seeds._binding(path)
    seeds._install_round_one(
        path,
        (
            {
                "doi": "10.5555/seed",
                "external_id": "https://openalex.org/W1",
                "title": "Eligible synthetic seed",
                "score": 90,
            },
        ),
    )
    assert offer_expansions(str(path), seeds.RUN, 2, (seeds._lane(),), seeds._clock) == ()
    action = seeds._manual_action(path)
    with pytest.raises(ValueError, match="disabled"):
        execute_expansion(path=str(path), action=action, adapter=None, clock=seeds._clock)
    binding = read_discovery_binding(path, seeds.RUN)
    key = "disabled-graph-slot"
    operation = V2DiscoveryOperation(
        run_id=seeds.RUN,
        artifact_id=discovery_id(seeds.RUN, "V2DiscoveryOperation", key),
        identity_key=key,
        binding_fingerprint=binding.fingerprint,
        action=action,
        created_at=seeds.NOW,
    )
    with pytest.raises(ValueError, match="disabled"):
        insert_discovery_operation(str(path), operation, seeds.NOW)
    assert not provider_attempt_audit(str(path), seeds.RUN).starts
