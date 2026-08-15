"""Secret-safe macOS Keychain storage for local provider credentials."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import MutableMapping
from pathlib import Path

from pydantic import ConfigDict, SecretStr, field_validator

from models import StrictModel

PROJECT_ROOT = Path(__file__).resolve().parent
KEYCHAIN_ACCOUNT = "ResearchAssistant"
KEYCHAIN_SERVICE_PREFIX = "ResearchAssistant."
KEYCHAIN_TIMEOUT_SECONDS = 10
SECURITY_EXECUTABLE = "/usr/bin/security"


class KeychainUnavailableError(RuntimeError):
    """Raised when secure local credential storage is unavailable."""


class ProviderCredentials(StrictModel):
    """Required and optional live provider secrets with redacted representations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mimo_api_key: SecretStr
    exa_api_key: SecretStr
    firecrawl_api_key: SecretStr | None = None

    @field_validator("mimo_api_key", "exa_api_key", "firecrawl_api_key", mode="before")
    @classmethod
    def validate_api_key(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("API keys must be non-empty and have no surrounding whitespace")
        if "\n" in value or "\r" in value:
            raise ValueError("API keys must be single-line values")
        return value

    def environment_items(self) -> tuple[tuple[str, str], ...]:
        """Return explicit process-environment boundary values."""
        items = (
            ("MIMO_API_KEY", self.mimo_api_key.get_secret_value()),
            ("EXA_API_KEY", self.exa_api_key.get_secret_value()),
        )
        if self.firecrawl_api_key is None:
            return items
        return items + (("FIRECRAWL_API_KEY", self.firecrawl_api_key.get_secret_value()),)


def save_credentials(credentials: ProviderCredentials) -> None:
    """Store supplied credentials in the macOS login Keychain without argv exposure."""
    _require_keychain()
    for environment_name, secret in credentials.environment_items():
        command = (
            SECURITY_EXECUTABLE,
            "add-generic-password",
            "-U",
            "-a",
            KEYCHAIN_ACCOUNT,
            "-s",
            _service_name(environment_name),
            "-w",
        )
        try:
            result = subprocess.run(
                command,
                input=f"{secret}\n",
                text=True,
                capture_output=True,
                timeout=KEYCHAIN_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise KeychainUnavailableError(
                f"macOS Keychain could not save {environment_name}; no key was logged"
            ) from exc
        if result.returncode != 0:
            raise KeychainUnavailableError(
                f"macOS Keychain could not save {environment_name}; no key was logged"
            )


def load_saved_credentials() -> ProviderCredentials | None:
    """Read required saved credentials and the optional fallback credential."""
    if not _keychain_available():
        return None
    try:
        mimo = _read_secret("MIMO_API_KEY")
        exa = _read_secret("EXA_API_KEY")
    except (OSError, subprocess.SubprocessError):
        return None
    if not mimo or not exa:
        return None
    return ProviderCredentials(
        mimo_api_key=mimo,
        exa_api_key=exa,
        firecrawl_api_key=_read_optional_secret(),
    )


def apply_credentials_to_environment(
    credentials: ProviderCredentials,
    environment: MutableMapping[str, str] | None = None,
) -> None:
    """Apply typed credentials only at the explicit process-environment boundary."""
    target = os.environ if environment is None else environment
    for name, value in credentials.environment_items():
        target[name] = value


def load_saved_credentials_into_environment(
    environment: MutableMapping[str, str] | None = None,
) -> bool:
    """Load Keychain credentials into one process environment when available."""
    credentials = load_saved_credentials()
    if credentials is None:
        return False
    apply_credentials_to_environment(credentials, environment)
    return True


def _read_secret(environment_name: str) -> str | None:
    command = (
        SECURITY_EXECUTABLE,
        "find-generic-password",
        "-a",
        KEYCHAIN_ACCOUNT,
        "-s",
        _service_name(environment_name),
        "-w",
    )
    result = subprocess.run(
        command,
        input=None,
        text=True,
        capture_output=True,
        timeout=KEYCHAIN_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        return None
    secret = result.stdout.rstrip("\r\n")
    return secret or None


def _read_optional_secret() -> str | None:
    try:
        return _read_secret("FIRECRAWL_API_KEY")
    except (OSError, subprocess.SubprocessError):
        return None


def _service_name(environment_name: str) -> str:
    return f"{KEYCHAIN_SERVICE_PREFIX}{environment_name}"


def _keychain_available() -> bool:
    return sys.platform == "darwin" and Path(SECURITY_EXECUTABLE).is_file()


def _require_keychain() -> None:
    if not _keychain_available():
        raise KeychainUnavailableError("Secure provider setup requires macOS Keychain")
