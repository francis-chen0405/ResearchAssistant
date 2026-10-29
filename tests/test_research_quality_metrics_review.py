from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from evaluations.research_quality import (
    DEFAULT_MANIFEST,
    evaluate,
    evaluate_observation,
    main,
)
from evaluations.research_quality_contracts import Benchmark

FIXTURE = DEFAULT_MANIFEST.parent / "fixture_bundle/manifest.json"


def _fixture_data() -> dict[str, Any]:
    return json.loads(FIXTURE.read_bytes())


def _fixture_result(data: dict[str, Any], *, k: int = 10) -> dict[str, Any]:
    benchmark = Benchmark.model_validate(data)
    return evaluate_observation(benchmark.topics[0], benchmark.observations[0], k)


@pytest.mark.parametrize(
    ("complete", "statement_ids", "expected_rate", "lower", "upper"),
    [
        (False, ["supported"], None, None, None),
        (False, ["supported", "unsupported", "unjudged"], None, None, None),
        (True, ["supported", "unsupported", "unjudged"], None, 1 / 3, 2 / 3),
        (True, ["supported", "unsupported"], 0.5, 0.5, 0.5),
        (True, [], None, None, None),
        (False, [], None, None, None),
    ],
)
def test_whole_final_output_bounds_require_complete_assertion_inventory(
    complete: bool,
    statement_ids: list[str],
    expected_rate: float | None,
    lower: float | None,
    upper: float | None,
) -> None:
    data = _fixture_data()
    observation = data["observations"][0]
    observation["final_inventory_complete"] = complete
    observation["statements"] = [
        s for s in observation["statements"] if s["statement_id"] in statement_ids
    ]
    result = _fixture_result(data)
    assert result["final_inventory_complete"] is complete
    assert result["supported_final_statement_rate"] == expected_rate
    assert result["supported_statement_lower_bound"] == lower
    assert result["supported_statement_upper_bound"] == upper
    assert result["recorded_subset_statement_scope"] == "recorded_final_statements"
    if not complete and statement_ids == ["supported"]:
        assert result["recorded_subset_supported_statement_lower_bound"] == 1
        assert result["recorded_subset_supported_statement_upper_bound"] == 1
    if not complete and len(statement_ids) == 3:
        assert result["recorded_subset_supported_statement_lower_bound"] == pytest.approx(1 / 3)
        assert result["recorded_subset_supported_statement_upper_bound"] == pytest.approx(2 / 3)


def test_stage_and_top_k_filtering_cannot_resolve_conflicting_work_judgments() -> None:
    data = _fixture_data()
    alias = data["observations"][0]["candidates"][1]
    alias["judgment"].update(useful=False, relevant=False)
    result = _fixture_result(data, k=1)
    for assessment in (
        result["stages"]["admission"],
        result["provider_precision_at_k"][0],
        result["ranked_union_at_k_diagnostic"],
    ):
        assert assessment["work_count"] == 1
        assert assessment["judged_work_count"] == 0
        assert assessment["precision"] is None
        assert assessment["judged_precision"] is None
        assert assessment["precision_lower_bound"] == 0
        assert assessment["precision_upper_bound"] == 1
        assert assessment["relevance_precision"] is None
        assert assessment["relevance_judgment_coverage"] == 0
        assert assessment["work_judgment_scope"] == "observation_inventory"
    assert result["full_text_work_count"] == 1
    assert result["admission_utility_status"] == "untested"


def test_work_grade_can_survive_through_unjudged_alias_without_inventing_capture() -> None:
    data = _fixture_data()
    candidates = data["observations"][0]["candidates"]
    candidates[0]["judgment"].update(useful=None, relevant=None, capture="unknown")
    candidates[1]["judgment"].update(capture="shell")
    result = _fixture_result(data, k=1)
    assert result["stages"]["admission"]["precision"] == 1
    assert result["stages"]["admission"]["relevance_precision"] == 1
    assert result["provider_precision_at_k"][0]["precision"] == 1
    assert result["full_text_work_count"] == 0
    assert result["full_text_reference_recall"] is None


@pytest.mark.parametrize(("new_url", "duplicates", "aliases"), [(False, 1, 1), (True, 0, 2)])
def test_repeated_exact_urls_are_separate_from_distinct_publication_aliases(
    new_url: bool, duplicates: int, aliases: int
) -> None:
    data = _fixture_data()
    observation = data["observations"][0]
    candidate = copy.deepcopy(observation["candidates"][0])
    candidate.update(candidate_id="a-repeat", rank=5)
    if new_url:
        candidate["url"] = "https://fixture.invalid/a-third-publication"
    observation["candidates"].append(candidate)
    result = _fixture_result(data)
    assert result["duplicate_urls"] == duplicates
    assert result["publication_aliases"] == aliases
    assert result["stages"]["returned"]["work_count"] == 3


@pytest.mark.parametrize(("reservation", "equal"), [("0.010", True), ("0.011", False)])
def test_exposure_comparison_uses_decimal_value_not_scale(
    tmp_path: Path, reservation: str, equal: bool
) -> None:
    target = tmp_path / "bundle"
    shutil.copytree(FIXTURE.parent, target)
    data = _fixture_data()
    second = copy.deepcopy(data["observations"][0])
    second.update(observation_id="fixture-other-scale", arm="other-scale")
    second["attempts"][0]["reserved_usd"] = reservation
    data["observations"].append(second)
    manifest = target / "manifest.json"
    manifest.write_text(json.dumps(data))
    report = evaluate(manifest)
    assert report["comparisons"][0]["same_recorded_exposure"] is equal
    assert all(r["actual_total_cost_usd"] is None for r in report["observations"])


def test_published_cost_and_exposure_preserve_all_decimal_digits(tmp_path: Path) -> None:
    target = tmp_path / "bundle"
    shutil.copytree(FIXTURE.parent, target)
    data = _fixture_data()
    observation = data["observations"][0]
    observation["audit_complete"] = True
    observation["attempts"][0].update(
        actual_usd="1.00000000000000000000000000001",
        cost_basis="synthetic exact-USD regression receipt",
        reserved_usd="1.00000000000000000000000000000",
    )
    manifest = target / "manifest.json"
    manifest.write_text(json.dumps(data))
    output = tmp_path / "published-report"

    assert main(["--manifest", str(manifest), "--output-dir", str(output)]) == 0

    result = json.loads((output / "results.json").read_text())["observations"][0]
    exact_amount = "1.00000000000000000000000000001"
    assert result["known_cost_subtotal_usd"] == exact_amount
    assert result["actual_total_cost_usd"] == exact_amount
    assert result["recorded_exposure_usd"] == exact_amount


def _synthetic_observation_manifest(
    tmp_path: Path, grades: tuple[bool | None, ...], *, complete: bool, human: bool
) -> Path:
    """Create independent synthetic saved-observation shapes, never collected research."""
    artifacts = []
    for name, role, payload in (
        ("settings.json", "request", b'{"synthetic_test":true}'),
        ("request.json", "request", b'{"query":"synthetic claim"}'),
        ("response.json", "raw_response", b'{"synthetic_response":true}'),
        ("snapshot.txt", "snapshot", b"Synthetic snapshot for metric regression only."),
    ):
        (tmp_path / name).write_bytes(payload)
        artifacts.append(
            {
                "path": name,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "media_type": "text/plain" if name.endswith("txt") else "application/json",
                "role": role,
            }
        )
    by_path = {artifact["path"]: artifact for artifact in artifacts}
    candidates = []
    for index, grade in enumerate(grades):
        candidates.append(
            {
                "candidate_id": f"candidate-{index}",
                "attempt_id": "synthetic-attempt",
                "url": f"https://example.org/synthetic/{index}",
                "work_id": f"synthetic-work-{index}",
                "rank": index + 1,
                "snapshot_path": "snapshot.txt",
                "judgment": {
                    "reviewer": "synthetic-test-reviewer",
                    "kind": "human" if human else "assistant",
                    "rationale": "Synthetic review field for metric regression only.",
                    "evidence_paths": ["snapshot.txt"],
                    "useful": grade,
                    "capture": "unknown",
                },
                "dispositions": [
                    {"stage": "returned", "outcome": "kept", "reason": "synthetic return"},
                    {"stage": "admission", "outcome": "kept", "reason": "synthetic decision"},
                ],
            }
        )
    claim = "Synthetic metric regression claim."
    # Explicit authored query/page receipts keep arithmetic fixtures subject to
    # the same inventory checks as real saved observations.
    query_id = "20000000-0000-4000-8000-000000000099"
    handoff = {
        "query": {
            "run_id": "10000000-0000-4000-8000-000000000099",
            "query_id": query_id,
            "direction": "support",
            "provider": "exa",
            "round_number": 1,
            "strategy": "fixture",
            "query_text": "synthetic claim",
            "created_at": "2026-10-12T00:00:00Z",
        },
        "results": [{"original_url": c["url"], "rank": c["rank"]} for c in candidates],
    }
    payload = json.dumps(handoff).encode()
    (tmp_path / "handoff.json").write_bytes(payload)
    artifacts.append(
        {
            "path": "handoff.json",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "media_type": "application/json",
            "role": "stage",
        }
    )
    data = {
        "schema_version": "research-quality-v1",
        "prepared_on": "2026-10-12",
        "baseline": {"synthetic_test": True},
        "topics": [
            {
                "topic_id": "synthetic-topic",
                "split": "development",
                "claim": claim,
                "rationale": "Synthetic metric regression only.",
                "short_query": "synthetic claim",
                "concepts": ["synthetic"],
                "reference": {"status": "pending", "method": "No quality denominator"},
            }
        ],
        "observations": [
            {
                "observation_id": "synthetic-saved-shape",
                "topic_id": "synthetic-topic",
                "arm": "synthetic-test",
                "origin": "replayed_observation",
                "collector": "synthetic-test",
                "provenance_note": "Synthetic saved-observation contract test; no real collection.",
                "source_identity": "synthetic-test",
                "settings_sha256": by_path["settings.json"]["sha256"],
                "settings_path": "settings.json",
                "input_sha256": hashlib.sha256(claim.encode()).hexdigest(),
                "started_at": "2026-10-12T00:00:00Z",
                "audit_complete": False,
                "candidate_inventory_complete": complete,
                "final_inventory_complete": False,
                "artifacts": artifacts,
                "discovery_handoff_paths": ["handoff.json"],
                "discovery_handoff_attempts": {"handoff.json": ["synthetic-attempt"]},
                "search_attempt_result_paths": {"synthetic-attempt": "handoff.json"},
                "attempts": [
                    {
                        "attempt_id": "synthetic-attempt",
                        "category": "search",
                        "provider": "exa",
                        "endpoint": "https://example.org/synthetic",
                        "settings": {"query_id": query_id},
                        "started_at": "2026-10-12T00:00:00Z",
                        "finished_at": "2026-10-12T00:00:01Z",
                        "outcome": "success",
                        "request": by_path["request.json"],
                        "response": by_path["response.json"],
                        "reserved_usd": "0",
                    }
                ],
                "candidates": candidates,
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    return path


@pytest.mark.parametrize(
    ("grades", "complete", "human", "status", "untested"),
    [
        ((None, None), True, True, "untested", True),
        ((True, None), True, True, "partial", True),
        ((True, False), True, True, "evaluated", False),
        ((True, False), False, True, "partial", True),
        ((True, False), True, False, "untested", True),
        ((), True, True, "untested", True),
    ],
)
def test_admission_behavior_does_not_establish_human_utility(
    tmp_path: Path,
    grades: tuple[bool | None, ...],
    complete: bool,
    human: bool,
    status: str,
    untested: bool,
) -> None:
    path = _synthetic_observation_manifest(tmp_path, grades, complete=complete, human=human)
    report = evaluate(path)
    result = report["observations"][0]
    assert result["admission_behavior_observed"] is bool(grades)
    assert result["admission_utility_status"] == status
    assert ("end-to-end admission utility" in report["untested"]) is untested
    admission = result["stages"]["admission"]
    if grades == (None, None) or not human:
        assert admission["precision"] is None
        assert admission["judgment_coverage"] == 0
    assert admission["metric_scope"] == "recorded_work_inventory"
    assert report["new_paid_calls"] == 0


def test_human_work_disagreement_stays_untested_after_negative_alias_is_dropped(
    tmp_path: Path,
) -> None:
    path = _synthetic_observation_manifest(tmp_path, (True, False), complete=True, human=True)
    data = json.loads(path.read_bytes())
    candidates = data["observations"][0]["candidates"]
    candidates[1]["work_id"] = candidates[0]["work_id"]
    candidates[1]["dispositions"][1]["outcome"] = "dropped"
    path.write_text(json.dumps(data))
    report = evaluate(path)
    result = report["observations"][0]
    assert result["stages"]["admission"]["stage_inventory_complete"]
    assert result["stages"]["admission"]["precision"] is None
    assert result["stages"]["admission"]["judgment_coverage"] == 0
    assert result["admission_utility_status"] == "untested"
    assert "end-to-end admission utility" in report["untested"]


def test_missing_admission_disposition_keeps_known_subset_utility_partial(tmp_path: Path) -> None:
    path = _synthetic_observation_manifest(tmp_path, (True, False), complete=True, human=True)
    data = json.loads(path.read_bytes())
    data["observations"][0]["candidates"][1]["dispositions"].pop()
    path.write_text(json.dumps(data))
    report = evaluate(path)
    result = report["observations"][0]
    assert not result["stages"]["admission"]["stage_inventory_complete"]
    assert result["stages"]["admission"]["precision"] == 1
    assert result["admission_utility_status"] == "partial"
    assert "end-to-end admission utility" in report["untested"]
