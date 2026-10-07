"""Fake page execution proves Phase-1 ownership and accounting without paid transports."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from test_discovery_store import NOW, RUN_ID, _binding, _init_run

from researchassistant.contracts.discovery_v2 import (
    V2CompiledQueryAction,
    V2ConceptGroup,
    V2ConceptualQuery,
    V2DiscoveryBinding,
    V2DiscoveryOperation,
    V2DiscoveryPolicy,
    V2ProviderAttemptCompletion,
    V2ProviderAttemptStart,
    V2ProviderCapabilities,
    discovery_hash,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider
from researchassistant.contracts.model_research import ResearchDirection
from researchassistant.storage.discovery_store import (
    bind_discovery_run,
    complete_provider_attempt,
    compute_discovery_audit_counters,
    insert_discovery_operation,
    read_discovery_artifact,
    reserve_provider_attempt,
)


def _compiled_setup(
    path: Path,
    provider: DiscoveryProvider = DiscoveryProvider.OPENALEX,
    physical_requests_per_page: int = 1,
) -> V2DiscoveryOperation:
    _init_run(path)
    previous = _binding()
    capability = V2ProviderCapabilities.model_validate(
        previous.capabilities[0]
        .model_copy(
            update={
                "max_metadata_per_page": 20,
                "max_metadata_per_operation": 50,
                "provider": provider,
                "physical_requests_per_page": physical_requests_per_page,
                "pagination": "page",
                "executable_pagination": "page",
            }
        )
        .model_dump(mode="python")
    )
    policy = V2DiscoveryPolicy(metadata_depth=50)
    binding = V2DiscoveryBinding.model_validate(
        previous.model_copy(
            update={
                "policy": policy,
                "capabilities": (capability,),
                "providers": (provider,),
                "provider_budgets": (
                    previous.provider_budgets[0].model_copy(update={"provider": provider}),
                ),
            }
        ).model_dump(mode="python")
    )
    bind_discovery_run(str(path), binding, NOW)
    concept = V2ConceptualQuery(
        run_id=RUN_ID,
        artifact_id=discovery_id(RUN_ID, "V2ConceptualQuery", "query"),
        identity_key="query",
        required_concepts=(V2ConceptGroup(concept="intervention"),),
        purpose="broad",
        provider=provider,
        direction=ResearchDirection.SUPPORT,
        round_number=1,
    )
    fields = dict(
        run_id=str(RUN_ID),
        artifact_id=str(discovery_id(RUN_ID, "V2CompiledQueryAction", "compiled")),
        identity_key="compiled",
        contract_identity="source-discovery-contracts-v1",
        action_type="query",
        conceptual_query=concept.model_dump(mode="json"),
        query_text="intervention",
        parameters=[],
        mode="lexical",
        requested_depth=50,
        effective_depth=min(50, 20 * (3 // physical_requests_per_page)),
        compiler_identity="source-query-compiler-v1",
        policy=policy.model_dump(mode="json"),
        capabilities=capability.model_dump(mode="json"),
    )
    fingerprint = discovery_hash(json.dumps(fields, sort_keys=True, separators=(",", ":")))
    action = V2CompiledQueryAction.model_validate(dict(fields, fingerprint=fingerprint))
    assert V2CompiledQueryAction.model_validate_json(action.model_dump_json()) == action
    operation = V2DiscoveryOperation(
        run_id=RUN_ID,
        artifact_id=discovery_id(RUN_ID, "V2DiscoveryOperation", "query-operation"),
        identity_key="query-operation",
        binding_fingerprint=binding.fingerprint,
        action=action,
        created_at=NOW,
    )
    return insert_discovery_operation(str(path), operation, NOW)


def _page(
    operation: V2DiscoveryOperation, sequence: int, page: int, records: int
) -> V2ProviderAttemptStart:
    key = f"page-{sequence}"
    return V2ProviderAttemptStart(
        run_id=RUN_ID,
        artifact_id=discovery_id(RUN_ID, "V2ProviderAttemptStart", key),
        identity_key=key,
        operation_id=operation.action.artifact_id,
        binding_fingerprint=operation.binding_fingerprint,
        provider=operation.action.capabilities.provider,
        sequence=sequence,
        page_number=page,
        requested_records=records,
        reserved_cost_usd=Decimal("0.001"),
        cost_basis="configured_upper_bound",
        started_at=NOW + timedelta(seconds=sequence),
    )


def _complete(path: Path, start: V2ProviderAttemptStart) -> V2ProviderAttemptCompletion:
    key = f"complete-{start.sequence}"
    completion = V2ProviderAttemptCompletion(
        run_id=RUN_ID,
        artifact_id=discovery_id(RUN_ID, "V2ProviderAttemptCompletion", key),
        identity_key=key,
        attempt_id=start.artifact_id,
        operation_id=start.operation_id,
        status="completed",
        response_hash="a" * 64,
        metadata_records=start.requested_records,
        actual_cost_usd=Decimal("0.001"),
        cost_basis="reported",
        completed_at=start.started_at + timedelta(milliseconds=1),
    )
    return complete_provider_attempt(str(path), completion, completion.completed_at)


def test_three_pages_have_three_durable_reservations_and_distinct_audit_counts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pages.sqlite"
    operation = _compiled_setup(path)
    for sequence, records in ((1, 20), (2, 20), (3, 10)):
        start = reserve_provider_attempt(str(path), _page(operation, sequence, sequence, records))
        _complete(path, start)
    counters = compute_discovery_audit_counters(str(path), RUN_ID)
    assert counters.logical_queries == 1
    assert counters.http_requests == 3
    assert counters.metadata_records == 50
    assert counters.unique_work_candidates == 0
    assert (
        counters.acquisition_attempts
        == counters.usable_snapshots
        == counters.admitted_evidence
        == 0
    )
    assert counters.unknown_requests == 0
    restored = read_discovery_artifact(str(path), RUN_ID, "V2DiscoveryOperation", "query-operation")
    assert restored == operation


def test_completed_page_replay_and_excess_cumulative_depth_cannot_start_transport(
    tmp_path: Path,
) -> None:
    path = tmp_path / "replays.sqlite"
    operation = _compiled_setup(path)
    start = reserve_provider_attempt(str(path), _page(operation, 1, 1, 20))
    completion = _complete(path, start)
    assert complete_provider_attempt(str(path), completion, completion.completed_at) == completion
    with pytest.raises(ValueError, match="completed page"):
        reserve_provider_attempt(str(path), _page(operation, 2, 1, 20))
    second = reserve_provider_attempt(str(path), _page(operation, 2, 2, 20))
    _complete(path, second)
    with pytest.raises(ValueError, match="cumulative page depth"):
        reserve_provider_attempt(str(path), _page(operation, 3, 3, 20))
    assert compute_discovery_audit_counters(str(path), RUN_ID).http_requests == 2


def test_validated_inspection_preserves_new_and_historical_bytes(tmp_path: Path) -> None:
    from hashlib import sha256

    from researchassistant.storage.discovery_store import inspect_discovery_run

    legacy_path = tmp_path / "legacy.sqlite"
    _init_run(legacy_path)
    original = legacy_path.read_bytes()
    old = inspect_discovery_run(str(legacy_path), RUN_ID)
    assert old.artifacts == ()
    assert old.counters is None
    assert legacy_path.read_bytes() == original
    path = tmp_path / "new.sqlite"
    operation = _compiled_setup(path)
    start = reserve_provider_attempt(str(path), _page(operation, 1, 1, 20))
    _complete(path, start)
    original_hash = sha256(path.read_bytes()).hexdigest()
    inspection = inspect_discovery_run(str(path), RUN_ID)
    assert operation in inspection.artifacts
    assert inspection.counters is not None
    assert inspection.counters.http_requests == 1
    assert inspection.counters.metadata_records == 20
    assert sha256(path.read_bytes()).hexdigest() == original_hash


def test_pubmed_search_and_summary_each_require_a_distinct_durable_reservation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pubmed.sqlite"
    operation = _compiled_setup(path, DiscoveryProvider.PUBMED, physical_requests_per_page=2)
    primary = reserve_provider_attempt(str(path), _page(operation, 1, 1, 20))
    response = _complete(path, primary)
    fields = _page(operation, 2, 1, 20).model_dump(mode="python")
    fields.update(
        request_kind="metadata",
        parent_attempt_id=primary.artifact_id,
        parent_response_hash=response.response_hash,
    )
    invalid = V2ProviderAttemptStart.model_validate(dict(fields, parent_response_hash="b" * 64))
    with pytest.raises(ValueError, match="parent response ownership"):
        reserve_provider_attempt(str(path), invalid)
    summary = reserve_provider_attempt(str(path), V2ProviderAttemptStart.model_validate(fields))
    assert compute_discovery_audit_counters(str(path), RUN_ID).http_requests == 2
    _complete(path, summary)
    counters = compute_discovery_audit_counters(str(path), RUN_ID)
    assert counters.logical_queries == 1
    assert counters.http_requests == 2
    assert counters.metadata_records == 40  # UID response plus bibliographic response.
    with pytest.raises(ValueError, match="completed page"):
        reserve_provider_attempt(
            str(path),
            V2ProviderAttemptStart.model_validate(
                dict(
                    fields,
                    sequence=3,
                    identity_key="page-3",
                    artifact_id=discovery_id(RUN_ID, "V2ProviderAttemptStart", "page-3"),
                )
            ),
        )


def test_pubmed_effective_depth_accounts_for_both_physical_requests() -> None:
    from researchassistant.research.discovery_capabilities import get_provider_capabilities
    from researchassistant.research.discovery_policy import effective_metadata_depth

    capability = get_provider_capabilities(DiscoveryProvider.PUBMED)
    assert capability.physical_requests_per_page == 2
    assert effective_metadata_depth(V2DiscoveryPolicy(), capability, 20, remaining_requests=1) == 0
    assert effective_metadata_depth(V2DiscoveryPolicy(), capability, 20, remaining_requests=2) == 20


def test_native_pagination_cannot_be_misstated_as_executable_depth() -> None:
    from pydantic import ValidationError

    from researchassistant.research.discovery_capabilities import get_provider_capabilities
    from researchassistant.research.discovery_policy import effective_metadata_depth

    capability = get_provider_capabilities(DiscoveryProvider.SERPSEARCH)
    assert capability.pagination == "page"
    assert capability.executable_pagination == "none"
    policy = V2DiscoveryPolicy()
    assert effective_metadata_depth(policy, capability, 20, 3) == 10
    assert effective_metadata_depth(policy, capability, 20, 3, executable=False) == 20
    with pytest.raises(ValidationError, match="matching native support"):
        V2ProviderCapabilities.model_validate(
            capability.model_copy(update={"executable_pagination": "cursor"}).model_dump(
                mode="python"
            )
        )


def test_provider_identity_urls_cannot_serialize_query_credentials() -> None:
    from pydantic import ValidationError

    from researchassistant.contracts.discovery_v2 import V2WorkIdentity

    with pytest.raises(ValidationError, match="credential-bearing"):
        V2WorkIdentity(
            grouping_key="opaque-work",
            provider_work_id="https://works.test/1?api_key=secret",
            resolution="provider_identity",
        )
