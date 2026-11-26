"""Regressions for the saved turf safety and maintenance run review."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from test_metadata_ranking import _item
from test_v2_phase5_acquisition_probe import _discovery
from test_v2_phase8_source_selection import _candidate
from test_v2_phase9_luna_evidence_analyst import (
    NOW,
    FakeLunaAnalyst,
    _assessment,
    _batch_input,
    _prepare_db,
    _routing,
)

from researchassistant.agents.adaptive_execution import _capture_exclusions
from researchassistant.agents.v2_evidence_analyst import (
    _exclude_discovery_only_finding,
    _preserve_exposure_caveat,
    run_v2_evidence_analyst,
)
from researchassistant.common.research_guidance import ANALYST_GUIDANCE
from researchassistant.contracts.discovery_v2 import V2MetadataDiscoveryPolicy
from researchassistant.contracts.model_evidence import V2EvidenceAnalystSnapshotContext
from researchassistant.contracts.models import V2AcquisitionProbeOutput, V2EvidenceAnalystState
from researchassistant.evidence.evidence_core import build_source_snapshot, fresh_sentence_spans
from researchassistant.evidence.source_excerpt import (
    extraction_source_view,
    source_context_excerpts,
)
from researchassistant.evidence.study_lineage import (
    _reported_sample_signature,
    build_study_lineage_notices,
)
from researchassistant.providers.mimo import _direct_mimo_prompt
from researchassistant.research.metadata_ranking import rank_metadata
from researchassistant.storage.store import insert_v2_artifact


def test_unattempted_prior_discovery_is_eligible_for_later_capture(tmp_path: Path) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    url = "https://example.test/field-cost-report"
    discovery = _discovery(run_id, (url,), ("retrieve",))
    # Earlier discovery saw it, but the capture allowance was exhausted.
    acquisition = V2AcquisitionProbeOutput(
        run_id=run_id,
        directions=discovery.directions,
        attempts=(),
        acquisitions=(),
        probes=(),
        survivors=(),
        completed_at=NOW,
    )
    insert_v2_artifact(path, "phase-4-discovery-scout", discovery, NOW)
    insert_v2_artifact(path, "phase-5-acquisition-probe", acquisition, NOW)
    excluded, locations = _capture_exclusions(path, discovery, 2, frozenset({url}), True, True)
    assert excluded == locations == frozenset()
    # Historical unranked exclusion policy retains its recorded meaning.
    assert _capture_exclusions(path, discovery, 2, frozenset({url}), False, False)[0]


def test_excerpt_exposes_main_result_and_denominator_caveat_beside_background() -> None:
    background = "A cited study reported more hamstring injuries on grass."
    result = "Overall injury incidence was lower on artificial turf (IRR 0.86, CI 0.78–0.95)."
    caveat = "The lack of exposure data limits the ability to calculate true injury rates."
    text = background + " Navigation without substantive findings." * 180 + result + " " + caveat
    view, selected = extraction_source_view(text, (background,), max_bytes=1800)
    assert result in view and caveat in view
    assert len(view.encode()) <= 1800
    spans = fresh_sentence_spans(text)
    assert all(f"[{index}] {spans[index - 1].text}" in view for index in selected)
    assert caveat in source_context_excerpts(text)


@pytest.mark.parametrize(
    "proposition",
    [
        "The page lists a study whose title reports higher injury incidence on artificial turf.",
        "The researchers hypothesized that artificial turf would increase sports injuries.",
    ],
)
def test_discovery_only_findings_are_rejected_without_another_call(
    tmp_path: Path, proposition: str
) -> None:
    run_id = uuid4()
    batch = _batch_input(run_id)
    assessment = _assessment().model_copy(update={"narrowest_supported_proposition": proposition})
    provider = FakeLunaAnalyst([assessment])
    path = _prepare_db(tmp_path, run_id)
    kwargs = dict(
        db_path=path,
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    first = run_v2_evidence_analyst(**kwargs)
    assert first.source_results[0].state is V2EvidenceAnalystState.REJECTED
    assert first.source_results[0].score_decision.claim_fit == 1
    assert run_v2_evidence_analyst(**kwargs) == first
    assert len(provider.requests) == 1
    assert ANALYST_GUIDANCE in provider.requests[0].rendered_prompt
    assert ANALYST_GUIDANCE in _direct_mimo_prompt(provider.requests[0])


def test_hypothesis_with_reported_findings_is_not_discarded() -> None:
    assessment = _assessment().model_copy(
        update={
            "narrowest_supported_proposition": (
                "The study hypothesized a benefit and found 62% completion."
            )
        }
    )
    assert _exclude_discovery_only_finding(assessment) == assessment


def test_missing_exposure_data_survives_into_factual_statement() -> None:
    context = V2EvidenceAnalystSnapshotContext(
        snapshot_id=uuid4(),
        snapshot_sha256="a" * 64,
        source_url="https://example.test/study",
        word_count=4000,
        truncated=False,
        preceding_context="A study.",
        following_context="More context.",
        source_excerpts=(
            "The lack of exposure data limits the ability to calculate true injury rates.",
        ),
    )
    assessment = _assessment().model_copy(
        update={
            "canonical_factual_statement": "In this study, fractures were more likely on grass."
        }
    )
    corrected = _preserve_exposure_caveat(assessment, context)
    assert "cannot establish injury rates per hour" in corrected.canonical_factual_statement
    assert any("exposure" in item for item in corrected.material_limitations)
    assert corrected.narrowest_supported_proposition == assessment.narrowest_supported_proposition
    legacy = context.model_copy(update={"source_excerpts": ()}).model_dump(mode="json")
    assert "source_excerpts" not in legacy
    assert V2EvidenceAnalystSnapshotContext.model_validate(legacy).source_excerpts == ()
    full = assessment.model_copy(
        update={
            "material_limitations": tuple(f"Recorded limitation {index}." for index in range(12))
        }
    )
    preserved = _preserve_exposure_caveat(full, context)
    assert len(preserved.material_limitations) == 12
    assert all(
        any(item in text for text in preserved.material_limitations)
        for item in full.material_limitations
    )


@pytest.mark.parametrize(
    "title",
    [
        "Natural grass versus synthetic turf: cost-benefit analysis",
        "20 year cost to meet the field need in Wayland with TURF and GRASS",
    ],
)
def test_comparative_financial_report_has_method_signal_without_publisher_bias(title: str) -> None:
    report = _item(
        0,
        title=title,
        abstract=None,
        source_type=None,
    )
    marketing = _item(
        1,
        title="Natural grass versus synthetic turf: save on maintenance",
        abstract=None,
        source_type=None,
    )
    kwargs = dict(
        exact_claim="Artificial turf costs less to maintain than natural grass",
        policy=V2MetadataDiscoveryPolicy(),
    )
    current = rank_metadata((marketing, report), **kwargs)
    assert current[0].item_id == report.item_id
    assert current[0].method_fit == 0.8
    historical = rank_metadata((report,), ranking_identity="source-candidate-ranking-v5", **kwargs)
    assert historical[0].method_fit is None


@pytest.mark.parametrize("reference_only", [False, True])
def test_matching_sample_accounts_warn_without_merging_evidence(reference_only: bool) -> None:
    run_id = uuid4()
    first = _candidate(uuid4(), family="a", probe_score=7)
    second = _candidate(uuid4(), family="b", probe_score=7)
    first = first.model_copy(update={"title": "High school sports injury report"})
    second = second.model_copy(update={"title": "Surface comparison: a retrospective cohort"})
    body = (
        "Researchers identified 953 injuries among high school athletes, with 585 occurring "
        "on artificial turf and 368 on natural grass. Data collected from high schools was "
        "analyzed to compare injury incidences based on sport."
    )
    snapshots = {
        candidate.source_id: build_source_snapshot(
            run_id=run_id,
            retrieval_attempt_id=uuid4(),
            snapshot_id=uuid4(),
            source_url=candidate.source_url,
            retrieved_at=NOW,
            normalized_text=("Introduction.\nReferences\n" if reference_only else "") + body,
            truncated=False,
            created_at=NOW,
        )
        for candidate in (first, second)
    }
    notices = build_study_lineage_notices((first, second), snapshots=snapshots)
    assert len(notices) == (0 if reference_only else 1)
    if notices:
        assert notices[0].basis == "matching_reported_sample"
        assert "unverified" in notices[0].explanation
    assert (first.source_family_id, second.source_family_id) == ("a", "b")


def test_source_context_excerpts_are_bounded_exact_untrusted_text() -> None:
    text = " ".join(
        f"Our results found {index} outcomes with confounding limitations." for index in range(30)
    )
    excerpts = source_context_excerpts(text)
    assert len(excerpts) <= 6
    assert all(excerpt in text and len(excerpt) <= 1800 for excerpt in excerpts)


def test_matching_decimal_statistics_do_not_establish_shared_sample_counts() -> None:
    numbers, _terms = _reported_sample_signature(
        "Results: We found odds ratios of 1.234, 2.456, and 3.789 with P < 0.001 "
        "and P < 0.005 in the study published in 2025."
    )
    assert numbers == frozenset()
