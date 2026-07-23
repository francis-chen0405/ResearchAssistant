"""Strict MVP-2B provider configuration with secret-safe representations."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
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
    candidate_seconds: float = Field(default=40.0, gt=0, le=40.0)
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
    adapter_version: str = "mvp2b-wigolo-v1"
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
