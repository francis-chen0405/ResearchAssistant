from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import BaseModel
from test_v2_phase5_acquisition_probe import (
    NOW as ACQUISITION_NOW,
)
from test_v2_phase5_acquisition_probe import (
    _discovery,
)
from test_v2_phase5_acquisition_probe import (
    _prepare_db as prepare_acquisition_db,
)
from test_v2_phase8_source_selection import (
    NOW as SELECTION_NOW,
)
from test_v2_phase8_source_selection import (
    _budget,
    _candidate,
    _prepare_db,
    _routing,
    _selection_input,
)
from test_v2_phase9_luna_evidence_analyst import (
    NOW as EXTRACTION_NOW,
)
from test_v2_phase9_luna_evidence_analyst import (
    _batch_input as extraction_batch_input,
)
from test_v2_phase9_luna_evidence_analyst import (
    _prepare_db as prepare_extraction_db,
)

import agents.v2_extraction as extraction_module
from agents.researcher import build_source_snapshot
from agents.v2_acquisition import run_v2_acquisition_probe
from agents.v2_extraction import V2ExtractionState, _extract_source
from agents.v2_source_selection import run_v2_source_selection_and_queue
from providers.llm import LLMProviderCapabilities, LLMRequest
from providers.mimo import MimoFailureCode, MimoProviderError
from researchassistant.contracts.model_research import V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY
from researchassistant.contracts.models import (
    ResearchDirection,
    V2AcquiredSource,
    V2AcquisitionPolicy,
    V2AcquisitionProbeOutput,
    V2AcquisitionProvider,
    V2DiscoveryScoutOutput,
    V2ProbeResult,
    V2VerbatimQuoteSelection,
)


class SequenceLLMProvider:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(self, outputs: list[object] | None = None) -> None:
        self.outputs = outputs
        self.requests = []

    def generate(self, request: LLMRequest) -> BaseModel:
        self.requests.append(request)
        if self.outputs is not None:
            output = self.outputs.pop(0)
            if isinstance(output, Exception):
                raise output
            assert isinstance(output, BaseModel)
            return output
        raise MimoProviderError(
            MimoFailureCode.AUTHENTICATION,
            "credentials are invalid",
            retryable=False,
        )


def test_exact_extraction_does_not_retry_terminal_provider_failure() -> None:
    now = datetime(2026, 10, 8, tzinfo=UTC)
    run_id = uuid4()
    source_id = uuid4()
    snapshot = build_source_snapshot(
        run_id=run_id,
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.test/study",
        retrieved_at=now,
        normalized_text=(
            "Researchers compared outcomes across regional schools. The measured outcome "
            "increased during the study period. The report describes the study limitations."
        ),
        truncated=False,
        created_at=now,
    )
    provider = SequenceLLMProvider()

    result = _extract_source(
        source_id=source_id,
        direction=ResearchDirection.SUPPORT,
        exact_claim="The program improved the measured outcome.",
        snapshot=snapshot,
        query_id=uuid4(),
        query_round=1,
        search_rank=1,
        llm_provider=provider,
        clock=lambda: now,
    )

    assert result.state is V2ExtractionState.FAILED
    assert result.attempts == 1
    assert len(provider.requests) == 1


def test_exact_extraction_retries_transient_provider_failure() -> None:
    from researchassistant.contracts.models import V2VerbatimQuoteSelection

    now = datetime(2026, 10, 8, tzinfo=UTC)
    run_id = uuid4()
    snapshot = build_source_snapshot(
        run_id=run_id,
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.test/study",
        retrieved_at=now,
        normalized_text=(
            "Researchers compared outcomes across regional schools. The measured outcome "
            "increased during the study period. The report describes the study limitations. "
            "The authors recommend further evaluation using additional comparison groups "
            "over time."
        ),
        truncated=False,
        created_at=now,
    )
    provider = SequenceLLMProvider(
        [
            MimoProviderError(
                MimoFailureCode.PERMANENT_FAILURE,
                "temporary service interruption",
                retryable=True,
            ),
            V2VerbatimQuoteSelection(
                selected_sentence_ranges=({"start_sentence": 1, "end_sentence": 4},)
            ),
        ]
    )

    result = _extract_source(
        source_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        exact_claim="The program improved the measured outcome.",
        snapshot=snapshot,
        query_id=uuid4(),
        query_round=1,
        search_rank=1,
        llm_provider=provider,
        clock=lambda: now,
    )

    assert result.state is V2ExtractionState.EXTRACTED
    assert result.attempts == 2
    assert len(provider.requests) == 2


def test_source_selection_falls_back_after_terminal_provider_failure(tmp_path: Path) -> None:
    source_ids = (uuid4(), uuid4())
    selection_input = _selection_input(
        (
            _candidate(source_ids[0], family="family-a", probe_score=10),
            _candidate(source_ids[1], family="family-b", probe_score=9),
        )
    )
    db_path = _prepare_db(tmp_path, selection_input.run_id)
    provider = SequenceLLMProvider()

    result = run_v2_source_selection_and_queue(
        db_path=db_path,
        selection_input=selection_input,
        llm_provider=provider,
        routing_config=_routing(),
        budget=_budget(),
        clock=lambda: SELECTION_NOW,
    )

    assert result.used_fallback is True
    assert result.selection_attempts == 1
    assert len(provider.requests) == 1
    assert set(result.queued_source_ids) == set(source_ids)


def test_source_selection_retries_transient_provider_failure(tmp_path: Path) -> None:
    from researchassistant.contracts.models import (
        V2SourceSelectionModelOutput,
        V2SourceSelectionRecommendation,
    )

    source_ids = (uuid4(), uuid4())
    selection_input = _selection_input(
        (
            _candidate(source_ids[0], family="family-a", probe_score=10),
            _candidate(source_ids[1], family="family-b", probe_score=9),
        )
    )
    db_path = _prepare_db(tmp_path, selection_input.run_id)
    provider = SequenceLLMProvider(
        [
            MimoProviderError(
                MimoFailureCode.PERMANENT_FAILURE,
                "temporary service interruption",
                retryable=True,
            ),
            V2SourceSelectionModelOutput(
                recommendations=tuple(
                    V2SourceSelectionRecommendation(
                        source_id=source_id,
                        rationale="Direct and complementary coverage.",
                    )
                    for source_id in source_ids
                )
            ),
        ]
    )

    result = run_v2_source_selection_and_queue(
        db_path=db_path,
        selection_input=selection_input,
        llm_provider=provider,
        routing_config=_routing(),
        budget=_budget(),
        clock=lambda: SELECTION_NOW,
    )

    assert result.used_fallback is False
    assert result.selection_attempts == 2
    assert len(provider.requests) == 2


def test_claim_aware_acquisition_resume_binds_claim_without_acquired_sources(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    discovery = _discovery(run_id, ("https://example.test/source",), ("skip",))
    db_path = prepare_acquisition_db(tmp_path, run_id)
    policy = V2AcquisitionPolicy(
        policy_identity=V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY,
    )
    first = run_v2_acquisition_probe(
        db_path=db_path,
        discovery_output=discovery,
        wigolo_provider=None,
        exact_claim="The program improves outcomes.",
        policy=policy,
        clock=lambda: ACQUISITION_NOW,
    )

    assert first.output.acquisitions == ()
    assert first.output.probes == ()
    with pytest.raises(ValueError, match="input identity changed"):
        run_v2_acquisition_probe(
            db_path=db_path,
            discovery_output=discovery,
            wigolo_provider=None,
            exact_claim="The program harms outcomes.",
            policy=policy,
            clock=lambda: ACQUISITION_NOW,
        )


def test_exact_extraction_resume_reuses_completed_source_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = extraction_batch_input(uuid4())
    queue_result = batch.queue_result
    source = queue_result.input.survivors[0]
    snapshot = batch.queued_candidates[0].snapshot
    discovery = V2DiscoveryScoutOutput(
        run_id=queue_result.run_id,
        directions=queue_result.input.directions,
        items=(),
        clusters=(),
        scout_batches=(),
        scout_audits=(),
        completed_at=EXTRACTION_NOW,
    )
    acquisition = V2AcquisitionProbeOutput(
        run_id=queue_result.run_id,
        directions=queue_result.input.directions,
        acquisitions=(
            V2AcquiredSource(
                cluster_id=source.source_id,
                direction=source.direction,
                snapshot=snapshot,
                provider=V2AcquisitionProvider.WIGOLO,
            ),
        ),
        attempts=(),
        probes=(
            V2ProbeResult(
                cluster_id=source.source_id,
                snapshot_id=snapshot.snapshot_id,
                snapshot_sha256=snapshot.snapshot_sha256,
                succeeded=True,
            ),
        ),
        survivors=(),
        completed_at=EXTRACTION_NOW,
    )
    db_path = prepare_extraction_db(tmp_path, queue_result.run_id)
    monkeypatch.setattr(extraction_module, "_search_rank", lambda *_: 1)
    provider = SequenceLLMProvider(
        [
            V2VerbatimQuoteSelection(
                selected_sentence_ranges=({"start_sentence": 1, "end_sentence": 2},)
            )
        ]
    )
    original_insert = extraction_module.insert_v2_artifact

    def fail_aggregate_persist(
        path: str,
        artifact_key: str,
        artifact: BaseModel,
        created_at: datetime,
    ) -> object:
        if artifact_key == extraction_module.V2_EXTRACTION_ARTIFACT_KEY:
            raise RuntimeError("simulated interruption after source checkpoint")
        return original_insert(path, artifact_key, artifact, created_at)

    monkeypatch.setattr(extraction_module, "insert_v2_artifact", fail_aggregate_persist)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        extraction_module.run_v2_exact_extraction(
            db_path=db_path,
            queue_result=queue_result,
            discovery_outputs=(discovery,),
            acquisition_outputs=(acquisition,),
            llm_provider=provider,
            routing_config=_routing(),
            clock=lambda: EXTRACTION_NOW,
        )

    assert len(provider.requests) == 1
    changed_acquisition = acquisition.model_copy(
        update={"completed_at": acquisition.completed_at + timedelta(seconds=1)}
    )
    with pytest.raises(ValueError, match="input identity changed"):
        extraction_module.run_v2_exact_extraction(
            db_path=db_path,
            queue_result=queue_result,
            discovery_outputs=(discovery,),
            acquisition_outputs=(changed_acquisition,),
            llm_provider=SequenceLLMProvider(),
            routing_config=_routing(),
            clock=lambda: EXTRACTION_NOW,
        )

    monkeypatch.setattr(extraction_module, "insert_v2_artifact", original_insert)
    resumed = extraction_module.run_v2_exact_extraction(
        db_path=db_path,
        queue_result=queue_result,
        discovery_outputs=(discovery,),
        acquisition_outputs=(acquisition,),
        llm_provider=SequenceLLMProvider(),
        routing_config=_routing(),
        clock=lambda: EXTRACTION_NOW,
    )

    assert len(resumed.sources) == 1
    assert resumed.sources[0].source_id == source.source_id
    assert len(provider.requests) == 1
