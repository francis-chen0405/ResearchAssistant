from __future__ import annotations

import copy
import hashlib
import json
import shutil
import socket
from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluations.research_quality import DEFAULT_MANIFEST, evaluate, main
from evaluations.research_quality_contracts import Benchmark

FIXTURE = DEFAULT_MANIFEST.parent / "fixture_bundle/manifest.json"


def _bundle(tmp_path: Path) -> Path:
    target = tmp_path / "bundle"
    shutil.copytree(FIXTURE.parent, target)
    return target / "manifest.json"


def _edit(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data))


def test_fixture_metrics_do_not_inflate_work_or_unknown_scores() -> None:
    report = evaluate(FIXTURE, replay=True)
    result = report["observations"][0]
    returned = result["stages"]["returned"]
    assert returned["work_count"] == 3
    assert returned["reference_recall"] == 0.5
    assert returned["precision"] is None
    assert returned["judged_precision"] == 0.5
    assert returned["precision_lower_bound"] == pytest.approx(1 / 3)
    assert returned["precision_upper_bound"] == pytest.approx(2 / 3)
    assert result["publication_aliases"] == 1
    assert result["resolved_study_groups"] == 1
    assert result["unresolved_study_candidates"] == 2
    assert result["actual_total_cost_usd"] is None
    assert result["recorded_exposure_usd"] == "0.01"
    assert result["supported_final_statement_rate"] is None
    assert result["supported_statement_lower_bound"] == pytest.approx(1 / 3)
    assert result["supported_statement_upper_bound"] == pytest.approx(2 / 3)
    assert result["discovery_replay"]["normalized_items"] == 4
    assert result["discovery_replay"]["new_physical_requests"] == 0
    assert report["origins"] == {"fixture": 1}


def test_prepared_manifest_has_no_invented_live_observations() -> None:
    benchmark = Benchmark.model_validate_json(DEFAULT_MANIFEST.read_bytes())
    assert len(benchmark.topics) == 8
    assert sum(t.split == "held_out" for t in benchmark.topics) == 2
    assert not benchmark.observations
    assert all(t.reference.status == "pending" for t in benchmark.topics)
    report = evaluate(DEFAULT_MANIFEST, replay=True)
    assert report["new_paid_calls"] == 0
    assert len(report["untested"]) == 5


def test_current_product_settings_preserve_frozen_baseline_except_new_capacity() -> None:
    from researchassistant.contracts.models import ResearchControls
    from researchassistant.providers.model_choices import model_options_payload
    from researchassistant.providers.v2_budget import V2RunCeilings
    from researchassistant.research.product_discovery import resolve_product_discovery

    baseline = Benchmark.model_validate_json(DEFAULT_MANIFEST.read_bytes()).baseline
    controls = ResearchControls()
    policy, _ = resolve_product_discovery(controls, controls.discovery_providers)
    assert controls.model_dump(mode="json") == baseline["controls"]
    current_policy = policy.model_dump(mode="json")
    assert current_policy["max_acquisition_per_round"] == 60
    assert baseline["discovery_policy"]["max_acquisition_per_round"] == 25
    assert {**current_policy, "max_acquisition_per_round": 25} == baseline["discovery_policy"]
    assert model_options_payload().model_dump(mode="json") == baseline["model_options"]
    assert V2RunCeilings().model_dump(mode="json") == baseline["model_ceilings"]


def test_no_network_or_credentials_are_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("offline benchmark attempted network access")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SERPSEARCH_API_KEY", raising=False)
    assert main(["--manifest", str(FIXTURE), "--output-dir", str(tmp_path), "--replay"]) == 0
    assert json.loads((tmp_path / "results.json").read_text())["new_paid_calls"] == 0


def test_snapshot_tampering_fails_closed(tmp_path: Path) -> None:
    path = _bundle(tmp_path)
    (path.parent / "snapshot.txt").write_text("tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        evaluate(path)


def test_checksum_valid_quotation_substitution_fails(tmp_path: Path) -> None:
    path = _bundle(tmp_path)
    data = json.loads(path.read_text())
    data["observations"][0]["statements"][0]["quote"] = "not in the frozen text"
    _edit(path, data)
    with pytest.raises(ValueError, match="quotation is not exact"):
        evaluate(path)


@pytest.mark.parametrize("origin", ["replayed_observation", "authorized_live"])
def test_authored_fixture_cannot_be_relabelled_as_live(origin: str) -> None:
    data = json.loads(FIXTURE.read_text())
    data["observations"][0]["origin"] = origin
    with pytest.raises(ValidationError):
        Benchmark.model_validate(data)


def test_missing_stage_is_unavailable_not_zero_recall(tmp_path: Path) -> None:
    path = _bundle(tmp_path)
    data = json.loads(path.read_text())
    data["observations"][0]["candidates"][0]["dispositions"] = [
        {
            "stage": "returned",
            "outcome": "kept",
            "reason": "fixture only returned observed",
        }
    ]
    _edit(path, data)
    result = evaluate(path)["observations"][0]
    assert result["stages"]["admission"]["reference_recall"] is None
    assert not result["stages"]["admission"]["stage_inventory_complete"]


def test_incomplete_physical_audit_prevents_total_cost_claim(tmp_path: Path) -> None:
    path = _bundle(tmp_path)
    data = json.loads(path.read_text())
    obs = data["observations"][0]
    obs["audit_complete"] = False
    obs["attempts"][0].update(actual_usd="0.002", cost_basis="authored fixture receipt")
    _edit(path, data)
    result = evaluate(path)["observations"][0]
    assert result["known_cost_subtotal_usd"] == "0.002"
    assert result["actual_total_cost_usd"] is None
    assert result["recorded_exposure_usd"] == "0.01"


def test_comparison_discloses_extra_requests_and_exposure(tmp_path: Path) -> None:
    path = _bundle(tmp_path)
    data = json.loads(path.read_text())
    added = copy.deepcopy(data["observations"][0])
    added.update(observation_id="fixture-more-exposure", arm="changed-fixture")
    attempt = copy.deepcopy(added["attempts"][0])
    attempt.update(attempt_id="search-2", outcome="unknown", finished_at=None, response=None)
    added["attempts"].append(attempt)
    data["observations"].append(added)
    _edit(path, data)
    comparison = evaluate(path)["comparisons"][0]
    assert not comparison["same_recorded_exposure"]
    assert comparison["physical_requests_left"] == {"search": 1}
    assert comparison["physical_requests_right"] == {"search": 2}


def test_reference_set_cannot_be_tuned_after_observation() -> None:
    data = json.loads(FIXTURE.read_text())
    data["topics"][0]["reference"]["locked_at"] = "2026-10-12T00:00:00Z"
    with pytest.raises(ValidationError, match="reference must be locked"):
        Benchmark.model_validate(data)


def test_duplicate_statement_ids_cannot_inflate_support_score() -> None:
    data = json.loads(FIXTURE.read_text())
    data["observations"][0]["statements"].append(data["observations"][0]["statements"][0])
    with pytest.raises(ValidationError, match="statement IDs must be unique"):
        Benchmark.model_validate(data)


def test_artifact_symlink_escape_is_rejected(tmp_path: Path) -> None:
    path = _bundle(tmp_path)
    snapshot = path.parent / "snapshot.txt"
    outside = tmp_path / "outside.txt"
    outside.write_bytes(snapshot.read_bytes())
    snapshot.unlink()
    snapshot.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes bundle"):
        evaluate(path)


def test_infinite_cost_and_unowned_attempt_are_rejected() -> None:
    data = json.loads(FIXTURE.read_text())
    data["observations"][0]["attempts"][0]["reserved_usd"] = "Infinity"
    with pytest.raises(ValidationError):
        Benchmark.model_validate(data)
    data = json.loads(FIXTURE.read_text())
    data["observations"][0]["candidates"][0]["attempt_id"] = "unowned"
    with pytest.raises(ValidationError, match="owned physical attempt"):
        Benchmark.model_validate(data)


def test_checksum_valid_settings_substitution_is_rejected(tmp_path: Path) -> None:
    path = _bundle(tmp_path)
    data = json.loads(path.read_text())
    value = b'{"fixture":true,"depth":50}'
    (path.parent / "settings.json").write_bytes(value)
    for artifact in data["observations"][0]["artifacts"]:
        if artifact["path"] == "settings.json":
            artifact["sha256"] = hashlib.sha256(value).hexdigest()
    _edit(path, data)
    with pytest.raises(ValidationError, match="settings digest"):
        evaluate(path)
