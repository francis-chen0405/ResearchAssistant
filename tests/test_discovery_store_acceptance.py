"""Acceptance tests for cross-artifact discovery ownership and bounded expansion."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from researchassistant.contracts.discovery_v2 import (
    V2DiscoveryBinding,
    V2DiscoveryOperation,
    V2DiscoveryPolicy,
    V2DiscoveryProviderBudget,
    V2ExpansionEdge,
    V2ExpansionResult,
    V2GraphNeighborAction,
    V2IdentityLookupAction,
    V2NormalizedDiscoveryCandidate,
    V2PreviewRequest,
    V2PreviewResult,
    V2PreviewSpan,
    V2ProviderAttemptCompletion,
    V2ProviderAttemptStart,
    V2ProviderCapabilities,
    V2RankComponents,
    V2RawDiscoveryCandidate,
    V2SeedEligibility,
    V2SourceLocation,
    V2WorkIdentity,
    discovery_id,
)
from researchassistant.contracts.model_contracts import DiscoveryProvider, SourceSnapshot
from researchassistant.contracts.model_research import (
    ResearchDirection,
    ResearchDirections,
    V2AcquiredSource,
    V2AcquisitionProbeOutput,
    V2AcquisitionProvider,
    V2PipelineIdentity,
    V2ProbePassage,
    V2ProbeResult,
    V2SurvivingSource,
)
from researchassistant.storage.discovery_store import (
    bind_discovery_run,
    complete_provider_attempt,
    insert_discovery_artifact,
    insert_discovery_candidate,
    insert_discovery_operation,
    insert_expansion_result,
    insert_preview,
    insert_raw_candidate,
    insert_seed_eligibility,
    provider_attempt_audit,
    read_discovery_artifact,
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
CLAIM = "The intervention changes the outcome."
RUN_ID = UUID("8eaf232a-c20b-4c93-a579-112ac61dc2f4")
PROVIDER = DiscoveryProvider.OPENALEX
RESPONSE_HASH = "a" * 64
DEFAULT_SNAPSHOT_ID = UUID("12322222-7c32-4771-a41e-8455ff099af9")


def _setup(
    path: Path,
    *,
    run_id: UUID = RUN_ID,
    policy: V2DiscoveryPolicy | None = None,
) -> V2DiscoveryOperation:
    init_db(str(path))
    insert_run(
        str(path),
        RunManifest(
            run_id=run_id,
            status=RunStatus.PLANNED,
            raw_claim=CLAIM,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    insert_v2_pipeline_identity(str(path), run_id, V2PipelineIdentity(), NOW)
    capability = V2ProviderCapabilities(
        provider=PROVIDER,
        search_modes=("lexical",),
        max_metadata_per_page=20,
        max_metadata_per_operation=20,
        pagination="none",
        identity_lookup=True,
        executable_identity_lookup=True,
        relationships=("references", "citing", "related"),
        executable_relationships=("references", "citing", "related"),
        executable_search_modes=("lexical",),
        documentation_urls=("https://docs.openalex.org/api-entities/works/search-works",),
    )
    selected_policy = policy or V2DiscoveryPolicy()
    binding = V2DiscoveryBinding(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2DiscoveryBinding", "binding"),
        identity_key="binding",
        exact_claim=CLAIM,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        providers=(PROVIDER,),
        policy=selected_policy,
        capabilities=(capability,),
        provider_budgets=(
            V2DiscoveryProviderBudget(
                provider=PROVIDER,
                max_requests=10,
                max_cost_usd=Decimal("0.01"),
                cost_policy_identity="fixture-upper-bound-v1",
                reservation_per_request_usd=Decimal("0.001"),
                cost_basis="configured_upper_bound",
            ),
        ),
        provider_configuration_hash="b" * 64,
        source_identity_hash="c" * 64,
        prompt_schema_hash="d" * 64,
    )
    bind_discovery_run(str(path), binding, NOW)
    action = V2IdentityLookupAction(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2IdentityLookupAction", "lookup"),
        identity_key="lookup",
        candidate_id=discovery_id(run_id, "V2RawDiscoveryCandidate", "raw"),
        work_identifier="https://doi.org/10.5555/example",
        provider=PROVIDER,
        direction=ResearchDirection.SUPPORT,
        round_number=1,
        policy=selected_policy,
        capabilities=capability,
    )
    operation = V2DiscoveryOperation(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2DiscoveryOperation", "operation-checkpoint"),
        identity_key="operation-checkpoint",
        binding_fingerprint=binding.fingerprint,
        action=action,
        created_at=NOW,
    )
    return insert_discovery_operation(str(path), operation, NOW)


def _start(
    path: Path,
    operation: V2DiscoveryOperation,
    *,
    key: str = "attempt",
    sequence: int = 1,
) -> V2ProviderAttemptStart:
    start = V2ProviderAttemptStart(
        run_id=operation.run_id,
        artifact_id=discovery_id(operation.run_id, "V2ProviderAttemptStart", key),
        identity_key=key,
        operation_id=operation.action.artifact_id,
        binding_fingerprint=operation.binding_fingerprint,
        provider=PROVIDER,
        sequence=sequence,
        page_number=1,
        requested_records=1,
        reserved_cost_usd=Decimal("0.001"),
        cost_basis="configured_upper_bound",
        started_at=NOW + timedelta(seconds=1),
    )
    return reserve_provider_attempt(str(path), start)


def _raw(
    run_id: UUID = RUN_ID,
    *,
    operation_id: UUID | None = None,
    attempt_id: UUID | None = None,
    response_hash: str = RESPONSE_HASH,
    key: str = "raw",
    work: V2WorkIdentity | None = None,
) -> V2RawDiscoveryCandidate:
    return V2RawDiscoveryCandidate(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2RawDiscoveryCandidate", key),
        identity_key=key,
        operation_id=operation_id or discovery_id(run_id, "V2IdentityLookupAction", "lookup"),
        attempt_id=attempt_id or discovery_id(run_id, "V2ProviderAttemptStart", "attempt"),
        provider=PROVIDER,
        direction=ResearchDirection.SUPPORT,
        round_number=1,
        provider_rank=1,
        response_hash=response_hash,
        work=work
        or V2WorkIdentity(
            grouping_key="doi:10.5555/example",
            doi="10.5555/example",
            provider_work_id="https://openalex.org/W123",
            resolution="verified_identifiers",
        ),
        locations=(
            V2SourceLocation(
                url="https://example.org/source",
                kind="landing",
                same_work_basis="provider_identity",
            ),
        ),
    )


def _normalized(
    raw: V2RawDiscoveryCandidate, *, key: str = "normalized"
) -> V2NormalizedDiscoveryCandidate:
    return V2NormalizedDiscoveryCandidate(
        run_id=raw.run_id,
        artifact_id=discovery_id(raw.run_id, "V2NormalizedDiscoveryCandidate", key),
        identity_key=key,
        raw_candidates=(raw,),
        work=raw.work,
        rank=V2RankComponents(rationale="Provider work identifier and DOI match."),
        disposition="retained",
        disposition_reason="Unique work candidate retained for further review.",
    )


@pytest.fixture
def _db_path(tmp_path: Path) -> Path:
    return tmp_path / "discovery.sqlite"


def _complete_fixture(path: Path) -> tuple[V2DiscoveryOperation, V2ProviderAttemptStart]:
    operation = _setup(path)
    start = _start(path, operation)
    completion = V2ProviderAttemptCompletion(
        run_id=operation.run_id,
        artifact_id=discovery_id(operation.run_id, "V2ProviderAttemptCompletion", "completion"),
        identity_key="completion",
        attempt_id=start.artifact_id,
        operation_id=operation.action.artifact_id,
        status="completed",
        response_hash=RESPONSE_HASH,
        result_ids=(discovery_id(operation.run_id, "V2RawDiscoveryCandidate", "raw"),),
        metadata_records=1,
        actual_cost_usd=Decimal("0.001"),
        cost_basis="reported",
        completed_at=NOW + timedelta(seconds=2),
    )
    complete_provider_attempt(str(path), completion, completion.completed_at)
    return operation, start


def _acquisition_output(
    run_id: UUID,
    source_id: UUID,
    *,
    snapshot_id: UUID = DEFAULT_SNAPSHOT_ID,
) -> V2AcquisitionProbeOutput:
    text = "The intervention changed the measured outcome in this study."
    snapshot_hash = hashlib.sha256(text.encode()).hexdigest()
    snapshot = SourceSnapshot(
        run_id=run_id,
        retrieval_attempt_id=UUID("54ab327b-7c32-4771-a41e-8455ff099af9"),
        snapshot_id=snapshot_id,
        source_url="https://example.org/source",
        retrieved_at=NOW,
        normalized_text=text,
        snapshot_sha256=snapshot_hash,
        word_count=len(text.split()),
        truncated=False,
        created_at=NOW,
    )
    passage_id = "fixture-passage-1"
    return V2AcquisitionProbeOutput(
        run_id=run_id,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        acquisitions=(
            V2AcquiredSource(
                cluster_id=source_id,
                direction=ResearchDirection.SUPPORT,
                snapshot=snapshot,
                provider=V2AcquisitionProvider.FIRECRAWL,
            ),
        ),
        attempts=(),
        probes=(
            V2ProbeResult(
                cluster_id=source_id,
                snapshot_id=snapshot.snapshot_id,
                snapshot_sha256=snapshot_hash,
                succeeded=True,
                passages=(
                    V2ProbePassage(
                        passage_id=passage_id,
                        snapshot_id=snapshot.snapshot_id,
                        snapshot_sha256=snapshot_hash,
                        source_cluster_id=source_id,
                        start_char=0,
                        end_char=len(text),
                        text=text,
                        score=1,
                        signals=("outcome",),
                    ),
                ),
            ),
        ),
        survivors=(
            V2SurvivingSource(
                cluster_id=source_id,
                direction=ResearchDirection.SUPPORT,
                snapshot_id=snapshot.snapshot_id,
                snapshot_sha256=snapshot_hash,
                passage_ids=(passage_id,),
            ),
        ),
        completed_at=NOW,
    )


def _persist_seed(
    path: Path,
    operation: V2DiscoveryOperation,
    *,
    seed_key: str = "seed-1",
) -> V2SeedEligibility:
    start = _start(path, operation, key=f"attempt-{seed_key}")
    completion = V2ProviderAttemptCompletion(
        run_id=operation.run_id,
        artifact_id=discovery_id(
            operation.run_id, "V2ProviderAttemptCompletion", f"completion-{seed_key}"
        ),
        identity_key=f"completion-{seed_key}",
        attempt_id=start.artifact_id,
        operation_id=operation.action.artifact_id,
        status="completed",
        response_hash=RESPONSE_HASH,
        result_ids=(discovery_id(operation.run_id, "V2RawDiscoveryCandidate", "raw"),),
        metadata_records=1,
        actual_cost_usd=Decimal("0.001"),
        cost_basis="reported",
        completed_at=NOW + timedelta(seconds=2),
    )
    complete_provider_attempt(str(path), completion, completion.completed_at)
    raw = _raw(attempt_id=start.artifact_id)
    normalized = _normalized(raw)
    insert_discovery_candidate(str(path), normalized, NOW + timedelta(seconds=3))
    source_id = UUID("a9c491d7-f471-41b0-bf79-1ce28764f894")
    output = _acquisition_output(operation.run_id, source_id)
    insert_v2_artifact(
        str(path), "phase-7-round-2-acquisition-probe", output, NOW + timedelta(seconds=4)
    )
    snapshot = output.acquisitions[0].snapshot
    seed = V2SeedEligibility(
        run_id=operation.run_id,
        artifact_id=discovery_id(operation.run_id, "V2SeedEligibility", seed_key),
        identity_key=seed_key,
        candidate_id=normalized.artifact_id,
        source_id=source_id,
        snapshot_id=snapshot.snapshot_id,
        work=normalized.work,
        eligible=True,
        reason="Candidate has a verified work identity and an acquired usable snapshot.",
    )
    return insert_seed_eligibility(str(path), seed, output, normalized, NOW + timedelta(seconds=5))


def _persist_distinct_candidate(path: Path, *, key: str) -> V2NormalizedDiscoveryCandidate:
    binding = read_discovery_binding(str(path), RUN_ID)
    action = V2IdentityLookupAction(
        run_id=RUN_ID,
        artifact_id=discovery_id(RUN_ID, "V2IdentityLookupAction", f"lookup-{key}"),
        identity_key=f"lookup-{key}",
        candidate_id=discovery_id(RUN_ID, "V2RawDiscoveryCandidate", key),
        work_identifier=f"https://doi.org/10.5555/{key}",
        provider=PROVIDER,
        direction=ResearchDirection.SUPPORT,
        round_number=1,
        policy=binding.policy,
        capabilities=binding.capabilities[0],
    )
    operation = V2DiscoveryOperation(
        run_id=RUN_ID,
        artifact_id=discovery_id(RUN_ID, "V2DiscoveryOperation", f"operation-{key}"),
        identity_key=f"operation-{key}",
        binding_fingerprint=binding.fingerprint,
        action=action,
        created_at=NOW + timedelta(seconds=11),
    )
    insert_discovery_operation(str(path), operation, NOW + timedelta(seconds=11))
    start = _start(path, operation, key=f"attempt-{key}")
    work = V2WorkIdentity(
        grouping_key=f"doi:10.5555/{key}",
        doi=f"10.5555/{key}",
        provider_work_id=f"https://openalex.org/{key}",
        resolution="verified_identifiers",
    )
    raw = _raw(
        operation_id=action.artifact_id,
        attempt_id=start.artifact_id,
        key=key,
        work=work,
    )
    completion = V2ProviderAttemptCompletion(
        run_id=RUN_ID,
        artifact_id=discovery_id(RUN_ID, "V2ProviderAttemptCompletion", f"completion-{key}"),
        identity_key=f"completion-{key}",
        attempt_id=start.artifact_id,
        operation_id=action.artifact_id,
        status="completed",
        response_hash=RESPONSE_HASH,
        result_ids=(raw.artifact_id,),
        metadata_records=1,
        actual_cost_usd=Decimal("0.001"),
        cost_basis="reported",
        completed_at=NOW + timedelta(seconds=12),
    )
    complete_provider_attempt(str(path), completion, completion.completed_at)
    candidate = _normalized(raw, key=f"normalized-{key}")
    return insert_discovery_candidate(str(path), candidate, NOW + timedelta(seconds=13))


def _persist_graph_expansion(
    path: Path,
    seed: V2SeedEligibility,
    *,
    action_key: str,
    relationship: str,
    work_key: str,
) -> V2ExpansionResult:
    binding = read_discovery_binding(str(path), seed.run_id)
    action = V2GraphNeighborAction(
        run_id=seed.run_id,
        artifact_id=discovery_id(seed.run_id, "V2GraphNeighborAction", action_key),
        identity_key=action_key,
        seed=seed,
        relationship=relationship,  # type: ignore[arg-type]
        provider=PROVIDER,
        direction=ResearchDirection.SUPPORT,
        round_number=1,
        requested_depth=1,
        policy=binding.policy,
        capabilities=binding.capabilities[0],
    )
    operation = V2DiscoveryOperation(
        run_id=seed.run_id,
        artifact_id=discovery_id(seed.run_id, "V2DiscoveryOperation", f"operation-{action_key}"),
        identity_key=f"operation-{action_key}",
        binding_fingerprint=binding.fingerprint,
        action=action,
        created_at=NOW + timedelta(seconds=6),
    )
    insert_discovery_operation(str(path), operation, NOW + timedelta(seconds=6))
    start = _start(path, operation, key=f"attempt-{action_key}")
    raw = _raw(
        operation_id=action.artifact_id,
        attempt_id=start.artifact_id,
        key=work_key,
        work=V2WorkIdentity(
            grouping_key=f"doi:10.5555/{work_key}",
            doi=f"10.5555/{work_key}",
            provider_work_id=f"https://openalex.org/{work_key}",
            resolution="verified_identifiers",
        ),
    )
    completion = V2ProviderAttemptCompletion(
        run_id=seed.run_id,
        artifact_id=discovery_id(
            seed.run_id, "V2ProviderAttemptCompletion", f"completion-{action_key}"
        ),
        identity_key=f"completion-{action_key}",
        attempt_id=start.artifact_id,
        operation_id=action.artifact_id,
        status="completed",
        response_hash=RESPONSE_HASH,
        result_ids=(raw.artifact_id,),
        metadata_records=1,
        actual_cost_usd=Decimal("0.001"),
        cost_basis="reported",
        completed_at=NOW + timedelta(seconds=7),
    )
    complete_provider_attempt(str(path), completion, completion.completed_at)
    insert_raw_candidate(str(path), raw, NOW + timedelta(seconds=8))
    edge = V2ExpansionEdge(
        run_id=seed.run_id,
        artifact_id=discovery_id(seed.run_id, "V2ExpansionEdge", f"edge-{action_key}"),
        identity_key=f"edge-{action_key}",
        action=action,
        candidate=raw,
        edge_verification="provider_reported",
    )
    result = V2ExpansionResult(
        run_id=seed.run_id,
        artifact_id=discovery_id(seed.run_id, "V2ExpansionResult", f"result-{action_key}"),
        identity_key=f"result-{action_key}",
        action=action,
        edges=(edge,),
        status="completed",
        reason="One provider-reported neighbor retained for review.",
    )
    return insert_expansion_result(str(path), result, NOW + timedelta(seconds=9))


def test_raw_candidate_requires_exact_completed_attempt_response_and_result_id(
    _db_path: Path,
) -> None:
    operation, start = _complete_fixture(_db_path)
    good = _raw()
    assert insert_raw_candidate(str(_db_path), good, NOW + timedelta(seconds=3)) == good

    wrong_hash = _raw(key="wrong-hash", response_hash="e" * 64)
    with pytest.raises(ValueError, match="response hash"):
        insert_raw_candidate(str(_db_path), wrong_hash, NOW + timedelta(seconds=4))

    wrong_id = _raw(key="unreturned")
    with pytest.raises(ValueError, match="was not returned"):
        insert_raw_candidate(str(_db_path), wrong_id, NOW + timedelta(seconds=5))

    wrong_attempt = _raw(
        key="wrong-attempt",
        attempt_id=discovery_id(RUN_ID, "V2ProviderAttemptStart", "other"),
    )
    with pytest.raises(ValueError, match="durable attempt"):
        insert_raw_candidate(str(_db_path), wrong_attempt, NOW + timedelta(seconds=6))
    assert provider_attempt_audit(str(_db_path), RUN_ID).starts == (start,)


def test_normalized_candidate_rejects_cross_run_raw_and_binds_persisted_raw(_db_path: Path) -> None:
    operation, _ = _complete_fixture(_db_path)
    raw = _raw()
    normalized = _normalized(raw)
    assert (
        insert_discovery_candidate(str(_db_path), normalized, NOW + timedelta(seconds=3))
        == normalized
    )
    assert read_v2_artifact(
        str(_db_path), RUN_ID, "source-discovery-v1:V2RawDiscoveryCandidate:raw"
    )

    other_run = UUID("8c66ee71-01e5-4bf0-9a3f-59c23c58100c")
    foreign_raw = _raw(other_run, key="foreign")
    with pytest.raises(ValidationError, match="cross-run"):
        V2NormalizedDiscoveryCandidate(
            run_id=RUN_ID,
            artifact_id=discovery_id(RUN_ID, "V2NormalizedDiscoveryCandidate", "foreign-parent"),
            identity_key="foreign-parent",
            raw_candidates=(foreign_raw,),
            work=foreign_raw.work,
            rank=V2RankComponents(rationale="fixture"),
            disposition="retained",
            disposition_reason="fixture",
        )
    wrong_operation = _raw(
        key="wrong-operation",
        operation_id=discovery_id(RUN_ID, "V2IdentityLookupAction", "other"),
    )
    with pytest.raises(KeyError):
        insert_raw_candidate(str(_db_path), wrong_operation, NOW + timedelta(seconds=4))


def test_seed_cap_is_enforced_across_the_entire_run(_db_path: Path) -> None:
    operation = _setup(_db_path, policy=V2DiscoveryPolicy(max_seeds_per_run=1))
    _persist_seed(_db_path, operation)
    candidate = _persist_distinct_candidate(_db_path, key="distinct-seed")
    source_id = UUID("a9c491d7-f471-41b0-bf79-1ce28764f894")
    output = _acquisition_output(RUN_ID, source_id)
    second_seed = V2SeedEligibility(
        run_id=RUN_ID,
        artifact_id=discovery_id(RUN_ID, "V2SeedEligibility", "seed-2"),
        identity_key="seed-2",
        candidate_id=candidate.artifact_id,
        source_id=source_id,
        snapshot_id=output.acquisitions[0].snapshot.snapshot_id,
        work=candidate.work,
        eligible=True,
        reason="A second seed candidate for the cap boundary.",
    )
    with pytest.raises(ValueError, match="seed cap"):
        insert_seed_eligibility(
            str(_db_path), second_seed, output, candidate, NOW + timedelta(seconds=10)
        )


@pytest.mark.parametrize(
    ("max_neighbors", "max_expansion", "message", "separate_seed"),
    (
        (1, 1, "run expansion candidate cap", True),
        (1, 2, "per-seed expansion cap", False),
    ),
)
def test_expansion_caps_accumulate_across_relationship_actions(
    tmp_path: Path,
    max_neighbors: int,
    max_expansion: int,
    message: str,
    separate_seed: bool,
) -> None:
    path = tmp_path / f"expansion-{max_neighbors}-{max_expansion}.sqlite"
    policy = V2DiscoveryPolicy(
        max_seeds_per_run=2 if separate_seed else 1,
        max_neighbors_per_seed=max_neighbors,
        max_expansion_per_run=max_expansion,
    )
    operation = _setup(path, policy=policy)
    seed = _persist_seed(path, operation)
    second_seed = seed
    if separate_seed:
        candidate_envelope = read_v2_artifact(
            str(path), RUN_ID, "source-discovery-v1:V2NormalizedDiscoveryCandidate:normalized"
        )
        candidate = V2NormalizedDiscoveryCandidate.model_validate_json(
            candidate_envelope.payload_json
        )
        source_id = UUID("a9c491d7-f471-41b0-bf79-1ce28764f894")
        output = _acquisition_output(RUN_ID, source_id)
        second_seed = V2SeedEligibility(
            run_id=RUN_ID,
            artifact_id=discovery_id(RUN_ID, "V2SeedEligibility", "seed-2"),
            identity_key="seed-2",
            candidate_id=seed.candidate_id,
            source_id=source_id,
            snapshot_id=output.acquisitions[0].snapshot.snapshot_id,
            work=seed.work,
            eligible=True,
            reason="A separate seed record for testing the run-wide expansion cap.",
        )
        insert_seed_eligibility(
            str(path), second_seed, output, candidate, NOW + timedelta(seconds=10)
        )
    _persist_graph_expansion(
        path,
        seed,
        action_key="graph-references",
        relationship="references",
        work_key="neighbor-one",
    )
    with pytest.raises(ValueError, match=message):
        _persist_graph_expansion(
            path,
            second_seed,
            action_key="graph-citing",
            relationship="citing",
            work_key="neighbor-two",
        )


def _preview_result(
    *,
    run_id: UUID,
    output: V2AcquisitionProbeOutput,
    claim: str = CLAIM,
    request_key: str = "preview-request",
    result_key: str = "preview-result",
) -> V2PreviewResult:
    source = output.acquisitions[0]
    text = source.snapshot.normalized_text
    span_text = "changed the measured outcome"
    start = text.index(span_text)
    request = V2PreviewRequest(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2PreviewRequest", request_key),
        identity_key=request_key,
        exact_claim=claim,
        direction=source.direction,
        directions=output.directions,
        source_id=source.cluster_id,
        snapshot_id=source.snapshot.snapshot_id,
        snapshot_hash=source.snapshot.snapshot_sha256,
    )
    return V2PreviewResult(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2PreviewResult", result_key),
        identity_key=result_key,
        request=request,
        spans=(
            V2PreviewSpan(
                start=start,
                end=start + len(span_text),
                text=span_text,
                section="results",
                context_before=text[:start],
                context_after=text[start + len(span_text) :],
                relevance_signals=("outcome",),
            ),
        ),
        content_classification="full_text",
        outcome="completed",
        reason="Exact result span matches the immutable acquired snapshot.",
    )


def test_preview_binds_nested_claim_and_immutable_stored_acquisition(_db_path: Path) -> None:
    _setup(_db_path)
    source_id = UUID("a9c491d7-f471-41b0-bf79-1ce28764f894")
    stored_output = _acquisition_output(RUN_ID, source_id)
    insert_v2_artifact(
        str(_db_path),
        "phase-7-round-2-acquisition-probe",
        stored_output,
        NOW,
    )

    wrong_claim = _preview_result(
        run_id=RUN_ID,
        output=stored_output,
        claim="A different claim from the frozen run.",
        request_key="wrong-claim-request",
        result_key="wrong-claim-result",
    )
    with pytest.raises(ValueError, match="claim differs"):
        insert_preview(str(_db_path), wrong_claim, stored_output, NOW + timedelta(seconds=1))

    valid = _preview_result(run_id=RUN_ID, output=stored_output)
    altered_output = _acquisition_output(
        RUN_ID,
        source_id,
        snapshot_id=UUID("32322222-7c32-4771-a41e-8455ff099af9"),
    )
    with pytest.raises(ValueError, match="immutable acquisition output"):
        insert_preview(str(_db_path), valid, altered_output, NOW + timedelta(seconds=2))
    assert insert_preview(str(_db_path), valid, stored_output, NOW + timedelta(seconds=2)) == valid


def test_discovery_typed_reader_dispatch_and_payload_hash_corruption(tmp_path: Path) -> None:
    path = tmp_path / "typed-read.sqlite"
    _setup(path)
    binding = read_discovery_binding(str(path), RUN_ID)
    assert insert_discovery_artifact(str(path), binding, NOW) == binding
    assert read_discovery_artifact(str(path), RUN_ID, "V2DiscoveryBinding", "binding") == binding
    with pytest.raises(ValueError, match="unregistered"):
        read_discovery_artifact(str(path), RUN_ID, "V2Unknown", "binding")

    conn = sqlite3.connect(path)
    conn.execute("DROP TRIGGER v2_artifacts_immutable_update")
    conn.execute(
        "UPDATE v2_artifacts SET payload_json = ? WHERE run_id = ? AND artifact_type = ?",
        ('{"broken":true}', str(RUN_ID), "V2DiscoveryBinding"),
    )
    conn.commit()
    conn.close()
    with pytest.raises(sqlite3.IntegrityError):
        read_discovery_artifact(str(path), RUN_ID, "V2DiscoveryBinding", "binding")
