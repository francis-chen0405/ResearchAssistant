from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from test_fresh_quote_occurrences import NOW, Selector
from test_product_discovery_pipeline import _run
from test_v2_phase12_production import _routing

import researchassistant.research.v2_orchestrator as pipeline
import researchassistant.storage.saved_source_suggestions as suggestion_store
from researchassistant.agents.adaptive_handoffs import V2AdaptiveContinuationResult
from researchassistant.agents.evidence_checkpoint import CHECKPOINT_KEY, V2EvidenceCheckpoint
from researchassistant.agents.v2_extraction import V2ExtractionState, _extract_source
from researchassistant.common.research_guidance import (
    ASSESSED_FINDINGS_GUIDANCE,
    SAVED_LEADS_GUIDANCE,
)
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchControls,
    ResearchDirection,
    SelectedSentenceRange,
    V2VerbatimQuoteSelection,
)
from researchassistant.contracts.research_discovery import V2DiscoveryScoutOutput
from researchassistant.evidence.evidence_core import (
    assemble_fresh_selected_quote,
    build_source_snapshot,
    fresh_sentence_spans,
)
from researchassistant.evidence.source_excerpt import extraction_source_view
from researchassistant.providers.llm import LLMRequest, completion_token_allowance
from researchassistant.providers.mimo import _request_payload
from researchassistant.providers.normalization import PDF_OMISSION_MARKER
from researchassistant.providers.v2_budget import BudgetedV2LLMProvider, V2BudgetSnapshot
from researchassistant.storage.saved_source_suggestions import saved_source_suggestions
from researchassistant.storage.store import read_v2_artifact


def test_excerpt_keeps_original_offsets_and_focus_under_byte_bound() -> None:
    opening = "A navigation sentence. " * 150
    result = (
        "In the controlled community study, removing interacting species increased the probability "
        "of secondary extinctions compared with intact communities, with effects varying by the "
        "strength of trophic redundancy and the identity of the species removed."
    )
    text = opening + result + " References follow. " * 150
    view, exposed = extraction_source_view(text, (result,), max_bytes=900)
    assert len(view.encode("utf-8")) <= 900
    spans = fresh_sentence_spans(text)
    number = next(i for i, span in enumerate(spans, 1) if span.text == result)
    assert number in exposed and number > 100
    assert f"[{number}] {result}" in view
    quote, offsets = assemble_fresh_selected_quote(
        text,
        V2VerbatimQuoteSelection(
            selected_sentence_ranges=(
                SelectedSentenceRange(start_sentence=number, end_sentence=number),
            )
        ),
        truncated=False,
    )
    assert result in quote
    assert text[offsets[0].start_char : offsets[0].end_char] == result


def test_checkpoint_drives_search_and_sources_are_not_assessed_twice(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.sqlite"
    result, model, _search = _run(
        path,
        ResearchControls(
            discovery_providers=(DiscoveryProvider.EXA,),
            seed_expansion_enabled=False,
        ),
    )
    assert result.failure_reason is None
    checkpoint = V2EvidenceCheckpoint.model_validate_json(
        read_v2_artifact(path, result.run_id, CHECKPOINT_KEY).payload_json
    )
    assert 1 <= len(checkpoint.findings) <= 4
    gaps = [
        r for r in model.requests if r.requested_output_type.__name__ == "V2GapAnalysisModelOutput"
    ]
    assert gaps[0].input_artifact.assessed_source_findings == checkpoint.findings
    assert all(item.supported_proposition for item in checkpoint.findings)
    extraction_counts = Counter(r.source_id for r in model.requests if r.stage.value == "extractor")
    assert all(extraction_counts[w.source_id] == 1 for w in checkpoint.waves)
    assert all(w.admission is None for w in checkpoint.waves)
    assert set(extraction_counts) == {
        s.source_id for s in result.final_output.all_surviving_sources
    }
    request = next(r for r in model.requests if r.stage.value == "extractor")
    routing = _routing()
    config = routing.mimo_v25_pro.model_copy(update={"max_completion_tokens": 32768})
    assert completion_token_allowance(request, 32768) == 8192
    payload = _request_payload(request, config)
    assert payload["max_completion_tokens"] == 8192
    native_prompt = payload["messages"][0]["content"]
    controlled = json.loads(
        native_prompt.split("<APPLICATION_CONTROLLED_STAGE_INPUT>\n", 1)[1].split(
            "\n</APPLICATION_CONTROLLED_STAGE_INPUT>", 1
        )[0]
    )
    assert "untrusted_source_text" not in controlled
    assert "selectable_source_text" not in controlled
    view = controlled["UNTRUSTED_SOURCE_TEXT"]["selectable_source_text"]
    assert view == request.input_artifact.selectable_source_text
    assert len(view.encode("utf-8")) <= 8000
    assert ASSESSED_FINDINGS_GUIDANCE in _request_payload(gaps[0], config)["messages"][0]["content"]
    reservation = routing.preflight().reserve(
        request.stage, 1000, output_limit=completion_token_allowance(request, 32768)
    )
    assert reservation.output_tokens <= 8192


def test_extraction_cannot_select_a_sentence_omitted_from_the_view() -> None:
    text = " ".join(
        f"Source sentence number {i} describes the measured community." for i in range(500)
    )
    _view, exposed = extraction_source_view(text)
    hidden = next(i for i in range(1, 501) if i not in exposed)
    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.test/long-study",
        retrieved_at=NOW,
        normalized_text=text,
        truncated=False,
        created_at=NOW,
    )
    result = _extract_source(
        source_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        exact_claim="Species loss affects ecosystems.",
        snapshot=snapshot,
        query_id=uuid4(),
        query_round=1,
        search_rank=1,
        llm_provider=Selector(((hidden, hidden),)),
        clock=lambda: NOW,
    )
    assert result.state is V2ExtractionState.FAILED
    assert "unexposed sentence" in result.failure


def test_extraction_cannot_quote_across_a_pdf_capture_omission() -> None:
    text = (
        "Page 25\n"
        "The report describes measured changes in the study region.\n"
        f"{PDF_OMISSION_MARKER}\n"
        "Later findings describe a higher recorded extinction risk."
    )
    marker_sentence = next(
        index
        for index, span in enumerate(fresh_sentence_spans(text), 1)
        if PDF_OMISSION_MARKER in span.text
    )
    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.test/partial-report.pdf",
        retrieved_at=NOW,
        normalized_text=text,
        truncated=True,
        created_at=NOW,
    )
    result = _extract_source(
        source_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        exact_claim="Species loss affects ecosystems.",
        snapshot=snapshot,
        query_id=uuid4(),
        query_round=1,
        search_rank=1,
        llm_provider=Selector(((marker_sentence, marker_sentence),)),
        clock=lambda: NOW,
    )
    assert result.state is V2ExtractionState.FAILED
    assert "selected quotation crosses omitted PDF text" in result.failure


def test_oversized_unsplittable_source_is_unassessed_without_a_model_call() -> None:
    class NoCallSelector(Selector):
        def generate(self, request: LLMRequest) -> V2VerbatimQuoteSelection:
            raise AssertionError("an unreadable excerpt must not issue a model call")

    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.test/unsplittable",
        retrieved_at=NOW,
        normalized_text="unpunctuated " * 2000,
        truncated=False,
        created_at=NOW,
    )
    result = _extract_source(
        source_id=uuid4(),
        direction=ResearchDirection.SUPPORT,
        exact_claim="Species loss affects ecosystems.",
        snapshot=snapshot,
        query_id=uuid4(),
        query_round=1,
        search_rank=1,
        llm_provider=NoCallSelector(()),
        clock=lambda: NOW,
    )
    assert result.state is V2ExtractionState.FAILED
    assert "Source excerpt unavailable" in result.failure


def test_prior_run_leads_are_read_only_deduplicated_metadata_and_reassessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "reuse.sqlite"
    controls = ResearchControls(
        discovery_providers=(DiscoveryProvider.EXA,), seed_expansion_enabled=False
    )
    first, _model, _search = _run(path, controls)
    before = path.read_bytes(), path.stat().st_mtime_ns
    leads = saved_source_suggestions(path, uuid4(), "Regional program improves course completion")
    assert leads and len(leads) <= 12
    assert len({lead.source_url for lead in leads}) == len(leads)
    assert all(lead.origin_run_id == first.run_id for lead in leads)
    assert all(
        set(lead.model_dump())
        == {"origin_run_id", "origin_source_id", "title", "source_url", "doi"}
        for lead in leads
    )
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    original_read = suggestion_store.read_v2_artifact

    def same_paper_metadata(database: object, run_id: UUID, key: str) -> object:
        artifact = original_read(database, run_id, key)
        if artifact.artifact_type == "V2DiscoveryScoutOutput":
            discovery = V2DiscoveryScoutOutput.model_validate_json(artifact.payload_json)
            discovery = discovery.model_copy(
                update={
                    "items": tuple(
                        item.model_copy(update={"doi": "10.1234/shared-paper"})
                        for item in discovery.items
                    )
                }
            )
            return SimpleNamespace(payload_json=discovery.model_dump_json())
        return artifact

    with monkeypatch.context() as patch:
        patch.setattr(suggestion_store, "read_v2_artifact", same_paper_metadata)
        aliases = saved_source_suggestions(
            path, uuid4(), "Regional program improves course completion"
        )
        assert len(aliases) == 1
        assert aliases[0].doi == "10.1234/shared-paper"
    second, model, _search = _run(path, controls)
    assert second.failure_reason is None
    planner = next(r for r in model.requests if r.stage.value == "planner")
    assert planner.input_artifact.saved_source_leads
    assert (
        SAVED_LEADS_GUIDANCE
        in _request_payload(planner, _routing().mimo_v25_pro)["messages"][0]["content"]
    )
    assert any(r.stage.value == "extractor" for r in model.requests)
    assert first.run_id != second.run_id


def test_checkpoint_evidence_survives_an_exhausted_final_analysis_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drained = False
    original_search = pipeline.run_v2_adaptive_search_continuation
    original_snapshot = BudgetedV2LLMProvider.snapshot

    def finish_search(**kwargs: Any) -> V2AdaptiveContinuationResult:
        nonlocal drained
        result = original_search(**kwargs)
        drained = True
        return result

    def remaining(self: BudgetedV2LLMProvider) -> V2BudgetSnapshot:
        result = original_snapshot(self)
        return (
            result.model_copy(
                update={
                    "physical_calls_remaining": 0,
                    "tokens_remaining": 0,
                    "cost_remaining_usd": Decimal("0"),
                }
            )
            if drained
            else result
        )

    monkeypatch.setattr(pipeline, "run_v2_adaptive_search_continuation", finish_search)
    monkeypatch.setattr(BudgetedV2LLMProvider, "snapshot", remaining)
    result, model, _search = _run(
        tmp_path / "exhausted.sqlite",
        ResearchControls(
            discovery_providers=(DiscoveryProvider.EXA,),
            seed_expansion_enabled=False,
        ),
    )
    assert result.failure_reason is None
    assert result.final_output.post_analysis_assessment.admitted_source_ids
    # Only the initial checkpoint can run extraction once search has drained its budget.
    gaps = [i for i, r in enumerate(model.requests) if r.stage.value == "gap_analysis"]
    assert not any(r.stage.value == "extractor" for r in model.requests[gaps[-1] + 1 :])


def test_failed_follow_up_reports_completed_preliminary_assessments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_follow_up(**kwargs: Any) -> None:
        raise RuntimeError("offline follow-up failure after evidence checkpoint")

    monkeypatch.setattr(pipeline, "run_v2_adaptive_search_continuation", fail_follow_up)
    path = tmp_path / "failed-after-checkpoint.sqlite"
    result, _model, _search = _run(
        path,
        ResearchControls(
            discovery_providers=(DiscoveryProvider.EXA,),
            seed_expansion_enabled=False,
        ),
    )
    assert result.final_output is None
    assert "offline follow-up failure" in result.failure_reason
    checkpoint = V2EvidenceCheckpoint.model_validate_json(
        read_v2_artifact(path, result.run_id, CHECKPOINT_KEY).payload_json
    )
    assert checkpoint.waves
    before = path.read_bytes(), path.stat().st_mtime_ns
    diagnostics = pipeline.build_v2_run_diagnostics(path, result.run_id, (DiscoveryProvider.EXA,))
    assert diagnostics.sources_analyzed == len({wave.source_id for wave in checkpoint.waves})
    assert diagnostics.sources_queued_for_analysis >= diagnostics.sources_analyzed
    assert diagnostics.approved_evidence_records == 0
    assert result.diagnostics == diagnostics
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
