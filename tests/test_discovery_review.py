"""Focused regression cases for source-discovery store review findings."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
import test_discovery_store as store_fixtures
import test_discovery_store_acceptance as acceptance_fixtures

from researchassistant.contracts.discovery_v2 import (
    V2DiscoveryFailure,
    V2NormalizedDiscoveryCandidate,
    V2ProviderAttemptCompletion,
    V2SeedEligibility,
    V2SourceLocation,
    discovery_id,
)
from researchassistant.storage.discovery_store import (
    _read_acquisition_for_preview,
    compute_discovery_audit_counters,
    insert_discovery_candidate,
    insert_seed_eligibility,
    provider_attempt_audit,
    reserve_provider_attempt,
)
from researchassistant.storage.store import insert_v2_artifact


def test_later_round_acquisition_is_selected_for_preview(tmp_path: Path) -> None:
    path = tmp_path / "later-round-preview.sqlite"
    acceptance_fixtures._setup(path)
    source_id = UUID("a9c491d7-f471-41b0-bf79-1ce28764f894")
    round_one = acceptance_fixtures._acquisition_output(acceptance_fixtures.RUN_ID, source_id)
    round_two = acceptance_fixtures._acquisition_output(
        acceptance_fixtures.RUN_ID,
        source_id,
        snapshot_id=UUID("32322222-7c32-4771-a41e-8455ff099af9"),
    )
    insert_v2_artifact(str(path), "phase-5-acquisition-probe", round_one, acceptance_fixtures.NOW)
    insert_v2_artifact(
        str(path), "phase-7-round-2-acquisition-probe", round_two, acceptance_fixtures.NOW
    )

    assert (
        _read_acquisition_for_preview(str(path), acceptance_fixtures.RUN_ID, round_two) == round_two
    )


@pytest.mark.parametrize(
    ("candidate_url", "snapshot_url"),
    (
        (
            "https://example.org/article?id=work-a",
            "https://example.org/article?id=work-b",
        ),
        ("https://example.org/Article", "https://example.org/article"),
        ("https://example.org/article", "https://example.org:8443/article"),
    ),
)
def test_seed_linkage_preserves_distinct_url_identity(
    tmp_path: Path, candidate_url: str, snapshot_url: str
) -> None:
    path = tmp_path / f"seed-url-identity-{len(candidate_url)}-{len(snapshot_url)}.sqlite"
    operation, _ = acceptance_fixtures._complete_fixture(path)
    raw = acceptance_fixtures._raw()
    raw = type(raw).model_validate(
        raw.model_copy(
            update={
                "locations": (
                    V2SourceLocation(
                        url=candidate_url,
                        kind="landing",
                        same_work_basis="provider_identity",
                    ),
                )
            }
        ).model_dump(mode="python")
    )
    candidate = V2NormalizedDiscoveryCandidate(
        run_id=operation.run_id,
        artifact_id=discovery_id(operation.run_id, "V2NormalizedDiscoveryCandidate", "url-seed"),
        identity_key="url-seed",
        raw_candidates=(raw,),
        work=raw.work,
        rank=acceptance_fixtures.V2RankComponents(rationale="Fixture identity check."),
        disposition="retained",
        disposition_reason="Fixture candidate for exact source identity validation.",
    )
    candidate = insert_discovery_candidate(
        str(path), candidate, acceptance_fixtures.NOW + timedelta(seconds=3)
    )

    source_id = UUID("a9c491d7-f471-41b0-bf79-1ce28764f894")
    output = acceptance_fixtures._acquisition_output(operation.run_id, source_id)
    acquired = output.acquisitions[0]
    snapshot = acquired.snapshot.model_copy(update={"source_url": snapshot_url})
    output = type(output).model_validate(
        output.model_copy(
            update={"acquisitions": (acquired.model_copy(update={"snapshot": snapshot}),)}
        ).model_dump(mode="python")
    )
    insert_v2_artifact(
        str(path), "phase-7-round-2-acquisition-probe", output, acceptance_fixtures.NOW
    )
    seed = V2SeedEligibility(
        run_id=operation.run_id,
        artifact_id=discovery_id(operation.run_id, "V2SeedEligibility", "query-mismatch"),
        identity_key="query-mismatch",
        candidate_id=candidate.artifact_id,
        source_id=source_id,
        snapshot_id=snapshot.snapshot_id,
        work=candidate.work,
        eligible=True,
        reason="Fixture candidate and acquisition have distinct canonical work URLs.",
    )

    with pytest.raises(ValueError, match="not linked to the candidate work identity"):
        insert_seed_eligibility(
            str(path), seed, output, candidate, acceptance_fixtures.NOW + timedelta(seconds=4)
        )


def test_unknown_failed_attempt_is_visible_in_audit_counters(tmp_path: Path) -> None:
    path = tmp_path / "unknown-audit.sqlite"
    store_fixtures._init_run(path)
    store_fixtures.bind_discovery_run(str(path), store_fixtures._binding(), store_fixtures.NOW)
    operation = store_fixtures._operation(path)
    start = reserve_provider_attempt(str(path), store_fixtures._start(operation))
    completion = V2ProviderAttemptCompletion(
        run_id=operation.run_id,
        artifact_id=discovery_id(
            operation.run_id, "V2ProviderAttemptCompletion", "unknown-failure"
        ),
        identity_key="unknown-failure",
        attempt_id=start.artifact_id,
        operation_id=operation.action.artifact_id,
        status="failed",
        failure=V2DiscoveryFailure(code="timeout", retryable=True, detail="unknown_after_start"),
        actual_cost_usd=None,
        cost_basis="unknown",
        completed_at=store_fixtures.NOW + timedelta(seconds=5),
    )
    store_fixtures.complete_provider_attempt(str(path), completion, completion.completed_at)

    assert provider_attempt_audit(str(path), operation.run_id).interrupted_unknown == (
        start.artifact_id,
    )
    assert compute_discovery_audit_counters(str(path), operation.run_id).unknown_requests == 1
