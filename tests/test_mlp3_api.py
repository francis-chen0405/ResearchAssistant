from __future__ import annotations

from collections.abc import MutableMapping
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from credential_store import ProviderCredentials
from frontend.api import ApiRuntime, create_app
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


class FakeController:
    def __init__(self, environment: MutableMapping[str, str]) -> None:
        self.environment = environment
        self.started: list[LiveRunRequest] = []
        self.cancelled: list[tuple[str, UUID]] = []
        self.configuration_requests: list[tuple[DiscoveryProvider, ...] | None] = []
        self.run_id = uuid4()

    def configuration_message(
        self,
        *,
        discovery_providers: tuple[DiscoveryProvider, ...] | None = None,
    ) -> str | None:
        self.configuration_requests.append(discovery_providers)
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
