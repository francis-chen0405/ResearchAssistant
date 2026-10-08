from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import UUID

from test_v2_phase8_source_selection import (
    NOW,
    _budget,
    _candidate,
    _prepare_db,
    _routing,
    _selection_input,
)

from agents.v2_source_selection import (
    run_v2_source_selection_and_queue,
)
from providers.llm import (
    LLMProviderCapabilities,
    LLMRequest,
    LLMStage,
    load_prompt_file,
    render_stage_prompt,
)
from providers.pricing import conservative_token_estimate
from researchassistant.contracts.discovery_v2 import (
    V2PreviewRequest,
    V2PreviewResult,
    V2PreviewSpan,
    discovery_id,
)
from researchassistant.contracts.model_research import (
    V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY,
    V2_ACQUISITION_PROBE_POLICY_IDENTITY,
    V2_PREVIEW_SELECTION_POLICY_IDENTITY,
    V2AcquisitionProbeOutput,
    V2ProbeResult,
    V2SourceSelectionInput,
    V2SourceSelectionModelOutput,
    V2SourceSelectionProbePassage,
    V2SourceSelectionRecommendation,
)
from researchassistant.contracts.research_directions import ResearchDirections
from researchassistant.contracts.source_selection_preview import V2SelectionShortlistAudit
from researchassistant.storage.store import read_v2_artifact

SOURCE_SELECTION_SHORTLIST_KEY = "source-selection-preview-shortlist-v2"
SHORTLIST_CAP = 24_000
FIXED_RUN_ID = UUID(int=9001)


class BoundedSourceSelector:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True,
        supports_structured_output_control=True,
    )

    def __init__(
        self,
        *,
        output_source_id: UUID | None = None,
        forbidden_source_id: UUID | None = None,
        estimator_overhead: int = 0,
    ) -> None:
        self.output_source_id = output_source_id
        self.forbidden_source_id = forbidden_source_id
        self.estimator_overhead = estimator_overhead
        self.requests: list[LLMRequest] = []
        self.estimates: list[tuple[LLMRequest, int, int]] = []

    def conservative_input_tokens(self, request: LLMRequest, minimum: int) -> int:
        estimated = minimum + self.estimator_overhead
        self.estimates.append((request, minimum, estimated))
        return estimated

    def generate(self, request: LLMRequest) -> V2SourceSelectionModelOutput:
        self.requests.append(request)
        source_id = self.forbidden_source_id or self.output_source_id
        if source_id is None:
            source_id = request.input_artifact.survivors[0].source_id
        return V2SourceSelectionModelOutput(
            recommendations=(
                V2SourceSelectionRecommendation(
                    source_id=source_id,
                    rationale="Prioritizes direct, complementary source coverage.",
                ),
            )
        )


def _large_selection_input(*, source_count: int = 36) -> V2SourceSelectionInput:
    candidates = []
    passage_text = "x" * 1200
    for index in range(source_count):
        source_id = UUID(int=index + 1)
        candidate = _candidate(
            source_id,
            family=f"family-{index:03d}",
            probe_score=source_count - index,
        )
        candidates.append(
            candidate.model_copy(
                update={
                    "probe_passages": tuple(
                        V2SourceSelectionProbePassage(
                            passage_id=f"passage-{index}-{letter}",
                            text=passage_text,
                            score=source_count - index,
                        )
                        for letter in ("a", "b", "c")
                    ),
                    "search_provenance": tuple(
                        item.model_copy(update={"query_id": UUID(int=1000 + index)})
                        for item in candidate.search_provenance
                    ),
                }
            )
        )
    base = _selection_input(tuple(candidates)).model_copy(
        update={"run_id": FIXED_RUN_ID, "policy_identity": V2_PREVIEW_SELECTION_POLICY_IDENTITY}
    )
    return base


def _run(
    tmp_path: Path,
    selection_input: V2SourceSelectionInput,
    provider: BoundedSourceSelector,
    *,
    budget_tokens: int = 2_000_000,
) -> tuple[object, str]:
    db_dir = tmp_path / f"db-{len(list(tmp_path.iterdir()))}"
    db_dir.mkdir()
    db_path = _prepare_db(db_dir, selection_input.run_id)
    result = run_v2_source_selection_and_queue(
        db_path=db_path,
        selection_input=selection_input,
        llm_provider=provider,
        routing_config=_routing(),
        budget=_budget(tokens_remaining=budget_tokens),
        clock=lambda: NOW,
    )
    return result, db_path


def _audit(db_path: str, run_id: UUID) -> V2SelectionShortlistAudit:
    artifact = read_v2_artifact(db_path, run_id, SOURCE_SELECTION_SHORTLIST_KEY)
    return V2SelectionShortlistAudit.model_validate_json(artifact.payload_json)


def _render_full_input(selection_input: V2SourceSelectionInput) -> str:
    prompt = load_prompt_file(
        Path(__file__).resolve().parents[1] / "prompts" / "source_selection_v3.md",
        expected_stage=LLMStage.SOURCE_SELECTION,
    )
    return render_stage_prompt(prompt, selection_input, V2SourceSelectionModelOutput)


def test_large_selection_uses_deterministic_audited_shortlist_with_full_reservation(
    tmp_path: Path,
) -> None:
    selection_input = _large_selection_input()
    full_prompt = _render_full_input(selection_input)
    assert conservative_token_estimate(full_prompt) > SHORTLIST_CAP

    providers = (
        BoundedSourceSelector(estimator_overhead=83),
        BoundedSourceSelector(estimator_overhead=83),
    )
    runs = []
    for index, provider in enumerate(providers):
        run_dir = tmp_path / f"run-{index}"
        run_dir.mkdir()
        result, db_path = _run(run_dir, selection_input, provider)
        runs.append((result, db_path, provider))

    first, first_path, first_provider = runs[0]
    second, second_path, second_provider = runs[1]
    first_audit = _audit(first_path, selection_input.run_id)
    second_audit = _audit(second_path, selection_input.run_id)
    assert first_audit == second_audit
    assert first_audit.input_token_cap == SHORTLIST_CAP
    assert 0 < first_audit.rendered_input_tokens <= SHORTLIST_CAP
    assert first_audit.total_sources == len(selection_input.survivors)
    assert len(first_audit.included_source_ids) == len(
        first_provider.requests[0].input_artifact.survivors
    )
    assert first_audit.included_source_ids == tuple(
        candidate.source_id for candidate in first_provider.requests[0].input_artifact.survivors
    )
    assert first_audit.omitted
    assert {row.source_id for row in first_audit.omitted} == {
        candidate.source_id
        for candidate in selection_input.survivors
        if candidate.source_id not in set(first_audit.included_source_ids)
    }
    assert all(row.disposition == "input_cap" for row in first_audit.omitted)
    for provider, result in ((first_provider, first), (second_provider, second)):
        request, minimum, actual = next(
            estimate for estimate in provider.estimates if estimate[0] == provider.requests[0]
        )
        assert request == provider.requests[0]
        assert first_audit.rendered_input_tokens == actual
        assert actual == conservative_token_estimate(request.rendered_prompt) + 83
        assert minimum == conservative_token_estimate(request.rendered_prompt)
        assert actual <= SHORTLIST_CAP
        reservation = result.selection_attempt_records[0]
        output_reserve = (
            _routing().preflight().for_stage(LLMStage.SOURCE_SELECTION).max_completion_tokens
        )
        assert reservation.reserved_tokens == actual + output_reserve
        assert result.used_fallback is False
    assert first_audit.included_source_ids == second_audit.included_source_ids


def test_recommendation_for_omitted_source_is_rejected_and_fallback_uses_full_pool(
    tmp_path: Path,
) -> None:
    selection_input = _large_selection_input()
    provider = BoundedSourceSelector(forbidden_source_id=selection_input.survivors[-1].source_id)

    result, db_path = _run(tmp_path, selection_input, provider)

    audit = _audit(db_path, selection_input.run_id)
    assert selection_input.survivors[-1].source_id in {row.source_id for row in audit.omitted}
    assert len(provider.requests) == 2
    assert all(
        selection_input.survivors[-1].source_id
        not in {candidate.source_id for candidate in request.input_artifact.survivors}
        for request in provider.requests
    )
    assert result.used_fallback is True
    assert any(
        "invented an unknown source ID" in attempt.failure
        for attempt in result.selection_attempt_records
        if attempt.failure is not None
    )
    assert set(result.recommended_source_ids).issubset(
        {candidate.source_id for candidate in selection_input.survivors}
    )


def test_input_cap_no_fit_falls_back_without_call_and_audits_every_source(
    tmp_path: Path,
) -> None:
    source = _candidate(UUID(int=1), family="too-large", probe_score=10).model_copy(
        update={"title": "title " * 6000}
    )
    selection_input = _selection_input((source,)).model_copy(
        update={"run_id": FIXED_RUN_ID, "policy_identity": V2_PREVIEW_SELECTION_POLICY_IDENTITY}
    )
    provider = BoundedSourceSelector()

    result, db_path = _run(tmp_path, selection_input, provider)

    audit = _audit(db_path, selection_input.run_id)
    assert provider.requests == []
    assert result.selection_attempt_records == ()
    assert result.used_fallback is True
    assert audit.included_source_ids == ()
    assert audit.rendered_input_tokens == 0
    assert len(audit.omitted) == 1
    assert audit.omitted[0].source_id == source.source_id
    assert audit.omitted[0].disposition == "input_cap"
    assert result.recommended_source_ids == (source.source_id,)


def test_insufficient_call_budget_uses_fallback_without_transport_or_false_input_omission(
    tmp_path: Path,
) -> None:
    selection_input = _large_selection_input(source_count=1)
    provider = BoundedSourceSelector()

    result, db_path = _run(tmp_path, selection_input, provider, budget_tokens=0)

    audit = _audit(db_path, selection_input.run_id)
    assert audit.included_source_ids == (selection_input.survivors[0].source_id,)
    assert audit.omitted == ()
    assert provider.requests == []
    assert result.selection_attempt_records == ()
    assert result.used_fallback is True
    assert result.recommended_source_ids == (selection_input.survivors[0].source_id,)
    assert result.queued_source_ids == ()


def test_probe_v1_v2_and_default_preview_v1_keep_historical_dump_hashes() -> None:
    run_id = UUID(int=7001)
    empty_probe_v1 = V2AcquisitionProbeOutput(
        run_id=run_id,
        directions=ResearchDirections(),
        acquisitions=(),
        attempts=(),
        probes=(),
        survivors=(),
        policy_identity=V2_ACQUISITION_PROBE_LEGACY_POLICY_IDENTITY,
        completed_at=NOW,
    )
    empty_probe_v2 = empty_probe_v1.model_copy(
        update={"policy_identity": V2_ACQUISITION_PROBE_POLICY_IDENTITY}
    )
    probe_result = V2ProbeResult(
        cluster_id=UUID(int=7002),
        snapshot_id=UUID(int=7003),
        snapshot_sha256="a" * 64,
        succeeded=True,
        passages=(),
        failure=None,
    )
    request_key = "golden-preview-v1"
    request = V2PreviewRequest(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2PreviewRequest", request_key),
        identity_key=request_key,
        exact_claim="The treatment reduces symptoms.",
        direction="support",
        directions=ResearchDirections(),
        source_id=UUID(int=7004),
        snapshot_id=UUID(int=7003),
        snapshot_hash="b" * 64,
    )
    result = V2PreviewResult(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2PreviewResult", request_key),
        identity_key=request_key,
        request=request,
        spans=(
            V2PreviewSpan(
                start=0,
                end=len("The treatment works."),
                text="The treatment works.",
                section="abstract",
            ),
        ),
        content_classification="abstract_only",
        outcome="completed",
        reason="historical fixture",
    )

    probe_v1_dump = empty_probe_v1.model_dump_json()
    probe_v2_dump = empty_probe_v2.model_dump_json()
    legacy_result_dump = probe_result.model_dump_json()
    request_dump = request.model_dump_json()
    preview_dump = result.model_dump_json()
    assert (
        V2AcquisitionProbeOutput.model_validate_json(probe_v1_dump).model_dump_json()
        == probe_v1_dump
    )
    assert (
        V2AcquisitionProbeOutput.model_validate_json(probe_v2_dump).model_dump_json()
        == probe_v2_dump
    )
    assert (
        V2ProbeResult.model_validate_json(legacy_result_dump).model_dump_json()
        == legacy_result_dump
    )
    assert V2PreviewRequest.model_validate_json(request_dump).model_dump_json() == request_dump
    assert V2PreviewResult.model_validate_json(preview_dump).model_dump_json() == preview_dump
    assert "asserted_components" not in request_dump and "target_gaps" not in request_dump
    assert all(
        key not in preview_dump
        for key in (
            "observed_sections",
            "missing_sections",
            "snapshot_truncated",
            "capture_usable",
            "relevance_score",
        )
    )
    assert '"preview"' not in legacy_result_dump
    actual_hashes = (
        sha256(probe_v1_dump.encode()).hexdigest(),
        sha256(probe_v2_dump.encode()).hexdigest(),
        sha256(legacy_result_dump.encode()).hexdigest(),
        sha256(request_dump.encode()).hexdigest(),
        sha256(preview_dump.encode()).hexdigest(),
    )
    assert actual_hashes == (
        "2d5baf74242d22949de77114d3c8efb8f0bc89cef988ecf0980c9bb375020bce",
        "b5d6ae6cae65d1a52d7f55218475a67e5117cf2cfa7ca23128dca3ba0c0482c7",
        "7490a7ebd86ac744d035c4b9b6d19a45352ab8c660964138312a951bace61c19",
        "f18c38813199b8c00746cc4b83c07503e92f308a0aec24af4aa45661c9519380",
        "540a5f499ab022ecb2186b25767587e0c8b739484babeb332e3f8d69b00723f6",
    )


def test_legacy_source_selection_prompt_bytes_remain_unchanged() -> None:
    prompt = Path(__file__).resolve().parents[1] / "prompts" / "source_selection.md"
    assert (
        sha256(prompt.read_bytes()).hexdigest()
        == "c095053044ba603a939d7ef1e13a2d5531c7ca6c591134f895533b8a4cf8f974"
    )
