"""Restart-safe exact extraction for the Phase-8 deep-analysis queue."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from agents.researcher import (
    CURRENT_QUOTE_LENGTH_POLICY,
    assemble_quote_block_from_selected_segments,
    filter_provisional_candidate,
    numbered_source_text,
    validate_snapshot_integrity,
)
from models import (
    CandidateQuoteBlock,
    ProvisionalCandidate,
    ResearchDirection,
    SourceSnapshot,
    Stance,
    StrictModel,
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
    V2EvidenceAnalystBatchInput,
    V2EvidenceAnalystCandidateInput,
    V2EvidenceAnalystExtractionFailure,
    V2SourceSelectionQueueResult,
    V2VerbatimQuoteSelection,
)
from providers.llm import (
    V2_LLM_ROUTING,
    LLMProvider,
    LLMRequest,
    LLMStage,
    ModelAlias,
    invoke_llm,
    load_prompt,
    render_stage_prompt,
)
from providers.v2_routing import V2RoutingConfig
from store import insert_v2_artifact, read_v2_artifact

V2_EXTRACTION_ARTIFACT_KEY = "phase-12-exact-extraction"
V2_EXTRACTION_POLICY_IDENTITY = "researchassistant-v2-phase-12-exact-extraction-v2"
V2_EXTRACTION_FILTER_VERSION = "researchassistant-v2-phase-12-post-filter-v1"
V2_EXTRACTION_MAX_ATTEMPTS = 2
_CLAIM_TOKEN_RE = re.compile(r"[a-z0-9]+")
_EXTRACTION_RETRY_GUIDANCE = (
    "The prior attempt returned an invalid empty, short, or otherwise unusable selection. "
    "On this retry, "
    "return at least one source sentence range. If one relevant sentence is too short, "
    "use a contiguous range of adjacent relevant sentences; do not return an empty array "
    "and do not invent or paraphrase source text."
)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("v2 extraction timestamps must be timezone-aware")
    return value


class V2ExtractionState(StrEnum):
    EXTRACTED = "extracted"
    FAILED = "failed"


class V2ExtractionLLMInput(StrictModel):
    """Exact immutable source surface exposed to the selection-only Extractor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    source_id: UUID
    direction: ResearchDirection
    exact_claim: str = Field(min_length=1)
    snapshot_id: UUID
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    truncated: bool
    untrusted_source_text: str = Field(min_length=1)
    selectable_source_text: str = Field(min_length=1)


class V2ExtractionSourceResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: UUID
    direction: ResearchDirection
    state: V2ExtractionState
    attempts: int = Field(ge=1, le=V2_EXTRACTION_MAX_ATTEMPTS)
    candidate: CandidateQuoteBlock | None = None
    failure: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> V2ExtractionSourceResult:
        if self.state is V2ExtractionState.EXTRACTED:
            if self.candidate is None or self.failure is not None:
                raise ValueError("successful extraction requires one candidate and no failure")
        elif self.candidate is not None or self.failure is None:
            raise ValueError("failed extraction requires a failure and no candidate")
        return self


class V2ExactExtractionResult(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    queue_result: V2SourceSelectionQueueResult
    sources: tuple[V2ExtractionSourceResult, ...]
    completed_at: datetime
    policy_identity: str = V2_EXTRACTION_POLICY_IDENTITY

    _completed_at_is_aware = field_validator("completed_at")(_aware)

    @model_validator(mode="after")
    def validate_queue_order(self) -> V2ExactExtractionResult:
        if self.queue_result.run_id != self.run_id:
            raise ValueError("extraction queue must match the run")
        if tuple(item.source_id for item in self.sources) != self.queue_result.queued_source_ids:
            raise ValueError("extraction results must reproduce the complete queue order")
        return self

    def analyst_input(
        self,
        snapshots: dict[UUID, SourceSnapshot],
    ) -> V2EvidenceAnalystBatchInput:
        """Project only deterministically valid candidates into Luna analysis."""
        direction_by_id = {
            item.source_id: item.direction for item in self.queue_result.input.survivors
        }
        candidates = tuple(
            V2EvidenceAnalystCandidateInput(
                source_id=item.source_id,
                direction=direction_by_id[item.source_id],
                candidate=item.candidate,
                snapshot=snapshots[item.source_id],
            )
            for item in self.sources
            if item.candidate is not None
        )
        return V2EvidenceAnalystBatchInput(
            run_id=self.run_id,
            exact_claim=self.queue_result.input.exact_claim,
            directions=self.queue_result.input.directions,
            queue_result=self.queue_result,
            queued_candidates=candidates,
            extraction_failures=tuple(
                V2EvidenceAnalystExtractionFailure(
                    source_id=item.source_id,
                    failure=item.failure,
                )
                for item in self.sources
                if item.candidate is None and item.failure is not None
            ),
        )


def run_v2_exact_extraction(
    *,
    db_path: str | Path,
    queue_result: V2SourceSelectionQueueResult,
    discovery_outputs: tuple[V2DiscoveryScoutOutput, ...],
    acquisition_outputs: tuple[V2AcquisitionProbeOutput, ...],
    llm_provider: LLMProvider,
    routing_config: V2RoutingConfig,
    artifact_key: str = V2_EXTRACTION_ARTIFACT_KEY,
    clock: Callable[[], datetime] | None = None,
) -> V2ExactExtractionResult:
    """Select exact passages for every queued survivor, preserving per-source failure."""
    now = clock or _utc_now
    path = str(Path(db_path).resolve())
    try:
        stored = read_v2_artifact(path, queue_result.run_id, artifact_key)
    except KeyError:
        stored = None
    if stored is not None:
        result = V2ExactExtractionResult.model_validate_json(stored.payload_json)
        if result.queue_result != queue_result:
            raise ValueError("persisted extraction result does not match the Phase-8 queue")
        return result

    route = routing_config.preflight().for_stage(LLMStage.EXTRACTOR)
    if route.logical_alias is not ModelAlias.MIMO_V25_PRO:
        raise ValueError("fresh v2 extraction must use MiMo-v2.5-Pro")
    if V2_LLM_ROUTING.for_stage(LLMStage.EXTRACTOR).primary is not route.logical_alias:
        raise ValueError("configured Extractor route does not match v2 policy")
    snapshots = _snapshots_by_source(acquisition_outputs)
    source_rows = {item.source_id: item for item in queue_result.input.survivors}
    results: list[V2ExtractionSourceResult] = []
    for source_id in queue_result.queued_source_ids:
        source = source_rows[source_id]
        snapshot = snapshots[source_id]
        results.append(
            _extract_source(
                source_id=source_id,
                direction=source.direction,
                exact_claim=queue_result.input.exact_claim,
                snapshot=snapshot,
                query_id=source.search_provenance[0].query_id,
                query_round=source.research_round,
                search_rank=_search_rank(source_id, discovery_outputs),
                llm_provider=llm_provider,
                clock=now,
            )
        )
    output = V2ExactExtractionResult(
        run_id=queue_result.run_id,
        queue_result=queue_result,
        sources=tuple(results),
        completed_at=_aware(now()),
    )
    insert_v2_artifact(path, artifact_key, output, output.completed_at)
    return output


def snapshots_by_source(
    acquisition_outputs: tuple[V2AcquisitionProbeOutput, ...],
) -> dict[UUID, SourceSnapshot]:
    """Return the immutable snapshot keyed by its survivor/source cluster ID."""
    return _snapshots_by_source(acquisition_outputs)


def _extract_source(
    *,
    source_id: UUID,
    direction: ResearchDirection,
    exact_claim: str,
    snapshot: SourceSnapshot,
    query_id: UUID,
    query_round: int,
    search_rank: int,
    llm_provider: LLMProvider,
    clock: Callable[[], datetime],
) -> V2ExtractionSourceResult:
    validate_snapshot_integrity(snapshot)
    input_artifact = V2ExtractionLLMInput(
        run_id=snapshot.run_id,
        source_id=source_id,
        direction=direction,
        exact_claim=exact_claim,
        snapshot_id=snapshot.snapshot_id,
        snapshot_sha256=snapshot.snapshot_sha256,
        truncated=snapshot.truncated,
        untrusted_source_text=snapshot.normalized_text,
        selectable_source_text=numbered_source_text(snapshot.normalized_text),
    )
    prompt = load_prompt(LLMStage.EXTRACTOR)
    base_rendered_prompt = render_stage_prompt(prompt, input_artifact, V2VerbatimQuoteSelection)
    last_failure = "Extractor did not return a valid selection."
    for attempt in range(1, V2_EXTRACTION_MAX_ATTEMPTS + 1):
        rendered_prompt = base_rendered_prompt
        if attempt > 1:
            rendered_prompt = (
                f"{rendered_prompt}\n\n<RETRY_VALIDATION_GUIDANCE>\n"
                f"{_EXTRACTION_RETRY_GUIDANCE}\n</RETRY_VALIDATION_GUIDANCE>"
            )
        request = LLMRequest(
            run_id=snapshot.run_id,
            stage=LLMStage.EXTRACTOR,
            prompt=prompt,
            rendered_prompt=rendered_prompt,
            input_artifact=input_artifact,
            input_artifact_ids=(snapshot.snapshot_id,),
            requested_output_type=V2VerbatimQuoteSelection,
            model_alias=ModelAlias.MIMO_V25_PRO,
            generation=V2_LLM_ROUTING.for_stage(LLMStage.EXTRACTOR).generation,
            source_id=source_id,
        )
        try:
            invocation = invoke_llm(llm_provider, request, clock=clock)
            selection = invocation.output_artifact
            if not isinstance(selection, V2VerbatimQuoteSelection):
                raise TypeError("Extractor returned an unexpected typed artifact")
        except Exception as exc:
            last_failure = f"{type(exc).__name__}: {exc}"[:1000]
            if attempt < V2_EXTRACTION_MAX_ATTEMPTS:
                continue
            return V2ExtractionSourceResult(
                source_id=source_id,
                direction=direction,
                state=V2ExtractionState.FAILED,
                attempts=attempt,
                failure=last_failure,
            )
        try:
            provisional = ProvisionalCandidate(
                run_id=snapshot.run_id,
                stance=(
                    Stance.SUPPORTING if direction is ResearchDirection.SUPPORT else Stance.OPPOSING
                ),
                source_url=snapshot.source_url,
                retrieval_attempt_id=snapshot.retrieval_attempt_id,
                query_id=query_id,
                query_round=query_round,
                search_rank=search_rank,
                snapshot_id=snapshot.snapshot_id,
                snapshot_sha256=snapshot.snapshot_sha256,
                extracted_quote_block=assemble_quote_block_from_selected_segments(
                    snapshot.normalized_text,
                    selection,
                    truncated=snapshot.truncated,
                ),
                extraction_prompt_version=prompt.version,
                extraction_model_name=ModelAlias.MIMO_V25_PRO.value,
                extracted_at=_aware(clock()),
            )
            filtered = filter_provisional_candidate(
                provisional,
                snapshot,
                claim_keywords=_claim_keywords(exact_claim),
                post_filter_version=V2_EXTRACTION_FILTER_VERSION,
                validation_clock=clock,
                quote_length_policy=CURRENT_QUOTE_LENGTH_POLICY,
            )
            if not filtered.valid or filtered.candidate is None:
                last_failure = filtered.rejection_message or "deterministic filter rejected quote"
                if attempt < V2_EXTRACTION_MAX_ATTEMPTS and _is_retryable_quote_length_failure(
                    last_failure
                ):
                    continue
                return V2ExtractionSourceResult(
                    source_id=source_id,
                    direction=direction,
                    state=V2ExtractionState.FAILED,
                    attempts=attempt,
                    failure=last_failure[:1000],
                )
            return V2ExtractionSourceResult(
                source_id=source_id,
                direction=direction,
                state=V2ExtractionState.EXTRACTED,
                attempts=attempt,
                candidate=filtered.candidate,
            )
        except ValueError as exc:
            return V2ExtractionSourceResult(
                source_id=source_id,
                direction=direction,
                state=V2ExtractionState.FAILED,
                attempts=attempt,
                failure=f"{type(exc).__name__}: {exc}"[:1000],
            )
    raise AssertionError("bounded extraction loop did not return")


def _is_retryable_quote_length_failure(message: str) -> bool:
    """Retry a short exact selection so the Extractor can extend it contiguously."""
    return message.startswith("quoted segments contain ") and "; need " in message


def _snapshots_by_source(
    outputs: tuple[V2AcquisitionProbeOutput, ...],
) -> dict[UUID, SourceSnapshot]:
    snapshots = {
        acquired.cluster_id: acquired.snapshot
        for output in outputs
        for acquired in output.acquisitions
    }
    return snapshots


def _search_rank(source_id: UUID, outputs: tuple[V2DiscoveryScoutOutput, ...]) -> int:
    for output in outputs:
        cluster = next((item for item in output.clusters if item.cluster_id == source_id), None)
        if cluster is None:
            continue
        items = {item.item_id: item for item in output.items}
        return min(items[item_id].provider_rank for item_id in cluster.item_ids)
    raise ValueError("queued survivor has no discovery rank provenance")


def _claim_keywords(claim: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            token for token in _CLAIM_TOKEN_RE.findall(claim.casefold()) if len(token) >= 4
        )
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)
