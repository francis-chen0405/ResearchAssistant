"""Frozen reference and query lineage resist checksum-valid input substitutions."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from evaluations.research_quality import DEFAULT_MANIFEST, evaluate
from evaluations.research_quality_contracts import Benchmark

FIXTURE = DEFAULT_MANIFEST.parent / "fixture_bundle"


def _bundle(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "bundle"
    shutil.copytree(FIXTURE, root)
    path = root / "manifest.json"
    return path, json.loads(path.read_text())


def _write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data))


@pytest.mark.parametrize("changed", ["works", "reviewer", "method", "scope", "lock_time", "claim"])
def test_scored_reference_and_lock_metadata_must_match_frozen_artifact(
    tmp_path: Path, changed: str
) -> None:
    path, data = _bundle(tmp_path)
    reference = data["topics"][0]["reference"]
    if changed == "works":
        reference["works"].pop()
    elif changed == "reviewer":
        reference["reviewer"] = "another-reviewer"
    elif changed == "method":
        reference["method"] = "changed sampling method"
    elif changed == "scope":
        reference["scope"] = "non_exhaustive"
    elif changed == "lock_time":
        reference["locked_at"] = "2026-10-10T19:00:00Z"
    else:
        data["topics"][0]["claim"] = "Another exact claim."
        data["observations"][0]["input_sha256"] = hashlib.sha256(
            b"Another exact claim."
        ).hexdigest()
    _write(path, data)
    with pytest.raises(ValueError, match="frozen reference artifact"):
        evaluate(path)


def _add_query(path: Path, data: dict[str, Any], *, candidates: bool) -> None:
    observation = data["observations"][0]
    response = json.loads((path.parent / "handoff.json").read_text())
    response["query"]["query_id"] = str(UUID(int=42))
    payload = json.dumps(response).encode()
    (path.parent / "another-handoff.json").write_bytes(payload)
    observation["artifacts"].append(
        {
            "path": "another-handoff.json",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "media_type": "application/json",
            "role": "stage",
        }
    )
    observation["discovery_handoff_paths"].append("another-handoff.json")
    observation["discovery_handoff_attempts"]["another-handoff.json"] = ["search-2"]
    (path.parent / "another-page.json").write_bytes(payload)
    observation["artifacts"].append(
        {
            "path": "another-page.json",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "media_type": "application/json",
            "role": "stage",
        }
    )
    observation["search_attempt_result_paths"]["search-2"] = "another-page.json"
    attempt = copy.deepcopy(observation["attempts"][0])
    attempt["attempt_id"] = "search-2"
    attempt["settings"]["query_id"] = response["query"]["query_id"]
    observation["attempts"].append(attempt)
    if candidates:
        added = copy.deepcopy(observation["candidates"])
        for candidate in added:
            candidate["candidate_id"] += "-query2"
            candidate["attempt_id"] = "search-2"
            for disposition in candidate["dispositions"]:
                if disposition.get("evidence_path") == "handoff.json":
                    disposition["evidence_path"] = "another-handoff.json"
        observation["candidates"].extend(added)


@pytest.mark.parametrize("replay", [False, True])
def test_same_urls_from_another_query_require_another_candidate_inventory(
    tmp_path: Path, replay: bool
) -> None:
    path, data = _bundle(tmp_path)
    _add_query(path, data, candidates=False)
    _write(path, data)
    with pytest.raises(ValueError, match="query-specific candidate inventory"):
        evaluate(path, replay=replay)


def test_repeated_urls_remain_distinct_results_of_two_owned_queries(tmp_path: Path) -> None:
    path, data = _bundle(tmp_path)
    _add_query(path, data, candidates=True)
    _write(path, data)
    result = evaluate(path, replay=True)["observations"][0]
    assert result["discovery_replay"]["normalized_items"] == 8
    assert result["discovery_replay"]["query_attempt_lineage_verified"]
    assert result["stages"]["returned"]["observed_candidates"] == 8
    assert len(result["provider_precision_at_k"]) == 2
    assert result["duplicate_urls"] == 4
    assert result["publication_aliases"] == 1


@pytest.mark.parametrize(
    "changed", ["missing_binding", "query_id", "provider", "unrepresented_attempt"]
)
def test_complete_replay_requires_exact_query_and_successful_attempt_lineage(
    tmp_path: Path, changed: str
) -> None:
    path, data = _bundle(tmp_path)
    obs = data["observations"][0]
    if changed == "missing_binding":
        obs["discovery_handoff_attempts"] = {}
    elif changed == "query_id":
        obs["attempts"][0]["settings"]["query_id"] = str(UUID(int=99))
    elif changed == "provider":
        obs["attempts"][0]["provider"] = "openalex"
    else:
        added = copy.deepcopy(obs["attempts"][0])
        added["attempt_id"] = "unrepresented-success"
        obs["attempts"].append(added)
    _write(path, data)
    with pytest.raises(
        ValueError, match="bindings|owned successful attempt|every successful search"
    ):
        evaluate(path, replay=True)


def test_incomplete_historical_handoffs_do_not_claim_transport_lineage(tmp_path: Path) -> None:
    path, data = _bundle(tmp_path)
    obs = data["observations"][0]
    obs["candidate_inventory_complete"] = False
    obs["candidates"] = []
    obs["statements"] = []
    obs["discovery_handoff_attempts"] = {}
    _write(path, data)
    report = evaluate(path, replay=True)["observations"][0]
    assert report["discovery_replay"]["normalized_items"] == 4
    assert not report["discovery_replay"]["query_attempt_lineage_verified"]
    assert not report["discovery_replay"]["candidate_inventory_available"]


@pytest.mark.parametrize("missing_page_candidate", [False, True])
def test_exact_aggregate_handoff_preserves_two_physical_pages_and_dropped_duplicate(
    tmp_path: Path, missing_page_candidate: bool
) -> None:
    path, data = _bundle(tmp_path)
    obs = data["observations"][0]
    page = json.loads((path.parent / "search-page.json").read_text())
    added = copy.deepcopy(obs["candidates"])
    for index, (result, candidate) in enumerate(zip(page["results"], added, strict=True), 5):
        result["rank"] = index
        candidate["rank"] = index
        candidate["candidate_id"] += "-page2"
        candidate["attempt_id"] = "search-2"
        candidate["snapshot_path"] = None
        candidate["judgment"] = None
        if index == 5:
            # The provider repeats the first URL on page two; production retains
            # its first occurrence in the exact aggregate response.
            for disposition in candidate["dispositions"]:
                if disposition["stage"] == "retained":
                    disposition["outcome"] = "dropped"
                    disposition["reason"] = "duplicate across physical pages"
                elif disposition["stage"] not in {"returned", "normalized"}:
                    disposition["outcome"] = "not_reached"
                    disposition["reason"] = "duplicate not retained"
        else:
            result["original_url"] += "-page2"
            candidate["url"] = result["original_url"]
            candidate["work_id"] += "-page2"
        for disposition in candidate["dispositions"]:
            disposition["evidence_path"] = "page2.json"
    page_payload = json.dumps(page).encode()
    (path.parent / "page2.json").write_bytes(page_payload)
    obs["artifacts"].append(
        {
            "path": "page2.json",
            "sha256": hashlib.sha256(page_payload).hexdigest(),
            "media_type": "application/json",
            "role": "stage",
        }
    )
    logical = json.loads((path.parent / "handoff.json").read_text())
    logical["results"].extend(page["results"][1:])
    logical_payload = json.dumps(logical).encode()
    (path.parent / "handoff.json").write_bytes(logical_payload)
    for artifact in obs["artifacts"]:
        if artifact["path"] == "handoff.json":
            artifact["sha256"] = hashlib.sha256(logical_payload).hexdigest()
    attempt = copy.deepcopy(obs["attempts"][0])
    attempt["attempt_id"] = "search-2"
    attempt["settings"]["page"] = 2
    obs["attempts"].append(attempt)
    obs["discovery_handoff_attempts"]["handoff.json"].append("search-2")
    obs["search_attempt_result_paths"]["search-2"] = "page2.json"
    obs["candidates"].extend(added[:-1] if missing_page_candidate else added)
    _write(path, data)
    if missing_page_candidate:
        with pytest.raises(ValueError, match="query-specific candidate inventory"):
            evaluate(path, replay=True)
    else:
        result = evaluate(path, replay=True)["observations"][0]
        assert result["discovery_replay"]["normalized_items"] == 7
        assert result["discovery_replay"]["query_attempt_lineage_verified"]
        assert result["stages"]["returned"]["observed_candidates"] == 8
        assert result["stages"]["retained"]["observed_candidates"] == 8
        # The original alias and its copied page-two alias are both dropped
        # later, separately from the exact-URL duplicate in the aggregate.
        assert result["stages"]["retained"]["work_count"] == 5
        assert result["physical_requests_by_category"] == {"search": 2}
        assert [r["returned_at_k"] for r in result["provider_precision_at_k"]] == [4, 4]


@pytest.mark.parametrize("field", ["title", "snippet", "metadata"])
def test_logical_result_metadata_must_match_its_frozen_physical_page(
    tmp_path: Path, field: str
) -> None:
    path, data = _bundle(tmp_path)
    logical = json.loads((path.parent / "handoff.json").read_text())
    result = logical["results"][-1]
    if field == "metadata":
        result["metadata"]["abstract"] = "Substituted result metadata."
    else:
        result[field] = "Substituted result metadata."
    payload = json.dumps(logical).encode()
    (path.parent / "handoff.json").write_bytes(payload)
    for artifact in data["observations"][0]["artifacts"]:
        if artifact["path"] == "handoff.json":
            artifact["sha256"] = hashlib.sha256(payload).hexdigest()
    _write(path, data)
    with pytest.raises(ValueError, match="physical page provenance"):
        evaluate(path, replay=True)


def test_generated_observation_schema_matches_live_contracts() -> None:
    saved = json.loads((DEFAULT_MANIFEST.parent / "schema.json").read_text())
    assert saved == Benchmark.model_json_schema()


@pytest.mark.parametrize(
    "surface", ["stage", "response", "request_url", "candidate", "endpoint", "reference"]
)
def test_credential_bearing_observation_content_fails_before_report_output(
    tmp_path: Path, surface: str
) -> None:
    path, data = _bundle(tmp_path)
    obs = data["observations"][0]
    unsafe_url = "https://example.test/source?api_key=SYNTHETIC_NOT_A_SECRET"
    if surface in {"stage", "response", "request_url"}:
        filename = {
            "stage": "handoff.json",
            "response": "provider.json",
            "request_url": "request.json",
        }[surface]
        payload = json.loads((path.parent / filename).read_text())
        if surface == "request_url":
            payload["url"] = unsafe_url
        else:
            payload["api_key"] = "SYNTHETIC_NOT_A_SECRET"
        encoded = json.dumps(payload).encode()
        (path.parent / filename).write_bytes(encoded)
        digest = hashlib.sha256(encoded).hexdigest()
        for artifact in obs["artifacts"]:
            if artifact["path"] == filename:
                artifact["sha256"] = digest
        for attempt in obs["attempts"]:
            for key in ("request", "response"):
                if attempt.get(key, {}).get("path") == filename:
                    attempt[key]["sha256"] = digest
    elif surface == "candidate":
        obs["candidates"][0]["url"] = unsafe_url
    elif surface == "endpoint":
        obs["attempts"][0]["endpoint"] = unsafe_url
    else:
        data["topics"][0]["reference"]["works"][0]["urls"] = [unsafe_url]
    _write(path, data)
    with pytest.raises(ValueError, match="credential content"):
        evaluate(path, replay=True)
