"""Strict MVP-2B provider configuration with secret-safe representations."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, SecretStr, field_validator

from models import StrictModel


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
    extractor_seconds: float = Field(default=180.0, gt=0, le=180.0)
    analyst_seconds: float = Field(default=120.0, gt=0, le=120.0)
    reviewer_seconds: float = Field(default=90.0, gt=0, le=90.0)
    synthesizer_seconds: float = Field(default=180.0, gt=0, le=180.0)


class RunCeilings(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_cost_usd: Decimal = Field(default=Decimal("1.00"), gt=0, le=Decimal("1.00"))
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


class FirecrawlConfig(StrictModel):
    """Optional Firecrawl acquisition-fallback configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: Literal["firecrawl"] = "firecrawl"
    provider_version: Literal["v2"] = "v2"
    adapter_version: Literal["mvp6.3-firecrawl-provenance-v2"] = "mvp6.3-firecrawl-provenance-v2"
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


class OpenRouterConfig(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: str = "openrouter"
    adapter_version: str = "mvp2b-openrouter-v1"
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: SecretStr
    primary_model: str = "xiaomi/mimo-v2.5-pro"
    fallback_model: str = "minimax/minimax-m3"
    max_output_tokens: int = Field(default=4096, ge=1, le=32768)
    deadlines: DeadlineConfig = DeadlineConfig()

    @field_validator("base_url")
    @classmethod
    def validate_https(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("OpenRouter base URL must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("OpenRouter base URL cannot contain credentials, query, or fragment")
        return value.rstrip("/")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> OpenRouterConfig:
        value = environment.get("OPENROUTER_API_KEY", "").strip()
        if not value:
            raise ProviderConfigurationError(
                "OPENROUTER_API_KEY is required in the process environment"
            )
        return cls(api_key=SecretStr(value))


class MimoConfig(StrictModel):
    """Strict direct Xiaomi MiMo configuration for MVP-3B."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: Literal["xiaomi-mimo"] = "xiaomi-mimo"
    adapter_version: Literal["mvp3b-xiaomi-mimo-v1"] = "mvp3b-xiaomi-mimo-v1"
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


class LiveSmokeConfig(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    approved_now: bool
    max_search_calls: int = Field(ge=1, le=1)
    max_acquisition_calls: int = Field(ge=1, le=1)
    max_llm_calls: int = Field(ge=1, le=1)
    max_tokens: int = Field(ge=1, le=25_000)
    max_cost_usd: Decimal = Field(gt=0, le=Decimal("0.10"))
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
