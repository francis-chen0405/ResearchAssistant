"""CLI configuration diagnostics expose safe labels without rejected secret values."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from researchassistant.runtime.cli import (
    CLIExitCode,
    _build_parser,
    _configuration_validation_message,
    _run_live_command,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://u:probe-secret@localhost",
        "http://localhost?api_key=probe-secret",
        "http://localhost/#probe-secret",
    ],
)
def test_rejected_endpoint_credentials_never_appear_in_cli_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], url: str
) -> None:
    path = tmp_path / "never-created.sqlite3"
    args = _build_parser().parse_args(
        [
            "run",
            "A generated public claim.",
            "--db-path",
            str(path),
            "--max-tokens",
            "1000",
        ]
    )
    result = _run_live_command(
        args,
        environment={"WIGOLO_BASE_URL": url},
        legacy_runner=None,
        identity_provider=lambda: pytest.fail("must fail before identity/provider setup"),
    )
    output = capsys.readouterr()
    assert result is CLIExitCode.CONFIGURATION_ERROR
    assert "configuration error" in output.err and "base_url" in output.err
    assert "probe-secret" not in output.err + output.out
    assert "input_value" not in output.err and not path.exists()


def test_error_context_and_untrusted_extra_field_names_are_redacted() -> None:
    error = ValidationError.from_exception_data(
        "SyntheticConfiguration",
        [
            {
                "type": "value_error",
                "loc": ("probe-secret",),
                "input": "probe-secret",
                "ctx": {"error": ValueError("probe-secret")},
            }
        ],
    )
    message = _configuration_validation_message(error)
    assert "probe-secret" not in message and "configuration error" in message


def test_missing_configuration_keeps_useful_safe_diagnostic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "never-created.sqlite3"
    args = _build_parser().parse_args(
        [
            "run",
            "A generated public claim.",
            "--db-path",
            str(path),
            "--max-tokens",
            "1000",
        ]
    )
    result = _run_live_command(
        args,
        environment={},
        legacy_runner=None,
        identity_provider=lambda: "offline-probe",
    )
    output = capsys.readouterr()
    assert result is CLIExitCode.CONFIGURATION_ERROR
    assert "required" in output.err and "key" in output.err.casefold()
    assert not path.exists()
