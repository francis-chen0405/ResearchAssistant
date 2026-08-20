"""Strict MVP-2B provider configuration with secret-safe representations."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, SecretStr, field_validator

from models import StrictModel
from money import ExactUSD


class ProviderConfigurationError(RuntimeError):
    """Raised before a live call when provider configuration is invalid."""


class DeadlineConfig(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    health_seconds: float = Field(default=2.0, gt=0, le=2.0)
    startup_seconds: float = Field(default=60.0, gt=0, le=60.0)
    search_seconds: float = Field(default=15.0, gt=0, le=15.0)
    html_fetch_seconds: float = Field(default=15.0, gt=0, le=15.0)
    pdf_fetch_seconds: float = Field(default=30.0, gt=0, le=30.0)
    browser_fetch_seconds: float = Field(default=25.0, gt=0, le=25.0)
    planner_seconds: float = Field(default=90.0, gt=0, le=90.0)
    scout_seconds: float = Field(default=90.0, gt=0, le=180.0)
    gap_analysis_seconds: float = Field(default=120.0, gt=0, le=180.0)
    search_agent_seconds: float = Field(default=90.0, gt=0, le=180.0)
    source_selection_seconds: float = Field(default=90.0, gt=0, le=180.0)
    extractor_seconds: float = Field(default=180.0, gt=0, le=180.0)
    analyst_seconds: float = Field(default=120.0, gt=0, le=120.0)
    reviewer_seconds: float = Field(default=90.0, gt=0, le=90.0)
    synthesizer_seconds: float = Field(default=180.0, gt=0, le=180.0)


class RunCeilings(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_cost_usd: Annotated[ExactUSD, Field(gt=Decimal("0"), le=Decimal("1.00"))] = Decimal("1.00")
    max_tokens: int = Field(default=1_000_000, ge=1, le=1_000_000)
    max_llm_calls: int = Field(default=160, ge=1, le=160)


class WigoloConfig(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: str = "wigolo"
    provider_version: str = "0.2.1"
    adapter_version: str = "mvp3b-wigolo-v3"
    base_url: str = "http://127.0.0.1:8000"
    reranker: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    max_redirects: int = Field(default=5, ge=0, le=5)
    max_html_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=10 * 1024 * 1024)
    max_pdf_bytes: int = Field(default=25 * 1024 * 1024, ge=1, le=25 * 1024 * 1024)
    max_pdf_pages: int = Field(default=100, ge=1, le=100)
    deadlines: DeadlineConfig = DeadlineConfig()

    @field_validator("base_url")
    @classmethod
    def validate_loopback(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Wigolo must use an HTTP loopback address")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Wigolo base URL cannot contain credentials, query, or fragment")
        return value.rstrip("/")


class ExaConfig(StrictModel):
    """Required Exa discovery configuration for new live runs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: Literal["exa"] = "exa"
    adapter_version: Literal["post-mvp5-exa-search-v1"] = "post-mvp5-exa-search-v1"
    base_url: str = "https://api.exa.ai"
    api_key: SecretStr
    search_type: Literal["auto"] = "auto"
    deadlines: DeadlineConfig = DeadlineConfig()

    @field_validator("base_url")
    @classmethod
    def validate_https(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Exa base URL must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Exa base URL cannot contain credentials, query, or fragment")
        return value.rstrip("/")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> ExaConfig:
        api_key = environment.get("EXA_API_KEY", "").strip()
        if not api_key:
            raise ProviderConfigurationError(
                "EXA_API_KEY is required in the explicitly supplied environment"
            )
        return cls(
            api_key=SecretStr(api_key),
            base_url=environment.get("EXA_BASE_URL", "https://api.exa.ai").strip(),
        )


class OpenAlexConfig(StrictModel):
    """Required OpenAlex scholarly-discovery configuration for MLP-4 runs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: Literal["openalex"] = "openalex"
    provider_version: Literal["works-api"] = "works-api"
    adapter_version: Literal["mlp4-openalex-works-v1"] = "mlp4-openalex-works-v1"
    base_url: str = "https://api.openalex.org"
    api_key: SecretStr
    max_search_calls_per_run: Literal[10] = 10
    max_search_cost_usd_per_run: Annotated[
        ExactUSD,
        Field(gt=Decimal("0"), le=Decimal("0.01")),
    ] = Decimal("0.01")
    nominal_search_cost_usd: Annotated[
        ExactUSD,
        Field(gt=Decimal("0"), le=Decimal("0.001")),
    ] = Decimal("0.001")
    deadlines: DeadlineConfig = DeadlineConfig()

    @field_validator("base_url")
    @classmethod
    def validate_https(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("OpenAlex base URL must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("OpenAlex base URL cannot contain credentials, query, or fragment")
        return value.rstrip("/")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> OpenAlexConfig:
        api_key = environment.get("OPENALEX_API_KEY", "").strip()
        if not api_key:
            raise ProviderConfigurationError(
                "OPENALEX_API_KEY is required in the explicitly supplied environment"
            )
        return cls(
            api_key=SecretStr(api_key),
            base_url=environment.get("OPENALEX_BASE_URL", "https://api.openalex.org").strip(),
        )


class SerpSearchConfig(StrictModel):
    """Strict Google-style SERP Search discovery configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: Literal["serpsearch"] = "serpsearch"
    provider_version: Literal["google-search-api-v1"] = "google-search-api-v1"
    adapter_version: Literal["mlp5-serpsearch-v1"] = "mlp5-serpsearch-v1"
    base_url: str = "https://api.serpsearch.com"
    api_key: SecretStr
    max_search_calls_per_run: Literal[12] = 12
    deadlines: DeadlineConfig = DeadlineConfig()

    @field_validator("base_url")
    @classmethod
    def validate_https(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("SERP Search base URL must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("SERP Search base URL cannot contain credentials, query, or fragment")
        return value.rstrip("/")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> SerpSearchConfig:
        api_key = environment.get("SERPSEARCH_API_KEY", "").strip()
        if not api_key:
            raise ProviderConfigurationError(
                "SERPSEARCH_API_KEY is required when SERP Search is enabled"
            )
        return cls(
            api_key=SecretStr(api_key),
            base_url=environment.get("SERPSEARCH_BASE_URL", "https://api.serpsearch.com").strip(),
        )


class FirecrawlConfig(StrictModel):
    """Optional Firecrawl acquisition-fallback configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: Literal["firecrawl"] = "firecrawl"
    provider_version: Literal["v2"] = "v2"
    adapter_version: Literal["mvp6.9-firecrawl-media-provenance-v3"] = (
        "mvp6.9-firecrawl-media-provenance-v3"
    )
    base_url: str = "https://api.firecrawl.dev"
    api_key: SecretStr
    deadlines: DeadlineConfig = DeadlineConfig()

    @field_validator("base_url")
    @classmethod
    def validate_https(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Firecrawl base URL must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Firecrawl base URL cannot contain credentials, query, or fragment")
        return value.rstrip("/")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> FirecrawlConfig | None:
        api_key = environment.get("FIRECRAWL_API_KEY", "").strip()
        if not api_key:
            return None
        return cls(
            api_key=SecretStr(api_key),
            base_url=environment.get("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev").strip(),
        )


class MimoConfig(StrictModel):
    """Strict direct Xiaomi MiMo configuration for MVP-3B."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: Literal["xiaomi-mimo"] = "xiaomi-mimo"
    adapter_version: Literal["mlp4-relaxed-evidence-yield-v1"] = "mlp4-relaxed-evidence-yield-v1"
    base_url: str = "https://api.xiaomimimo.com/v1"
    api_key: SecretStr
    model: Literal["mimo-v2.5-pro"] = "mimo-v2.5-pro"
    max_completion_tokens: int = Field(default=4096, ge=1, le=32768)
    deadlines: DeadlineConfig = DeadlineConfig()

    @field_validator("base_url")
    @classmethod
    def validate_https(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Xiaomi MiMo base URL must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Xiaomi MiMo base URL cannot contain credentials, query, or fragment")
        return value.rstrip("/")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> MimoConfig:
        api_key = environment.get("MIMO_API_KEY", "").strip()
        if not api_key:
            raise ProviderConfigurationError(
                "MIMO_API_KEY is required in the explicitly supplied environment"
            )
        base_url = environment.get(
            "MIMO_BASE_URL",
            "https://api.xiaomimimo.com/v1",
        ).strip()
        model = environment.get("MIMO_MODEL", "mimo-v2.5-pro").strip()
        return cls(
            api_key=SecretStr(api_key),
            base_url=base_url,
            model=model,
        )


class MimoRouteConfig(StrictModel):
    """One explicitly selected Xiaomi-compatible MiMo physical route for v2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: Literal["xiaomi-mimo"] = "xiaomi-mimo"
    adapter_version: Literal["v2-mimo-routing-v1"] = "v2-mimo-routing-v1"
    base_url: str = "https://api.xiaomimimo.com/v1"
    api_key: SecretStr
    model: str = Field(min_length=1)
    max_completion_tokens: int = Field(default=4096, ge=1, le=32768)
    deadlines: DeadlineConfig = DeadlineConfig()

    @field_validator("base_url")
    @classmethod
    def validate_https(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Xiaomi MiMo base URL must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Xiaomi MiMo base URL cannot contain credentials, query, or fragment")
        return value.rstrip("/")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
        *,
        model_environment_name: str,
        default_model: str | None,
    ) -> MimoRouteConfig:
        api_key = environment.get("MIMO_API_KEY", "").strip()
        if not api_key:
            raise ProviderConfigurationError(
                "MIMO_API_KEY is required in the explicitly supplied environment"
            )
        model = environment.get(model_environment_name, default_model or "").strip()
        if not model:
            raise ProviderConfigurationError(
                f"{model_environment_name} is required for the selected MiMo v2 route"
            )
        return cls(
            api_key=SecretStr(api_key),
            base_url=environment.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1").strip(),
            model=model,
        )


class LunaConfig(StrictModel):
    """Configuration-only boundary for the v2 Luna route.

    The physical provider model is deliberately supplied at deployment time.  Phase 2
    establishes no Luna transport or live invocation behavior.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: Literal["luna"] = "luna"
    adapter_version: Literal["v2-luna-configuration-v1"] = "v2-luna-configuration-v1"
    base_url: str
    api_key: SecretStr
    model: str = Field(min_length=1)
    max_completion_tokens: int = Field(default=4096, ge=1, le=32768)
    deadlines: DeadlineConfig = DeadlineConfig()

    @field_validator("base_url")
    @classmethod
    def validate_https(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Luna base URL must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Luna base URL cannot contain credentials, query, or fragment")
        return value.rstrip("/")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> LunaConfig:
        missing = tuple(
            name
            for name in ("LUNA_API_KEY", "LUNA_BASE_URL", "LUNA_MODEL")
            if not environment.get(name, "").strip()
        )
        if missing:
            raise ProviderConfigurationError(
                f"{', '.join(missing)} are required for the selected Luna v2 route"
            )
        return cls(
            api_key=SecretStr(environment["LUNA_API_KEY"].strip()),
            base_url=environment["LUNA_BASE_URL"].strip(),
            model=environment["LUNA_MODEL"].strip(),
        )


class LiveSmokeConfig(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    approved_now: bool
    max_search_calls: int = Field(ge=1, le=1)
    max_acquisition_calls: int = Field(ge=1, le=1)
    max_llm_calls: int = Field(ge=1, le=1)
    max_tokens: int = Field(ge=1, le=25_000)
    max_cost_usd: Annotated[ExactUSD, Field(gt=Decimal("0"), le=Decimal("0.10"))]
    output_path: Path

    @field_validator("output_path")
    @classmethod
    def validate_dedicated_output(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("live smoke output path must be absolute")
        if value.name in {"", ".", ".."}:
            raise ValueError("live smoke output path must be dedicated")
        return value

    def require_enabled(self) -> None:
        if not self.enabled or not self.approved_now:
            raise ProviderConfigurationError(
                "live smoke requires both the enable flag and execution-time approval"
            )
