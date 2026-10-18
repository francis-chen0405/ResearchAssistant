"""API teardown cancels and drains before retiring the service it owns."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_mlp3_api import FakeServices

from researchassistant.api import api
from researchassistant.api.live_service import LiveResearchController


@pytest.mark.parametrize("desktop_owned", [False, True])
def test_lifespan_has_one_shutdown_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, desktop_owned: bool
) -> None:
    calls: list[str] = []
    controller = LiveResearchController(environment={})
    services = FakeServices()

    def shutdown(*, timeout: float = 90) -> bool:
        assert timeout == 90
        calls.append("drain")
        return True

    def stop() -> object:
        calls.append("stop")
        return None

    monkeypatch.setattr(controller, "shutdown", shutdown)
    monkeypatch.setattr(services, "owns_running_process", lambda: True)
    monkeypatch.setattr(services, "stop", stop)
    monkeypatch.setattr(api, "_prepare_default_database", lambda: None)
    runtime = api.ApiRuntime(controller=controller, services=services, environment={})
    app = api.create_app(
        runtime, load_keychain_on_start=False, shutdown_controller_on_exit=not desktop_owned
    )
    try:
        with TestClient(app):
            pass
        assert calls == ([] if desktop_owned else ["drain", "stop"])
    finally:
        # Use the original implementation to close the actual empty executor.
        LiveResearchController.shutdown(controller, timeout=1)


def test_cli_drains_and_retires_owned_service_after_server_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    controller = LiveResearchController(environment={})
    services = FakeServices()
    runtime = api.ApiRuntime(controller=controller, services=services, environment={})

    def fail_server(*args: object, **kwargs: object) -> None:
        raise RuntimeError("fixture server failure")

    def drain(*, timeout: float = 90) -> bool:
        assert timeout == 90
        calls.append("drain")
        return True

    monkeypatch.setattr(api, "create_default_runtime", lambda: runtime)
    monkeypatch.setattr(api.uvicorn, "run", fail_server)
    monkeypatch.setattr(controller, "shutdown", drain)
    monkeypatch.setattr(services, "owns_running_process", lambda: True)
    monkeypatch.setattr(services, "stop", lambda: calls.append("stop"))
    try:
        with pytest.raises(RuntimeError, match="fixture server failure"):
            api.main()
        assert calls == ["drain", "stop"]
    finally:
        LiveResearchController.shutdown(controller, timeout=1)


def test_cli_deadline_remains_bounded_when_owned_service_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = LiveResearchController(environment={})
    services = FakeServices()
    runtime = api.ApiRuntime(controller=controller, services=services, environment={})
    calls: list[str] = []

    class ForcedExit(Exception):
        pass

    def stop() -> None:
        calls.append("stop")
        raise OSError("fixture cleanup failure")

    def exit_process(code: int) -> None:
        assert code == 1
        calls.append("exit")
        raise ForcedExit

    monkeypatch.setattr(api, "create_default_runtime", lambda: runtime)
    monkeypatch.setattr(api.uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(controller, "shutdown", lambda **kwargs: False)
    monkeypatch.setattr(controller, "has_active_runs", lambda: True)
    monkeypatch.setattr(services, "owns_running_process", lambda: True)
    monkeypatch.setattr(services, "stop", stop)
    monkeypatch.setattr(api.os, "_exit", exit_process)
    try:
        with pytest.raises(ForcedExit):
            api.main()
        assert calls == ["stop", "exit"]
    finally:
        LiveResearchController.shutdown(controller, timeout=1)
