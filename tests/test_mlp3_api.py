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
)
from frontend.service_manager import ServiceDiagnostic


class FakeController:
    def __init__(self, environment: MutableMapping[str, str]) -> None:
        self.environment = environment
        self.started: list[LiveRunRequest] = []
        self.cancelled: list[tuple[str, UUID]] = []
        self.run_id = uuid4()

    def configuration_message(self) -> str | None:
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
        "exa_api_key": "exa-super-secret",
        "firecrawl_api_key": "firecrawl-super-secret",
    }

    response = client.post("/api/credentials", json=payload)

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert "secret" not in response.text
    assert saved[0].environment_items() == (
        ("MIMO_API_KEY", "mimo-super-secret"),
        ("EXA_API_KEY", "exa-super-secret"),
        ("FIRECRAWL_API_KEY", "firecrawl-super-secret"),
    )


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
        },
    )

    assert rejected.status_code == 422
    assert accepted.status_code == 200
    request = controller.started[0]
    assert request.raw_claim == "A public claim"
    assert request.max_tokens == 200_000
    assert request.max_cost_usd == Decimal("0.15")
    assert request.max_llm_calls == 160
    assert request.research_controls.depth.value == "standard"


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
