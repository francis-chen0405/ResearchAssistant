"""Offline configuration diagnostics and presence-only settings projection."""

from __future__ import annotations

from collections.abc import MutableMapping
from decimal import Decimal, localcontext

from researchassistant.api.dependencies import ApiDependencies
from researchassistant.api.http_contracts import (
    ConfigurationCheckInput,
    ConfigurationResponse,
    ModelOptionDisplay,
    ModelOptionsResponse,
)
from researchassistant.api.runtime import ApiRuntime
from researchassistant.api.security import redact_text
from researchassistant.contracts.models import DiscoveryProvider
from researchassistant.providers.model_choices import (
    CONFIGURABLE_PROFILE_ID,
    DEFAULT_STAGE_MODELS,
    model_options_payload,
)
from researchassistant.providers.model_profiles import (
    STANDARD_PROFILE,
    ProfileId,
    profile_environment,
)
from researchassistant.providers.v2_factory import V2ProductionFactoryConfig
from researchassistant.runtime.application_runtime import repository_identity


def _selected_discovery_providers(
    *,
    use_serpsearch: bool,
    use_exa: bool,
    use_openalex: bool,
    use_arxiv: bool,
    use_pubmed: bool,
) -> tuple[DiscoveryProvider, ...]:
    """Resolve website provider switches in the canonical provider order."""
    return tuple(
        provider
        for provider, enabled in (
            (DiscoveryProvider.SERPSEARCH, use_serpsearch),
            (DiscoveryProvider.EXA, use_exa),
            (DiscoveryProvider.OPENALEX, use_openalex),
            (DiscoveryProvider.ARXIV, use_arxiv),
            (DiscoveryProvider.PUBMED, use_pubmed),
        )
        if enabled
    )


def _saved_credential_names(environment: MutableMapping[str, str]) -> tuple[str, ...]:
    """Expose presence only; browser clients never receive credential values."""
    labels = (
        ("mimo", "MIMO_API_KEY"),
        ("openai", "LUNA_API_KEY"),
        ("serpsearch", "SERPSEARCH_API_KEY"),
        ("exa", "EXA_API_KEY"),
        ("openalex", "OPENALEX_API_KEY"),
        ("pubmed", "PUBMED_API_KEY"),
        ("firecrawl", "FIRECRAWL_API_KEY"),
    )
    return tuple(label for label, key in labels if environment.get(key, "").strip())


def _per_token_price(value: Decimal | None) -> str | None:
    """Convert the user-facing USD-per-million price into the strict route unit."""
    if value is None:
        return None
    with localcontext() as context:
        context.prec = max(28, len(value.as_tuple().digits))
        return format(value / Decimal("1000000"), "f")


def _saved_setting_names(environment: MutableMapping[str, str]) -> tuple[str, ...]:
    """Expose non-secret route-setting presence for the local setup checklist."""
    labels = (
        ("MiMo input price", "MIMO_V25_INPUT_USD_PER_TOKEN"),
        ("MiMo output price", "MIMO_V25_OUTPUT_USD_PER_TOKEN"),
        ("Luna input price", "LUNA_INPUT_USD_PER_TOKEN"),
        ("Luna output price", "LUNA_OUTPUT_USD_PER_TOKEN"),
        ("Luna API base URL", "LUNA_BASE_URL"),
        ("Luna model ID", "LUNA_MODEL"),
    )
    return tuple(label for label, key in labels if environment.get(key, "").strip())


def model_options() -> ModelOptionsResponse:
    """Return the selectable per-stage model catalog and defaults."""
    payload = model_options_payload()
    return ModelOptionsResponse(
        choices=tuple(
            ModelOptionDisplay(
                id=choice.id,
                label=choice.label,
                provider=choice.provider,
                input_per_million=choice.input_per_million,
                output_per_million=choice.output_per_million,
            )
            for choice in payload.choices
        ),
        defaults=payload.defaults,
    )


def configuration(
    runtime: ApiRuntime,
    dependencies: ApiDependencies,
    model_profile: ProfileId | None = None,
    use_serpsearch: bool = True,
    use_exa: bool = True,
    use_openalex: bool = True,
    use_arxiv: bool = False,
    use_pubmed: bool = False,
) -> ConfigurationResponse:
    discovery_providers = _selected_discovery_providers(
        use_serpsearch=use_serpsearch,
        use_exa=use_exa,
        use_openalex=use_openalex,
        use_arxiv=use_arxiv,
        use_pubmed=use_pubmed,
    )
    selected_profile = model_profile
    current_stage_models = DEFAULT_STAGE_MODELS
    config_message: str | None = None
    if selected_profile != STANDARD_PROFILE.id:
        try:
            saved_interface = dependencies.read_preferences().interface
            selected_profile = selected_profile or saved_interface.modelProfile
            current_stage_models = saved_interface.stageModels
        except (OSError, ValueError, RuntimeError):
            config_message = "Saved model selections could not be read. Review your settings."
    if config_message is None:
        selected_stage_models = (
            current_stage_models if selected_profile == CONFIGURABLE_PROFILE_ID else None
        )
        config_message = runtime.controller.configuration_message(
            discovery_providers=discovery_providers,
            model_profile=selected_profile,
            stage_models=current_stage_models,
        )
        try:
            V2ProductionFactoryConfig.from_environment(
                profile_environment(
                    runtime.environment,
                    selected_profile,
                    stage_models=selected_stage_models,
                ),
                repository_revision=repository_identity(),
                discovery_providers=discovery_providers,
                stage_models=selected_stage_models,
            )
            config_message = None
        except (ValueError, RuntimeError) as exc:
            config_message = redact_text(exc)
    return ConfigurationResponse(
        configured=config_message is None and runtime.credential_error is None,
        message=(
            runtime.credential_error
            or config_message
            or "MiMo and your selected research sources are configured; credentials are "
            "checked when research starts."
        ),
        default_db_path=str(dependencies.prepare_default_database()),
        firecrawl_enabled=bool(runtime.environment.get("FIRECRAWL_API_KEY", "").strip()),
        saved_credentials=_saved_credential_names(runtime.environment),
        saved_settings=_saved_setting_names(runtime.environment),
        service=runtime.services.probe(),
    )


def configuration_check(
    runtime: ApiRuntime, dependencies: ApiDependencies, payload: ConfigurationCheckInput
) -> ConfigurationResponse:
    """Check selected model routes and enabled source credentials without a call."""
    discovery_providers = _selected_discovery_providers(
        use_serpsearch=payload.use_serpsearch,
        use_exa=payload.use_exa,
        use_openalex=payload.use_openalex,
        use_arxiv=payload.use_arxiv,
        use_pubmed=payload.use_pubmed,
    )
    selected_stage_models = (
        payload.stage_models if payload.model_profile == CONFIGURABLE_PROFILE_ID else None
    )
    config_message = runtime.controller.configuration_message(
        discovery_providers=discovery_providers,
        model_profile=payload.model_profile,
        stage_models=payload.stage_models,
    )
    try:
        V2ProductionFactoryConfig.from_environment(
            profile_environment(
                runtime.environment,
                payload.model_profile,
                stage_models=selected_stage_models,
            ),
            repository_revision=repository_identity(),
            discovery_providers=discovery_providers,
            stage_models=selected_stage_models,
        )
        config_message = None
    except (ValueError, RuntimeError) as exc:
        config_message = redact_text(exc)
    return ConfigurationResponse(
        configured=config_message is None and runtime.credential_error is None,
        message=(
            runtime.credential_error
            or config_message
            or "Selected models and research sources are configured; credentials are "
            "checked when research starts."
        ),
        default_db_path=str(dependencies.prepare_default_database()),
        firecrawl_enabled=bool(runtime.environment.get("FIRECRAWL_API_KEY", "").strip()),
        saved_credentials=_saved_credential_names(runtime.environment),
        saved_settings=_saved_setting_names(runtime.environment),
        service=runtime.services.probe(),
    )
