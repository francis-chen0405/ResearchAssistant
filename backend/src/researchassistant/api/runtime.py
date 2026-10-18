"""Explicit application services and the shared lifecycle coordinator."""

from __future__ import annotations

import os
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Protocol
from uuid import UUID

from researchassistant.api.live_lifecycle import LifecycleCoordinator
from researchassistant.api.live_service import (
    LiveHistoryItem,
    LiveResearchController,
    LiveRunRequest,
    LiveRunSnapshot,
    LiveStartResult,
    ResearchTrail,
)
from researchassistant.api.service_manager import ServiceDiagnostic, WigoloServiceManager
from researchassistant.contracts.models import DiscoveryProvider
from researchassistant.platform_support.credential_store import (
    ProviderCredentials,
    apply_credentials_to_environment,
    load_saved_credentials_into_environment,
    save_credentials,
)
from researchassistant.providers.model_choices import DEFAULT_STAGE_MODELS, StageModelSelections
from researchassistant.providers.model_profiles import ProfileId


class ControllerBoundary(Protocol):
    def shutdown(self, *, timeout: float = 90) -> bool: ...

    def configuration_message(
        self,
        *,
        discovery_providers: tuple[DiscoveryProvider, ...] | None = None,
        model_profile: ProfileId | None = None,
        stage_models: StageModelSelections = DEFAULT_STAGE_MODELS,
    ) -> str | None: ...

    def start(self, request: LiveRunRequest) -> LiveStartResult: ...

    def snapshot(self, db_path: str | Path, run_id: UUID) -> LiveRunSnapshot: ...

    def cancel(self, db_path: str | Path, run_id: UUID) -> str: ...

    def history(self, db_path: str | Path, *, limit: int = 100) -> tuple[LiveHistoryItem, ...]: ...

    def research_trail(self, db_path: str | Path, run_id: UUID) -> ResearchTrail: ...

    def has_active_runs(self) -> bool: ...


class ServiceBoundary(Protocol):
    def probe(self) -> ServiceDiagnostic: ...

    def start(self) -> ServiceDiagnostic: ...

    def stop(self) -> ServiceDiagnostic: ...

    def owns_running_process(self) -> bool: ...


class ApiRuntime:
    """Explicit application-owned services and secret boundaries."""

    def __init__(
        self,
        *,
        controller: ControllerBoundary,
        services: ServiceBoundary,
        environment: MutableMapping[str, str],
        credential_saver: Callable[[ProviderCredentials], None] = save_credentials,
        credential_applier: Callable[
            [ProviderCredentials, MutableMapping[str, str] | None], None
        ] = apply_credentials_to_environment,
        credential_loader: Callable[[MutableMapping[str, str] | None], bool] = (
            load_saved_credentials_into_environment
        ),
    ) -> None:
        self.credential_error: str | None = None
        self.controller = controller
        self.lifecycle = (
            controller.lifecycle
            if isinstance(controller, LiveResearchController)
            else LifecycleCoordinator()
        )
        self.services = services
        self.environment = environment
        self.credential_saver = credential_saver
        self.credential_applier = credential_applier
        self.credential_loader = credential_loader


def create_default_runtime() -> ApiRuntime:
    environment = os.environ
    controller = LiveResearchController(environment=environment)
    services = WigoloServiceManager(base_environment=environment)
    return ApiRuntime(controller=controller, services=services, environment=environment)
