from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pytest
from test_v2_phase5_acquisition_probe import FixtureScraper, _discovery, _prepare_db, _response

from agents.v2_acquisition import run_v2_acquisition_probe
from agents.v2_adaptive_search import V2MergedSurvivor, V2MergedSurvivorPool
from agents.v2_source_selection import build_v2_source_selection_input
from researchassistant.contracts.discovery_v2 import (
    V2PreviewRequest,
    V2PreviewResult,
    V2PreviewSpan,
    discovery_id,
)
from researchassistant.contracts.model_contracts import SourceSnapshot
from researchassistant.contracts.model_research import (
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
    V2SourceSelectionInput,
)

CLAIM = "The intervention changes the outcome."
SOURCE_TEXT = (
    "Researchers compared outcomes before and after the intervention. "
    "The study reports measured changes in the primary outcome and describes its method. "
    "The authors discuss limitations and recommend careful evaluation of the results. "
) * 4


def _acquired_case(
    tmp_path: Path,
) -> tuple[
    V2DiscoveryScoutOutput,
    V2AcquisitionProbeOutput,
    V2MergedSurvivorPool,
    SourceSnapshot,
]:
    run_id = uuid4()
    url = "https://example.test/preview-source"
    discovery = _discovery(run_id, (url,), ("retrieve",))
    db_path = _prepare_db(tmp_path, run_id)
    acquisition = run_v2_acquisition_probe(
        db_path=db_path,
        discovery_output=discovery,
        wigolo_provider=FixtureScraper({url: _response(url, SOURCE_TEXT)}),
        clock=lambda: discovery.completed_at,
    ).output
    survivor = acquisition.survivors[0]
    snapshot = acquisition.acquisitions[0].snapshot
    merged = V2MergedSurvivorPool(
        run_id=run_id,
        sources=(
            V2MergedSurvivor(
                research_round=1,
                source_url=url,
                survivor=survivor,
            ),
        ),
    )
    return discovery, acquisition, merged, snapshot


def _preview(
    request: V2PreviewRequest,
    snapshot: SourceSnapshot,
    *,
    text_override: str | None = None,
    request_update: dict[str, object] | None = None,
    outcome: Literal["completed", "unavailable"] = "completed",
) -> V2PreviewResult:
    exact_text = snapshot.normalized_text[:120]
    span_text = text_override if text_override is not None else exact_text
    preview_request = (
        request.model_copy(update=request_update) if request_update is not None else request
    )
    spans = (
        ()
        if outcome == "unavailable"
        else (
            V2PreviewSpan(
                start=0,
                end=len(exact_text),
                text=span_text,
                section="results",
            ),
        )
    )
    identity_key = f"test-preview/{request.snapshot_id}"
    return V2PreviewResult(
        run_id=request.run_id,
        artifact_id=discovery_id(request.run_id, "V2PreviewResult", identity_key),
        identity_key=identity_key,
        request=preview_request,
        spans=spans,
        content_classification="full_text" if outcome == "completed" else "unknown",
        outcome=outcome,
        reason="fixture exact snapshot span" if spans else "preview unavailable in fixture",
    )


def _build(
    case: tuple[
        V2DiscoveryScoutOutput,
        V2AcquisitionProbeOutput,
        V2MergedSurvivorPool,
        SourceSnapshot,
    ],
    *,
    preview_builder: Callable[[V2PreviewRequest, SourceSnapshot], V2PreviewResult] | None,
) -> V2SourceSelectionInput:
    discovery, acquisition, merged, _snapshot_value = case
    return build_v2_source_selection_input(
        exact_claim=CLAIM,
        merged_survivors=merged,
        discovery_outputs=(discovery,),
        acquisition_outputs=(acquisition,),
        gap_outputs=(),
        preview_builder=preview_builder,
    )


def test_valid_preview_replaces_probe_passages_with_exact_snapshot_text(tmp_path: Path) -> None:
    case = _acquired_case(tmp_path)
    _discovery_output, _acquisition_output, _merged, snapshot = case
    called: list[tuple[V2PreviewRequest, SourceSnapshot]] = []

    def builder(request: V2PreviewRequest, source: SourceSnapshot) -> V2PreviewResult:
        called.append((request, source))
        return _preview(request, source)

    selection = _build(case, preview_builder=builder)

    assert len(called) == 1
    assert called[0][0].exact_claim == CLAIM
    assert called[0][1].snapshot_id == snapshot.snapshot_id
    assert len(selection.survivors) == 1
    assert selection.survivors[0].probe_passages[0].text == snapshot.normalized_text[:120]
    assert selection.survivors[0].probe_passages[0].passage_id.startswith("preview:")


def test_unavailable_preview_falls_back_to_persisted_probe_passages(tmp_path: Path) -> None:
    case = _acquired_case(tmp_path)
    acquisition = case[1]

    def builder(request: V2PreviewRequest, snapshot: SourceSnapshot) -> V2PreviewResult:
        return _preview(request, snapshot, outcome="unavailable")

    selection = _build(case, preview_builder=builder)

    assert tuple(item.text for item in selection.survivors[0].probe_passages) == tuple(
        item.text for item in acquisition.probes[0].passages
    )
    assert not selection.survivors[0].probe_passages[0].passage_id.startswith("preview:")


@pytest.mark.parametrize("forgery", ["text", "snapshot", "claim"])
def test_forged_preview_text_snapshot_or_claim_is_rejected(
    tmp_path: Path,
    forgery: str,
) -> None:
    case = _acquired_case(tmp_path)

    def builder(request: V2PreviewRequest, snapshot: SourceSnapshot) -> V2PreviewResult:
        if forgery == "text":
            exact_text = snapshot.normalized_text[:120]
            altered = ("X" if exact_text[0] != "X" else "Y") + exact_text[1:]
            return _preview(request, snapshot, text_override=altered)
        if forgery == "snapshot":
            return _preview(request, snapshot, request_update={"snapshot_hash": "0" * 64})
        return _preview(request, snapshot, request_update={"exact_claim": "A different claim."})

    expected = (
        "text/context differs from immutable snapshot"
        if forgery == "text"
        else "exact claim/snapshot request"
    )
    with pytest.raises(ValueError, match=expected):
        _build(case, preview_builder=builder)
