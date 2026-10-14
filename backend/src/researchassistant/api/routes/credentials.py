"""Credentials HTTP routes; application dependencies are supplied by assembly."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from researchassistant.api.application_services.configuration import (
    _per_token_price,
    _saved_setting_names,
    _selected_discovery_providers,
)
from researchassistant.api.constants import CREDENTIAL_ACCESS_MESSAGE
from researchassistant.api.dependencies import ApiDependencies
from researchassistant.api.http_contracts import (
    ConnectionCheckInput,
    CredentialSetupRequest,
    CredentialSetupResponse,
)
from researchassistant.api.provider_connections import ConnectionCheck
from researchassistant.api.runtime import ApiRuntime
from researchassistant.api.security import redact_text
from researchassistant.platform_support.credential_store import (
    KeychainUnavailableError,
    ProviderCredentials,
)
from researchassistant.providers.model_choices import CONFIGURABLE_PROFILE_ID, DEFAULT_STAGE_MODELS


def build_router(runtime: ApiRuntime, dependencies: ApiDependencies) -> APIRouter:
    router = APIRouter()

    @router.post("/api/credentials/{name}/check", response_model=ConnectionCheck)
    def validate_connection(
        name: str, payload: ConnectionCheckInput | None = None
    ) -> ConnectionCheck:
        try:
            if payload is None:
                try:
                    interface = dependencies.read_preferences().interface
                    payload = ConnectionCheckInput(
                        model_profile=interface.modelProfile,
                        stage_models=interface.stageModels,
                    )
                except (OSError, ValueError, RuntimeError):
                    if name in ("mimo", "openai"):
                        return ConnectionCheck(
                            provider=name,
                            state="unavailable",
                            message=(
                                "Saved model selections could not be read. Review your settings."
                            ),
                        )
                    payload = ConnectionCheckInput(
                        model_profile=CONFIGURABLE_PROFILE_ID,
                        stage_models=DEFAULT_STAGE_MODELS,
                    )
            return dependencies.check_connection(
                name,
                runtime.environment,
                model_profile=payload.model_profile,
                stage_models=payload.stage_models,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Unknown provider.") from exc

    @router.post("/api/credentials/{name}/remove")
    def delete_credential(name: str) -> dict[str, bool]:
        with runtime.lifecycle.idle_change(
            runtime.controller.has_active_runs, message="Wait for active research to finish."
        ):
            try:
                dependencies.remove_credential(name)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="Unknown provider credential.") from exc
            except KeychainUnavailableError as exc:
                raise HTTPException(
                    status_code=503, detail="Credential vault is unavailable."
                ) from exc
            runtime.environment.pop(name, None)
        return {"removed": True}

    @router.post("/api/credentials", response_model=CredentialSetupResponse)
    def store_credentials(
        payload: CredentialSetupRequest,
        use_serpsearch: bool = True,
        use_exa: bool = True,
        use_openalex: bool = True,
        use_arxiv: bool = False,
        use_pubmed: bool = False,
    ) -> CredentialSetupResponse:
        with runtime.lifecycle.idle_change(
            runtime.controller.has_active_runs, message="Wait for active research to finish."
        ):
            if not any(
                (
                    payload.mimo_api_key,
                    payload.luna_api_key,
                    payload.luna_base_url,
                    payload.luna_model,
                    payload.mimo_v25_input_usd_per_million,
                    payload.mimo_v25_output_usd_per_million,
                    payload.luna_input_usd_per_million,
                    payload.luna_output_usd_per_million,
                    payload.serpsearch_api_key,
                    payload.exa_api_key,
                    payload.openalex_api_key,
                    payload.firecrawl_api_key,
                    payload.pubmed_api_key,
                )
            ):
                raise HTTPException(status_code=422, detail="Enter at least one API key to save.")
            credentials = ProviderCredentials(
                mimo_api_key=(
                    payload.mimo_api_key.get_secret_value()
                    if payload.mimo_api_key is not None
                    else None
                ),
                luna_api_key=(
                    payload.luna_api_key.get_secret_value()
                    if payload.luna_api_key is not None
                    else None
                ),
                luna_base_url=payload.luna_base_url,
                luna_model=payload.luna_model,
                mimo_v25_input_usd_per_token=_per_token_price(
                    payload.mimo_v25_input_usd_per_million
                ),
                mimo_v25_output_usd_per_token=_per_token_price(
                    payload.mimo_v25_output_usd_per_million
                ),
                luna_input_usd_per_token=_per_token_price(payload.luna_input_usd_per_million),
                luna_output_usd_per_token=_per_token_price(payload.luna_output_usd_per_million),
                exa_api_key=(
                    payload.exa_api_key.get_secret_value()
                    if payload.exa_api_key is not None
                    else None
                ),
                openalex_api_key=(
                    payload.openalex_api_key.get_secret_value()
                    if payload.openalex_api_key is not None
                    else None
                ),
                serpsearch_api_key=(
                    payload.serpsearch_api_key.get_secret_value()
                    if payload.serpsearch_api_key is not None
                    else None
                ),
                pubmed_api_key=(
                    payload.pubmed_api_key.get_secret_value()
                    if payload.pubmed_api_key is not None
                    else None
                ),
                firecrawl_api_key=(
                    payload.firecrawl_api_key.get_secret_value()
                    if payload.firecrawl_api_key is not None
                    else None
                ),
            )
            try:
                runtime.credential_saver(credentials)
                runtime.credential_applier(credentials, runtime.environment)
                runtime.credential_error = None
            except KeychainUnavailableError as exc:
                raise HTTPException(status_code=503, detail=CREDENTIAL_ACCESS_MESSAGE) from exc
        discovery_providers = _selected_discovery_providers(
            use_serpsearch=use_serpsearch,
            use_exa=use_exa,
            use_openalex=use_openalex,
            use_arxiv=use_arxiv,
            use_pubmed=use_pubmed,
        )
        config_message = runtime.controller.configuration_message(
            discovery_providers=discovery_providers,
            model_profile=payload.model_profile,
            stage_models=payload.stage_models,
        )
        return CredentialSetupResponse(
            saved=True,
            configured=config_message is None,
            message=(
                "Provider keys saved securely in the operating system credential vault."
                if config_message is None
                else "Provider keys saved securely in the operating system credential vault. "
                + redact_text(config_message)
            ),
            saved_settings=_saved_setting_names(runtime.environment),
        )

    return router
