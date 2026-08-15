from __future__ import annotations

import subprocess
from collections.abc import Sequence

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


def test_keychain_save_never_places_secrets_in_command_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []

    def fake_run(
        command: Sequence[str],
        *,
        input: str | None,
        text: bool,
        capture_output: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(command), input))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(credential_store.sys, "platform", "darwin")
    monkeypatch.setattr(credential_store.subprocess, "run", fake_run)
    credentials = ProviderCredentials(mimo_api_key="mimo-secret", exa_api_key="exa-secret")

    save_credentials(credentials)

    assert len(calls) == 2
    assert all(command[-1] == "-w" for command, _ in calls)
    assert all("secret" not in " ".join(command) for command, _ in calls)
    assert {password for _, password in calls} == {"mimo-secret\n", "exa-secret\n"}


def test_keychain_load_returns_typed_credentials_without_logging_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "ResearchAssistant.MIMO_API_KEY": "mimo-secret\n",
        "ResearchAssistant.EXA_API_KEY": "exa-secret\n",
        "ResearchAssistant.FIRECRAWL_API_KEY": "firecrawl-secret\n",
    }

    def fake_run(
        command: Sequence[str],
        *,
        input: str | None,
        text: bool,
        capture_output: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        service = command[command.index("-s") + 1]
        return subprocess.CompletedProcess(command, 0, stdout=values[service], stderr="")

    monkeypatch.setattr(credential_store.sys, "platform", "darwin")
    monkeypatch.setattr(credential_store.subprocess, "run", fake_run)

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
