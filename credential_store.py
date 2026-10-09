"""Secret-safe macOS Keychain storage for local provider credentials."""

from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import MutableMapping
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ConfigDict, SecretStr, field_validator

from models import StrictModel

PROJECT_ROOT = Path(__file__).resolve().parent
KEYCHAIN_ACCOUNT = "ResearchAssistant"
KEYCHAIN_SERVICE_PREFIX = "ResearchAssistant."
SECURITY_FRAMEWORK = "/System/Library/Frameworks/Security.framework/Security"
CORE_FOUNDATION_FRAMEWORK = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
ERR_SEC_SUCCESS = 0
ERR_SEC_ITEM_NOT_FOUND = -25300


class KeychainUnavailableError(RuntimeError):
    """Raised when secure local credential storage is unavailable."""


class ProviderCredentials(StrictModel):
    """Required and optional live provider secrets with redacted representations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mimo_api_key: SecretStr | None = None
    luna_api_key: SecretStr | None = None
    luna_base_url: str | None = None
    luna_model: str | None = None
    mimo_v25_input_usd_per_token: str | None = None
    mimo_v25_output_usd_per_token: str | None = None
    luna_input_usd_per_token: str | None = None
    luna_output_usd_per_token: str | None = None
    exa_api_key: SecretStr | None = None
    openalex_api_key: SecretStr | None = None
    serpsearch_api_key: SecretStr | None = None
    pubmed_api_key: SecretStr | None = None
    firecrawl_api_key: SecretStr | None = None

    @field_validator(
        "mimo_api_key",
        "luna_api_key",
        "luna_base_url",
        "luna_model",
        "mimo_v25_input_usd_per_token",
        "mimo_v25_output_usd_per_token",
        "luna_input_usd_per_token",
        "luna_output_usd_per_token",
        "exa_api_key",
        "openalex_api_key",
        "serpsearch_api_key",
        "pubmed_api_key",
        "firecrawl_api_key",
        mode="before",
    )
    @classmethod
    def validate_provider_value(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("Provider values must be non-empty and have no surrounding whitespace")
        if "\n" in value or "\r" in value:
            raise ValueError("Provider values must be single-line values")
        return value

    @field_validator("luna_base_url")
    @classmethod
    def validate_luna_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Luna base URL must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Luna base URL cannot contain credentials, query, or fragment")
        return value.rstrip("/")

    def environment_items(self) -> tuple[tuple[str, str], ...]:
        """Return explicit process-environment boundary values."""
        items: tuple[tuple[str, str], ...] = ()
        if self.mimo_api_key is not None:
            items += (("MIMO_API_KEY", self.mimo_api_key.get_secret_value()),)
        if self.luna_api_key is not None:
            items += (("LUNA_API_KEY", self.luna_api_key.get_secret_value()),)
        if self.luna_base_url is not None:
            items += (("LUNA_BASE_URL", self.luna_base_url),)
        if self.luna_model is not None:
            items += (("LUNA_MODEL", self.luna_model),)
        if self.mimo_v25_input_usd_per_token is not None:
            items += (("MIMO_V25_INPUT_USD_PER_TOKEN", self.mimo_v25_input_usd_per_token),)
        if self.mimo_v25_output_usd_per_token is not None:
            items += (("MIMO_V25_OUTPUT_USD_PER_TOKEN", self.mimo_v25_output_usd_per_token),)
        if self.luna_input_usd_per_token is not None:
            items += (("LUNA_INPUT_USD_PER_TOKEN", self.luna_input_usd_per_token),)
        if self.luna_output_usd_per_token is not None:
            items += (("LUNA_OUTPUT_USD_PER_TOKEN", self.luna_output_usd_per_token),)
        if self.exa_api_key is not None:
            items += (("EXA_API_KEY", self.exa_api_key.get_secret_value()),)
        if self.openalex_api_key is not None:
            items += (("OPENALEX_API_KEY", self.openalex_api_key.get_secret_value()),)
        if self.serpsearch_api_key is not None:
            items += (("SERPSEARCH_API_KEY", self.serpsearch_api_key.get_secret_value()),)
        if self.pubmed_api_key is not None:
            items += (("PUBMED_API_KEY", self.pubmed_api_key.get_secret_value()),)
        if self.firecrawl_api_key is None:
            return items
        return items + (("FIRECRAWL_API_KEY", self.firecrawl_api_key.get_secret_value()),)


def save_credentials(credentials: ProviderCredentials) -> None:
    """Store credentials through the in-process macOS Security framework."""
    _require_keychain()
    for environment_name, secret in credentials.environment_items():
        _write_keychain_secret(environment_name, secret)


def load_saved_credentials() -> ProviderCredentials | None:
    """Read every saved key so optional discovery choices survive API restart."""
    if not _keychain_available():
        return None
    try:
        mimo = _read_secret("MIMO_API_KEY")
    except KeychainUnavailableError:
        return None
    credentials = ProviderCredentials(
        mimo_api_key=mimo,
        luna_api_key=_read_optional_secret("LUNA_API_KEY"),
        luna_base_url=_read_optional_secret("LUNA_BASE_URL"),
        luna_model=_read_optional_secret("LUNA_MODEL"),
        mimo_v25_input_usd_per_token=_read_optional_secret("MIMO_V25_INPUT_USD_PER_TOKEN"),
        mimo_v25_output_usd_per_token=_read_optional_secret("MIMO_V25_OUTPUT_USD_PER_TOKEN"),
        luna_input_usd_per_token=_read_optional_secret("LUNA_INPUT_USD_PER_TOKEN"),
        luna_output_usd_per_token=_read_optional_secret("LUNA_OUTPUT_USD_PER_TOKEN"),
        exa_api_key=_read_optional_secret("EXA_API_KEY"),
        openalex_api_key=_read_optional_secret("OPENALEX_API_KEY"),
        serpsearch_api_key=_read_optional_secret("SERPSEARCH_API_KEY"),
        pubmed_api_key=_read_optional_secret("PUBMED_API_KEY"),
        firecrawl_api_key=_read_optional_secret(),
    )
    if not credentials.environment_items():
        return None
    return credentials


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
    security = _load_security_framework()
    keychain_ref = _copy_default_keychain(security)
    account = KEYCHAIN_ACCOUNT.encode("utf-8")
    service = _service_name(environment_name).encode("utf-8")
    password_length = ctypes.c_uint32()
    password_data = ctypes.c_void_p()
    item_ref = ctypes.c_void_p()
    status = security.SecKeychainFindGenericPassword(
        keychain_ref,
        len(service),
        service,
        len(account),
        account,
        ctypes.byref(password_length),
        ctypes.byref(password_data),
        ctypes.byref(item_ref),
    )
    if status == ERR_SEC_ITEM_NOT_FOUND:
        _release_item(keychain_ref)
        return None
    if status != ERR_SEC_SUCCESS:
        _release_item(keychain_ref)
        raise KeychainUnavailableError(
            f"macOS Keychain could not read {environment_name} (status {status})"
        )
    try:
        secret_bytes = ctypes.string_at(password_data, password_length.value)
        secret = secret_bytes.decode("utf-8")
        return secret or None
    except UnicodeDecodeError as exc:
        raise KeychainUnavailableError(
            f"macOS Keychain returned invalid data for {environment_name}"
        ) from exc
    finally:
        if password_data.value is not None:
            security.SecKeychainItemFreeContent(None, password_data)
        _release_item(item_ref)
        _release_item(keychain_ref)


def _read_optional_secret(environment_name: str = "FIRECRAWL_API_KEY") -> str | None:
    try:
        return _read_secret(environment_name)
    except (KeychainUnavailableError, KeyError):
        return None


def _write_keychain_secret(environment_name: str, secret: str) -> None:
    security = _load_security_framework()
    keychain_ref = _copy_default_keychain(security)
    account = KEYCHAIN_ACCOUNT.encode("utf-8")
    service = _service_name(environment_name).encode("utf-8")
    secret_bytes = secret.encode("utf-8")
    item_ref = ctypes.c_void_p()
    status = security.SecKeychainFindGenericPassword(
        keychain_ref,
        len(service),
        service,
        len(account),
        account,
        None,
        None,
        ctypes.byref(item_ref),
    )
    if status == ERR_SEC_SUCCESS:
        try:
            status = security.SecKeychainItemModifyAttributesAndData(
                item_ref,
                None,
                len(secret_bytes),
                secret_bytes,
            )
        finally:
            _release_item(item_ref)
    elif status == ERR_SEC_ITEM_NOT_FOUND:
        status = security.SecKeychainAddGenericPassword(
            keychain_ref,
            len(service),
            service,
            len(account),
            account,
            len(secret_bytes),
            secret_bytes,
            ctypes.byref(item_ref),
        )
        _release_item(item_ref)
    _release_item(keychain_ref)
    if status != ERR_SEC_SUCCESS:
        raise KeychainUnavailableError(
            f"macOS Keychain could not save {environment_name} (status {status}); no key was logged"
        )


def _load_security_framework() -> ctypes.CDLL:
    try:
        security = ctypes.CDLL(SECURITY_FRAMEWORK)
    except OSError as exc:
        raise KeychainUnavailableError("Secure provider setup requires macOS Keychain") from exc
    security.SecKeychainFindGenericPassword.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    )
    security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
    security.SecKeychainCopyDefault.argtypes = (ctypes.POINTER(ctypes.c_void_p),)
    security.SecKeychainCopyDefault.restype = ctypes.c_int32
    security.SecKeychainAddGenericPassword.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_void_p),
    )
    security.SecKeychainAddGenericPassword.restype = ctypes.c_int32
    security.SecKeychainItemModifyAttributesAndData.argtypes = (
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_char_p,
    )
    security.SecKeychainItemModifyAttributesAndData.restype = ctypes.c_int32
    security.SecKeychainItemFreeContent.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    security.SecKeychainItemFreeContent.restype = ctypes.c_int32
    return security


def _copy_default_keychain(security: ctypes.CDLL) -> ctypes.c_void_p:
    keychain_ref = ctypes.c_void_p()
    status = security.SecKeychainCopyDefault(ctypes.byref(keychain_ref))
    if status != ERR_SEC_SUCCESS or keychain_ref.value is None:
        raise KeychainUnavailableError(f"macOS login Keychain is unavailable (status {status})")
    return keychain_ref


def _release_item(item_ref: ctypes.c_void_p) -> None:
    if item_ref.value is None:
        return
    try:
        core_foundation = ctypes.CDLL(CORE_FOUNDATION_FRAMEWORK)
    except OSError:
        return
    core_foundation.CFRelease.argtypes = (ctypes.c_void_p,)
    core_foundation.CFRelease.restype = None
    core_foundation.CFRelease(item_ref)


def _service_name(environment_name: str) -> str:
    return f"{KEYCHAIN_SERVICE_PREFIX}{environment_name}"


def _keychain_available() -> bool:
    return sys.platform == "darwin" and os.path.lexists(SECURITY_FRAMEWORK)


def _require_keychain() -> None:
    if not _keychain_available():
        raise KeychainUnavailableError("Secure provider setup requires macOS Keychain")
