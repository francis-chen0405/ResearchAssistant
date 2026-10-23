"""Four-round source retention is bounded without changing historical contracts."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
import test_product_discovery_pipeline as product
from pydantic import ValidationError
from test_preview_selection_bounds import BoundedSourceSelector, _large_selection_input, _run
from test_v2_phase8_source_selection import _candidate

from researchassistant.agents.v2_source_selection import run_v2_source_selection_and_queue
from researchassistant.api.live_history import research_trail
from researchassistant.api.live_progress import snapshot_from_v2_result
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchControls,
    ResearchDirection,
    ResearchDirections,
    ResearchMode,
    V2GapAnalysisModelOutput,
    V2SourceSelectionInput,
    V2SourceSelectionQueueResult,
)
from researchassistant.contracts.research_policy import (
    V2_PREVIEW_SELECTION_LEGACY_POLICY_IDENTITY,
    V2_PREVIEW_SELECTION_POLICY_IDENTITY,
    V2_SOURCE_SELECTION_POLICY_IDENTITY,
)
from researchassistant.contracts.source_selection_preview import V2SelectionShortlistAudit
from researchassistant.providers.llm import LLMRequest
from researchassistant.research.v2_orchestrator import V2ProductionState, run_v2_production_pipeline
from researchassistant.storage.store import read_v2_artifact


def _capacity_input(count: int) -> V2SourceSelectionInput:
    base = _large_selection_input(source_count=1)
    return V2SourceSelectionInput.model_validate(
        {
            **base.model_dump(),
            "survivors": tuple(
                _candidate(UUID(int=index + 1), family=f"family-{index}", probe_score=1)
                for index in range(count)
            ),
        }
    )


@pytest.mark.parametrize(
    "policy", [V2_SOURCE_SELECTION_POLICY_IDENTITY, V2_PREVIEW_SELECTION_LEGACY_POLICY_IDENTITY]
)
def test_historical_selection_keeps_its_original_limit(policy: str) -> None:
    current = _capacity_input(76)
    with pytest.raises(ValidationError, match="at most 75"):
        V2SourceSelectionInput.model_validate({**current.model_dump(), "policy_identity": policy})


def test_current_selection_supports_four_rounds_of_sixty_sources() -> None:
    assert len(_capacity_input(240).survivors) == 240
    with pytest.raises(ValidationError, match="at most 240"):
        _capacity_input(241)


def test_current_shortlist_dispositions_every_source_without_raising_budgets(
    tmp_path: Path,
) -> None:
    selection = _capacity_input(100)
    provider = BoundedSourceSelector()
    result, path = _run(tmp_path, selection, provider)
    audit = V2SelectionShortlistAudit.model_validate_json(
        read_v2_artifact(
            path, selection.run_id, "source-selection-preview-shortlist-v3"
        ).payload_json
    )
    assert audit.policy_identity == "source-selection-shortlist-v3"
    assert audit.total_sources == 100 and audit.input_token_cap == 24_000
    assert audit.rendered_input_tokens <= 24_000 and audit.omitted
    assert set(audit.included_source_ids) | {row.source_id for row in audit.omitted} == {
        source.source_id for source in selection.survivors
    }
    assert len(result.source_statuses) == 100
    assert result.physical_calls_after_reserve <= result.initial_budget.physical_call_ceiling
    assert result.total_reserved_tokens <= result.initial_budget.tokens_remaining
    assert result.total_reserved_cost_usd <= result.initial_budget.cost_remaining_usd
    with pytest.raises(ValidationError, match="at most 75"):
        V2SelectionShortlistAudit.model_validate(
            {**audit.model_dump(), "policy_identity": "source-selection-shortlist-v2"}
        )


def test_legacy_claim_preview_keeps_its_shortlist_policy_and_exact_resume(tmp_path: Path) -> None:
    from test_v2_phase8_source_selection import NOW, _budget, _routing

    selection = V2SourceSelectionInput.model_validate(
        {
            **_capacity_input(5).model_dump(),
            "policy_identity": V2_PREVIEW_SELECTION_LEGACY_POLICY_IDENTITY,
        }
    )
    _, path = _run(tmp_path, selection, BoundedSourceSelector())
    saved = read_v2_artifact(path, selection.run_id, "source-selection-preview-shortlist-v2")
    audit = V2SelectionShortlistAudit.model_validate_json(saved.payload_json)
    assert audit.policy_identity == "source-selection-shortlist-v2"
    provider = BoundedSourceSelector()
    resumed = run_v2_source_selection_and_queue(
        db_path=path,
        selection_input=selection,
        llm_provider=provider,
        routing_config=_routing(),
        budget=_budget(tokens_remaining=2_000_000),
        clock=lambda: NOW,
    )
    assert resumed.resumed and not provider.requests
    assert read_v2_artifact(path, selection.run_id, saved.artifact_key) == saved
    with pytest.raises(KeyError):
        read_v2_artifact(path, selection.run_id, "source-selection-preview-shortlist-v3")


@pytest.mark.parametrize("corrupt_current", [False, True])
def test_history_uses_current_shortlist_without_hiding_invalid_current_records(
    tmp_path: Path, corrupt_current: bool
) -> None:
    import sqlite3

    from test_historical_reads_phase3 import WHEN, _v2_trail_database
    from test_preview_inspection import _attach_selection_result, _replace_fixture_artifact

    from researchassistant.contracts.source_selection_preview import V2SelectionOmission
    from researchassistant.storage.store import insert_v2_artifact

    path = tmp_path / "generated-history.sqlite3"
    run_id, _ = _v2_trail_database(path)
    _attach_selection_result(path, run_id)
    legacy = V2SelectionShortlistAudit(
        run_id=run_id,
        total_sources=1,
        included_source_ids=(UUID(int=201),),
        omitted=(),
        rendered_input_tokens=100,
    )
    current = V2SelectionShortlistAudit(
        run_id=run_id,
        policy_identity="source-selection-shortlist-v3",
        total_sources=1,
        included_source_ids=(),
        omitted=(
            V2SelectionOmission(source_id=UUID(int=201), reason="Generated bounded omission."),
        ),
        rendered_input_tokens=0,
    )
    insert_v2_artifact(str(path), "source-selection-preview-shortlist-v2", legacy, WHEN)
    key = "source-selection-preview-shortlist-v3"
    insert_v2_artifact(str(path), key, current, WHEN)
    if corrupt_current:
        with sqlite3.connect(path) as connection:
            _replace_fixture_artifact(
                connection, key, {**current.model_dump(mode="json"), "total_sources": 2}
            )
    before = path.read_bytes(), path.stat().st_mtime_ns
    trail = research_trail(path, run_id)
    row = next(item for item in trail.items if item.research_round == 1)
    if corrupt_current:
        assert row.selection_input_disposition is None
        assert any(issue.record_key == key for issue in trail.compatibility_issues)
    else:
        assert row.selection_input_disposition == "omitted_input_cap"
        assert row.selection_input_reason == "Generated bounded omission."
        assert not trail.compatibility_issues
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


class _BalancedModel(product.production._ConceptModel):
    def generate(self, request: LLMRequest) -> object:
        result = super().generate(request)
        if isinstance(result, V2GapAnalysisModelOutput) and result.continue_research:
            changes = {"direction": ResearchDirection.CHALLENGE}
            return V2GapAnalysisModelOutput.model_validate(
                {
                    **result.model_dump(),
                    "material_gaps": (
                        *result.material_gaps,
                        *(
                            gap.model_copy(update={**changes, "gap_id": f"challenge-{gap.gap_id}"})
                            for gap in result.material_gaps
                        ),
                    ),
                    "new_search_directions": (
                        *result.new_search_directions,
                        *(
                            lane.model_copy(
                                update={**changes, "gap_id": f"challenge-{lane.gap_id}"}
                            )
                            for lane in result.new_search_directions
                        ),
                    ),
                }
            )
        return result


class _DistinctSearch(product._WideSearch):
    def search(self, request: product.phase12.SearchRequest) -> product.phase12.SearchResponse:
        result = super().search(request)
        return result.model_copy(
            update={
                "results": [
                    item.model_copy(update={"title": f"{item.title} request {len(self.requests)}"})
                    for item in result.results
                ]
            }
        )


@pytest.mark.parametrize("source_target", [20, 30])
def test_balanced_four_round_run_releases_more_than_seventy_five_source_dispositions(
    tmp_path: Path,
    source_target: int,
) -> None:
    path = tmp_path / "generated.sqlite3"
    controls = ResearchControls(
        discovery_providers=(DiscoveryProvider.EXA, DiscoveryProvider.OPENALEX),
        research_mode=ResearchMode.BALANCED,
        sources_per_stance_per_round=source_target,
    )
    model, search = _BalancedModel(completed_rounds=4), _DistinctSearch()
    result = run_v2_production_pipeline(
        product.production.CLAIM,
        db_path=path,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=True),
        discovery_providers=controls.discovery_providers,
        search_providers={provider: search for provider in controls.discovery_providers},
        wigolo_provider=product.phase12._Scraper(),
        llm_provider=model,
        routing_config=product.phase12._routing(),
        ceilings=product.production.CEILINGS,
        research_controls=controls,
        clock=lambda: product.phase12.NOW,
    )
    assert result.state is V2ProductionState.RELEASED, result.failure_reason
    selection = V2SourceSelectionQueueResult.model_validate_json(
        read_v2_artifact(
            path, result.run_id, "phase-13-source-selection-deep-analysis-queue-analyzer-admission"
        ).payload_json
    )
    assert selection.input.policy_identity == V2_PREVIEW_SELECTION_POLICY_IDENTITY
    retained_count = len(selection.input.survivors)
    assert 75 < retained_count <= min(240, 8 * source_target)
    assert len(selection.source_statuses) == retained_count
    assert {source.research_round for source in selection.input.survivors} == {1, 2, 3, 4}
    assert len(model.requests) <= product.production.CEILINGS.max_physical_calls
    before = path.read_bytes(), path.stat().st_mtime_ns
    trail = research_trail(path, result.run_id)
    snapshot = snapshot_from_v2_result(result)
    assert len({item.url for item in trail.items if item.source_selection_status}) == retained_count
    assert snapshot.classification == "released" and not trail.compatibility_issues
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
