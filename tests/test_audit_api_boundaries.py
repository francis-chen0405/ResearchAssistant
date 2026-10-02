from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_mlp3_api import FakeController, FakeServices

from frontend.api import ApiRuntime, LoopbackGuardMiddleware, create_app
from frontend.live_service import LiveResearchController


@pytest.mark.parametrize("authorization", (b"\xff", b"Bearer \xff"))
def test_desktop_session_rejects_non_ascii_authorization_without_server_error(
    authorization: bytes,
) -> None:
    app = FastAPI()
    app.add_middleware(
        LoopbackGuardMiddleware,
        allowed_hosts=("testserver",),
        allowed_origins=(),
        session_token="a" * 64,
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/health", headers={b"authorization": authorization})

    assert response.status_code == 401
    assert response.json() == {"detail": "Desktop session required."}


@pytest.mark.parametrize("invalid_field", ("claim", "directory", "missing_parent", "not_sqlite"))
def test_start_rejects_invalid_live_request_before_controller(
    tmp_path: Path, invalid_field: str
) -> None:
    controller = FakeController({})
    runtime = ApiRuntime(controller=controller, services=FakeServices(), environment={})
    app = create_app(runtime, load_keychain_on_start=False, allowed_hosts=("testserver",))
    client = TestClient(app, raise_server_exceptions=False)
    claim = "A public claim"
    database = tmp_path / "research.sqlite3"
    if invalid_field == "claim":
        claim = " A public claim "
    elif invalid_field == "directory":
        database = tmp_path
    elif invalid_field == "missing_parent":
        database = tmp_path / "missing" / "research.sqlite3"
    else:
        database.write_text("invalid-private-database-content")

    response = client.post(
        "/api/research/start",
        json={"raw_claim": claim, "acknowledged_public": True, "db_path": str(database)},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request fields."}
    assert not controller.started
    assert "invalid-private-database-content" not in response.text


def test_snapshot_reports_incompatible_database_without_server_error_or_changes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "invalid.sqlite3"
    database.write_bytes(b"invalid-private-database-content")
    before = database.read_bytes(), database.stat().st_mtime_ns
    controller = LiveResearchController(environment={})
    runtime = ApiRuntime(controller=controller, services=FakeServices(), environment={})
    app = create_app(runtime, load_keychain_on_start=False, allowed_hosts=("testserver",))
    client = TestClient(app, raise_server_exceptions=False)
    try:
        response = client.get(f"/api/research/{uuid4()}", params={"db_path": str(database)})
        assert response.status_code == 400
        assert isinstance(response.json()["detail"], str)
        assert "invalid-private-database-content" not in response.text
        assert (database.read_bytes(), database.stat().st_mtime_ns) == before
    finally:
        controller.shutdown(timeout=0)
