"""Unchanged request and response contracts for the local HTTP boundary."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator

from researchassistant.api.constants import API_VERSION
from researchassistant.api.live_service import LiveHistoryItem
from researchassistant.api.service_manager import ServiceDiagnostic
from researchassistant.contracts.models import ResearchDirections, StrictModel
from researchassistant.platform_support.credential_store import ProviderCredentials
from researchassistant.providers.model_choices import (
    CONFIGURABLE_PROFILE_ID,
    DEFAULT_STAGE_MODELS,
    StageModelSelections,
)
from researchassistant.providers.model_profiles import ProfileId


class ApiHealth(StrictModel):
    status: str = "ok"
    product: str = "ResearchAssistant"
    api_version: str = API_VERSION


class ConfigurationResponse(StrictModel):
    configured: bool
    message: str
    default_db_path: str = Field(min_length=1)
    firecrawl_enabled: bool
    saved_credentials: tuple[str, ...] = ()
    saved_settings: tuple[str, ...] = ()
    service: ServiceDiagnostic


class ConfigurationCheckInput(StrictModel):
    """Typed offline setup check for a selected model mix and source lanes."""

    model_profile: ProfileId = CONFIGURABLE_PROFILE_ID
    stage_models: StageModelSelections = DEFAULT_STAGE_MODELS
    use_serpsearch: bool = True
    use_exa: bool = True
    use_openalex: bool = True
    use_arxiv: bool = False
    use_pubmed: bool = False


class ConnectionCheckInput(StrictModel):
    """The exact model selection whose account access should be checked."""

    model_profile: ProfileId
    stage_models: StageModelSelections


class CredentialSetupRequest(StrictModel):
    model_profile: ProfileId = CONFIGURABLE_PROFILE_ID
    stage_models: StageModelSelections = DEFAULT_STAGE_MODELS
    mimo_api_key: SecretStr | None = None
    luna_api_key: SecretStr | None = None
    luna_base_url: str | None = None
    luna_model: str | None = None
    mimo_v25_input_usd_per_million: Decimal | None = Field(default=None, gt=0)
    mimo_v25_output_usd_per_million: Decimal | None = Field(default=None, gt=0)
    luna_input_usd_per_million: Decimal | None = Field(default=None, gt=0)
    luna_output_usd_per_million: Decimal | None = Field(default=None, gt=0)
    exa_api_key: SecretStr | None = None
    openalex_api_key: SecretStr | None = None
    serpsearch_api_key: SecretStr | None = None
    pubmed_api_key: SecretStr | None = None
    firecrawl_api_key: SecretStr | None = None

    @field_validator(
        "mimo_api_key",
        "luna_api_key",
        "exa_api_key",
        "openalex_api_key",
        "serpsearch_api_key",
        "pubmed_api_key",
        "firecrawl_api_key",
        "luna_model",
        mode="before",
    )
    @classmethod
    def validate_single_line_value(cls, value: object) -> object:
        return ProviderCredentials.validate_provider_value(value)

    @field_validator("luna_base_url")
    @classmethod
    def validate_luna_base_url(cls, value: str | None) -> str | None:
        if value is not None and "platform.openai.com" in value.casefold():
            raise ValueError(
                "Use the OpenAI API endpoint https://api.openai.com/v1, not the OpenAI "
                "dashboard URL."
            )
        return ProviderCredentials.validate_luna_base_url(value)


class CredentialSetupResponse(StrictModel):
    saved: bool
    configured: bool
    message: str = Field(min_length=1)
    saved_settings: tuple[str, ...] = ()


class ResearchStartInput(StrictModel):
    model_profile: ProfileId = CONFIGURABLE_PROFILE_ID
    stage_models: StageModelSelections = DEFAULT_STAGE_MODELS
    raw_claim: str = Field(min_length=1)
    acknowledged_public: bool
    db_path: str | None = None
    run_id: UUID | None = None
    max_tokens: int = Field(default=500_000, ge=1, le=500_000)
    max_cost_usd: Decimal = Field(default=Decimal("0.20"), gt=0, le=Decimal("20.00"))
    max_llm_calls: int = Field(default=160, ge=1, le=160)
    support_enabled: bool = True
    challenge_enabled: bool = False
    include_counterevidence: bool = False
    sources_per_stance_per_round: Literal[5, 10, 15, 20] = 10
    use_serpsearch: bool = True
    use_exa: bool = True
    use_openalex: bool = True
    use_arxiv: bool = False
    use_pubmed: bool = False
    use_crossref: bool = True
    metadata_depth: Literal[10, 20, 50] = 20
    seed_expansion_enabled: bool = Field(default=True, strict=True)
    scholarly_search_mode: Literal["lexical", "semantic", "auto"] = "lexical"

    @model_validator(mode="after")
    def validate_research_directions(self) -> ResearchStartInput:
        if not self.support_enabled and not (
            self.challenge_enabled or self.include_counterevidence
        ):
            raise ValueError("Enable Support, Challenge, or both research directions.")
        if self.scholarly_search_mode == "semantic" and not self.use_openalex:
            raise ValueError("Meaning based scholarly search requires OpenAlex to be selected.")
        return self

    def directions(self) -> ResearchDirections:
        """Resolve the legacy counterevidence control without changing old clients."""
        return ResearchDirections(
            support_enabled=self.support_enabled,
            challenge_enabled=self.challenge_enabled or self.include_counterevidence,
        )


class RunLocator(StrictModel):
    db_path: str = Field(min_length=1)


class CancelResponse(StrictModel):
    cancelled: bool = True
    message: str = Field(min_length=1)


class HistoryResponse(StrictModel):
    items: tuple[LiveHistoryItem, ...]
