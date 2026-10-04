"""Explicit, read-only contract dispatch. No fallback is used by research resume.

Hashes authenticate stored bytes, not an assertion that historical policy is current.
All decoded historical objects carry an inspection-only marker and cannot be written
through Ledger/artifact admission. Unknown identities yield a per-record result.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Literal, TypeVar

from pydantic import model_validator

from researchassistant.contracts.historical import (
    AugustLedgerRecord,
    HistoricalRead,
    RecordCompatibilityError,
    RecordCompatibilityResult,
)
from researchassistant.contracts.models import (
    LedgerRecord,
    PersistedStageArtifact,
    ProviderRunContract,
    SourceSnapshot,
    StrictModel,
    V2DeepAnalysisBackfillResult,
    V2EvidenceAnalystBatchInput,
    V2EvidenceAnalystBatchResult,
    V2EvidenceAnalystState,
    V2PersistedArtifact,
    V2ReviewerLedgerBatchResult,
    V2SourceSelectionQueueResult,
)

ModelT = TypeVar("ModelT", bound=StrictModel)
AUGUST_SCHEMA = "d082c3c69733fbd7dd4b99856b3b3dace9bd91708a3447d93888da09e7242397"
AUGUST_PROMPTS = "90a906ecd8103a388cfcc04cf1024b1acc0c376e405ff865c54070f807ec4478"
AUGUST_POLICY = (
    "mvp3b-direct-mimo-one-retry-v1|mvp3b-direct-mimo-reserve-reconcile-v1|"
    "xiaomi-mimo-price-cap-2026-07-15-v1|"
    "9a3f54f0d90e66601bac30144b0cefd6f189000288d304a220d80119cce1e961|"
    "836beefaf32535362f82aa2e5a958e6fbcf825e1e1b7a3384461aed300ec7234|rank5-keep3"
)


def _incompatible(key: str, kind: str, message: str) -> RecordCompatibilityError:
    return RecordCompatibilityError(
        RecordCompatibilityResult(
            record_key=key,
            artifact_type=kind,
            message=message,
        )
    )


def _validated_contract(contract: ProviderRunContract, key: str, kind: str) -> None:
    try:
        ProviderRunContract.model_validate(contract.model_dump())
    except ValueError as exc:
        raise _incompatible(key, kind, "recorded provider fingerprint/identity is invalid") from exc


def decode_ledger(values: dict[str, Any], contract: ProviderRunContract | None) -> LedgerRecord:
    key = str(values.get("ledger_claim_id", "unknown-ledger"))
    try:
        return LedgerRecord.model_validate(values)
    except ValueError:
        pass
    if contract is None or (
        contract.schema_identity,
        contract.prompt_identity,
        contract.policy_identity,
    ) != (AUGUST_SCHEMA, AUGUST_PROMPTS, AUGUST_POLICY):
        raise _incompatible(key, "LedgerRecord", "unsupported recorded Ledger contract identity")
    # Recheck the canonical provider fingerprint even for caller-constructed models.
    _validated_contract(contract, key, "LedgerRecord")
    if str(contract.run_id) != str(values.get("run_id")):
        raise _incompatible(key, "LedgerRecord", "record does not match its provider run")
    try:
        return AugustLedgerRecord.model_validate(values)
    except ValueError as exc:
        raise _incompatible(key, "LedgerRecord", "invalid recorded phase8 Ledger shape") from exc


def verify_historical_snapshot(record: LedgerRecord, snapshot: SourceSnapshot) -> None:
    """Check the immutable original snapshot relationship and content hash."""
    if (
        record.run_id != snapshot.run_id
        or record.snapshot_id != snapshot.snapshot_id
        or record.retrieval_attempt_id != snapshot.retrieval_attempt_id
        or record.snapshot_sha256 != snapshot.snapshot_sha256
        or sha256(snapshot.normalized_text.encode("utf-8")).hexdigest() != snapshot.snapshot_sha256
    ):
        raise _incompatible(
            str(record.ledger_claim_id),
            "LedgerRecord",
            "historical snapshot provenance/hash mismatch",
        )


def _verify_snapshot_payloads(payload: Any, key: str, kind: str) -> None:
    if isinstance(payload, dict):
        if "normalized_text" in payload and "snapshot_sha256" in payload:
            text = payload["normalized_text"]
            if not isinstance(text, str) or (
                sha256(text.encode("utf-8")).hexdigest() != payload["snapshot_sha256"]
            ):
                raise _incompatible(key, kind, "stored snapshot content hash mismatch")
        for value in payload.values():
            _verify_snapshot_payloads(value, key, kind)
    elif isinstance(payload, list):
        for value in payload:
            _verify_snapshot_payloads(value, key, kind)


class Phase8QueueResult(V2SourceSelectionQueueResult, HistoricalRead):
    physical_calls_per_source: Literal[7, 12]
    source_physical_call_cap: Literal[7, 12] | None = None
    mandatory_synthesis_physical_calls: Literal[2]

    @model_validator(mode="after")
    def validate_historical_policy(self) -> Phase8QueueResult:
        if self.input.policy_identity != "researchassistant-v2-phase-8-source-selection-v1":
            raise ValueError("unsupported historical queue policy")
        return self


class Phase9AnalystInput(V2EvidenceAnalystBatchInput, HistoricalRead):
    queue_result: Phase8QueueResult
    policy_identity: Literal[
        "researchassistant-v2-phase-9-luna-evidence-analyst-v1",
        "researchassistant-v2-phase-9-luna-evidence-analyst-v2",
    ]

    @model_validator(mode="after")
    def validate_complete_queue(self) -> Phase9AnalystInput:
        # Historical policy names differ; run/claim/direction/candidate checks remain.
        if self.queue_result.run_id != self.run_id:
            raise ValueError("historical Analyst queue must match the run")
        if self.queue_result.input.exact_claim != self.exact_claim:
            raise ValueError("historical Analyst claim must match its queue")
        if self.queue_result.input.directions != self.directions:
            raise ValueError("historical Analyst directions must match its queue")
        source_ids = tuple(item.source_id for item in self.queued_candidates)
        failures = tuple(item.source_id for item in self.extraction_failures)
        expected = tuple(
            source_id
            for source_id in self.queue_result.queued_source_ids
            if source_id in set(source_ids)
        )
        if source_ids != expected or len(source_ids) != len(set(source_ids)):
            raise ValueError("historical candidates must retain unique queue order")
        if len(failures) != len(set(failures)) or not set(failures).issubset(
            self.queue_result.queued_source_ids
        ):
            raise ValueError("historical failures must retain unique queued sources")
        survivors = {item.source_id: item for item in self.queue_result.input.survivors}
        for item in self.queued_candidates:
            if (
                item.candidate.run_id != self.run_id
                or item.direction is not survivors[item.source_id].direction
            ):
                raise ValueError("historical candidate provenance cannot change")
            self.directions.require_permitted(item.direction)
        return self


class Phase9AnalystResult(V2EvidenceAnalystBatchResult, HistoricalRead):
    input: Phase9AnalystInput
    # Early batches recorded identity only in their input; absence stays unknown.
    policy_identity: (
        Literal[
            "researchassistant-v2-phase-9-luna-evidence-analyst-v1",
            "researchassistant-v2-phase-9-luna-evidence-analyst-v2",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_complete_survivor_output(self) -> Phase9AnalystResult:
        if self.input.run_id != self.run_id:
            raise ValueError("Phase-9 result must match its input run")
        if self.policy_identity is not None and self.policy_identity != self.input.policy_identity:
            raise ValueError("Phase-9 result policy identity must match its input")
        expected = tuple(item.source_id for item in self.input.queue_result.input.survivors)
        actual = tuple(item.source_id for item in self.source_results)
        if actual != expected or len(actual) != len(set(actual)):
            raise ValueError("Phase-9 output must retain every survivor in Phase-8 order")
        directions = {
            item.source_id: item.direction for item in self.input.queue_result.input.survivors
        }
        queued = set(self.input.queue_result.queued_source_ids)
        for item in self.source_results:
            if item.run_id != self.run_id:
                raise ValueError("Phase-9 source results must match the run")
            if item.direction is not directions[item.source_id]:
                raise ValueError("Phase-9 survivor direction cannot change")
            if (item.source_id in queued) == (item.state is V2EvidenceAnalystState.NOT_QUEUED):
                raise ValueError("Phase-9 queued state must match Phase-8")
        return self


class Phase10ReviewerResult(V2ReviewerLedgerBatchResult, HistoricalRead):
    analyst_result: Phase9AnalystResult
    policy_identity: Literal[
        "researchassistant-v2-phase-10-reviewer-ledger-v1",
        "researchassistant-v2-phase-10-reviewer-ledger-v2",
    ]


class Phase12BackfillResult(V2DeepAnalysisBackfillResult, HistoricalRead):
    final_queue_result: Phase8QueueResult
    final_admission_result: None = None
    final_reviewer_result: Phase10ReviewerResult
    policy_identity: Literal["researchassistant-v2-phase-12-deep-analysis-backfill-v1"]


def decode_v2_artifact(artifact: V2PersistedArtifact, model_type: type[ModelT]) -> ModelT:
    """Decode an envelope whose original bytes/hash are retained by the caller."""
    key, kind = artifact.artifact_key, artifact.artifact_type
    if kind != model_type.__name__:
        raise _incompatible(key, kind, "artifact type does not match the requested contract")
    if sha256(artifact.payload_json.encode("utf-8")).hexdigest() != artifact.payload_sha256:
        raise _incompatible(key, kind, "stored artifact hash mismatch")
    try:
        payload = json.loads(artifact.payload_json)
    except ValueError as exc:
        raise _incompatible(
            artifact.artifact_key, artifact.artifact_type, "invalid stored JSON"
        ) from exc
    if not isinstance(payload, dict) or str(payload.get("run_id")) != str(artifact.run_id):
        raise _incompatible(key, kind, "artifact run identity mismatch")
    _verify_snapshot_payloads(payload, key, kind)
    supported_policies = {
        "V2ExactExtractionResult": {
            "researchassistant-v2-phase-12-exact-extraction-v1",
            "researchassistant-v2-phase-12-exact-extraction-v2",
            "researchassistant-v2-phase-13-exact-extraction-analyzer-admission-v1",
            "researchassistant-v2-phase-13-exact-extraction-analyzer-admission-v2",
            "researchassistant-v2-phase-13-exact-extraction-analyzer-admission-v3",
        },
        "V2DeepAnalysisBackfillResult": {
            "researchassistant-v2-phase-12-deep-analysis-backfill-v1",
            "researchassistant-v2-phase-13-deep-analysis-backfill-analyzer-admission-v1",
            "researchassistant-v2-phase-13-deep-analysis-backfill-analyzer-admission-v2-waves4",
        },
    }
    if (
        kind in supported_policies
        and payload.get("policy_identity") not in supported_policies[kind]
    ):
        raise _incompatible(key, kind, "unknown recorded provider-policy identity")
    try:
        return model_type.model_validate(payload)
    except ValueError:
        pass
    # Deliberately explicit dispatch, never model_construct or patched global validators.
    registry: dict[str, type[StrictModel]] = {
        "V2SourceSelectionQueueResult": Phase8QueueResult,
        "V2EvidenceAnalystBatchResult": Phase9AnalystResult,
        "V2ReviewerLedgerBatchResult": Phase10ReviewerResult,
        "V2DeepAnalysisBackfillResult": Phase12BackfillResult,
    }
    if kind == "V2ExactExtractionResult":
        from agents.v2_extraction import V2ExactExtractionResult

        class Phase12ExtractionResult(V2ExactExtractionResult, HistoricalRead):
            queue_result: Phase8QueueResult
            policy_identity: Literal[
                "researchassistant-v2-phase-12-exact-extraction-v1",
                "researchassistant-v2-phase-12-exact-extraction-v2",
            ]

        decoder: type[StrictModel] | None = Phase12ExtractionResult
    else:
        decoder = registry.get(kind)
    if decoder is None:
        raise _incompatible(key, kind, "unknown or unsafe recorded historical format")
    try:
        return decoder.model_validate(payload)  # type: ignore[return-value]
    except ValueError as exc:
        raise _incompatible(
            key, kind, "unsupported historical policy or invalid versioned shape"
        ) from exc


# These hashes identify the two verified pre-current researcher contract families.
LEGACY_TRAIL_IDENTITIES = frozenset(
    {
        (
            "9b5c005afd700bfec172adb916c7508b59e17664b2a9529e5e4ffdaa1b5d56ca",
            "b87360febff592aa8504bd0d375e33a4611ff9abb840b080b7e2732844bfe78a",
        ),
        (
            "3d60a7e189890c779c772e4a3776e2884a64cb946bb884c937cfd2424a84bcc1",
            "df281a82a903a818eb429812cef5994e928f708dd4258bf4243baecaeb9a7060",
        ),
    }
)
LEGACY_TRAIL_POLICY_PREFIX = (
    "mvp9-nonretryable-exact-selection-v1|mvp6.8-exact-decimal-reserve-reconcile-v1|"
    "xiaomi-mimo-price-cap-2026-08-10-v2|"
    "9a3f54f0d90e66601bac30144b0cefd6f189000288d304a220d80119cce1e961|"
    "4fba91f92c205a961dd17999f5c6e77c72aee242689eb35a5f5dff48d392aeab|"
    'controls:{"depth":"standard","focus":null,"length":"report","research_mode":"focused",'
    '"sources_per_stance_per_round":7,"tone":"neutral"}|'
)
LEGACY_TRAIL_POLICIES = frozenset(
    {
        LEGACY_TRAIL_POLICY_PREFIX + "mvp6.4-evidence-density-50-75-v1|mvp11-research-governor-v1",
        LEGACY_TRAIL_POLICY_PREFIX + "mlp4-relaxed-evidence-yield-20-30-v1|"
        "mlp4-relaxed-discovery-floor-5-v1|mvp11-research-governor-v1",
    }
)


def decode_native_artifact(
    artifact: PersistedStageArtifact,
    model_type: type[ModelT],
    contract: ProviderRunContract | None,
) -> ModelT:
    """Decode only at inspection call sites, after current decoding has failed."""
    key = artifact.artifact_key
    if artifact.artifact_type != model_type.__name__:
        raise _incompatible(key, artifact.artifact_type, "unexpected native artifact type")
    try:
        payload = json.loads(artifact.payload_json)
    except ValueError as exc:
        raise _incompatible(
            artifact.artifact_key, artifact.artifact_type, "invalid stored JSON"
        ) from exc
    if not isinstance(payload, dict) or str(payload.get("run_id")) != str(artifact.run_id):
        raise _incompatible(key, artifact.artifact_type, "native artifact run identity mismatch")
    _verify_snapshot_payloads(payload, key, artifact.artifact_type)
    try:
        return model_type.model_validate(payload)
    except ValueError:
        pass
    if contract is None:
        raise _incompatible(key, artifact.artifact_type, "missing recorded provider contract")
    _validated_contract(contract, key, artifact.artifact_type)
    if contract.run_id != artifact.run_id:
        raise _incompatible(key, artifact.artifact_type, "provider contract belongs to another run")
    from researchassistant.research.orchestrator import AnalysisStageResult, ResearcherPairResult

    if model_type is AnalysisStageResult:

        class AugustAnalysisResult(AnalysisStageResult, HistoricalRead):
            ledger_records: tuple[AugustLedgerRecord, ...]

        ledger_values = payload.get("ledger_records")
        if not isinstance(ledger_values, list) or any(
            not isinstance(values, dict) or "ledger_claim_id" not in values
            for values in ledger_values
        ):
            raise _incompatible(key, artifact.artifact_type, "invalid historical Ledger collection")
        for values in ledger_values:
            decode_ledger(values, contract)
        decoder: type[StrictModel] = AugustAnalysisResult
    elif model_type is ResearcherPairResult:
        if (contract.schema_identity, contract.prompt_identity) not in LEGACY_TRAIL_IDENTITIES or (
            contract.policy_identity not in LEGACY_TRAIL_POLICIES
        ):
            raise _incompatible(key, artifact.artifact_type, "unknown recorded researcher contract")
        decoder = _legacy_researcher_type(contract)
    else:
        raise _incompatible(key, artifact.artifact_type, "unknown native historical format")
    try:
        return decoder.model_validate(payload)  # type: ignore[return-value]
    except ValueError as exc:
        raise _incompatible(
            key, artifact.artifact_type, "invalid recorded historical shape"
        ) from exc


def _legacy_researcher_type(contract: ProviderRunContract) -> type[StrictModel]:
    from agents.supportingresearcher import ResearcherRetrievalBatch
    from providers.ranking import DiscoveryDecision, RankedDiscoveryResult
    from researchassistant.contracts.models import (
        DiscoveryProvider,
        SearchIntent,
        SearchQuery,
        missing_required_query_exclusions,
    )
    from researchassistant.research.orchestrator import ResearcherPairResult, ResearcherStageResult

    # Before the relaxed-discovery-floor-5 policy, scores <20 were discarded.
    discard_floor = 5 if "mlp4-relaxed-discovery-floor-5-v1" in contract.policy_identity else 20

    class LegacySearchQuery(SearchQuery, HistoricalRead):
        @model_validator(mode="after")
        def validate_provider_query(self) -> LegacySearchQuery:
            if self.provider in {DiscoveryProvider.EXA, DiscoveryProvider.SERPSEARCH}:
                if missing_required_query_exclusions(self.exclusion_parameters):
                    raise ValueError("historical web queries require persisted exclusions")
                # The recorded web lane accepted academic-study intent.
            elif self.intent is not SearchIntent.ACADEMIC_STUDY or self.exclusion_parameters:
                raise ValueError(
                    "historical academic queries require academic intent without exclusions"
                )
            return self

    class LegacyRanking(RankedDiscoveryResult, HistoricalRead):
        query: LegacySearchQuery

        @model_validator(mode="after")
        def validate_score_and_selection(self) -> LegacyRanking:
            if self.score != self.components.total:
                raise ValueError("historical scores must match their components")
            if (self.decision is DiscoveryDecision.SELECTED) != (self.selection_rank is not None):
                raise ValueError("only historical selected results may have a rank")
            if self.decision is DiscoveryDecision.DISCARDED and self.score >= discard_floor:
                raise ValueError("historical discarded score exceeds its recorded floor")
            return self

    class LegacyBatch(ResearcherRetrievalBatch, HistoricalRead):
        discovery_ranking: tuple[LegacyRanking, ...] = ()

    class LegacySide(ResearcherStageResult, HistoricalRead):
        retrieval_batch: LegacyBatch | None = None

    class LegacyPair(ResearcherPairResult, HistoricalRead):
        supporting: LegacySide
        opposing: LegacySide

    return LegacyPair
