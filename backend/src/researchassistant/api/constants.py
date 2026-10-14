"""Stable local API version, transport defaults and credential diagnostic."""

from __future__ import annotations

API_HOST = "127.0.0.1"

API_PORT = 8765

API_VERSION = "mlp-5-v2-phase13-analyzer-admission"

CREDENTIAL_ACCESS_MESSAGE = (
    "Credential vault access was not granted. On macOS, the system Keychain prompt "
    "needs your Mac login/keychain password, not a provider API key. "
    "Enter API keys only in the app's provider fields."
)

WEB_ORIGINS = ("http://127.0.0.1:3000", "http://localhost:3000")

LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
