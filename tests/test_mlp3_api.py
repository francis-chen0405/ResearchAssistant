from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from credential_store import ProviderCredentials
from desktop_settings import InterfaceSettings, Preferences
from frontend.api import ApiRuntime, ConnectionCheck, create_app
from frontend.live_service import (
    LiveHistoryItem,
    LiveRunRequest,
    LiveRunSnapshot,
    LiveStartResult,
    ResearchProgress,
    ResearchTrail,
)
from frontend.service_manager import ServiceDiagnostic
from models import DiscoveryProvider
from providers.model_choices import (
    CONFIGURABLE_PROFILE_ID,
    DEFAULT_STAGE_MODELS,
    ModelChoice,
    StageModelSelections,
)


class FakeController:
    def __init__(self, environment: MutableMapping[str, str]) -> None:
        self.environment = environment
        self.started: list[LiveRunRequest] = []
        self.cancelled: list[tuple[str, UUID]] = []
        self.configuration_requests: list[tuple[DiscoveryProvider, ...] | None] = []
        self.selection_requests: list[tuple[str | None, object]] = []
        self.run_id = uuid4()

    def configuration_message(
        self,
        *,
        discovery_providers: tuple[DiscoveryProvider, ...] | None = None,
        model_profile: str | None = None,
        stage_models: object = None,
    ) -> str | None:
        self.configuration_requests.append(discovery_providers)
        self.selection_requests.append((model_profile, stage_models))
        if self.environment.get("MIMO_API_KEY") and self.environment.get("EXA_API_KEY"):
            return None
        return "Provider configuration is incomplete."

    def start(self, request: LiveRunRequest) -> LiveStartResult:
        self.started.append(request)
        self.run_id = request.run_id or self.run_id
        return LiveStartResult(
            started=True,
            run_id=self.run_id,
            classification="starting",
            message="Research started.",
        )

    def snapshot(self, db_path: str | Path, run_id: UUID) -> LiveRunSnapshot:
        if run_id != self.run_id:
            raise KeyError(run_id)
        progress = ResearchProgress(
            stance="supporting",
            status="running",
            model_attempts=1,
            retrieval_attempts=2,
            usable_snapshots=1,
            candidates=1,
        )
        return LiveRunSnapshot(
            run_id=run_id,
            db_path=str(db_path),
            raw_claim="A public claim",
            classification="running",
            stage="research",
            message="Research is running.",
            diagnostic_component="research",
            model_calls_used=1,
            retrieval_attempts_used=2,
            supporting=progress,
            opposing=progress.model_copy(update={"stance": "opposing"}),
        )

    def cancel(self, db_path: str | Path, run_id: UUID) -> str:
        self.cancelled.append((str(db_path), run_id))
        return "Cancellation persisted."

    def history(self, db_path: str | Path, *, limit: int = 100) -> tuple[LiveHistoryItem, ...]:
        del db_path, limit
        return (
            LiveHistoryItem(
                run_id=self.run_id,
                raw_claim="A public claim",
                status="running",
                stage="research",
                updated_at="2026-08-14T12:00:00+00:00",
            ),
        )

    def research_trail(self, db_path: str | Path, run_id: UUID) -> ResearchTrail:
        del db_path
        if run_id != self.run_id:
            raise KeyError(run_id)
        return ResearchTrail(run_id=run_id, items=())

    def has_active_runs(self) -> bool:
        return False


class FakeServices:
    def __init__(self) -> None:
        self.state = "unhealthy"

    def probe(self) -> ServiceDiagnostic:
        return self._diagnostic()

    def start(self) -> ServiceDiagnostic:
        self.state = "healthy"
        return self._diagnostic()

    def stop(self) -> ServiceDiagnostic:
        self.state = "stopped"
        return self._diagnostic()

    def owns_running_process(self) -> bool:
        return False

    def _diagnostic(self) -> ServiceDiagnostic:
        return ServiceDiagnostic(
            state=self.state,  # type: ignore[arg-type]
            wigolo_ready=self.state == "healthy",
            searxng_readiness="configured" if self.state == "healthy" else "unavailable",
            message=f"Service is {self.state}.",
            owned_process=self.state == "healthy",
        )


def _client() -> tuple[TestClient, FakeController, list[ProviderCredentials]]:
    environment: dict[str, str] = {}
    controller = FakeController(environment)
    services = FakeServices()
    saved: list[ProviderCredentials] = []

    def save(credentials: ProviderCredentials) -> None:
        saved.append(credentials)

    runtime = ApiRuntime(
        controller=controller,
        services=services,
        environment=environment,
        credential_saver=save,
    )
    app = create_app(
        runtime,
        load_keychain_on_start=False,
        allowed_hosts=("testserver",),
        allowed_origins=("http://127.0.0.1:3000",),
    )
    return TestClient(app), controller, saved


def test_api_rejects_nonlocal_origin_and_unknown_fields() -> None:
    client, _, _ = _client()

    blocked = client.get(
        "/api/health",
        headers={"Origin": "https://example.com"},
    )
    invalid = client.post(
        "/api/research/start",
        json={
            "raw_claim": "A public claim",
            "acknowledged_public": True,
            "unexpected": "not allowed",
        },
    )

    assert blocked.status_code == 403
    assert invalid.status_code == 422


def test_credentials_are_saved_and_never_returned() -> None:
    client, _, saved = _client()
    payload = {
        "mimo_api_key": "mimo-super-secret",
        "luna_api_key": "openai-super-secret",
        "luna_base_url": "https://api.example.test/v1",
        "luna_model": "deployment-luna-model",
        "mimo_v25_input_usd_per_million": "1",
        "mimo_v25_output_usd_per_million": "2",
        "luna_input_usd_per_million": "3",
        "luna_output_usd_per_million": "4",
        "exa_api_key": "exa-super-secret",
        "openalex_api_key": "openalex-super-secret",
        "pubmed_api_key": "pubmed-super-secret",
        "firecrawl_api_key": "firecrawl-super-secret",
    }

    response = client.post("/api/credentials", json=payload)

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["saved_settings"] == [
        "MiMo input price",
        "MiMo output price",
        "Luna input price",
        "Luna output price",
        "Luna API base URL",
        "Luna model ID",
    ]
    assert "secret" not in response.text
    assert saved[0].environment_items() == (
        ("MIMO_API_KEY", "mimo-super-secret"),
        ("LUNA_API_KEY", "openai-super-secret"),
        ("LUNA_BASE_URL", "https://api.example.test/v1"),
        ("LUNA_MODEL", "deployment-luna-model"),
        ("MIMO_V25_INPUT_USD_PER_TOKEN", "0.000001"),
        ("MIMO_V25_OUTPUT_USD_PER_TOKEN", "0.000002"),
        ("LUNA_INPUT_USD_PER_TOKEN", "0.000003"),
        ("LUNA_OUTPUT_USD_PER_TOKEN", "0.000004"),
        ("EXA_API_KEY", "exa-super-secret"),
        ("OPENALEX_API_KEY", "openalex-super-secret"),
        ("PUBMED_API_KEY", "pubmed-super-secret"),
        ("FIRECRAWL_API_KEY", "firecrawl-super-secret"),
    )


def test_credentials_can_save_one_new_provider_key_without_resending_existing_keys() -> None:
    client, _, saved = _client()

    response = client.post("/api/credentials", json={"serpsearch_api_key": "serpsearch-secret"})

    assert response.status_code == 200
    assert "secret" not in response.text
    assert saved[0].environment_items() == (("SERPSEARCH_API_KEY", "serpsearch-secret"),)

    empty = client.post("/api/credentials", json={})
    assert empty.status_code == 422
    assert empty.json()["detail"] == "Enter at least one API key to save."


def test_credentials_readiness_receives_the_selected_model_mix() -> None:
    client, controller, _ = _client()
    selected = {
        "planner": "mimo-v2.6-flash",
        "scout": "mimo-v2.6-flash",
        "gap_analysis": "mimo-v2.6-flash",
        "search_agent": "mimo-v2.6-flash",
        "source_selection": "mimo-v2.6-flash",
        "extractor": "mimo-v2.6-flash",
        "analyst": "mimo-v2.6-flash",
    }

    response = client.post(
        "/api/credentials",
        json={
            "model_profile": "configurable-2026-09",
            "stage_models": selected,
            "mimo_api_key": "mimo-secret",
            "exa_api_key": "exa-secret",
        },
    )

    assert response.status_code == 200
    assert controller.selection_requests[-1][0] == "configurable-2026-09"
    assert controller.selection_requests[-1][1].model_dump(mode="json") == selected


def test_provider_connection_check_receives_explicit_or_saved_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import frontend.api as api_module

    client, _, _ = _client()
    selected = StageModelSelections(
        planner=ModelChoice.GPT_6_SOL_HIGH,
        scout=ModelChoice.GPT_6_SOL_HIGH,
        gap_analysis=ModelChoice.GPT_6_SOL_HIGH,
        search_agent=ModelChoice.GPT_6_SOL_HIGH,
        source_selection=ModelChoice.GPT_6_SOL_HIGH,
        extractor=ModelChoice.GPT_6_SOL_HIGH,
        analyst=ModelChoice.GPT_6_SOL_HIGH,
    )
    saved = StageModelSelections(
        planner=ModelChoice.MIMO_V26_FLASH,
        scout=ModelChoice.MIMO_V26_FLASH,
        gap_analysis=ModelChoice.MIMO_V26_FLASH,
        search_agent=ModelChoice.MIMO_V26_FLASH,
        source_selection=ModelChoice.MIMO_V26_FLASH,
        extractor=ModelChoice.MIMO_V26_FLASH,
        analyst=ModelChoice.MIMO_V26_FLASH,
    )

    def saved_preferences() -> Preferences:
        return Preferences(interface=InterfaceSettings(stageModels=saved))

    monkeypatch.setattr(api_module, "read_preferences", saved_preferences)
    seen: list[tuple[str, str, StageModelSelections]] = []

    def check(
        name: str,
        environment: Mapping[str, str],
        *,
        model_profile: str,
        stage_models: StageModelSelections,
    ) -> ConnectionCheck:
        del environment
        seen.append((name, model_profile, stage_models))
        return ConnectionCheck(provider=name, state="unavailable", message="Not ready.")

    monkeypatch.setattr(api_module, "check_connection", check)
    explicit = client.post(
        "/api/credentials/openai/check",
        json={
            "model_profile": CONFIGURABLE_PROFILE_ID,
            "stage_models": selected.model_dump(mode="json"),
        },
    )
    saved_selection = client.post("/api/credentials/mimo/check")

    assert explicit.status_code == 200
    assert saved_selection.status_code == 200
    assert seen == [
        ("openai", CONFIGURABLE_PROFILE_ID, selected),
        ("mimo", CONFIGURABLE_PROFILE_ID, saved),
    ]


def test_get_configuration_uses_saved_stage_model_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import frontend.api as api_module

    client, controller, _ = _client()
    controller.environment.update(
        {
            "MIMO_API_KEY": "test-mimo",
            "EXA_API_KEY": "test-exa",
            "LUNA_BASE_URL": "https://gateway.example.test/v1",
        }
    )
    selected = StageModelSelections(
        planner=ModelChoice.MIMO_V26_FLASH,
        scout=ModelChoice.MIMO_V26_FLASH,
        gap_analysis=ModelChoice.MIMO_V26_FLASH,
        search_agent=ModelChoice.MIMO_V26_FLASH,
        source_selection=ModelChoice.MIMO_V26_FLASH,
        extractor=ModelChoice.MIMO_V26_FLASH,
        analyst=ModelChoice.MIMO_V26_FLASH,
    )

    def saved_preferences() -> Preferences:
        return Preferences(interface=InterfaceSettings(stageModels=selected))

    monkeypatch.setattr(api_module, "read_preferences", saved_preferences)

    response = client.get(
        "/api/configuration",
        params={
            "model_profile": CONFIGURABLE_PROFILE_ID,
            "use_serpsearch": "false",
            "use_exa": "true",
            "use_openalex": "false",
            "use_arxiv": "false",
            "use_pubmed": "false",
        },
    )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    without_profile = client.get(
        "/api/configuration",
        params={
            "use_serpsearch": "false",
            "use_exa": "true",
            "use_openalex": "false",
            "use_arxiv": "false",
            "use_pubmed": "false",
        },
    )
    assert without_profile.status_code == 200
    assert without_profile.json()["configured"] is True


def test_get_configuration_is_not_ready_for_invalid_saved_preferences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import frontend.api as api_module

    client, controller, _ = _client()
    controller.environment.update({"MIMO_API_KEY": "test-mimo", "EXA_API_KEY": "test-exa"})

    def invalid_preferences() -> Preferences:
        raise ValueError("private invalid saved preference details")

    monkeypatch.setattr(api_module, "read_preferences", invalid_preferences)

    response = client.get("/api/configuration")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert "saved model selections could not be read" in response.json()["message"].lower()
    assert "private invalid saved preference details" not in response.text


def test_connection_check_without_body_is_unavailable_for_invalid_saved_preferences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import frontend.api as api_module

    client, _, _ = _client()
    called = False

    def invalid_preferences() -> Preferences:
        raise ValueError("invalid saved preference details")

    def check(
        name: str,
        environment: Mapping[str, str],
        *,
        model_profile: str,
        stage_models: StageModelSelections,
    ) -> ConnectionCheck:
        nonlocal called
        del environment, model_profile, stage_models
        called = True
        return ConnectionCheck(provider=name, state="connected", message="Should not be used.")

    monkeypatch.setattr(api_module, "read_preferences", invalid_preferences)
    monkeypatch.setattr(api_module, "check_connection", check)

    response = client.post("/api/credentials/openai/check")

    assert response.status_code == 200
    assert response.json()["state"] == "unavailable"
    assert "saved model selections could not be read" in response.json()["message"].lower()
    assert "invalid saved preference details" not in response.text
    assert called is False


@pytest.mark.parametrize(
    "path,payload",
    [
        (
            "/api/configuration/check",
            {"model_profile": CONFIGURABLE_PROFILE_ID},
        ),
        ("/api/credentials", {"mimo_api_key": "test-mimo"}),
    ],
)
def test_internal_type_error_is_not_treated_as_legacy_controller_signature(
    path: str,
    payload: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, controller, _ = _client()

    def configuration_message(
        *,
        discovery_providers: tuple[DiscoveryProvider, ...] | None = None,
        model_profile: str | None = None,
        stage_models: StageModelSelections = DEFAULT_STAGE_MODELS,
    ) -> str | None:
        del discovery_providers, stage_models
        if model_profile is not None:
            raise TypeError("internal stage_models processing failed")
        return None

    monkeypatch.setattr(controller, "configuration_message", configuration_message)

    with pytest.raises(TypeError, match="internal stage_models processing failed"):
        client.post(path, json=payload)


def test_start_uses_safe_defaults_and_requires_acknowledgement(tmp_path: Path) -> None:
    client, controller, _ = _client()
    database = tmp_path / "live.sqlite3"

    rejected = client.post(
        "/api/research/start",
        json={"raw_claim": "A public claim", "acknowledged_public": False},
    )
    accepted = client.post(
        "/api/research/start",
        json={
            "raw_claim": "A public claim",
            "acknowledged_public": True,
            "db_path": str(database),
            "sources_per_stance_per_round": 20,
        },
    )

    assert rejected.status_code == 422
    assert accepted.status_code == 200
    request = controller.started[0]
    assert request.raw_claim == "A public claim"
    assert request.max_tokens == 500_000
    assert request.max_cost_usd == Decimal("0.20")
    assert request.max_llm_calls == 160
    assert request.research_controls.depth.value == "standard"
    assert request.research_controls.sources_per_stance_per_round == 20


def test_browser_claim_submission_trims_whitespace_before_api_request() -> None:
    page_source = (Path(__file__).parents[1] / "web" / "app" / "page.tsx").read_text()

    assert "const trimmedClaim = claim.trim();" in page_source
    assert "raw_claim: trimmedClaim" in page_source


def test_start_freezes_selected_discovery_sources_and_rejects_an_empty_set(tmp_path: Path) -> None:
    client, controller, _ = _client()
    database = tmp_path / "live.sqlite3"

    accepted = client.post(
        "/api/research/start",
        json={
            "raw_claim": "A public claim",
            "acknowledged_public": True,
            "db_path": str(database),
            "use_serpsearch": True,
            "use_exa": False,
            "use_openalex": False,
        },
    )
    rejected = client.post(
        "/api/research/start",
        json={
            "raw_claim": "A public claim",
            "acknowledged_public": True,
            "db_path": str(database),
            "use_serpsearch": False,
            "use_exa": False,
            "use_openalex": False,
        },
    )

    assert accepted.status_code == 200
    assert controller.started[0].research_controls.discovery_providers == ("serpsearch",)
    assert rejected.status_code == 422
    assert "at least one" in rejected.json()["detail"]


def test_start_links_arxiv_pubmed_and_crossref_controls(tmp_path: Path) -> None:
    client, controller, _ = _client()

    response = client.post(
        "/api/research/start",
        json={
            "raw_claim": "A public claim",
            "acknowledged_public": True,
            "db_path": str(tmp_path / "academic.sqlite3"),
            "use_serpsearch": False,
            "use_exa": False,
            "use_openalex": False,
            "use_arxiv": True,
            "use_pubmed": True,
            "use_crossref": True,
        },
    )

    assert response.status_code == 200
    assert controller.started[0].research_controls.discovery_providers == ("arxiv", "pubmed")
    assert controller.started[0].crossref_enabled is True


def test_configuration_reports_saved_key_presence_without_returning_secrets() -> None:
    client, _, _ = _client()
    client.post(
        "/api/credentials",
        json={
            "pubmed_api_key": "pubmed-super-secret",
            "mimo_v25_input_usd_per_million": "1.25",
        },
    )

    response = client.get("/api/configuration")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["saved_credentials"] == ["pubmed"]
    assert response.json()["saved_settings"] == ["MiMo input price"]
    assert "secret" not in response.text


def test_configuration_checks_the_selected_provider_switches() -> None:
    client, controller, _ = _client()

    response = client.get(
        "/api/configuration",
        params={
            "use_serpsearch": False,
            "use_exa": False,
            "use_openalex": False,
            "use_arxiv": True,
            "use_pubmed": True,
        },
    )

    assert response.status_code == 200
    assert controller.configuration_requests[-1] == (
        DiscoveryProvider.ARXIV,
        DiscoveryProvider.PUBMED,
    )


def test_start_preserves_independent_v2_research_directions(tmp_path: Path) -> None:
    client, controller, _ = _client()
    response = client.post(
        "/api/research/start",
        json={
            "raw_claim": "A public claim",
            "acknowledged_public": True,
            "db_path": str(tmp_path / "challenge-only.sqlite3"),
            "support_enabled": False,
            "challenge_enabled": True,
        },
    )

    assert response.status_code == 200
    assert controller.started[0].directions.support_enabled is False
    assert controller.started[0].directions.challenge_enabled is True


def test_snapshot_history_cancellation_and_service_controls(tmp_path: Path) -> None:
    client, controller, _ = _client()
    database = str(tmp_path / "live.sqlite3")

    snapshot = client.get(
        f"/api/research/{controller.run_id}",
        params={"db_path": database},
    )
    history = client.get("/api/history", params={"db_path": database})
    cancelled = client.post(
        f"/api/research/{controller.run_id}/cancel",
        json={"db_path": database},
    )
    started = client.post("/api/service/start")
    stopped = client.post("/api/service/stop")

    assert snapshot.status_code == 200
    assert snapshot.json()["classification"] == "running"
    assert len(history.json()["items"]) == 1
    assert cancelled.json()["cancelled"] is True
    assert controller.cancelled == [(database, controller.run_id)]
    assert started.json()["wigolo_ready"] is True
    assert stopped.json()["state"] == "stopped"


def test_research_trail_returns_not_found_for_an_unknown_run(tmp_path: Path) -> None:
    client, _, _ = _client()

    response = client.get(
        f"/api/research/{uuid4()}/trail",
        params={"db_path": str(tmp_path / "live.sqlite3")},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Research run not found."


def test_phase3_catalog_and_profile_configuration_are_offline() -> None:
    client, controller, _ = _client()
    controller.environment.update({"MIMO_API_KEY": "test-mimo", "LUNA_API_KEY": "test-luna"})
    catalog = client.get("/api/model-profiles")
    assert catalog.status_code == 200
    assert catalog.json()[0]["id"] == "standard-2026-09"
    assert "test-luna" not in catalog.text
    ready = client.get(
        "/api/configuration",
        params={
            "model_profile": "standard-2026-09",
            "use_serpsearch": "false",
            "use_exa": "false",
            "use_openalex": "false",
            "use_arxiv": "true",
        },
    )
    assert ready.status_code == 200
    assert ready.json()["configured"] is True
    assert "LUNA_INPUT_USD_PER_TOKEN" not in controller.environment
    assert client.get("/api/configuration?model_profile=unknown").status_code == 422


def test_model_options_and_selection_aware_configuration_check_are_offline() -> None:
    client, controller, _ = _client()
    controller.environment.update({"LUNA_API_KEY": "test-luna"})

    options = client.get("/api/model-options")
    assert options.status_code == 200
    payload = options.json()
    assert len(payload["choices"]) == 6
    assert {
        "id",
        "label",
        "provider",
        "input_per_million",
        "output_per_million",
    } == set(payload["choices"][0])
    assert payload["defaults"]["scout"] == "gpt-6-luna-high"
    assert payload["defaults"]["planner"] == "gpt-6-luna-xhigh"
    luna_choices = {
        choice["id"]: choice
        for choice in payload["choices"]
        if choice["id"].startswith("gpt-6-luna-")
    }
    assert set(luna_choices) == {"gpt-6-luna-high", "gpt-6-luna-xhigh"}
    assert all(choice["input_per_million"] == "0.10" for choice in luna_choices.values())
    assert all(choice["output_per_million"] == "0.50" for choice in luna_choices.values())

    checked = client.post(
        "/api/configuration/check",
        json={
            "stage_models": payload["defaults"],
            "use_serpsearch": False,
            "use_exa": False,
            "use_openalex": False,
            "use_arxiv": True,
            "use_pubmed": False,
        },
    )
    assert checked.status_code == 200
    assert checked.json()["configured"] is True


def test_phase3_profile_is_carried_in_the_typed_start_request(tmp_path: Path) -> None:
    client, controller, _ = _client()
    result = client.post(
        "/api/research/start",
        json={
            "model_profile": "standard-2026-09",
            "raw_claim": "A public claim",
            "acknowledged_public": True,
            "db_path": str(tmp_path / "research.sqlite3"),
            "max_cost_usd": "0.50",
        },
    )
    assert result.status_code == 200
    assert controller.started[0].model_profile == "standard-2026-09"
    assert controller.started[0].max_cost_usd == Decimal("0.50")
    rejected = client.post(
        "/api/research/start",
        json={
            "model_profile": "arbitrary-model",
            "raw_claim": "A public claim",
            "acknowledged_public": True,
        },
    )
    assert rejected.status_code == 422
    assert len(controller.started) == 1


def test_phase3_credentials_cannot_change_during_active_research() -> None:
    from unittest.mock import patch

    client, controller, saved = _client()
    with patch.object(controller, "has_active_runs", return_value=True):
        response = client.post("/api/credentials", json={"mimo_api_key": "must-not-save"})
        assert response.status_code == 409
        assert client.post("/api/credentials/MIMO_API_KEY/remove").status_code == 409
    assert not saved
    assert "must-not-save" not in response.text


def test_phase3_denied_vault_access_explains_system_password_without_echoing_key() -> None:
    from credential_store import KeychainUnavailableError

    environment: dict[str, str] = {}

    def deny(credentials: ProviderCredentials) -> None:
        raise KeychainUnavailableError("Native access cancelled at a private local path")

    app = create_app(
        ApiRuntime(
            controller=FakeController(environment),
            services=FakeServices(),
            environment=environment,
            credential_saver=deny,
        ),
        load_keychain_on_start=False,
        allowed_hosts=("testserver",),
    )
    response = TestClient(app).post(
        "/api/credentials", json={"mimo_api_key": "not-a-real-provider-key"}
    )
    assert response.status_code == 503
    assert "Mac login/keychain password" in response.text
    assert "not-a-real-provider-key" not in response.text
    assert "private local path" not in response.text
    assert not environment
