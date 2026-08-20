from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from models import (
    V2_POLICY_IDENTITY,
    ProviderRunContract,
    ResearchControls,
    ResearchDirection,
    ResearchDirections,
    ResearchMode,
    RunManifest,
    RunStatus,
    SearchDirectionGapReference,
    Stage,
    V2InitialResearchPlan,
    V2PipelineIdentity,
    V2PlannedSearch,
    canonical_v2_artifact_json,
    v2_artifact_fingerprint,
)
from provider_contract import canonical_provider_contract_payload, provider_contract_fingerprint
from store import (
    CURRENT_SCHEMA_VERSION,
    init_db,
    insert_provider_run_contract,
    insert_run,
    insert_v2_artifact,
    insert_v2_pipeline_identity,
    open_read_only_store,
    read_v2_artifact,
)

NOW = datetime(2026, 8, 20, tzinfo=UTC)


@pytest.mark.parametrize(
    ("support_enabled", "challenge_enabled", "expected"),
    [
        (True, False, (ResearchDirection.SUPPORT,)),
        (False, True, (ResearchDirection.CHALLENGE,)),
        (True, True, (ResearchDirection.SUPPORT, ResearchDirection.CHALLENGE)),
    ],
)
def test_v2_all_valid_direction_combinations(
    support_enabled: bool,
    challenge_enabled: bool,
    expected: tuple[ResearchDirection, ...],
) -> None:
    directions = ResearchDirections(
        support_enabled=support_enabled, challenge_enabled=challenge_enabled
    )

    assert directions.enabled_directions == expected


def test_v2_rejects_both_directions_disabled() -> None:
    with pytest.raises(ValidationError, match="at least one research direction"):
        ResearchDirections(support_enabled=False, challenge_enabled=False)


def test_v2_challenge_only_initial_plan_is_valid() -> None:
    directions = ResearchDirections(support_enabled=False, challenge_enabled=True)
    plan = V2InitialResearchPlan(
        run_id=uuid4(),
        directions=directions,
        searches=(
            V2PlannedSearch(
                search_id="challenge-1",
                direction=ResearchDirection.CHALLENGE,
                query_text="limitations of the claim",
            ),
        ),
        created_at=NOW,
    )

    assert plan.searches[0].direction is ResearchDirection.CHALLENGE


def test_v2_rejects_artifact_for_disabled_direction() -> None:
    with pytest.raises(ValidationError, match="disabled research direction"):
        V2InitialResearchPlan(
            run_id=uuid4(),
            directions=ResearchDirections(support_enabled=False, challenge_enabled=True),
            searches=(
                V2PlannedSearch(
                    search_id="support-1",
                    direction=ResearchDirection.SUPPORT,
                    query_text="evidence for the claim",
                    gap_references=(
                        SearchDirectionGapReference(
                            reference_id="gap-1",
                            direction=ResearchDirection.SUPPORT,
                            gap_description="supporting evidence gap",
                        ),
                    ),
                ),
            ),
            created_at=NOW,
        )


def test_legacy_focused_controls_remain_support_only_compatible() -> None:
    controls = ResearchDirections(support_enabled=True, challenge_enabled=False)
    legacy = ResearchControls.from_policy_identity(
        'legacy|controls:{"depth":"standard","discovery_providers":["serpsearch","exa","openalex"],"focus":null,"length":"report","research_mode":"focused","sources_per_stance_per_round":10,"tone":"neutral"}'
    )

    assert legacy.research_mode is ResearchMode.FOCUSED
    assert controls.enabled_directions == (ResearchDirection.SUPPORT,)


def test_legacy_balanced_controls_remain_support_and_challenge_compatible() -> None:
    legacy = ResearchControls.from_policy_identity(
        'legacy|controls:{"depth":"standard","discovery_providers":["serpsearch","exa","openalex"],"focus":null,"length":"report","research_mode":"balanced","sources_per_stance_per_round":10,"tone":"neutral"}'
    )

    assert legacy.research_mode is ResearchMode.BALANCED


def _insert_planned_run(db_path: str, run_id: UUID) -> None:
    insert_run(
        db_path,
        RunManifest(
            run_id=run_id,
            status=RunStatus.PLANNED,
            raw_claim="A public claim.",
            current_stage=Stage.CLAIM_PLANNER,
            created_at=NOW,
            updated_at=NOW,
        ),
    )


def test_v2_migration_is_additive_idempotent_and_persists_canonical_artifacts(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "v2.sqlite3")
    init_db(db_path)
    init_db(db_path)
    run_id = uuid4()
    _insert_planned_run(db_path, run_id)
    identity = V2PipelineIdentity()
    insert_v2_pipeline_identity(db_path, run_id, identity, NOW)
    plan = V2InitialResearchPlan(
        run_id=run_id,
        directions=ResearchDirections(support_enabled=False, challenge_enabled=True),
        searches=(
            V2PlannedSearch(
                search_id="challenge-1",
                direction=ResearchDirection.CHALLENGE,
                query_text="challenge the claim",
            ),
        ),
        created_at=NOW,
    )

    persisted = insert_v2_artifact(db_path, "initial-plan", plan, NOW)

    with sqlite3.connect(db_path) as connection:
        versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations")]
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert CURRENT_SCHEMA_VERSION == 12
    assert versions == list(range(1, 13))
    assert {"v2_run_identities", "v2_artifacts"} <= tables
    assert persisted.payload_json == canonical_v2_artifact_json(plan)
    assert persisted.payload_sha256 == v2_artifact_fingerprint(plan)
    assert read_v2_artifact(db_path, run_id, "initial-plan") == persisted


def test_historical_schema_ten_stays_readable_for_inspection(tmp_path: Path) -> None:
    db_path = tmp_path / "historical.sqlite3"
    init_db(str(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE v2_artifacts")
        connection.execute("DROP TABLE v2_run_identities")
        connection.execute("DELETE FROM schema_migrations WHERE version = 11")
        connection.execute("DROP TABLE v2_round_one_search_queries")
        connection.execute("DROP TABLE v2_initial_planner_outputs")
        connection.execute("DELETE FROM schema_migrations WHERE version = 12")
        connection.commit()

    with open_read_only_store(str(db_path)) as store:
        assert store.compatibility.schema_version == 10


def test_v2_identity_requires_explicit_pipeline_policy(tmp_path: Path) -> None:
    db_path = str(tmp_path / "identity.sqlite3")
    init_db(db_path)
    run_id = uuid4()
    _insert_planned_run(db_path, run_id)
    insert_v2_pipeline_identity(db_path, run_id, V2PipelineIdentity(), NOW)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT policy_identity FROM v2_run_identities WHERE run_id = ?", (str(run_id),)
        ).fetchone() == (V2_POLICY_IDENTITY,)


def test_v2_identity_rejects_resuming_a_pre_v2_provider_contract(tmp_path: Path) -> None:
    db_path = str(tmp_path / "pre-v2.sqlite3")
    init_db(db_path)
    run_id = uuid4()
    _insert_planned_run(db_path, run_id)
    values = {
        "fingerprint_version": "v1",
        "provider_identity": "legacy-provider",
        "adapter_identity": "legacy-adapter",
        "model_identity": "legacy-model",
        "prompt_identity": "legacy-prompts",
        "schema_identity": "legacy-schema",
        "normalization_identity": "legacy-normalization",
        "policy_identity": "legacy-policy",
        "repository_revision": "legacy-revision",
    }
    payload_json = canonical_provider_contract_payload(values)
    insert_provider_run_contract(
        db_path,
        ProviderRunContract(
            run_id=run_id,
            fingerprint_sha256=provider_contract_fingerprint(payload_json),
            provider_identity=values["provider_identity"],
            adapter_identity=values["adapter_identity"],
            model_identity=values["model_identity"],
            prompt_identity=values["prompt_identity"],
            schema_identity=values["schema_identity"],
            normalization_identity=values["normalization_identity"],
            policy_identity=values["policy_identity"],
            repository_revision=values["repository_revision"],
            payload_json=payload_json,
            created_at=NOW,
        ),
    )

    with pytest.raises(ValueError, match="pre-v2 provider run"):
        insert_v2_pipeline_identity(db_path, run_id, V2PipelineIdentity(), NOW)
