"""Settings HTTP routes; application dependencies are supplied by assembly."""

from __future__ import annotations

from fastapi import APIRouter

from researchassistant.api.application_services import configuration as configuration_service
from researchassistant.api.dependencies import ApiDependencies
from researchassistant.api.http_contracts import (
    ConfigurationCheckInput,
    ConfigurationResponse,
)
from researchassistant.api.runtime import ApiRuntime
from researchassistant.platform_support.desktop_settings import InterfaceSettings
from researchassistant.providers.model_profiles import (
    CONFIGURABLE_PROFILE,
    STANDARD_PROFILE,
    ModelProfile,
    ProfileId,
)


def build_router(runtime: ApiRuntime, dependencies: ApiDependencies) -> APIRouter:
    router = APIRouter()

    @router.get("/api/preferences", response_model=InterfaceSettings)
    def preferences() -> InterfaceSettings:
        return dependencies.read_preferences().interface

    @router.post("/api/preferences", response_model=InterfaceSettings)
    def save_preferences(payload: InterfaceSettings) -> InterfaceSettings:
        return dependencies.update_preferences(interface=payload).interface

    @router.get("/api/model-profiles", response_model=tuple[ModelProfile, ...])
    def model_profiles() -> tuple[ModelProfile, ...]:
        return (STANDARD_PROFILE, CONFIGURABLE_PROFILE)

    @router.get("/api/model-options")
    def model_options() -> dict[str, object]:
        """Return the selectable per-stage model catalog and defaults."""
        return configuration_service.model_options()

    @router.get("/api/configuration", response_model=ConfigurationResponse)
    def configuration(
        model_profile: ProfileId | None = None,
        use_serpsearch: bool = True,
        use_exa: bool = True,
        use_openalex: bool = True,
        use_arxiv: bool = False,
        use_pubmed: bool = False,
    ) -> ConfigurationResponse:
        return configuration_service.configuration(
            runtime,
            dependencies,
            model_profile=model_profile,
            use_serpsearch=use_serpsearch,
            use_exa=use_exa,
            use_openalex=use_openalex,
            use_arxiv=use_arxiv,
            use_pubmed=use_pubmed,
        )

    @router.post("/api/configuration/check", response_model=ConfigurationResponse)
    def configuration_check(payload: ConfigurationCheckInput) -> ConfigurationResponse:
        """Check selected model routes and enabled source credentials without a call."""
        return configuration_service.configuration_check(runtime, dependencies, payload)

    return router
