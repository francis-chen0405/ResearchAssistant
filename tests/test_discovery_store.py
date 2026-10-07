from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from researchassistant.contracts.discovery_v2 import (
    V2DiscoveryBinding,
    V2DiscoveryFailure,
    V2DiscoveryOperation,
    V2DiscoveryPolicy,
    V2DiscoveryProviderBudget,
    V2IdentityLookupAction,
    V2ProviderAttemptCompletion,
    V2ProviderAttemptStart,
    V2ProviderCapabilities,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import (
    ResearchDirection,
    ResearchDirections,
    V2PipelineIdentity,
)
from researchassistant.storage.discovery_store import (
    bind_discovery_run,
    complete_provider_attempt,
    compute_discovery_audit_counters,
    insert_discovery_operation,
    provider_attempt_audit,
    read_discovery_binding,
    reserve_provider_attempt,
)
from researchassistant.storage.store import (
    RunManifest,
    RunStatus,
    Stage,
    init_db,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
    read_v2_artifact,
)

NOW = datetime(2026, 10, 6, tzinfo=UTC)
RUN_ID = UUID("e9c6c066-6dc4-4f60-b826-17db2143fb1e")
PROVIDER = DiscoveryProvider.OPENALEX


def _binding(run_id: UUID = RUN_ID, *, max_requests: int = 3) -> V2DiscoveryBinding:
    capability = V2ProviderCapabilities(
        provider=PROVIDER,
        search_modes=("lexical",),
        max_metadata_per_page=20,
        max_metadata_per_operation=20,
        pagination="none",
        identity_lookup=True,
        executable_identity_lookup=True,
        relationships=(),
        executable_search_modes=("lexical",),
        documentation_urls=("https://docs.openalex.org/api-entities/works/search-works",),
    )
    return V2DiscoveryBinding(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2DiscoveryBinding", "binding"),
        identity_key="binding",
        exact_claim="The intervention changes the outcome.",
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        providers=(PROVIDER,),
        policy=V2DiscoveryPolicy(),
        capabilities=(capability,),
        provider_budgets=(
            V2DiscoveryProviderBudget(
                provider=PROVIDER,
                max_requests=max_requests,
                max_cost_usd=Decimal("0.01"),
                cost_policy_identity="openalex-configured-upper-bound-v1",
                reservation_per_request_usd=Decimal("0.001"),
                cost_basis="configured_upper_bound",
            ),
        ),
        provider_configuration_hash="a" * 64,
        source_identity_hash="b" * 64,
        prompt_schema_hash="c" * 64,
    )


def _init_run(path: Path, run_id: UUID = RUN_ID) -> None:
    init_db(str(path))
    insert_run(
        str(path),
        RunManifest(
            run_id=run_id,
            status=RunStatus.PLANNED,
            raw_claim="The intervention changes the outcome.",
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(str(path), run_id, V2PipelineIdentity(), NOW)


def _operation(path: Path, run_id: UUID = RUN_ID) -> V2DiscoveryOperation:
    binding = read_discovery_binding(str(path), run_id)
    action = V2IdentityLookupAction(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2IdentityLookupAction", "lookup-1"),
        identity_key="lookup-1",
        candidate_id=discovery_id(run_id, "V2RawDiscoveryCandidate", "raw-1"),
        work_identifier="https://doi.org/10.1234/example",
        provider=PROVIDER,
        direction=ResearchDirection.SUPPORT,
        round_number=1,
        policy=binding.policy,
        capabilities=binding.capabilities[0],
    )
    operation = V2DiscoveryOperation(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2DiscoveryOperation", "lookup-op-1"),
        identity_key="lookup-op-1",
        binding_fingerprint=binding.fingerprint,
        action=action,
        created_at=NOW,
    )
    return insert_discovery_operation(str(path), operation, NOW)


def _start(
    operation: V2DiscoveryOperation, sequence: int = 1, *, key: str | None = None
) -> V2ProviderAttemptStart:
    return V2ProviderAttemptStart(
        run_id=operation.run_id,
        artifact_id=discovery_id(
            operation.run_id, "V2ProviderAttemptStart", key or f"attempt-{sequence}"
        ),
        identity_key=key or f"attempt-{sequence}",
        operation_id=operation.action.artifact_id,
        binding_fingerprint=operation.binding_fingerprint,
        provider=PROVIDER,
        sequence=sequence,
        page_number=1,
        requested_records=1,
        reserved_cost_usd=Decimal("0.001"),
        cost_basis="configured_upper_bound",
        started_at=NOW + timedelta(seconds=sequence),
    )


def test_binding_is_immutable_and_must_precede_prior_v2_artifacts(tmp_path: Path) -> None:
    path = tmp_path / "fresh.sqlite"
    _init_run(path)
    binding = _binding()
    assert bind_discovery_run(str(path), binding, NOW) == binding.fingerprint
    assert read_discovery_binding(str(path), RUN_ID) == binding
    assert bind_discovery_run(str(path), binding, NOW) == binding.fingerprint

    other = binding.model_copy(update={"exact_claim": "A different claim."})
    with pytest.raises(sqlite3.IntegrityError, match="conflicts"):
        bind_discovery_run(str(path), other, NOW)

    legacy_path = tmp_path / "legacy.sqlite"
    _init_run(legacy_path)
    # A v2 pipeline artifact is evidence that fresh discovery policy was not selected.
    old = V2DiscoveryOperation(
        run_id=RUN_ID,
        artifact_id=discovery_id(RUN_ID, "V2DiscoveryOperation", "old"),
        identity_key="old",
        binding_fingerprint="d" * 64,
        action=_operation(path).action,
        created_at=NOW,
    )
    insert_v2_artifact(str(legacy_path), "legacy-operation", old, NOW)
    with pytest.raises(ValueError, match="prior v2 artifacts"):
        bind_discovery_run(str(legacy_path), _binding(), NOW)


def test_durable_attempts_charge_unknown_starts_and_cannot_be_replayed(tmp_path: Path) -> None:
    path = tmp_path / "attempts.sqlite"
    _init_run(path)
    bind_discovery_run(str(path), _binding(), NOW)
    operation = _operation(path)
    first = reserve_provider_attempt(str(path), _start(operation))
    audit = provider_attempt_audit(str(path), RUN_ID)
    assert audit.interrupted_unknown == (first.artifact_id,)
    with pytest.raises(ValueError, match="unknown request outcome"):
        reserve_provider_attempt(str(path), _start(operation, sequence=2, key="unknown-retry"))
    failed = V2ProviderAttemptCompletion(
        run_id=RUN_ID,
        artifact_id=discovery_id(RUN_ID, "V2ProviderAttemptCompletion", "failed-first"),
        identity_key="failed-first",
        attempt_id=first.artifact_id,
        operation_id=operation.action.artifact_id,
        status="failed",
        failure=V2DiscoveryFailure(code="timeout", retryable=True, detail="provider_failure"),
        actual_cost_usd=Decimal("0.001"),
        cost_basis="reported",
        completed_at=NOW + timedelta(seconds=5),
    )
    complete_provider_attempt(str(path), failed, failed.completed_at)
    with pytest.raises(ValueError, match="dense"):
        reserve_provider_attempt(str(path), _start(operation, sequence=1, key="retry-1"))

    # A separately reserved retry consumes the same run budget and next sequence.
    second = reserve_provider_attempt(str(path), _start(operation, sequence=2, key="retry-2"))
    completion = V2ProviderAttemptCompletion(
        run_id=RUN_ID,
        artifact_id=discovery_id(RUN_ID, "V2ProviderAttemptCompletion", "complete-retry-2"),
        identity_key="complete-retry-2",
        attempt_id=second.artifact_id,
        operation_id=operation.action.artifact_id,
        status="completed",
        response_hash="e" * 64,
        metadata_records=1,
        actual_cost_usd=Decimal("0.001"),
        cost_basis="reported",
        completed_at=NOW + timedelta(seconds=10),
    )
    complete_provider_attempt(str(path), completion, completion.completed_at)
    assert provider_attempt_audit(str(path), RUN_ID).interrupted_unknown == ()
    with pytest.raises(ValueError, match="completed page"):
        reserve_provider_attempt(str(path), _start(operation, sequence=3, key="duplicate-page"))
    with pytest.raises(sqlite3.IntegrityError, match="replay conflicts"):
        changed = completion.model_copy(update={"metadata_records": 0})
        complete_provider_attempt(str(path), changed, changed.completed_at)


def test_reservation_race_has_one_winner_and_provider_budget_is_durable(tmp_path: Path) -> None:
    path = tmp_path / "race.sqlite"
    _init_run(path)
    bind_discovery_run(str(path), _binding(max_requests=1), NOW)
    operation = _operation(path)
    starts = [_start(operation, key=f"race-{index}") for index in range(2)]

    def reserve(start: V2ProviderAttemptStart) -> bool:
        try:
            reserve_provider_attempt(str(path), start)
        except ValueError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, starts))
    assert sum(results) == 1
    assert len(provider_attempt_audit(str(path), RUN_ID).starts) == 1


def test_read_only_artifact_reads_verify_hash_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "readonly.sqlite"
    _init_run(path)
    binding = _binding()
    bind_discovery_run(str(path), binding, NOW)
    before = path.stat().st_mtime_ns
    assert read_discovery_binding(str(path), RUN_ID) == binding
    assert read_v2_artifact(str(path), RUN_ID, "source-discovery-v1:V2DiscoveryBinding:binding")
    assert path.stat().st_mtime_ns == before

    conn = sqlite3.connect(path)
    conn.execute("DROP TRIGGER v2_artifacts_immutable_update")
    conn.execute(
        "UPDATE v2_artifacts SET payload_json = ? WHERE run_id = ? AND artifact_type = ?",
        ('{"broken":true}', str(RUN_ID), "V2DiscoveryBinding"),
    )
    conn.commit()
    conn.close()
    with pytest.raises(sqlite3.IntegrityError):
        read_discovery_binding(str(path), RUN_ID)


def test_round_four_transport_requires_persisted_governor_decision(tmp_path: Path) -> None:
    path = tmp_path / "round-four.sqlite"
    _init_run(path)
    binding = _binding()
    bind_discovery_run(str(path), binding, NOW)
    round_one = _operation(path)
    action = type(round_one.action).model_validate(
        round_one.action.model_copy(
            update={
                "round_number": 4,
                "artifact_id": discovery_id(RUN_ID, "V2IdentityLookupAction", "lookup-r4"),
                "identity_key": "lookup-r4",
            }
        ).model_dump(mode="python")
    )
    operation = V2DiscoveryOperation.model_validate(
        round_one.model_copy(
            update={
                "action": action,
                "artifact_id": discovery_id(RUN_ID, "V2DiscoveryOperation", "round-four"),
                "identity_key": "round-four",
            }
        ).model_dump(mode="python")
    )
    insert_discovery_operation(str(path), operation, NOW)
    with pytest.raises(ValueError, match="Governor authorization"):
        reserve_provider_attempt(str(path), _start(operation, key="round-four-attempt"))


def test_provider_budget_exposure_is_reserved_and_audit_is_derived(tmp_path: Path) -> None:
    path = tmp_path / "budget.sqlite"
    _init_run(path)
    binding = _binding(max_requests=3).model_copy(
        update={
            "provider_budgets": (
                V2DiscoveryProviderBudget(
                    provider=PROVIDER,
                    max_requests=3,
                    max_cost_usd=Decimal("0.001"),
                    cost_policy_identity="openalex-configured-upper-bound-v1",
                    reservation_per_request_usd=Decimal("0.001"),
                    cost_basis="configured_upper_bound",
                ),
            )
        }
    )
    binding = V2DiscoveryBinding.model_validate(binding.model_dump(mode="python"))
    bind_discovery_run(str(path), binding, NOW)
    operation = _operation(path)
    reserve_provider_attempt(str(path), _start(operation))
    retry_action = type(operation.action).model_validate(
        operation.action.model_copy(
            update={
                "identity_key": "lookup-2",
                "artifact_id": discovery_id(RUN_ID, "V2IdentityLookupAction", "lookup-2"),
            }
        ).model_dump(mode="python")
    )
    retry_operation = V2DiscoveryOperation.model_validate(
        operation.model_copy(
            update={
                "identity_key": "lookup-op-2",
                "artifact_id": discovery_id(RUN_ID, "V2DiscoveryOperation", "lookup-op-2"),
                "action": retry_action,
            }
        ).model_dump(mode="python")
    )
    insert_discovery_operation(str(path), retry_operation, NOW)
    with pytest.raises(ValueError, match="cost budget"):
        reserve_provider_attempt(str(path), _start(retry_operation, key="attempt-2"))
    counters = compute_discovery_audit_counters(str(path), RUN_ID)
    assert counters.http_requests == 1
    assert counters.unknown_requests == 1
