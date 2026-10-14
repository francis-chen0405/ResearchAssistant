"""Deterministic offline HTTP inventory shared by the before/after contract test."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from test_mlp3_api import FakeController, FakeServices

from researchassistant.api import api
from researchassistant.api.provider_connections import ConnectionCheck
from researchassistant.platform_support.desktop_settings import InterfaceSettings, Preferences
from researchassistant.storage.history_import import HistoryImportResult


def registered_routes(routes: list[object]) -> Iterator[APIRoute]:
    """Flatten FastAPI's included routers without counting OpenAPI-deduplicated paths."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):
            yield from registered_routes(route.original_router.routes)


def contract_inventory(monkeypatch: pytest.MonkeyPatch, folder: Path) -> dict[str, object]:
    """Exercise every HTTP operation with isolated settings, vault and controller."""
    run_id = UUID("00000000-0000-0000-0000-000000000001")
    environment: dict[str, str] = {}
    controller = FakeController(environment)
    controller.run_id = run_id
    settings = Preferences()

    def read_preferences() -> Preferences:
        return settings

    def update_preferences(*, interface: InterfaceSettings) -> Preferences:
        return settings.model_copy(update={"interface": interface})

    def connection(name: str, *args: object, **kwargs: object) -> ConnectionCheck:
        return ConnectionCheck(provider=name, state="unavailable", message="Offline check.")

    def history(source: Path) -> HistoryImportResult:
        return HistoryImportResult(db_path="/fixture/import.sqlite3", run_count=0)

    monkeypatch.setattr(api, "DEFAULT_LIVE_DB", Path("/fixture/live.sqlite3"))
    monkeypatch.setattr(api, "prepare_default_database", lambda: Path("/fixture/live.sqlite3"))
    monkeypatch.setattr(api, "read_preferences", read_preferences)
    monkeypatch.setattr(api, "update_preferences", update_preferences)
    monkeypatch.setattr(api, "check_connection", connection)
    monkeypatch.setattr(api, "remove_credential", lambda name: None)
    monkeypatch.setattr(api, "import_history", history)
    runtime = api.ApiRuntime(
        controller=controller,
        services=FakeServices(),
        environment=environment,
        credential_saver=lambda credentials: None,
    )
    app = api.create_app(runtime, load_keychain_on_start=False, allowed_hosts=("testserver",))
    client = TestClient(app)
    routes = sorted(
        (method, route.path, route.name, route.status_code or 200)
        for route in registered_routes(app.routes)
        for method in route.methods
    )
    database = str(folder / "absent.sqlite3")
    prefix = f"/api/research/{run_id}"
    requests = [
        ("GET", "/api/health", {}),
        ("GET", "/api/model-profiles", {}),
        ("GET", "/api/model-options", {}),
        ("GET", "/api/configuration", {}),
        ("POST", "/api/configuration/check", {"json": {}}),
        ("GET", "/api/preferences", {}),
        ("POST", "/api/preferences", {"json": InterfaceSettings().model_dump(mode="json")}),
        ("POST", "/api/credentials/openai/check", {}),
        ("POST", "/api/credentials/MIMO_API_KEY/remove", {}),
        ("POST", "/api/credentials", {"json": {"mimo_api_key": "offline-secret"}}),
        ("POST", "/api/history/import", {"params": {"source": "/fixture/source.sqlite3"}}),
        (
            "POST",
            "/api/research/start",
            {
                "json": {
                    "raw_claim": "A public claim",
                    "acknowledged_public": True,
                    "run_id": str(run_id),
                    "db_path": database,
                }
            },
        ),
        ("GET", prefix, {"params": {"db_path": database}}),
        ("POST", prefix + "/cancel", {"json": {"db_path": database}}),
        ("GET", prefix + "/trail", {"params": {"db_path": database}}),
        ("GET", prefix + "/v2-result", {"params": {"db_path": database}}),
        ("GET", prefix + "/v2-evidence", {"params": {"db_path": database}}),
        ("GET", "/api/history", {}),
        ("GET", "/api/service", {}),
        ("POST", "/api/service/start", {}),
        ("POST", "/api/service/stop", {}),
        ("POST", "/api/credentials", {"json": {"mimo_api_key": "secret", "extra": True}}),
        (
            "POST",
            "/api/research/start",
            {"json": {"raw_claim": "A public claim", "acknowledged_public": False}},
        ),
        ("GET", "/api/health", {"headers": {"Origin": "https://outside.example"}}),
    ]
    responses = []
    for method, path, kwargs in requests:
        response = client.request(method, path, **kwargs)
        responses.append(
            {
                "method": method,
                "path": path,
                "status": response.status_code,
                "body": response.json(),
                "retry_after": response.headers.get("retry-after"),
            }
        )
    # The request path is the only machine-dependent value in these offline responses.
    import json

    return json.loads(
        json.dumps({"routes": routes, "openapi": app.openapi(), "responses": responses}).replace(
            database, "/fixture/absent.sqlite3"
        )
    )
