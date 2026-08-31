from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import hosted_canonical
from frontend.hosted_api import create_hosted_app
from hosted import (
    HostedArtifact,
    HostedAuthenticationError,
    HostedCheckpoint,
    HostedConflictError,
    HostedExecutionResult,
    HostedJobLease,
    HostedJobRunner,
    HostedProviderCredentials,
    HostedResearchRequest,
    HostedRun,
    InMemoryHostedRepository,
    LocalHistoryRun,
    MigrationBundle,
    ProviderCredentialUpdate,
    SupabaseJWTVerifier,
    canonical_migration_fingerprint,
    token_for_tests,
    utc_now,
)
from hosted_worker import CanonicalHostedPipelineExecutor
from models import ResearchDirections, Stage
from providers.v2_budget import V2BudgetSnapshot, V2RunCeilings
from v2_orchestrator import V2ProductionPipelineResult, V2ProductionState

SECRET = "test-hosted-secret"
ROOT = Path(__file__).parents[1]


def request_payload() -> HostedResearchRequest:
    return HostedResearchRequest(raw_claim="A public claim", acknowledged_public=True)


def auth_client(repository: InMemoryHostedRepository, subject: str) -> TestClient:
    verifier = SupabaseJWTVerifier(SECRET)
    client = TestClient(create_hosted_app(repository=repository, verifier=verifier))
    client.headers["Authorization"] = f"Bearer {token_for_tests(subject, SECRET)}"
    return client


def test_verified_identity_is_required_and_runs_are_isolated() -> None:
    repository = InMemoryHostedRepository()
    first = auth_client(repository, "user-one")
    second = auth_client(repository, "user-two")
    response = first.post("/v1/research", json=request_payload().model_dump(mode="json"))
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert second.get(f"/v1/research/{run_id}").status_code == 404
    assert first.get(f"/v1/research/{run_id}").status_code == 200


def test_client_cannot_supply_account_identity_or_read_secret() -> None:
    repository = InMemoryHostedRepository()
    client = auth_client(repository, "user-one")
    payload = request_payload().model_dump(mode="json")
    payload["owner_id"] = "user-two"
    assert client.post("/v1/research", json=payload).status_code == 422
    response = client.put(
        "/v1/providers/credentials",
        json=ProviderCredentialUpdate(exa_api_key="do-not-return").model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert "do-not-return" not in response.text
    assert next(item for item in response.json()["credentials"] if item["name"] == "exa_api_key")[
        "configured"
    ]


class SuccessfulExecutor:
    def execute(
        self,
        lease: HostedJobLease,
        heartbeat: Callable[[HostedCheckpoint], HostedRun],
    ) -> HostedExecutionResult:
        heartbeat(
            HostedCheckpoint(
                stage="discovery",
                checkpoint="searches",
                progress_percent=25,
                message="Searching.",
            )
        )
        artifact = HostedArtifact(
            artifact_id=uuid4(),
            run_id=lease.run.run_id,
            owner_id=lease.run.owner_id,
            artifact_type="release",
            fingerprint="a" * 64,
            payload_json='{"brief":"ready"}',
            created_at=utc_now(),
        )
        return HostedExecutionResult(
            status="released",
            stage="validation",
            message="Released.",
            final_artifact=artifact,
        )


def test_worker_lease_checkpoint_completion_and_immutable_artifact() -> None:
    repository = InMemoryHostedRepository()
    run = repository.create_run("user-one", request_payload())
    result = HostedJobRunner(repository, SuccessfulExecutor(), worker_id="worker-a").run_once()
    assert result is not None
    assert result.run_id == run.run_id
    assert result.status == "released"
    detail = repository.get_detail("user-one", run.run_id)
    assert detail.artifacts[0].artifact_type == "release"
    with pytest.raises(HostedConflictError):
        repository.add_artifact(detail.artifacts[0])


def test_canonical_hosted_executor_projects_typed_result_and_reads_worker_credentials() -> None:
    repository = InMemoryHostedRepository()
    run = repository.create_run("user-one", request_payload())
    repository.save_credentials(
        "user-one",
        ProviderCredentialUpdate(exa_api_key="worker-secret", luna_model="gpt-5.6-luna"),
    )
    lease = repository.claim_job("worker-a", 300)
    assert lease is not None
    seen_credentials: list[HostedProviderCredentials] = []

    def canonical_runner(
        received_lease: HostedJobLease,
        credentials: HostedProviderCredentials,
        heartbeat: Callable[[HostedCheckpoint], HostedRun],
    ) -> V2ProductionPipelineResult:
        assert received_lease.run.run_id == run.run_id
        seen_credentials.append(credentials)
        heartbeat(
            HostedCheckpoint(
                stage="validation",
                checkpoint="canonical-test",
                progress_percent=50,
                message="Canonical test checkpoint.",
            )
        )
        return V2ProductionPipelineResult(
            run_id=run.run_id,
            db_path="/not-used-by-hosted-adapter",
            raw_claim=run.raw_claim,
            state=V2ProductionState.CANCELLED,
            current_stage=Stage.FINAL_RENDERER_VALIDATOR,
            failure_reason="Cancellation was observed.",
            budget=V2BudgetSnapshot(
                physical_calls_used=0,
                token_exposure=0,
                cost_exposure_usd=0,
                physical_calls_remaining=160,
                tokens_remaining=500_000,
                cost_remaining_usd=0.20,
            ),
            completed_at=utc_now(),
        )

    result = CanonicalHostedPipelineExecutor(repository, canonical_runner).execute(
        lease,
        lambda checkpoint: repository.heartbeat(lease, checkpoint),
    )
    assert result.status == "cancelled"
    assert result.final_artifact is not None
    assert seen_credentials[0].exa_api_key is not None
    assert seen_credentials[0].exa_api_key.get_secret_value() == "worker-secret"


def test_deployment_owned_canonical_runner_uses_typed_request_and_ephemeral_scratch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = InMemoryHostedRepository()
    run = repository.create_run(
        "user-one",
        request_payload().model_copy(
            update={
                "max_tokens": 1234,
                "max_cost_usd": "0.10",
                "max_llm_calls": 12,
                "support_enabled": False,
                "challenge_enabled": True,
            }
        ),
    )
    lease = repository.claim_job("worker-a", 300)
    assert lease is not None
    credentials = HostedProviderCredentials(
        mimo_api_key="mimo-secret",
        luna_api_key="luna-secret",
        exa_api_key="exa-secret",
        openalex_api_key="openalex-secret",
        serpsearch_api_key="serpsearch-secret",
    )
    for name, value in {
        "MIMO_V25_INPUT_USD_PER_TOKEN": "0.000001",
        "MIMO_V25_OUTPUT_USD_PER_TOKEN": "0.000002",
        "LUNA_INPUT_USD_PER_TOKEN": "0.000003",
        "LUNA_OUTPUT_USD_PER_TOKEN": "0.000004",
        "RENDER_GIT_COMMIT": "staging-test-revision",
    }.items():
        monkeypatch.setenv(name, value)

    def fake_repository(environment: Mapping[str, str]) -> InMemoryHostedRepository:
        del environment
        return repository

    seen: dict[str, object] = {}

    original_from_environment = hosted_canonical.V2ProductionFactoryConfig.from_environment

    def capture_config(
        environment: Mapping[str, str],
        *,
        repository_revision: str,
        discovery_providers: tuple[object, ...],
        ceilings: V2RunCeilings,
        crossref_enabled: bool,
    ) -> object:
        seen["environment"] = dict(environment)
        return original_from_environment(
            environment,
            repository_revision=repository_revision,
            discovery_providers=discovery_providers,
            ceilings=ceilings,
            crossref_enabled=crossref_enabled,
        )

    def fake_canonical_run(raw_claim: str, **kwargs: object) -> V2ProductionPipelineResult:
        scratch_path = kwargs["db_path"]
        assert isinstance(scratch_path, Path)
        assert scratch_path.parent.is_dir()
        seen["scratch_path"] = scratch_path
        assert raw_claim == run.raw_claim
        assert kwargs["wigolo_provider"] is None
        directions = kwargs["directions"]
        assert isinstance(directions, ResearchDirections)
        assert directions.support_enabled is False
        assert directions.challenge_enabled is True
        ceilings = kwargs["ceilings"]
        assert isinstance(ceilings, V2RunCeilings)
        assert ceilings.max_physical_calls == 12
        assert ceilings.max_total_tokens == 1234
        assert ceilings.max_total_cost_usd == Decimal("0.10")
        return V2ProductionPipelineResult(
            run_id=run.run_id,
            db_path=str(scratch_path),
            raw_claim=raw_claim,
            state=V2ProductionState.CANCELLED,
            current_stage=Stage.FINAL_RENDERER_VALIDATOR,
            failure_reason="Cancellation was observed.",
            budget=V2BudgetSnapshot(
                physical_calls_used=0,
                token_exposure=0,
                cost_exposure_usd=0,
                physical_calls_remaining=12,
                tokens_remaining=1234,
                cost_remaining_usd=0.10,
            ),
            completed_at=utc_now(),
        )

    monkeypatch.setattr(hosted_canonical, "build_repository_from_environment", fake_repository)
    monkeypatch.setattr(
        hosted_canonical.V2ProductionFactoryConfig,
        "from_environment",
        staticmethod(capture_config),
    )
    monkeypatch.setattr(hosted_canonical, "run_v2_production_pipeline", fake_canonical_run)
    result = hosted_canonical.run_canonical_hosted_pipeline(
        lease,
        credentials,
        lambda checkpoint: repository.heartbeat(lease, checkpoint),
    )

    assert result.run_id == run.run_id
    effective_environment = seen["environment"]
    assert isinstance(effective_environment, dict)
    assert effective_environment["MIMO_API_KEY"] == "mimo-secret"
    assert effective_environment["LUNA_API_KEY"] == "luna-secret"
    assert effective_environment["EXA_API_KEY"] == "exa-secret"
    assert isinstance(seen["scratch_path"], Path)
    assert not seen["scratch_path"].exists()


class RetryExecutor:
    def execute(
        self,
        lease: HostedJobLease,
        heartbeat: Callable[[HostedCheckpoint], HostedRun],
    ) -> HostedExecutionResult:
        del lease, heartbeat
        raise RuntimeError("temporary provider failure")


def test_worker_requeues_transient_failures_with_bounded_attempts() -> None:
    repository = InMemoryHostedRepository()
    repository.create_run("user-one", request_payload())
    runner = HostedJobRunner(repository, RetryExecutor(), worker_id="worker-a")
    assert runner.run_once() is not None
    assert repository.list_history("user-one", 10).items[0].status == "queued"
    assert runner.run_once() is not None
    assert runner.run_once() is not None
    assert repository.list_history("user-one", 10).items[0].status == "failed"


def test_migration_fingerprint_and_import_are_idempotent() -> None:
    local_run = LocalHistoryRun(
        local_run_id=uuid4(),
        raw_claim="A historical claim",
        status="running",
        stage="discovery",
        updated_at=datetime.now(UTC),
        fingerprint="b" * 64,
        complete=False,
        source_schema_version=13,
    )
    fingerprint = canonical_migration_fingerprint((local_run,), 13)
    bundle = MigrationBundle(
        source_fingerprint=fingerprint,
        source_schema_version=13,
        created_at=utc_now(),
        runs=(local_run,),
    )
    repository = InMemoryHostedRepository()
    first = repository.import_history("user-one", bundle)
    second = repository.import_history("user-one", bundle)
    assert first.imported == 1 and first.history_only == 1
    assert second.already_imported == 1 and second.imported == 0
    assert second.source_fingerprint == first.source_fingerprint


def test_migration_reports_same_local_id_with_different_fingerprint_as_collision() -> None:
    local_run = LocalHistoryRun(
        local_run_id=uuid4(),
        raw_claim="A historical claim",
        status="failed",
        stage="validation",
        updated_at=datetime.now(UTC),
        fingerprint="c" * 64,
        source_schema_version=13,
    )
    repository = InMemoryHostedRepository()
    first_bundle = MigrationBundle(
        source_fingerprint="d" * 64,
        source_schema_version=13,
        created_at=utc_now(),
        runs=(local_run,),
    )
    second_bundle = first_bundle.model_copy(
        update={
            "source_fingerprint": "e" * 64,
            "runs": (local_run.model_copy(update={"fingerprint": "f" * 64}),),
        }
    )
    repository.import_history("user-one", first_bundle)
    result = repository.import_history("user-one", second_bundle)
    assert result.imported == 0
    assert result.collisions == (local_run.local_run_id,)


def test_expired_access_token_is_rejected() -> None:
    verifier = SupabaseJWTVerifier(SECRET)
    token = token_for_tests("user-one", SECRET, expires_at=utc_now() - timedelta(seconds=1))
    with pytest.raises(HostedAuthenticationError):
        verifier.verify(token)


def test_staging_blueprint_is_free_compatible_and_embeds_the_worker() -> None:
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert blueprint.count("\n    name: researchassistant-staging-") == 2
    assert blueprint.count("type: web") == 2
    assert "type: pserv" not in blueprint
    assert "type: worker" not in blueprint
    assert "plan: free" in blueprint
    assert "HOSTED_EMBEDDED_WORKER" in blueprint
    assert "HOSTED_API_URL" in blueprint
    assert "healthCheckPath: /v1/health" in blueprint
    assert "cron" not in blueprint.casefold()
    assert "keyvalue" not in blueprint.casefold()
    assert "databases:" not in blueprint


def test_magic_link_uses_supabase_redirect_parameter() -> None:
    source = (ROOT / "web" / "app" / "api" / "auth" / "magic-link" / "route.ts").read_text(
        encoding="utf-8"
    )
    assert 'redirect_to: new URL("/auth/callback", request.url).toString()' in source
    assert "email_redirect_to" not in source


def test_render_api_embeds_the_worker_only_when_explicitly_enabled() -> None:
    source = (ROOT / "render_api.py").read_text(encoding="utf-8")
    assert "embedded_worker_lifespan" in source
    assert "HOSTED_EMBEDDED_WORKER" in source
    assert 'casefold() != "true"' in source
    assert "worker_thread.join(timeout=15)" in source


def test_supabase_schema_protects_every_account_table_and_vault_values() -> None:
    schema = (ROOT / "supabase" / "migrations" / "001_hosted_foundation.sql").read_text(
        encoding="utf-8"
    )
    for table in (
        "profiles",
        "research_runs",
        "research_run_events",
        "research_artifacts",
        "provider_credentials",
        "user_settings",
        "historical_runs",
        "migration_imports",
    ):
        assert f"alter table public.{table} enable row level security" in schema
    assert schema.count("auth.uid()") >= 8
    assert "vault.create_secret" in schema
    assert "vault.decrypted_secrets" in schema
    assert "vault.decrypt_secret" not in schema
    assert "vault.delete_secret" not in schema
    assert "research artifacts are immutable" in schema
    assert "for update skip locked" in schema.casefold()
