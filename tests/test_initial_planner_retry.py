"""Planner response repair and restart behavior without external model calls."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from test_bounded_stage_checkpoint_resume import _advancing_clock
from test_v2_phase3_initial_planner import FakeConceptPlanner, _routing
from test_v2_resume_integrity import _substitute

from researchassistant.agents import v2_initial_planner as planner
from researchassistant.agents import v2_stage_checkpoint as journal
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchDirections,
)
from researchassistant.contracts.research_coverage import V2InitialPlannerClaimComponent
from researchassistant.providers.llm import LLMRequest, LLMStage
from researchassistant.providers.mimo import MimoFailureCode, MimoProviderError
from researchassistant.providers.v2_budget import (
    BudgetedV2LLMProvider,
    V2RunCeilings,
    read_v2_physical_call_audit,
)
from researchassistant.storage.store import init_db, read_v2_artifact

CLAIM = (
    "Automated license plate readers discriminate against people of color and impoverished people."
)
CHECKPOINT = "initial-planner-checkpoint-v1"


class RepairPlanner(FakeConceptPlanner):
    def __init__(self, failures: int = 1, *, retryable: bool = True) -> None:
        super().__init__()
        self.failures = failures
        self.retryable = retryable

    def generate(self, request: LLMRequest) -> object:
        if len(self.requests) < self.failures:
            self.requests.append(request)
            raise MimoProviderError(
                MimoFailureCode.SCHEMA if self.retryable else MimoFailureCode.REFUSAL,
                "schema diagnostics: claim_coverage_focus:planner_duplicate_coverage_dimension"
                if self.retryable
                else "provider refused the request",
                retryable=self.retryable,
            )
        output = super().generate(request)
        return type(output).model_validate(
            output.model_dump()
            | {
                "claim_coverage_focus": [
                    {
                        "dimension": "population_and_setting",
                        "claim_component": "people of color and impoverished people",
                    }
                ]
            }
        )


def _arguments(tmp_path: Path, provider: object) -> dict:
    return dict(
        raw_claim=CLAIM,
        db_path=tmp_path / "planner.sqlite3",
        directions=ResearchDirections(),
        discovery_providers=(DiscoveryProvider.EXA,),
        llm_provider=provider,
        routing_config=_routing(),
        run_id=uuid4(),
        clock=_advancing_clock(),
    )


def test_duplicate_coverage_retries_once_and_preserves_both_groups(tmp_path: Path) -> None:
    provider = RepairPlanner()
    args = _arguments(tmp_path, provider)
    result = planner.run_v2_initial_planner(**args)
    assert len(provider.requests) == 2
    assert result.invocation.retry.attempt_number == 2
    assert result.invocation.retry.automatic_retry_performed
    assert result.planner_output.raw_claim == CLAIM
    populations = [
        item.claim_component
        for item in result.planner_output.claim_coverage_focus
        if item.dimension.value == "population_and_setting"
    ]
    assert populations == ["people of color and impoverished people"]
    for request in provider.requests:
        assert "Use each claim_coverage_focus dimension at most once" in request.rendered_prompt
        assert "people of color and impoverished people" in request.rendered_prompt
        assert request.prompt.version.endswith("-grouped-v1")
    assert "previous response was rejected" in provider.requests[1].rendered_prompt
    resumed = planner.run_v2_initial_planner(**args)
    assert resumed.planner_output.model_dump(mode="json") == result.planner_output.model_dump(
        mode="json"
    )
    assert len(provider.requests) == 2


@pytest.mark.parametrize(("failures", "retryable", "expected"), [(2, True, 2), (1, False, 1)])
def test_exhausted_or_terminal_failures_are_not_repeated_on_resume(
    tmp_path: Path, failures: int, retryable: bool, expected: int
) -> None:
    provider = RepairPlanner(failures, retryable=retryable)
    args = _arguments(tmp_path, provider)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            planner.run_v2_initial_planner(**args)
    assert len(provider.requests) == expected
    for number in range(1, expected + 1):
        record = journal.read_checkpoint(
            str(args["db_path"]),
            args["run_id"],
            f"{CHECKPOINT}/attempt-{number}/outcome",
            journal.V2StageOutcomeCheckpoint,
        )
        assert record.failure and record.invocation.retry.attempt_number == number


@pytest.mark.parametrize("persist_second_outcome", [False, True])
def test_interrupted_retry_reuses_success_or_retains_unknown_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, persist_second_outcome: bool
) -> None:
    provider = RepairPlanner()
    args = _arguments(tmp_path, provider)
    insert = journal.insert_v2_artifact

    def interrupt(*values: object, **kwargs: object) -> object:
        if values[1] == f"{CHECKPOINT}/attempt-2/outcome":
            if persist_second_outcome:
                insert(*values, **kwargs)
            raise KeyboardInterrupt("after retry")
        return insert(*values, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(journal, "insert_v2_artifact", interrupt)
        with pytest.raises(KeyboardInterrupt):
            planner.run_v2_initial_planner(**args)
    assert len(provider.requests) == 2
    for _ in range(2):
        if persist_second_outcome:
            assert planner.run_v2_initial_planner(**args).resumed
        else:
            with pytest.raises(RuntimeError, match="unknown outcome"):
                planner.run_v2_initial_planner(**args)
    assert len(provider.requests) == 2


@pytest.mark.parametrize("limit", ["physical-call", "total-token", "cost"])
def test_retry_budget_guard_preserves_failed_call_and_blocks_dispatch(
    tmp_path: Path, limit: str
) -> None:
    class EstimatedRepairPlanner(RepairPlanner):
        def conservative_input_tokens(self, request: LLMRequest, minimum_tokens: int) -> int:
            assert minimum_tokens <= 10_000
            return 10_000

    provider = EstimatedRepairPlanner()
    args = _arguments(tmp_path, provider)
    reservation = args["routing_config"].preflight().reserve(LLMStage.PLANNER, 10_000)
    ceilings = V2RunCeilings(
        max_physical_calls=1 if limit == "physical-call" else 160,
        max_total_tokens=reservation.reserved_tokens if limit == "total-token" else 500_000,
        max_total_cost_usd=reservation.reserved_cost_usd if limit == "cost" else "5",
    )
    init_db(args["db_path"])
    args["llm_provider"] = BudgetedV2LLMProvider(
        db_path=args["db_path"],
        run_id=args["run_id"],
        provider=provider,
        routing_config=args["routing_config"],
        ceilings=ceilings,
        clock=args["clock"],
    )
    for _ in range(2):
        with pytest.raises(RuntimeError, match=f"{limit} ceiling"):
            planner.run_v2_initial_planner(**args)
    audit = read_v2_physical_call_audit(args["db_path"], args["run_id"])
    assert len(provider.requests) == len(audit.starts) == 1
    assert audit.completions[0] is not None and not audit.completions[0].succeeded
    blocked = journal.read_checkpoint(
        str(args["db_path"]),
        args["run_id"],
        f"{CHECKPOINT}/attempt-2/outcome",
        journal.V2StageOutcomeCheckpoint,
    )
    assert blocked.terminal_provider_failure


def test_typed_schema_rejection_can_be_repaired_even_when_marked_nonretryable(
    tmp_path: Path,
) -> None:
    class InvalidTypedPlanner(FakeConceptPlanner):
        def generate(self, request: LLMRequest) -> object:
            output = super().generate(request)
            if len(self.requests) == 1:
                component = V2InitialPlannerClaimComponent(
                    dimension="population_and_setting",
                    claim_component="people of color and impoverished people",
                )
                return output.model_copy(update={"claim_coverage_focus": (component, component)})
            return output

    provider = InvalidTypedPlanner()
    result = planner.run_v2_initial_planner(**_arguments(tmp_path, provider))
    assert len(provider.requests) == 2
    assert result.invocation.retry.attempt_number == 2


def test_historical_checkpoint_retains_original_prompt_and_single_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = RepairPlanner(failures=2)
    args = _arguments(tmp_path, provider)

    def interrupt(**kwargs: object) -> object:
        raise KeyboardInterrupt("before request intent")

    with monkeypatch.context() as scoped:
        scoped.setattr(planner, "stage_attempt", interrupt)
        with pytest.raises(KeyboardInterrupt):
            planner.run_v2_initial_planner(**args)
    saved = read_v2_artifact(args["db_path"], args["run_id"], CHECKPOINT)
    payload = json.loads(saved.payload_json)
    del payload["response_policy"]
    _substitute(args["db_path"], args["run_id"], CHECKPOINT, payload)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="planner_duplicate_coverage_dimension"):
            planner.run_v2_initial_planner(**args)
    assert len(provider.requests) == 1
    assert not provider.requests[0].prompt.version.endswith("-grouped-v1")


def test_resume_after_first_failure_dispatches_only_the_remaining_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = RepairPlanner()
    args = _arguments(tmp_path, provider)
    save = planner.save_stage_outcome

    def interrupt(path: str, attempt: object, outcome: object) -> None:
        save(path, attempt, outcome)
        raise KeyboardInterrupt("after first failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(planner, "save_stage_outcome", interrupt)
        with pytest.raises(KeyboardInterrupt):
            planner.run_v2_initial_planner(**args)
    assert len(provider.requests) == 1
    assert planner.run_v2_initial_planner(**args).invocation.retry.attempt_number == 2
    assert len(provider.requests) == 2


@pytest.mark.parametrize("failures", [1, 2])
def test_production_releases_after_repair_or_stops_before_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failures: int
) -> None:
    import test_product_discovery_pipeline as product

    from researchassistant.contracts.models import ResearchControls

    generate = product.production._ConceptModel.generate
    planner_calls = []

    def fail_then_repair(self: object, request: LLMRequest) -> object:
        if request.stage.value == "planner":
            planner_calls.append(request)
            if len(planner_calls) <= failures:
                raise MimoProviderError(
                    MimoFailureCode.SCHEMA,
                    "schema diagnostics: claim_coverage_focus:planner_duplicate_coverage_dimension",
                    retryable=True,
                )
        return generate(self, request)

    monkeypatch.setattr(product.production._ConceptModel, "generate", fail_then_repair)
    path = tmp_path / "production.sqlite3"
    result, _, search = product._run(
        path, ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    )
    audit = read_v2_physical_call_audit(path, result.run_id)
    physical_plans = [item for item in audit.starts if item.stage == "planner"]
    assert len(planner_calls) == len(physical_plans) == 2
    assert all(item is not None for item in audit.completions)
    if failures == 1:
        assert result.state.value == "released", result.failure_reason
        assert search.requests
    else:
        assert result.state.value == "failed"
        assert "planner_duplicate_coverage_dimension" in result.failure_reason
        assert not search.requests
