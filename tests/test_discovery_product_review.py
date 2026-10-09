"""Independent product-boundary regressions for Phase 6 discovery controls."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from frontend.api import ApiRuntime, create_app
from frontend.live_contracts import LiveRunRequest
from frontend.service_manager import ServiceDiagnostic
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchControls,
    ResearchDirections,
)
from researchassistant.research.v2_orchestrator import run_v2_production_pipeline
from researchassistant.runtime.application_runtime import CLIExitCode
from researchassistant.runtime.cli import _build_parser, _run_live_command


class _StartController:
    def __init__(self) -> None:
        self.requests: list[LiveRunRequest] = []

    def start(self, request: LiveRunRequest) -> Any:
        self.requests.append(request)
        run_id = request.run_id or uuid4()
        return {
            "started": True,
            "run_id": str(run_id),
            "classification": "starting",
            "message": "Research started.",
        }


class _UnusedServices:
    def probe(self) -> ServiceDiagnostic:
        return ServiceDiagnostic(
            state="stopped",
            wigolo_ready=False,
            searxng_readiness="unavailable",
            message="Offline test fixture.",
        )

    def owns_running_process(self) -> bool:
        return False


def _start_client() -> tuple[TestClient, _StartController]:
    controller = _StartController()
    runtime = ApiRuntime(
        controller=controller,
        services=_UnusedServices(),
        environment={},
    )
    app = create_app(
        runtime,
        load_keychain_on_start=False,
        allowed_hosts=("testserver",),
    )
    return TestClient(app), controller


def test_start_endpoint_accepts_product_settings_and_defaults_old_clients(
    tmp_path: Path,
) -> None:
    client, controller = _start_client()
    base: dict[str, object] = {
        "raw_claim": "A public claim",
        "acknowledged_public": True,
        "db_path": str(tmp_path / "live.sqlite3"),
        "use_serpsearch": False,
        "use_exa": False,
        "use_openalex": True,
    }

    old_client = client.post("/api/research/start", json=base)
    configured = client.post(
        "/api/research/start",
        json={
            **base,
            "metadata_depth": 50,
            "seed_expansion_enabled": False,
            "scholarly_search_mode": "semantic",
        },
    )

    assert old_client.status_code == 200
    assert configured.status_code == 200
    assert controller.requests[0].research_controls.metadata_depth == 20
    assert controller.requests[0].research_controls.seed_expansion_enabled is True
    assert controller.requests[0].research_controls.scholarly_search_mode == "lexical"
    assert controller.requests[1].research_controls.metadata_depth == 50
    assert controller.requests[1].research_controls.seed_expansion_enabled is False
    assert controller.requests[1].research_controls.scholarly_search_mode == "semantic"
    assert controller.requests[1].research_controls.discovery_providers == (
        DiscoveryProvider.OPENALEX,
    )


def test_direct_v2_api_rejects_semantic_mode_without_openalex_before_transport(
    tmp_path: Path,
) -> None:
    controls = ResearchControls(
        metadata_depth=50,
        seed_expansion_enabled=False,
        scholarly_search_mode="semantic",
        discovery_providers=(DiscoveryProvider.EXA,),
    )

    with pytest.raises(ValueError, match="requires OpenAlex"):
        run_v2_production_pipeline(
            "A public claim",
            db_path=tmp_path / "direct.sqlite3",
            directions=ResearchDirections(),
            discovery_providers=(DiscoveryProvider.EXA,),
            search_providers={},
            wigolo_provider=None,
            llm_provider=None,
            routing_config=None,
            research_controls=controls,
        )


def test_cli_parses_product_controls_and_rejects_them_at_legacy_runner_boundary(
    tmp_path: Path,
) -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "run",
            "A public claim",
            "--db-path",
            str(tmp_path / "legacy.sqlite3"),
            "--max-tokens",
            "1000",
            "--metadata-depth",
            "50",
            "--no-seed-expansion",
            "--scholarly-search-mode",
            "semantic",
        ]
    )
    legacy_calls: list[Mapping[str, object]] = []

    def legacy_runner(*_args: object, **kwargs: object) -> object:
        legacy_calls.append(kwargs)
        return object()

    result = _run_live_command(
        args,
        environment={},
        legacy_runner=legacy_runner,
        identity_provider=lambda: "offline-review",
    )

    assert result == CLIExitCode.INVALID_INPUT
    assert legacy_calls == []


def test_controls_keep_historical_settings_absent_when_unrecorded() -> None:
    controls = ResearchControls(discovery_providers=(DiscoveryProvider.OPENALEX,))

    assert controls.model_dump(mode="json").get("metadata_depth") is None
    assert controls.canonical_json().find("metadata_depth") == -1
