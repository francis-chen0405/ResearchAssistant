"""Typed preview diagnostics remain inspectable through the read-only history trail."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from test_historical_reads_phase3 import WHEN, _v2_trail_database

from frontend.live_history import research_trail
from researchassistant.contracts.discovery_v2 import (
    V2PreviewRequest,
    V2PreviewResult,
    V2PreviewSpan,
    discovery_id,
)
from researchassistant.contracts.metadata_ranking import MetadataRank
from researchassistant.contracts.model_research import (
    V2AcquisitionProbeOutput,
    V2DeepAnalysisBudget,
    V2DeepAnalysisSourceStatus,
    V2DeepAnalysisTokenReservation,
    V2SourceSelectionCandidate,
    V2SourceSelectionInput,
    V2SourceSelectionQueueResult,
    V2SourceSelectionRecommendation,
    V2SourceSelectionSearchProvenance,
)
from researchassistant.contracts.models import ResearchDirection, ResearchDirections
from researchassistant.storage.store import insert_v2_artifact


def _attach_probe_preview(path: Path, run_id: UUID) -> V2PreviewResult:
    """Add a valid current preview to the offline round-one fixture artifact."""
    cluster_id = UUID(int=201)
    snapshot_id = UUID(int=401)
    text = "Offline source text for public research trail round 1."
    digest = sha256(text.encode()).hexdigest()
    identity_key = f"probe-preview/{cluster_id}/{snapshot_id}"
    request = V2PreviewRequest(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2PreviewRequest", identity_key),
        identity_key=identity_key,
        exact_claim="Offline claim for historical trail compatibility.",
        direction=ResearchDirection.SUPPORT,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        source_id=cluster_id,
        snapshot_id=snapshot_id,
        snapshot_hash=digest,
        preview_identity="source-claim-preview-v2",
    )
    preview = V2PreviewResult(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2PreviewResult", identity_key),
        identity_key=identity_key,
        request=request,
        spans=(
            V2PreviewSpan(
                start=0,
                end=len(text),
                text=text,
                section="results",
                relevance_signals=("claim component match",),
                omitted_before=False,
                omitted_after=False,
            ),
        ),
        content_classification="full_text",
        outcome="completed",
        reason="Exact substantive result window found.",
        observed_sections=("results",),
        missing_sections=("methods",),
        snapshot_truncated=False,
        capture_usable=True,
        relevance_score=82,
    )
    artifact_key = "phase-5-acquisition-probe"
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT payload_json FROM v2_artifacts WHERE run_id=? AND artifact_key=?",
            (str(run_id), artifact_key),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload["probes"][0]["preview"] = preview.model_dump(mode="json")
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        triggers = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='v2_artifacts'"
        ).fetchall()
        try:
            for name, _sql in triggers:
                connection.execute(f'DROP TRIGGER "{name}"')
            connection.execute(
                "UPDATE v2_artifacts SET payload_json=?, payload_sha256=? "
                "WHERE run_id=? AND artifact_key=?",
                (
                    payload_json,
                    sha256(payload_json.encode()).hexdigest(),
                    str(run_id),
                    artifact_key,
                ),
            )
        finally:
            for _name, sql in triggers:
                connection.execute(sql)
        connection.commit()
    return preview


def test_trail_exposes_exact_probe_preview_as_non_evidence(tmp_path: Path) -> None:
    database = tmp_path / "preview-trail.sqlite3"
    run_id, _item_ids = _v2_trail_database(database)
    expected = _attach_probe_preview(database, run_id)
    before = database.read_bytes(), database.stat().st_mtime_ns

    trail = research_trail(database, run_id)

    item = next(item for item in trail.items if item.research_round == 1)
    assert item.preview == expected
    assert item.preview is not None
    assert item.preview.spans[0].text == "Offline source text for public research trail round 1."
    assert item.preview.relevance_score == 82
    assert item.preview.reason == "Exact substantive result window found."
    assert item.metadata_rank is None
    assert item.selection_rationale is None
    assert item.source_selection_rank is None
    assert item.source_selection_status is None
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before


def test_historical_trail_leaves_preview_and_selection_details_absent(tmp_path: Path) -> None:
    database = tmp_path / "historical-trail.sqlite3"
    run_id, _item_ids = _v2_trail_database(database)

    trail = research_trail(database, run_id)

    item = next(item for item in trail.items if item.research_round == 1)
    assert item.preview is None
    assert item.metadata_rank is None
    assert item.selection_rationale is None
    assert item.source_selection_rank is None
    assert item.source_selection_status is None
    assert not trail.compatibility_issues


def _attach_selection_result(
    database: Path, run_id: UUID
) -> tuple[V2PreviewResult, MetadataRank, str]:
    _attach_probe_preview(database, run_id)
    cluster_id = UUID(int=201)
    item_id = UUID(int=1)
    identity_key = f"selection-preview/{cluster_id}/{UUID(int=401)}"
    text = "Offline source text for public research trail round 1."
    digest = sha256(text.encode()).hexdigest()
    directions = ResearchDirections(support_enabled=True, challenge_enabled=False)
    request = V2PreviewRequest(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2PreviewRequest", identity_key),
        identity_key=identity_key,
        exact_claim="Offline claim for historical trail compatibility.",
        direction=ResearchDirection.SUPPORT,
        directions=directions,
        source_id=cluster_id,
        snapshot_id=UUID(int=401),
        snapshot_hash=digest,
        preview_identity="source-claim-preview-v2",
    )
    selection_preview = V2PreviewResult(
        run_id=run_id,
        artifact_id=discovery_id(run_id, "V2PreviewResult", identity_key),
        identity_key=identity_key,
        request=request,
        spans=(
            V2PreviewSpan(
                start=0,
                end=len(text),
                text=text,
                section="results",
                relevance_signals=("selection-stage relevance",),
                omitted_before=False,
                omitted_after=False,
            ),
        ),
        content_classification="full_text",
        outcome="completed",
        reason="Selection preview confirms a relevant results section.",
        observed_sections=("results",),
        missing_sections=("methods",),
        snapshot_truncated=False,
        capture_usable=True,
        relevance_score=91,
    )
    metadata_rank = MetadataRank(
        item_id=item_id,
        rank=3,
        score=0.72,
        directness=0.8,
        method_fit=0.7,
        gap_fit=0.6,
        identity_completeness=0.9,
        novelty=0.5,
        diversity=0.8,
        work_key="doi:10.0000/offline",
        lane_direction=ResearchDirection.SUPPORT,
        lane_provider="exa",
        rationale=("Metadata suggests a direct study match.",),
    )
    candidate = V2SourceSelectionCandidate(
        source_id=cluster_id,
        direction=ResearchDirection.SUPPORT,
        source_family_id="family:offline",
        research_round=1,
        source_url="https://example.test/history/1",
        title="Offline study",
        discovery_providers=("exa",),
        probe_passages=(),
        search_provenance=(
            V2SourceSelectionSearchProvenance(
                query_id=UUID(int=101),
                provider="exa",
                round_number=1,
                query_text="offline history query 1",
                targeted_gap_ids=(),
            ),
        ),
        snapshot_word_count=len(text.split()),
        deep_analysis_input_tokens=1000,
        preview=selection_preview,
        metadata_ranks=(metadata_rank,),
    )
    selection_input = V2SourceSelectionInput(
        run_id=run_id,
        exact_claim="Offline claim for historical trail compatibility.",
        directions=directions,
        survivors=(candidate,),
        gap_history=(),
        policy_identity="researchassistant-v2-phase-8-source-selection-v2",
    )
    rationale = "Relevant exact results window supports prioritizing this source."
    queue_result = V2SourceSelectionQueueResult(
        run_id=run_id,
        input=selection_input,
        initial_budget=V2DeepAnalysisBudget(
            physical_calls_used=0,
            tokens_remaining=10000,
            cost_remaining_usd=Decimal("1.00"),
        ),
        recommended_source_ids=(cluster_id,),
        recommendation_rationales=(
            V2SourceSelectionRecommendation(source_id=cluster_id, rationale=rationale),
        ),
        used_fallback=True,
        selection_attempts=0,
        selection_attempt_records=(),
        queued_source_ids=(cluster_id,),
        source_statuses=(
            V2DeepAnalysisSourceStatus(
                source_id=cluster_id,
                direction=ResearchDirection.SUPPORT,
                recommended=True,
                recommendation_rank=1,
                selection_rationale=rationale,
                queued_for_deep_analysis=True,
                queue_rank=1,
            ),
        ),
        queue_capacity=1,
        mandatory_synthesis_reservable=True,
        physical_calls_after_reserve=3,
        total_reserved_tokens=1000,
        total_reserved_cost_usd=Decimal("0.01"),
        token_reservations=(
            V2DeepAnalysisTokenReservation(
                source_id=cluster_id,
                queue_size=1,
                cumulative_reserved_tokens=1000,
                cumulative_reserved_cost_usd=Decimal("0.01"),
            ),
        ),
        completed_at=WHEN,
    )
    insert_v2_artifact(
        str(database),
        "phase-13-source-selection-deep-analysis-queue-analyzer-admission",
        queue_result,
        WHEN,
    )
    return selection_preview, metadata_rank, rationale


def test_selection_preview_and_rationale_supersede_probe_preview(tmp_path: Path) -> None:
    database = tmp_path / "selected-preview-trail.sqlite3"
    run_id, _item_ids = _v2_trail_database(database)
    selection_preview, metadata_rank, rationale = _attach_selection_result(database, run_id)

    trail = research_trail(database, run_id)

    item = next(item for item in trail.items if item.research_round == 1)
    assert item.preview == selection_preview
    assert item.preview is not None
    assert item.preview.reason == "Selection preview confirms a relevant results section."
    assert item.metadata_rank == metadata_rank
    assert item.selection_rationale == rationale
    assert item.source_selection_rank == 1
    assert item.source_selection_status == "recommended"


def _replace_fixture_artifact(
    connection: sqlite3.Connection, key: str, payload: dict[str, Any]
) -> None:
    """Simulate a checksum-valid corrupt artifact in a disposable fixture only."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    triggers = connection.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='v2_artifacts'"
    ).fetchall()
    try:
        for name, _sql in triggers:
            connection.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
        connection.execute(
            "UPDATE v2_artifacts SET payload_json=?, payload_sha256=? WHERE artifact_key=?",
            (encoded, sha256(encoded.encode()).hexdigest(), key),
        )
    finally:
        for _name, sql in triggers:
            connection.execute(sql)


@pytest.mark.parametrize("mismatch", ["source", "direction"])
def test_trail_rejects_checksum_valid_preview_with_wrong_acquisition_owner(
    tmp_path: Path, mismatch: str
) -> None:
    database = tmp_path / "mismatched-preview.sqlite3"
    run_id, _item_ids = _v2_trail_database(database)
    _attach_selection_result(database, run_id)
    acquisition_key = "phase-5-acquisition-probe"
    selection_key = "phase-13-source-selection-deep-analysis-queue-analyzer-admission"
    with sqlite3.connect(database) as connection:
        payloads = dict(connection.execute("SELECT artifact_key, payload_json FROM v2_artifacts"))
        acquisition = json.loads(payloads[acquisition_key])
        selection = json.loads(payloads[selection_key])
        if mismatch == "source":
            # A real second acquired source has identical captured text/hash but
            # its own snapshot ID. A's preview must not borrow that snapshot.
            other = json.loads(json.dumps(acquisition["acquisitions"][0]))
            other["cluster_id"] = str(UUID(int=299))
            other["snapshot"]["snapshot_id"] = str(UUID(int=499))
            other["snapshot"]["source_url"] = "https://example.test/other-source"
            acquisition["acquisitions"].append(other)
            probe = json.loads(json.dumps(acquisition["probes"][0]))
            probe.update(
                cluster_id=other["cluster_id"], snapshot_id=other["snapshot"]["snapshot_id"]
            )
            probe.pop("preview")
            acquisition["probes"].append(probe)
            selection["input"]["survivors"][0]["preview"]["request"]["snapshot_id"] = other[
                "snapshot"
            ]["snapshot_id"]
        else:
            both = {"support_enabled": True, "challenge_enabled": True}
            acquisition["directions"] = both
            acquisition["acquisitions"][0]["direction"] = "challenge"
            acquisition["probes"][0].pop("preview")
            selection["input"]["directions"] = both
            selection["input"]["survivors"][0]["preview"]["request"]["directions"] = both
        # These records satisfy their own schemas and exact snapshot hash/text
        # checks. Rejection must come from cross-artifact source/lane ownership.
        V2AcquisitionProbeOutput.model_validate(acquisition)
        V2SourceSelectionQueueResult.model_validate(selection)
        _replace_fixture_artifact(connection, acquisition_key, acquisition)
        _replace_fixture_artifact(connection, selection_key, selection)
    before = database.read_bytes(), database.stat().st_mtime_ns

    trail = research_trail(database, run_id)

    item = next(item for item in trail.items if item.research_round == 1)
    assert len(trail.compatibility_issues) == 1
    assert trail.compatibility_issues[0].record_key == selection_key
    if mismatch == "direction":
        assert item.preview is None
    else:
        assert item.preview is not None
    if item.preview is not None:
        # Safe fallback is A's validated acquisition preview, never B's snapshot.
        assert item.preview.request.snapshot_id == UUID(int=401)
        assert item.preview.reason == "Exact substantive result window found."
    assert (database.read_bytes(), database.stat().st_mtime_ns) == before
