from __future__ import annotations

import pytest
from pydantic import ValidationError

import credential_store
from credential_store import ProviderCredentials, load_saved_credentials, save_credentials


def test_provider_credentials_are_strict_and_secret_safe() -> None:
    credentials = ProviderCredentials(
        mimo_api_key="mimo-secret",
        exa_api_key="exa-secret",
        firecrawl_api_key="firecrawl-secret",
    )

    assert "mimo-secret" not in repr(credentials)
    assert "exa-secret" not in repr(credentials)
    assert credentials.environment_items() == (
        ("MIMO_API_KEY", "mimo-secret"),
        ("EXA_API_KEY", "exa-secret"),
        ("FIRECRAWL_API_KEY", "firecrawl-secret"),
    )
    with pytest.raises(ValidationError):
        ProviderCredentials(
            mimo_api_key="mimo-secret",
            exa_api_key="exa-secret",
            unknown="not-allowed",
        )


def test_keychain_availability_accepts_the_macos_shared_cache_framework_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(credential_store.sys, "platform", "darwin")
    monkeypatch.setattr(credential_store.os.path, "lexists", lambda path: True)

    assert credential_store._keychain_available() is True


def test_keychain_save_uses_the_in_process_native_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_write(environment_name: str, secret: str) -> None:
        calls.append((environment_name, secret))

    monkeypatch.setattr(credential_store, "_keychain_available", lambda: True)
    monkeypatch.setattr(credential_store, "_write_keychain_secret", fake_write)
    credentials = ProviderCredentials(mimo_api_key="mimo-secret", exa_api_key="exa-secret")

    save_credentials(credentials)

    assert calls == [
        ("MIMO_API_KEY", "mimo-secret"),
        ("EXA_API_KEY", "exa-secret"),
    ]
    source = credential_store.PROJECT_ROOT.joinpath("credential_store.py").read_text(
        encoding="utf-8"
    )
    assert "subprocess.run" not in source


def test_keychain_save_can_add_one_provider_key_without_replacing_saved_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_write(environment_name: str, secret: str) -> None:
        calls.append((environment_name, secret))

    monkeypatch.setattr(credential_store, "_keychain_available", lambda: True)
    monkeypatch.setattr(credential_store, "_write_keychain_secret", fake_write)

    save_credentials(ProviderCredentials(serpsearch_api_key="serpsearch-secret"))

    assert calls == [("SERPSEARCH_API_KEY", "serpsearch-secret")]


def test_keychain_load_returns_typed_credentials_without_logging_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "MIMO_API_KEY": "mimo-secret",
        "EXA_API_KEY": "exa-secret",
        "FIRECRAWL_API_KEY": "firecrawl-secret",
    }

    monkeypatch.setattr(credential_store, "_keychain_available", lambda: True)
    monkeypatch.setattr(
        credential_store,
        "_read_secret",
        lambda environment_name: values[environment_name],
    )

    credentials = load_saved_credentials()

    assert credentials is not None
    assert credentials.environment_items()[0] == ("MIMO_API_KEY", "mimo-secret")
    assert "secret" not in repr(credentials)


def test_launcher_defers_missing_credentials_to_local_provider_setup() -> None:
    launcher = credential_store.PROJECT_ROOT.joinpath("Launch ResearchAssistant.command").read_text(
        encoding="utf-8"
    )

    assert "display dialog" not in launcher
    assert "Enter MIMO_API_KEY" not in launcher
    assert "frontend.api" in launcher
    assert 'next" start' in launcher
    assert "127.0.0.1:3000" in launcher
    assert 'EXPECTED_API_VERSION="mlp-5-v2-phase13-analyzer-admission"' in launcher
    assert "streamlit" not in launcher.lower()
