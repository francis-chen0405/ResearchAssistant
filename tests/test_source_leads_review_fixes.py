"""Saved-source review regressions, using only isolated offline databases."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from test_acquisition_usable_fallback import ALTERNATE, LANDING, _clustered, _policy
from test_historical_reads_phase3 import _cases, _v2_envelope
from test_source_leads import _captured
from test_v2_phase5_acquisition_probe import NOW, FixtureScraper, _discovery, _prepare_db, _response
from test_v2_phase9_luna_evidence_analyst import (
    FakeLunaAnalyst,
    _assessment,
    _batch_input,
    _draft,
    _routing,
)

from researchassistant.agents import v2_evidence_admission
from researchassistant.agents.v2_acquisition import run_v2_acquisition_probe
from researchassistant.agents.v2_evidence_analyst import run_v2_evidence_analyst
from researchassistant.contracts.historical import HistoricalRead
from researchassistant.contracts.model_evidence import (
    V2EvidenceAdmissionBatchResult,
    V2EvidenceAdmissionSourceResult,
    V2EvidenceAnalystBatchResult,
    V2EvidenceRelationship,
)
from researchassistant.contracts.models import StrictModel, V2SourceSelectionQueueResult
from researchassistant.contracts.research_selection import V2SourceSelectionInput
from researchassistant.providers.v2_budget import V2CancellationRequested
from researchassistant.storage.historical_decode import decode_v2_artifact
from researchassistant.storage.source_leads import read_source_leads
from researchassistant.storage.store import insert_v2_artifact, read_v2_artifact


def _save_discovery_for_survivors(path: str, selection: V2SourceSelectionInput) -> None:
    for number in sorted({source.research_round for source in selection.survivors}):
        sources = tuple(source for source in selection.survivors if source.research_round == number)
        by_url = {source.source_url: source for source in sources}
        discovery = _discovery(
            selection.run_id,
            tuple(source.source_url for source in sources),
            tuple("retrieve" for _source in sources),
        )
        items = tuple(
            item.model_copy(
                update={
                    "round_number": number,
                    "direction": by_url[item.source_url].direction,
                    "provenance_chain": tuple(
                        provenance.model_copy(
                            update={
                                "round_number": number,
                                "direction": by_url[item.source_url].direction,
                            }
                        )
                        for provenance in item.provenance_chain
                    ),
                }
            )
            for item in discovery.items
        )
        provenance_by_item = {item.item_id: item.provenance_chain for item in items}
        clusters = tuple(
            cluster.model_copy(
                update={
                    "cluster_id": by_url[cluster.preferred_url].source_id,
                    "metadata_provenance": tuple(
                        provenance
                        for item_id in cluster.item_ids
                        for provenance in provenance_by_item[item_id]
                    ),
                }
            )
            for cluster in discovery.clusters
        )
        discovery = discovery.model_copy(update={"items": items, "clusters": clusters})
        key = (
            "phase-4-discovery-scout" if number == 1 else f"phase-7-round-{number}-discovery-scout"
        )
        insert_v2_artifact(path, key, discovery, NOW)


def _rewrite_artifact(
    path: str,
    key: str,
    mutation: Callable[[dict[str, Any]], None] | None = None,
    *,
    new_key: str | None = None,
    corrupt_checksum: bool = False,
) -> None:
    """Explicitly corrupt an isolated fixture, restoring product triggers afterward."""
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT payload_json FROM v2_artifacts WHERE artifact_key=?", (key,)
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        if mutation is not None:
            mutation(payload)
        encoded = json.dumps(payload)
        digest = "0" * 64 if corrupt_checksum else sha256(encoded.encode()).hexdigest()
        triggers = connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='v2_artifacts'"
        ).fetchall()
        for name, _sql in triggers:
            connection.execute(f'DROP TRIGGER "{name}"')
        connection.execute(
            "UPDATE v2_artifacts SET artifact_key=?,payload_json=?,payload_sha256=? "
            "WHERE artifact_key=?",
            (new_key or key, encoded, digest, key),
        )
        for _name, sql in triggers:
            connection.execute(sql)


def _admission_fixture(
    tmp_path: Path,
    *,
    include_batch: bool = False,
    relationship: V2EvidenceRelationship = V2EvidenceRelationship.SUPPORTS,
    claim_fit: int = 4,
) -> tuple[str, UUID, V2EvidenceAdmissionSourceResult, V2EvidenceAnalystBatchResult]:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    batch = _batch_input(run_id)
    _save_discovery_for_survivors(path, batch.queue_result.input)
    assessment = _assessment(relationship=relationship, claim_fit=claim_fit)
    if relationship is V2EvidenceRelationship.UNRELATED:
        assessment = assessment.model_copy(
            update={
                "canonical_factual_statement": None,
                "reasoning": (
                    "The saved study measures attendance, not the claimed completion outcome."
                ),
            }
        )
    elif claim_fit < 3:
        assessment = assessment.model_copy(
            update={
                "reasoning": (
                    "The source reports a regional association and cannot establish "
                    "this broader claim."
                ),
            }
        )
    responses: list[StrictModel | Exception] = [assessment]
    if relationship is not V2EvidenceRelationship.UNRELATED and claim_fit >= 3:
        assert assessment.canonical_factual_statement is not None
        responses.append(_draft(assessment, assessment.canonical_factual_statement))
    provider = FakeLunaAnalyst(responses)
    analyst = run_v2_evidence_analyst(
        db_path=path,
        batch_input=batch,
        llm_provider=provider,
        routing_config=_routing(),
        clock=lambda: NOW,
    )
    if include_batch:
        v2_evidence_admission.run_v2_evidence_admission(
            db_path=path, analyst_result=analyst, clock=lambda: NOW
        )
    else:
        original_insert = v2_evidence_admission.insert_v2_artifact

        def interrupt_aggregate(
            db_path: str | Path,
            artifact_key: str,
            artifact: StrictModel,
            created_at: datetime,
        ) -> None:
            if isinstance(artifact, V2EvidenceAdmissionBatchResult):
                raise V2CancellationRequested("offline interruption before admission aggregate")
            original_insert(db_path, artifact_key, artifact, created_at)

        with pytest.MonkeyPatch.context() as patcher:
            patcher.setattr(v2_evidence_admission, "insert_v2_artifact", interrupt_aggregate)
            with pytest.raises(V2CancellationRequested, match="offline interruption"):
                v2_evidence_admission.run_v2_evidence_admission(
                    db_path=path, analyst_result=analyst, clock=lambda: NOW
                )
    source_id = batch.queued_candidates[0].source_id
    source = V2EvidenceAdmissionSourceResult.model_validate_json(
        read_v2_artifact(
            path, run_id, f"phase-13-evidence-admission-source-v2-{source_id}"
        ).payload_json
    )
    return path, run_id, source, analyst


@pytest.mark.parametrize("case_name", ("queue-cap12", "analyst-v1", "analyst-v2"))
def test_known_historical_stages_remain_inspectable_without_conversion(
    tmp_path: Path, case_name: str
) -> None:
    fixture = next(
        case for case in _cases("v2-prior-policy-artifacts.json") if case["case"] == case_name
    )
    model_type = (
        V2SourceSelectionQueueResult if case_name == "queue-cap12" else V2EvidenceAnalystBatchResult
    )
    key = (
        "phase-8-source-selection-deep-analysis-queue"
        if case_name == "queue-cap12"
        else "phase-9-luna-evidence-analyst"
    )
    envelope = _v2_envelope(fixture).model_copy(update={"artifact_key": key})
    decoded = decode_v2_artifact(envelope, model_type)
    assert isinstance(decoded, HistoricalRead)
    queue = (
        decoded if isinstance(decoded, V2SourceSelectionQueueResult) else decoded.input.queue_result
    )
    path = _prepare_db(tmp_path, envelope.run_id)
    _save_discovery_for_survivors(path, queue.input)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO v2_artifacts(run_id,artifact_key,artifact_type,payload_json,"
            "payload_sha256,created_at) VALUES(?,?,?,?,?,?)",
            (
                str(envelope.run_id),
                key,
                envelope.artifact_type,
                envelope.payload_json,
                envelope.payload_sha256,
                envelope.created_at.isoformat(),
            ),
        )
    before = Path(path).read_bytes(), Path(path).stat().st_mtime_ns
    page = read_source_leads(path, envelope.run_id)
    assert {lead.source_id for lead in page.items} == {
        source.source_id for source in queue.input.survivors
    }
    stage = "selection" if case_name == "queue-cap12" else "analysis"
    assert all(any(step.stage == stage for step in lead.history) for lead in page.items)
    assert (Path(path).read_bytes(), Path(path).stat().st_mtime_ns) == before
    assert read_v2_artifact(path, envelope.run_id, key).payload_json == envelope.payload_json


@pytest.mark.parametrize("legacy_key", (False, True))
def test_interrupted_admission_retains_saved_state_and_source_family(
    tmp_path: Path, legacy_key: bool
) -> None:
    path, run_id, source, _analyst = _admission_fixture(tmp_path)
    if legacy_key:
        _rewrite_artifact(
            path,
            f"phase-13-evidence-admission-source-v2-{source.source_id}",
            new_key=f"phase-13-evidence-admission-source-{source.source_id}",
        )
    before = Path(path).read_bytes(), Path(path).stat().st_mtime_ns
    lead = read_source_leads(path, run_id).items[0]
    assert lead.disposition == "analyzer_admitted"
    assert lead.source_family == source.provenance.source_family_id
    assert "Admission outcome was not recorded." not in lead.unknowns
    assert [(step.stage, step.status) for step in lead.history].count(
        ("admission", "analyzer_admitted")
    ) == 1
    assert (Path(path).read_bytes(), Path(path).stat().st_mtime_ns) == before


def test_matching_local_and_aggregate_admission_does_not_repeat_history(tmp_path: Path) -> None:
    path, run_id, source, _analyst = _admission_fixture(tmp_path, include_batch=True)
    lead = read_source_leads(path, run_id).items[0]
    assert lead.disposition == "analyzer_admitted"
    assert lead.source_family == source.provenance.source_family_id
    assert [(step.stage, step.status) for step in lead.history].count(
        ("admission", "analyzer_admitted")
    ) == 1


@pytest.mark.parametrize("corruption", ("key", "checksum", "run", "ownership", "conflict"))
def test_source_local_admission_corruption_fails_closed(tmp_path: Path, corruption: str) -> None:
    path, run_id, source, _analyst = _admission_fixture(
        tmp_path, include_batch=corruption == "conflict"
    )
    key = f"phase-13-evidence-admission-source-v2-{source.source_id}"
    if corruption == "key":
        _rewrite_artifact(path, key, new_key="unexpected-admission-source-key")
    elif corruption == "checksum":
        _rewrite_artifact(path, key, corrupt_checksum=True)
    else:
        foreign_id = uuid4()

        def mutate(payload: dict[str, Any]) -> None:
            if corruption == "run":
                payload["run_id"] = str(foreign_id)
                payload["evidence_record"]["run_id"] = str(foreign_id)
            elif corruption == "ownership":
                payload["source_id"] = str(foreign_id)
                payload["provenance"]["source_id"] = str(foreign_id)
            else:
                payload["provenance"]["source_family_id"] = "conflicting-saved-family"

        _rewrite_artifact(
            path,
            key,
            mutate,
            new_key=(
                f"phase-13-evidence-admission-source-v2-{foreign_id}"
                if corruption == "ownership"
                else None
            ),
        )
    before = Path(path).read_bytes(), Path(path).stat().st_mtime_ns
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        read_source_leads(path, run_id)
    assert (Path(path).read_bytes(), Path(path).stat().st_mtime_ns) == before


@pytest.mark.parametrize(
    ("relationship", "claim_fit"),
    ((V2EvidenceRelationship.UNRELATED, 2), (V2EvidenceRelationship.SUPPORTS, 1)),
)
def test_rejected_sources_keep_saved_assessment_and_score_reasons(
    tmp_path: Path, relationship: V2EvidenceRelationship, claim_fit: int
) -> None:
    path, run_id, _source, analyst = _admission_fixture(
        tmp_path, include_batch=True, relationship=relationship, claim_fit=claim_fit
    )
    result = analyst.source_results[0]
    assert result.assessment is not None and result.score_decision is not None
    assert result.state.value == "rejected" and result.failure is None
    lead = read_source_leads(path, run_id).items[0]
    displayed_reasons = "\n".join((lead.reason, *(step.reason or "" for step in lead.history)))
    assert result.assessment.reasoning in displayed_reasons
    assert result.score_decision.rationale in displayed_reasons
    assert lead.disposition == "analyst_rejected"
    assert "Claim Fit" in displayed_reasons or "claim_fit" in displayed_reasons


def test_shell_url_and_readable_alternate_preserve_distinct_capture_outcomes(
    tmp_path: Path,
) -> None:
    path, run_id = _captured(tmp_path)
    leads = {lead.url: lead for lead in read_source_leads(path, run_id).items}
    assert leads[LANDING].capture_status == "unusable"
    assert leads[ALTERNATE].capture_status == "readable"
    assert leads[LANDING].readable_alternate_url == ALTERNATE
    assert leads[ALTERNATE].readable_alternate_url is None
    assert [step.status for step in leads[LANDING].history if step.stage == "capture"] == [
        "unusable",
        "readable",
    ]


def test_cancel_after_shell_keeps_untried_alternate_unknown(tmp_path: Path) -> None:
    path, run_id = _captured(tmp_path, cancelled=True)
    leads = {lead.url: lead for lead in read_source_leads(path, run_id).items}
    assert leads[LANDING].capture_status == "unusable"
    assert leads[ALTERNATE].capture_status == "unknown"
    assert all(lead.readable_alternate_url is None for lead in leads.values())


def test_dispatch_without_response_stays_attempted_for_its_url_only(tmp_path: Path) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    discovery = _clustered(run_id)
    insert_v2_artifact(path, "phase-4-discovery-scout", discovery, NOW)
    scraper = FixtureScraper({LANDING: V2CancellationRequested("offline transport interrupted")})
    with pytest.raises(V2CancellationRequested):
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=scraper,
            exact_claim="Does the intervention work?",
            policy=_policy(),
            clock=lambda: NOW,
        )
    leads = {lead.url: lead for lead in read_source_leads(path, run_id).items}
    assert leads[LANDING].capture_status == "attempted"
    assert leads[ALTERNATE].capture_status == "unknown"
    assert all(lead.readable_alternate_url is None for lead in leads.values())


def test_legacy_aggregate_does_not_assign_alternate_capture_to_failed_url(tmp_path: Path) -> None:
    from researchassistant.contracts.models import V2AcquisitionPolicy
    from researchassistant.providers.acquisition import AcquisitionFailureCode
    from researchassistant.providers.scraper import ScraperProviderError

    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    discovery = _clustered(run_id)
    insert_v2_artifact(path, "phase-4-discovery-scout", discovery, NOW)
    text = (
        "Methods describe 600 participants in a controlled study. "
        "Results found no significant difference and discuss study limitations. "
    ) * 30
    scraper = FixtureScraper(
        {
            LANDING: ScraperProviderError(AcquisitionFailureCode.CONNECTION, "offline failure"),
            ALTERNATE: _response(ALTERNATE, text),
        }
    )
    run_v2_acquisition_probe(
        db_path=path,
        discovery_output=discovery,
        wigolo_provider=scraper,
        exact_claim="Does the intervention work?",
        policy=V2AcquisitionPolicy(
            policy_identity="researchassistant-v2-phase-5-acquisition-probe-v3",
            allow_firecrawl_fallback=False,
        ),
        clock=lambda: NOW,
    )
    leads = {lead.url: lead for lead in read_source_leads(path, run_id).items}
    assert leads[LANDING].capture_status == "failed"
    assert leads[ALTERNATE].capture_status == "readable"
    assert leads[LANDING].readable_alternate_url == ALTERNATE
