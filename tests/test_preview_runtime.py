"""Fresh previews reach physical selection while extraction retains the owned snapshot."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from test_v2_phase5_acquisition_probe import FixtureScraper, _discovery, _prepare_db, _response
from test_v2_phase8_source_selection import _budget, _routing

from agents.v2_acquisition import run_v2_acquisition_probe
from agents.v2_adaptive_search import V2MergedSurvivor, V2MergedSurvivorPool
from agents.v2_source_selection import (
    build_v2_source_selection_input,
    run_v2_source_selection_and_queue,
)
from providers.llm import LLMProviderCapabilities, LLMRequest
from researchassistant.contracts.model_research import (
    V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY,
    V2AcquisitionPolicy,
    V2SourceSelectionModelOutput,
    V2SourceSelectionRecommendation,
)
from researchassistant.evidence.evidence_core import fresh_numbered_source_text

CLAIM = "The intervention reduces symptoms."
STUDY = (
    "A disappointing opening from a publication archive.\n"
    "Methods\nWe randomized 120 adults to the intervention or usual care and assessed "
    "symptoms at baseline and after twelve weeks using a validated questionnaire.\n"
    "Results\nThe intervention had no significant effect on symptoms compared with usual care. "
    "The confidence interval included zero, and the authors caution that follow-up was short.\n"
    "References\n1. Unrelated-economic-bibliography (2020). DOI 10.1000/never-preview, "
    "n=9000, p=0.0001.\n"
)


class Selector:
    capabilities = LLMProviderCapabilities(
        supports_temperature=True, supports_structured_output_control=True
    )

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> V2SourceSelectionModelOutput:
        self.requests.append(request)
        return V2SourceSelectionModelOutput(
            recommendations=(
                V2SourceSelectionRecommendation(
                    source_id=request.input_artifact.survivors[0].source_id,
                    rationale="Substantive methods and null findings deserve independent analysis.",
                ),
            )
        )


def test_fresh_acquisition_selection_and_extractor_snapshot_boundary(tmp_path: Path) -> None:
    run_id = uuid4()
    url = "https://example.test/current-study"
    discovery = _discovery(run_id, (url,), ("retrieve",))
    path = _prepare_db(tmp_path, run_id)
    acquisition = run_v2_acquisition_probe(
        db_path=path,
        discovery_output=discovery,
        wigolo_provider=FixtureScraper({url: _response(url, STUDY)}),
        exact_claim=CLAIM,
        asserted_components=("intervention", "symptoms"),
        policy=V2AcquisitionPolicy(policy_identity=V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY),
        clock=lambda: discovery.completed_at,
    ).output
    assert acquisition.survivors
    probe = acquisition.probes[0]
    assert probe.preview is not None and probe.preview.capture_usable
    assert all("Unrelated-economic" not in span.text for span in probe.passages)
    assert any("no significant effect" in span.text for span in probe.passages)
    snapshot = acquisition.acquisitions[0].snapshot
    numbered = fresh_numbered_source_text(snapshot.normalized_text)
    assert "Unrelated-economic" in numbered
    assert snapshot.normalized_text == STUDY
    merged = V2MergedSurvivorPool(
        run_id=run_id,
        sources=(
            V2MergedSurvivor(
                research_round=1,
                source_url=url,
                survivor=acquisition.survivors[0],
            ),
        ),
    )
    selection = build_v2_source_selection_input(
        exact_claim=CLAIM,
        merged_survivors=merged,
        discovery_outputs=(discovery,),
        acquisition_outputs=(acquisition,),
        gap_outputs=(),
        claim_aware=True,
        asserted_components=("intervention", "symptoms"),
    )
    model = Selector()
    result = run_v2_source_selection_and_queue(
        db_path=path,
        selection_input=selection,
        llm_provider=model,
        routing_config=_routing(),
        budget=_budget(),
        clock=lambda: discovery.completed_at,
    )
    assert len(model.requests) == 1
    actual = model.requests[0].rendered_prompt
    assert "randomized 120 adults" in actual
    assert "no significant effect" in actual
    assert "Unrelated-economic" not in actual and "never-preview" not in actual
    assert "untrusted data" in actual
    assert result.queued_source_ids == (acquisition.survivors[0].cluster_id,)
    assert snapshot.normalized_text == STUDY
    with pytest.raises(ValueError, match="identity changed"):
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=None,
            exact_claim="The intervention increases symptoms.",
            policy=V2AcquisitionPolicy(policy_identity=V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY),
        )


@pytest.mark.parametrize("text", ["", "OSF", "References\nDOI 10.1234/only 1999 2020 55 88"])
def test_empty_shell_and_reference_failures_remain_inspectable(tmp_path: Path, text: str) -> None:
    run_id = uuid4()
    url = "https://example.test/unusable"
    discovery = _discovery(run_id, (url,), ("retrieve",))
    result = run_v2_acquisition_probe(
        db_path=_prepare_db(tmp_path, run_id),
        discovery_output=discovery,
        wigolo_provider=FixtureScraper({url: _response(url, text)}),
        exact_claim=CLAIM,
        policy=V2AcquisitionPolicy(policy_identity=V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY),
        clock=lambda: discovery.completed_at,
    ).output
    assert result.survivors == ()
    if text:
        assert result.acquisitions[0].snapshot.normalized_text == text
        assert result.probes[0].failure and result.probes[0].preview is not None
    else:
        assert result.acquisitions == ()
        assert any(row.failure_code == "empty_capture" for row in result.attempts)


def test_unrelated_substantive_capture_survives_with_neutral_preview(tmp_path: Path) -> None:
    run_id = uuid4()
    url = "https://example.test/unrelated-study"
    discovery = _discovery(run_id, (url,), ("retrieve",))
    text = (
        "Methods\nWe randomized adults with hypertension to supervised exercise or usual care "
        "and measured blood pressure before treatment and after sixteen weeks of follow-up.\n"
        "Results\nSystolic blood pressure fell by eight millimeters of mercury in the exercise "
        "group while the usual-care group remained unchanged during follow-up.\n"
    )
    acquisition = run_v2_acquisition_probe(
        db_path=_prepare_db(tmp_path, run_id),
        discovery_output=discovery,
        wigolo_provider=FixtureScraper({url: _response(url, text)}),
        exact_claim="Automated license plate readers reduce crime.",
        policy=V2AcquisitionPolicy(policy_identity=V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY),
    ).output
    assert acquisition.survivors
    preview = acquisition.probes[0].preview
    assert preview is not None and preview.outcome == "unavailable"
    assert preview.capture_usable and preview.relevance_score == 0
    assert all(span.score == 0 for span in acquisition.probes[0].passages)


def test_chinese_preview_does_not_bypass_existing_quote_length_gate(tmp_path: Path) -> None:
    run_id = uuid4()
    url = "https://example.test/chinese-study"
    discovery = _discovery(run_id, (url,), ("retrieve",))
    text = (
        "摘要\n一项随机对照试验纳入了120名抑郁症患者。干预组的抑郁症状评分下降了4分。\n"
        "方法\n研究人员将参与者随机分配到干预组和对照组。\n"
        "结果\n干预组的抑郁症状明显减少。"
    )
    acquisition = run_v2_acquisition_probe(
        db_path=_prepare_db(tmp_path, run_id),
        discovery_output=discovery,
        wigolo_provider=FixtureScraper({url: _response(url, text)}),
        exact_claim="干预减少抑郁症状。",
        asserted_components=("干预", "抑郁症状"),
        policy=V2AcquisitionPolicy(policy_identity=V2_CLAIM_PREVIEW_PROBE_POLICY_IDENTITY),
    ).output

    probe = acquisition.probes[0]
    assert probe.preview is not None and probe.preview.capture_usable is True
    assert probe.preview.outcome == "completed" and probe.preview.relevance_score > 0
    assert probe.succeeded is False
    assert probe.failure == "acquired snapshot cannot meet the minimum quote length"
    assert acquisition.survivors == ()
    assert acquisition.acquisitions[0].snapshot.normalized_text == text


def test_selection_preserves_one_source_envelope_and_lower_call_ceiling(tmp_path: Path) -> None:
    from test_v2_phase8_source_selection import _candidate, _selection_input

    from researchassistant.contracts.model_research import V2_PREVIEW_SELECTION_POLICY_IDENTITY

    run_id = uuid4()
    candidates = tuple(
        _candidate(uuid4(), family=f"family-{index}", probe_score=1) for index in range(4)
    )
    selection = _selection_input(candidates).model_copy(
        update={
            "run_id": run_id,
            "policy_identity": V2_PREVIEW_SELECTION_POLICY_IDENTITY,
        }
    )
    provider = Selector()
    budget = _budget(tokens_remaining=65000).model_copy(update={"physical_call_ceiling": 3})
    result = run_v2_source_selection_and_queue(
        db_path=_prepare_db(tmp_path, run_id),
        selection_input=selection,
        llm_provider=provider,
        routing_config=_routing(),
        budget=budget,
    )
    # Selection cannot consume capacity needed by the existing three-call source envelope.
    assert provider.requests == []
    assert result.used_fallback
    assert len(result.queued_source_ids) == 1
    assert result.physical_calls_after_reserve <= 3
