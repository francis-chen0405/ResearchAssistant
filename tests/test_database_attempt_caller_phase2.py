from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

import researchassistant.research.orchestrator as orchestrator
from providers.llm import DEFAULT_LLM_ROUTING, LLMStage
from researchassistant.contracts.models import (
    ModelAttemptStatus,
    ModelRouteAttempt,
    ModelUsageMetadata,
    RunManifest,
    RunStatus,
    Stage,
)
from researchassistant.storage.store import (
    finish_model_route_attempt,
    init_db,
    insert_run,
    reserve_model_route_attempt,
)

NOW = datetime(2026, 10, 4, tzinfo=UTC)


class _Input(BaseModel):
    run_id: UUID
    text: str


class _Output(BaseModel):
    value: str


class _NoCallProvider:
    def generate(self, request: object) -> BaseModel:
        raise AssertionError("a completed compatible attempt must bypass the provider")


def _database(path: Path, run_id: UUID) -> str:
    db_path = str(path)
    init_db(db_path)
    insert_run(
        db_path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.RUNNING,
            raw_claim="routed attempt caller identity",
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    return db_path


def _attempt(
    *,
    run_id: UUID,
    operation_id: UUID,
    input_artifact_id: UUID,
    identity_override: dict[str, object] | None = None,
) -> ModelRouteAttempt:
    config = orchestrator.ProviderOrchestrationConfig(routing=DEFAULT_LLM_ROUTING)
    stage = LLMStage.PLANNER
    alias = config.routing.for_stage(stage).primary
    attempt = ModelRouteAttempt(
        run_id=run_id,
        operation_id=operation_id,
        attempt_id=orchestrator._attempt_id(run_id, operation_id, alias, 0, 1),
        stage=stage.value,
        output_type=_Output.__name__,
        model_alias=alias.value,
        pinned_model_snapshot=config.pinned_snapshot_for(alias),
        route_index=0,
        attempt_number=1,
        input_artifact_ids=(input_artifact_id,),
        status=ModelAttemptStatus.RUNNING,
        started_at=NOW,
        reserved_tokens=20,
        reserved_cost_usd=Decimal("0.02"),
    )
    if identity_override:
        attempt = attempt.model_copy(update=identity_override)
    return attempt


def _persist_completed(db_path: str, attempt: ModelRouteAttempt) -> ModelRouteAttempt:
    reserve_model_route_attempt(db_path, attempt, max_model_calls=4)
    finished = attempt.model_copy(
        update={
            "status": ModelAttemptStatus.COMPLETED,
            "ended_at": NOW + timedelta(seconds=1),
            "latency_ms": 1000,
            "usage": ModelUsageMetadata(total_tokens=2, cost_usd=Decimal("0.001")),
            "output_json": _Output(value="cached").model_dump_json(),
        }
    )
    finish_model_route_attempt(db_path, finished)
    return finished


def _invoke(
    db_path: str,
    run_id: UUID,
    operation_id: UUID,
    input_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> _Output:
    config = orchestrator.ProviderOrchestrationConfig(routing=DEFAULT_LLM_ROUTING)
    monkeypatch.setattr(orchestrator, "build_stage_request", lambda **_kwargs: object())
    monkeypatch.setattr(
        orchestrator,
        "_conservative_reservation",
        lambda _request, _alias, _config: (20, Decimal("0.02")),
    )
    return orchestrator._invoke_routed(
        db_path=db_path,
        provider=_NoCallProvider(),
        stage=LLMStage.PLANNER,
        input_artifact=_Input(run_id=run_id, text="current input"),
        requested_output_type=_Output,
        input_artifact_ids=(input_id,),
        operation_id=operation_id,
        config=config,
        clock=lambda: NOW,
        objective_validator=lambda output, _alias: output,
        run_id=run_id,
    )


@pytest.mark.parametrize(
    "identity_override",
    [
        {"stage": "reviewer"},
        {"output_type": "DifferentOutput"},
        {"model_alias": "different-model"},
        {"pinned_model_snapshot": "different-deployment"},
        {"input_artifact_ids": (UUID(int=99),)},
        {"reserved_tokens": 21},
        {"reserved_cost_usd": Decimal("0.03")},
    ],
    ids=["stage", "output", "model", "pin", "inputs", "reserved-tokens", "reserved-cost"],
)
def test_completed_attempt_with_caller_identity_drift_is_rejected(
    tmp_path: Path,
    identity_override: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, operation_id, input_id = uuid4(), uuid4(), UUID(int=1)
    db_path = _database(tmp_path / "caller-replay.sqlite3", run_id)
    _persist_completed(
        db_path,
        _attempt(
            run_id=run_id,
            operation_id=operation_id,
            input_artifact_id=input_id,
            identity_override=identity_override,
        ),
    )
    with pytest.raises(orchestrator.Phase9OrchestrationError, match="identity"):
        _invoke(db_path, run_id, operation_id, input_id, monkeypatch)


def test_completed_compatible_attempt_is_reused_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, operation_id, input_id = uuid4(), uuid4(), UUID(int=1)
    db_path = _database(tmp_path / "caller-replay.sqlite3", run_id)
    _persist_completed(
        db_path,
        _attempt(
            run_id=run_id,
            operation_id=operation_id,
            input_artifact_id=input_id,
        ).model_copy(update={"started_at": NOW - timedelta(seconds=5)}),
    )
    assert _invoke(db_path, run_id, operation_id, input_id, monkeypatch) == _Output(value="cached")


def test_terminal_completion_returned_by_reservation_skips_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, operation_id, input_id = uuid4(), uuid4(), UUID(int=1)
    db_path = _database(tmp_path / "reservation-race.sqlite3", run_id)
    original_reserve = orchestrator.reserve_model_route_attempt

    def reserve_then_finish(
        path: str, attempt: ModelRouteAttempt, **kwargs: object
    ) -> ModelRouteAttempt:
        reserved = original_reserve(path, attempt, **kwargs)
        return _persist_completed(path, reserved)

    monkeypatch.setattr(orchestrator, "reserve_model_route_attempt", reserve_then_finish)
    monkeypatch.setattr(
        orchestrator,
        "build_stage_request",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        orchestrator,
        "_conservative_reservation",
        lambda _request, _alias, _config: (20, Decimal("0.02")),
    )

    assert _invoke(db_path, run_id, operation_id, input_id, monkeypatch) == _Output(value="cached")


def test_running_attempt_usage_claims_do_not_replace_conservative_reservation() -> None:
    running = _attempt(
        run_id=uuid4(),
        operation_id=uuid4(),
        input_artifact_id=UUID(int=1),
    ).model_copy(
        update={
            "usage": ModelUsageMetadata(total_tokens=1, cost_usd=Decimal("0.001")),
        }
    )

    accounting = orchestrator.summarize_model_usage((running,))

    assert accounting.exact_total_tokens is None
    assert accounting.exact_total_cost_usd is None
    assert accounting.known_token_subtotal == 0
    assert accounting.known_cost_subtotal_usd == 0
    assert accounting.conservative_reserved_tokens == 20
    assert accounting.conservative_reserved_cost_usd == Decimal("0.02")
