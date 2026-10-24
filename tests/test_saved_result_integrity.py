"""Checksum-valid artifact substitutions must fail closed on every read surface."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from test_v2_phase10_reviewer_ledger import Phase10Provider, _approved, _run
from test_v2_phase11_final_output import _continuation, _synthesis

from researchassistant.agents.v2_final_output import (
    V2_FINAL_OUTPUT_ARTIFACT_KEY,
    build_v2_final_research_output,
)
from researchassistant.api.application_services.result_reads import read_evidence, read_result
from researchassistant.contracts.models import v2_payload_fingerprint
from researchassistant.evidence.brief_export import BriefExportFormat, export_released_brief
from researchassistant.storage.store import insert_v2_artifact


@pytest.mark.core
@pytest.mark.parametrize("change", ["run", "claim", "released_text"])
@pytest.mark.parametrize("surface", ["result", "evidence", "export"])
def test_checksum_valid_substitution_is_rejected_without_writes(
    tmp_path: Path, change: str, surface: str
) -> None:
    database, admitted = _run(tmp_path, Phase10Provider([_approved()]))
    output = build_v2_final_research_output(
        reviewer_result=admitted,
        continuation=_continuation(admitted.run_id),
        synthesis=_synthesis(admitted),
        created_at=admitted.completed_at,
    )
    insert_v2_artifact(database, V2_FINAL_OUTPUT_ARTIFACT_KEY, output, admitted.completed_at)
    payload = output.model_dump(mode="json")
    if change == "run":
        # A structurally valid other-run artifact with its own legitimate hash.
        other_id = uuid4()
        other = output.model_copy(
            update={
                "run_id": other_id,
                "synthesis": output.synthesis.model_copy(update={"run_id": other_id}),
            }
        )
        payload = other.model_dump(mode="json")
    elif change == "claim":
        payload["exact_claim"] = "A substituted exact claim."
    else:
        payload["release_validation"]["rendered_output_hash"] = "0" * 64
    encoded = json.dumps(payload)
    with sqlite3.connect(database) as connection:
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='v2_artifacts_immutable_update'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER v2_artifacts_immutable_update")
        connection.execute(
            "UPDATE v2_artifacts SET payload_json=?, payload_sha256=? "
            "WHERE run_id=? AND artifact_key=?",
            (
                encoded,
                v2_payload_fingerprint(encoded),
                str(admitted.run_id),
                V2_FINAL_OUTPUT_ARTIFACT_KEY,
            ),
        )
        connection.execute(trigger)
    before = Path(database).read_bytes()
    destination = tmp_path / "result.md"
    with pytest.raises((ValueError, sqlite3.IntegrityError), match="run|claim|hash"):
        if surface == "result":
            read_result(database, admitted.run_id)
        elif surface == "evidence":
            read_evidence(database, admitted.run_id)
        else:
            export_released_brief(
                database, str(admitted.run_id), destination, BriefExportFormat.MARKDOWN
            )
    assert not destination.exists()
    assert Path(database).read_bytes() == before


@pytest.mark.core
@pytest.mark.slow
@pytest.mark.parametrize("change", ["claim", "released_text"])
def test_status_rejects_checksum_valid_embedded_release_changes(
    tmp_path: Path, change: str
) -> None:
    from test_product_discovery_pipeline import _run as product_run

    from researchassistant.api.live_service import LiveResearchController
    from researchassistant.contracts.models import DiscoveryProvider, ResearchControls
    from researchassistant.research.v2_orchestrator import V2_PRODUCTION_ARTIFACT_KEY

    database = tmp_path / "product.sqlite3"
    result, _, _ = product_run(
        database, ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    )
    assert result.final_output is not None and result.final_output.release_validation.valid
    with sqlite3.connect(database) as connection:
        payload = json.loads(
            connection.execute(
                "SELECT payload_json FROM v2_artifacts WHERE run_id=? AND artifact_key=?",
                (str(result.run_id), V2_PRODUCTION_ARTIFACT_KEY),
            ).fetchone()[0]
        )
        if change == "claim":
            payload["final_output"]["exact_claim"] = "A substituted exact claim."
        else:
            payload["final_output"]["release_validation"]["rendered_output_hash"] = "0" * 64
        encoded = json.dumps(payload)
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='v2_artifacts_immutable_update'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER v2_artifacts_immutable_update")
        connection.execute(
            "UPDATE v2_artifacts SET payload_json=?, payload_sha256=? "
            "WHERE run_id=? AND artifact_key=?",
            (
                encoded,
                v2_payload_fingerprint(encoded),
                str(result.run_id),
                V2_PRODUCTION_ARTIFACT_KEY,
            ),
        )
        connection.execute(trigger)
    before = database.read_bytes()
    controller = LiveResearchController(environment={})
    try:
        with pytest.raises(ValueError, match="claim|hash"):
            controller.snapshot(database, result.run_id)
        assert database.read_bytes() == before
    finally:
        controller.shutdown(timeout=1)


@pytest.mark.core
@pytest.mark.slow
@pytest.mark.parametrize("historical", [False, True])
@pytest.mark.parametrize("change", ["statement", "quote", "ledger_id", "claim"])
def test_supplemental_evidence_must_agree_with_released_output(
    tmp_path: Path, historical: bool, change: str
) -> None:
    from test_product_discovery_pipeline import _run as product_run

    from researchassistant.agents.v2_evidence_admission import V2_EVIDENCE_ADMISSION_ARTIFACT_KEY
    from researchassistant.agents.v2_reviewer_ledger import V2_REVIEWER_LEDGER_ARTIFACT_KEY
    from researchassistant.contracts.models import DiscoveryProvider, ResearchControls

    if historical:
        database, admitted = _run(tmp_path, Phase10Provider([_approved()]))
        output = build_v2_final_research_output(
            reviewer_result=admitted,
            continuation=_continuation(admitted.run_id),
            synthesis=_synthesis(admitted),
            created_at=admitted.completed_at,
        )
        insert_v2_artifact(database, V2_FINAL_OUTPUT_ARTIFACT_KEY, output, admitted.completed_at)
        run_id = admitted.run_id
        artifact_key = V2_REVIEWER_LEDGER_ARTIFACT_KEY
        field = "ledger_record"
    else:
        database = str(tmp_path / "product.sqlite3")
        result, _, _ = product_run(
            Path(database), ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
        )
        run_id = result.run_id
        artifact_key = V2_EVIDENCE_ADMISSION_ARTIFACT_KEY
        field = "evidence_record"
    original = read_result(database, run_id)
    assert original.release_validation.valid
    display = read_evidence(database, run_id)
    assert display.items
    with sqlite3.connect(database) as connection:
        payload = json.loads(
            connection.execute(
                "SELECT payload_json FROM v2_artifacts WHERE run_id=? AND artifact_key=?",
                (str(run_id), artifact_key),
            ).fetchone()[0]
        )
        record = next(item[field] for item in payload["source_results"] if item[field])
        if change == "statement":
            record["approved_factual_statement"] = "This statement never appeared in the release."
        elif change == "quote":
            record["approved_claim_text"] = "This quotation never appeared in the source."
        elif change == "ledger_id":
            record["ledger_claim_id"] = str(uuid4())
        else:
            payload["analyst_result"]["input"]["exact_claim"] = "A substituted research question."
            payload["analyst_result"]["input"]["queue_result"]["input"]["exact_claim"] = (
                "A substituted research question."
            )
        encoded = json.dumps(payload)
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='v2_artifacts_immutable_update'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER v2_artifacts_immutable_update")
        connection.execute(
            "UPDATE v2_artifacts SET payload_json=?, payload_sha256=? "
            "WHERE run_id=? AND artifact_key=?",
            (encoded, v2_payload_fingerprint(encoded), str(run_id), artifact_key),
        )
        connection.execute(trigger)
    path = Path(database)
    before = path.read_bytes(), path.stat().st_mtime_ns
    with pytest.raises(ValueError, match="statement|claim|Ledger|quote"):
        read_evidence(database, run_id)
    assert read_result(database, run_id) == original
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.core
def test_historical_evidence_cannot_replace_its_reviewer_approval(tmp_path: Path) -> None:
    from researchassistant.api.application_services.evidence_projection import (
        _build_v2_evidence_display,
    )

    _, admitted = _run(tmp_path, Phase10Provider([_approved()]))
    output = build_v2_final_research_output(
        reviewer_result=admitted,
        continuation=_continuation(admitted.run_id),
        synthesis=_synthesis(admitted),
        created_at=admitted.completed_at,
    )
    assert _build_v2_evidence_display(output, admitted).items
    source = admitted.source_results[0]
    assert source.ledger_record is not None
    replaced = source.model_copy(
        update={
            "ledger_record": source.ledger_record.model_copy(
                update={"reviewer_approval_id": uuid4()}
            )
        }
    )
    changed = admitted.model_copy(
        update={"source_results": (replaced, *admitted.source_results[1:])}
    )
    with pytest.raises(ValueError, match="reviewer_approval_id"):
        _build_v2_evidence_display(output, changed)
