from __future__ import annotations

import io
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

import frontend.service_manager as service_manager_module
from cli import CLIExitCode
from frontend.live_service import (
    LiveResearchController,
    LiveRunRequest,
    exit_code_for_status,
)
from frontend.security import redact_text
from frontend.service_manager import ServiceDiagnostic, WigoloServiceManager
from models import (
    PresentationTone,
    ReportLength,
    ResearchControls,
    ResearchDepth,
    RunManifest,
    RunStatus,
    Stage,
)
from orchestrator import ProviderPipelineResult, ProviderRunStatus
from providers.search import SearchFailureCode, SearchProviderError
from store import init_db, insert_run

CLAIM = "The fixture policy improves student outcomes."
SECRET = "mvp5-secret-value-that-must-never-appear"
ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "tests" / "mvp4_subprocess_driver.py"


def _request(tmp_path: Path, *, run_id: UUID | None = None) -> LiveRunRequest:
    return LiveRunRequest(
        raw_claim=CLAIM,
        db_path=str(tmp_path / "live.sqlite3"),
        run_id=run_id,
        max_tokens=100_000,
        max_cost_usd=Decimal("0.15"),
    )


def _terminal_result(
    db_path: str,
    run_id: UUID,
    *,
    status: ProviderRunStatus = ProviderRunStatus.FAILED,
) -> ProviderPipelineResult:
    return ProviderPipelineResult(
        run_id=run_id,
        status=status,
        raw_claim=CLAIM,
        db_path=db_path,
        current_stage=Stage.CLAIM_PLANNER,
        failure_reason="mocked provider failure" if status is ProviderRunStatus.FAILED else None,
    )


def test_live_request_requires_exact_claim_and_explicit_budgets(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="leading or trailing"):
        _request(tmp_path).model_copy(update={"raw_claim": f" {CLAIM}"}).model_dump()
        LiveRunRequest(
            raw_claim=f" {CLAIM}",
            db_path=str(tmp_path / "live.sqlite3"),
            max_tokens=100,
            max_cost_usd=Decimal("0.01"),
        )
    with pytest.raises(ValidationError):
        LiveRunRequest(
            raw_claim=CLAIM,
            db_path=str(tmp_path / "live.sqlite3"),
            max_tokens=1_000_001,
            max_cost_usd=Decimal("0.01"),
        )
    unsafe = tmp_path / "notes.txt"
    unsafe.write_text("not sqlite", encoding="utf-8")
    with pytest.raises(ValidationError, match="not a SQLite file"):
        LiveRunRequest(
            raw_claim=CLAIM,
            db_path=str(unsafe),
            max_tokens=100,
            max_cost_usd=Decimal("0.01"),
        )


def test_missing_configuration_is_friendly_and_creates_no_database(tmp_path: Path) -> None:
    request = _request(tmp_path, run_id=uuid4())
    controller = LiveResearchController(environment={})
    result = controller.start(request)
    snapshot = controller.snapshot(request.db_path, result.run_id)

    assert result.classification == "configuration_error"
    assert snapshot.exit_code == CLIExitCode.CONFIGURATION_ERROR
    assert "MIMO_API_KEY" in snapshot.message
    assert not Path(request.db_path).exists()


def test_duplicate_start_reconnects_without_second_worker(tmp_path: Path) -> None:
    entered = Event()
    release = Event()
    calls = 0
    run_id = uuid4()
    request = _request(tmp_path, run_id=run_id)

    def runner(raw_claim: str, **kwargs: object) -> ProviderPipelineResult:
        nonlocal calls
        calls += 1
        entered.set()
        release.wait(timeout=5)
        return _terminal_result(str(kwargs["db_path"]), UUID(str(kwargs["run_id"])))

    controller = LiveResearchController(
        environment={"MIMO_API_KEY": SECRET, "EXA_API_KEY": "exa-test-secret"},
        runner=runner,
    )
    first = controller.start(request)
    assert entered.wait(timeout=2)
    second = controller.start(request)
    same_database_other_run = controller.start(_request(tmp_path, run_id=uuid4()))
    release.set()
    snapshot = controller.snapshot(request.db_path, run_id)
    deadline = monotonic() + 2
    while snapshot.classification == "starting" and monotonic() < deadline:
        sleep(0.01)
        snapshot = controller.snapshot(request.db_path, run_id)

    assert first.started is True
    assert second.started is False
    assert second.classification == "duplicate_active"
    assert same_database_other_run.started is False
    assert same_database_other_run.classification == "duplicate_active"
    assert "already has an active research run" in same_database_other_run.message
    assert snapshot.classification == "failed"
    assert calls == 1


def test_live_controller_passes_requested_research_controls_to_runner(tmp_path: Path) -> None:
    controls = ResearchControls(
        depth=ResearchDepth.FOCUSED,
        length=ReportLength.BRIEF,
        tone=PresentationTone.NEUTRAL,
    )
    request = _request(tmp_path, run_id=uuid4()).model_copy(update={"research_controls": controls})
    received_controls: ResearchControls | None = None

    def runner(raw_claim: str, **kwargs: object) -> ProviderPipelineResult:
        nonlocal received_controls
        received_controls = kwargs["research_controls"]
        assert isinstance(received_controls, ResearchControls)
        return _terminal_result(str(kwargs["db_path"]), UUID(str(kwargs["run_id"])))

    controller = LiveResearchController(
        environment={"MIMO_API_KEY": SECRET, "EXA_API_KEY": "exa-test-secret"},
        runner=runner,
    )
    start = controller.start(request)
    snapshot = controller.snapshot(request.db_path, start.run_id)
    deadline = monotonic() + 2
    while snapshot.classification == "starting" and monotonic() < deadline:
        sleep(0.01)
        snapshot = controller.snapshot(request.db_path, start.run_id)

    assert start.started is True
    assert received_controls == controls
    assert snapshot.classification == "failed"


def test_worker_exception_is_redacted_from_ui_snapshot(tmp_path: Path) -> None:
    request = _request(tmp_path, run_id=uuid4())

    def runner(*args: object, **kwargs: object) -> ProviderPipelineResult:
        raise RuntimeError(f"Authorization: Bearer {SECRET}")

    controller = LiveResearchController(
        environment={"MIMO_API_KEY": SECRET, "EXA_API_KEY": "exa-test-secret"},
        runner=runner,
    )
    result = controller.start(request)
    snapshot = controller.snapshot(request.db_path, result.run_id)
    deadline = monotonic() + 2
    while snapshot.classification == "starting" and monotonic() < deadline:
        sleep(0.01)
        snapshot = controller.snapshot(request.db_path, result.run_id)

    assert snapshot.classification == "failed"
    assert SECRET not in snapshot.model_dump_json()
    assert "REDACTED" in snapshot.message


def test_history_reconnects_from_authoritative_database(tmp_path: Path) -> None:
    db_path = tmp_path / "history.sqlite3"
    init_db(str(db_path))
    now = datetime.now(UTC)
    manifest = RunManifest(
        run_id=uuid4(),
        status=RunStatus.RUNNING,
        raw_claim=CLAIM,
        current_stage=Stage.CLAIM_PLANNER,
        created_at=now,
        updated_at=now,
    )
    insert_run(str(db_path), manifest)

    controller = LiveResearchController(environment={"MIMO_API_KEY": SECRET})
    history = controller.history(db_path)

    assert len(history) == 1
    assert history[0].run_id == manifest.run_id
    assert history[0].raw_claim == CLAIM


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (ProviderRunStatus.RELEASED, CLIExitCode.RELEASED),
        (ProviderRunStatus.BLOCKED, CLIExitCode.BLOCKED),
        (ProviderRunStatus.FAILED, CLIExitCode.FAILED),
        (ProviderRunStatus.CANCELLED, CLIExitCode.CANCELLED),
        (ProviderRunStatus.RUNNING, CLIExitCode.RUNNING),
    ],
)
def test_exact_mvp4_exit_code_mapping(status: ProviderRunStatus, expected: CLIExitCode) -> None:
    assert exit_code_for_status(status) is expected


def test_redaction_covers_explicit_key_authorization_and_assignments() -> None:
    value = (
        f"{SECRET} Authorization: Bearer abc.def MIMO_API_KEY=another-secret token: final-secret"
    )
    safe = redact_text(value, secrets=(SECRET,))
    assert SECRET not in safe
    assert "abc.def" not in safe
    assert "another-secret" not in safe
    assert "final-secret" not in safe


def test_live_controller_redacts_every_provider_key_value() -> None:
    secrets = {
        "MIMO_API_KEY": "mimo-raw-secret",
        "EXA_API_KEY": "exa-raw-secret",
        "FIRECRAWL_API_KEY": "firecrawl-raw-secret",
    }
    controller = LiveResearchController(environment=secrets)

    safe = controller._redact(" ".join(secrets.values()))

    assert all(secret not in safe for secret in secrets.values())


def test_service_probe_requires_exact_wigolo_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    class HealthyAdapter:
        def __init__(self, config: object, **kwargs: object) -> None:
            pass

        def verify_health(self) -> None:
            return None

    monkeypatch.setattr(service_manager_module, "WigoloSearchAdapter", HealthyAdapter)
    assert WigoloServiceManager(base_environment={}).probe().state == "healthy"

    class WrongAdapter(HealthyAdapter):
        def verify_health(self) -> None:
            raise SearchProviderError(
                SearchFailureCode.MISSING_CONFIGURATION,
                "loopback service is not the configured Wigolo 0.2.1 instance",
            )

    monkeypatch.setattr(service_manager_module, "WigoloSearchAdapter", WrongAdapter)
    diagnostic = WigoloServiceManager(base_environment={}).probe()
    assert diagnostic.state == "wrong_service"
    assert diagnostic.wigolo_ready is False


def test_service_launch_excludes_secrets_and_stops_only_owned_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 4242
        returncode: int | None = None
        stdout = io.StringIO("")
        stderr = io.StringIO("")

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, timeout: float) -> int:
            self.returncode = 0
            return 0

    process = FakeProcess()

    def popen(command: list[str], **kwargs: object) -> FakeProcess:
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return process

    class UnhealthyAdapter:
        def __init__(self, config: object, **kwargs: object) -> None:
            pass

        def verify_health(self) -> None:
            raise SearchProviderError(
                SearchFailureCode.CONNECTION,
                "Wigolo health check could not connect to loopback service",
                retryable=True,
            )

    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(service_manager_module, "WigoloSearchAdapter", UnhealthyAdapter)
    monkeypatch.setattr(
        service_manager_module.os, "killpg", lambda pid, sig: killed.append((pid, sig))
    )
    manager = WigoloServiceManager(
        popen=popen,
        base_environment={"PATH": "/usr/bin", "HOME": "/tmp/home", "MIMO_API_KEY": SECRET},
    )

    started = manager.start()
    environment = captured["environment"]
    assert started.state == "starting"
    assert captured["command"] == ["npx", "-y", "wigolo@0.2.1", "serve"]
    assert isinstance(environment, dict)
    assert "MIMO_API_KEY" not in environment
    assert "WIGOLO_SEARCH" not in environment
    assert "SEARXNG_MODE" not in environment
    assert "EXA_API_KEY" not in environment
    assert "FIRECRAWL_API_KEY" not in environment

    stopped = manager.stop()
    assert stopped.state == "stopped"
    assert stopped.pid == process.pid
    assert killed and killed[0][0] == process.pid


def test_stop_never_kills_unowned_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        service_manager_module.os, "killpg", lambda pid, sig: killed.append((pid, sig))
    )
    stopped = WigoloServiceManager(base_environment={}).stop()
    assert stopped.message.startswith("No application-owned")
    assert killed == []


def test_live_streamlit_renders_friendly_missing_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamlit.testing.v1 import AppTest

    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setenv("RESEARCHASSISTANT_DISABLE_KEYCHAIN", "1")
    app = AppTest.from_file(str(ROOT / "frontend" / "live_app.py"), default_timeout=10).run()

    assert not app.exception
    assert any("not configured" in error.value for error in app.error)
    assert any("Human review is required" in caption.value for caption in app.caption)
    assert all(SECRET not in element.value for element in (*app.error, *app.caption))


def test_live_streamlit_acknowledgement_does_not_deadlock_submit_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("MIMO_API_KEY", SECRET)
    monkeypatch.setenv("EXA_API_KEY", "exa-test-secret")
    monkeypatch.setattr(
        WigoloServiceManager,
        "probe",
        lambda self: ServiceDiagnostic(
            state="healthy",
            wigolo_ready=True,
            searxng_readiness="configured",
            message="Pinned Wigolo 0.2.1 is healthy.",
        ),
    )
    app = AppTest.from_file(str(ROOT / "frontend" / "live_app.py"), default_timeout=10).run()
    start = next(item for item in app.button if item.label == "Begin research")

    assert not start.disabled
    start.click().run()
    assert any("confirm" in error.value.lower() for error in app.error)


def test_live_streamlit_omits_research_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("MIMO_API_KEY", SECRET)
    monkeypatch.setenv("EXA_API_KEY", "exa-test-secret")
    monkeypatch.setattr(
        WigoloServiceManager,
        "probe",
        lambda self: ServiceDiagnostic(
            state="healthy",
            wigolo_ready=True,
            searxng_readiness="configured",
            message="Pinned Wigolo 0.2.1 is healthy.",
        ),
    )

    app = AppTest.from_file(str(ROOT / "frontend" / "live_app.py"), default_timeout=10).run()
    labels = {
        "Research depth",
        "Presentation tone",
        "Report length",
        "Focus: geographic area (optional)",
        "Focus: timeframe (optional)",
        "Focus: population (optional)",
        "Focus: analytical lens (optional)",
    }
    rendered_labels = {item.label for item in (*app.selectbox, *app.text_input)}

    assert not app.exception
    assert labels.isdisjoint(rendered_labels)
    assert "Research controls" not in (ROOT / "frontend" / "live_app.py").read_text(
        encoding="utf-8"
    )


def test_live_streamlit_uses_clean_primary_layout_and_reveals_advanced_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("MIMO_API_KEY", SECRET)
    monkeypatch.setenv("EXA_API_KEY", "exa-test-secret")
    monkeypatch.setattr(
        WigoloServiceManager,
        "probe",
        lambda self: ServiceDiagnostic(
            state="healthy",
            wigolo_ready=True,
            searxng_readiness="configured",
            message="Pinned Wigolo 0.2.1 is healthy.",
        ),
    )

    app = AppTest.from_file(str(ROOT / "frontend" / "live_app.py"), default_timeout=10).run()
    button_labels = {item.label for item in app.button}
    markdown = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert {"History", "Provider setup", "Advanced", "Begin research"} <= button_labels
    assert "Research the claim" in markdown
    source = (ROOT / "frontend" / "live_app.py").read_text(encoding="utf-8")
    assert all(
        removed not in source
        for removed in ("nature-window", "nature-sun", "nature-hill", "nature-path")
    )
    assert all(item.value != "Local services" for item in app.subheader)

    next(item for item in app.button if item.label == "Advanced").click().run()

    assert not app.exception
    assert any(item.value == "Run settings" for item in app.subheader)
    assert any(item.value == "Local services" for item in app.subheader)
    assert {"MiMo cost ceiling (USD)", "SQLite database", "Run ID (optional)"} <= {
        item.label for item in app.text_input
    }
    assert {"Token ceiling", "Physical MiMo call ceiling"} <= {
        item.label for item in app.number_input
    }


def test_live_streamlit_provider_setup_uses_password_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamlit.testing.v1 import AppTest

    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setenv("RESEARCHASSISTANT_DISABLE_KEYCHAIN", "1")
    app = AppTest.from_file(str(ROOT / "frontend" / "live_app.py"), default_timeout=10).run()

    next(item for item in app.button if item.label == "Provider setup").click().run()

    assert not app.exception
    fields = {item.label: item for item in app.text_input}
    assert {"MiMo API key", "Exa API key", "Firecrawl API key (optional)"} <= fields.keys()
    assert all(field.proto.type == field.proto.PASSWORD for field in fields.values())


def test_mocked_released_run_reconnects_in_live_streamlit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from streamlit.testing.v1 import AppTest

    db_path = tmp_path / "mocked-live-web.sqlite3"
    run_id = uuid4()
    environment = {
        **os.environ,
        "MIMO_API_KEY": SECRET,
        "EXA_API_KEY": "exa-test-secret",
        "MIMO_BASE_URL": "https://api.xiaomimimo.com/v1",
        "MIMO_MODEL": "mimo-v2.5-pro",
        "MVP4_DB_PATH": str(db_path),
        "MVP4_RUN_ID": str(run_id),
        "MVP4_MOCK_SCENARIO": "released",
        "MVP4_REPOSITORY_IDENTITY": "source-sha256:" + "a" * 64,
    }
    process = subprocess.run(
        [
            sys.executable,
            str(DRIVER),
            "run",
            CLAIM,
            "--db-path",
            str(db_path),
            "--run-id",
            str(run_id),
            "--max-tokens",
            "1000000",
            "--max-cost-usd",
            "1.00",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert process.returncode == CLIExitCode.RELEASED
    assert SECRET not in process.stdout + process.stderr + db_path.read_bytes().decode(
        "utf-8", errors="ignore"
    )

    snapshot = LiveResearchController(environment={}).snapshot(db_path, run_id)
    assert snapshot.supporting.model_attempts > 0
    assert snapshot.opposing.model_attempts > 0

    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.setenv("RESEARCHASSISTANT_DISABLE_KEYCHAIN", "1")
    app = AppTest.from_file(str(ROOT / "frontend" / "live_app.py"), default_timeout=10).run()
    next(item for item in app.button if item.label == "History").click().run()
    history_input = next(item for item in app.text_input if item.label == "History database")
    history_input.input(str(db_path)).run()
    open_button = next(item for item in app.button if item.label == "Open run")
    open_button.click().run()

    assert not app.exception
    assert any("Released after deterministic validation" in item.value for item in app.success)
    assert any(item.value == "Validated final brief" for item in app.subheader)
    assert any(item.label == "Download brief" for item in app.get("download_button"))
    rendered = "\n".join(item.value for item in (*app.error, *app.warning, *app.success))
    assert SECRET not in rendered
