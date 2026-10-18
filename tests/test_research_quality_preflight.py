from __future__ import annotations

import json
import shutil
import socket
from pathlib import Path

import pytest

from evaluations.research_quality_preflight import CASE_DIR, REQUIRED_KEYS, inspect_preflight


def _allowance(tmp_path: Path) -> Path:
    target = tmp_path / "case"
    shutil.copytree(CASE_DIR, target)
    return target / "allowance.json"


def test_preflight_stops_without_secrets_or_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket, "socket", forbidden)
    path = _allowance(tmp_path)
    # Credential-only fixtures use the exact approved historical identity. Prompt
    # 15 source changes intentionally reject that allowance in the real runtime.
    frozen_identity = json.loads((path.parent / "prepared.json").read_text())["baseline"][
        "source_identity"
    ]
    report = inspect_preflight(path, credential_reader=lambda name: None, identity=frozen_identity)
    assert report["status"] == "stopped_before_transport"
    assert report["new_provider_requests"] == 0
    assert report["incremental_paid_call_cost_usd"] == "0.00"
    assert report["account_invoice_total_usd"] is None
    assert report["human_quality_judgments"] == "pending"
    assert report["native_credentials"] == dict.fromkeys(REQUIRED_KEYS, "missing")


def test_preflight_never_records_keys_or_provider_exception_text(tmp_path: Path) -> None:
    def read(name: str) -> str | None:
        if name == "LUNA_API_KEY":
            return "private-value-never-persist"
        raise RuntimeError("private-exception-never-persist")

    path = _allowance(tmp_path)
    frozen_identity = json.loads((path.parent / "prepared.json").read_text())["baseline"][
        "source_identity"
    ]
    report = inspect_preflight(path, credential_reader=read, identity=frozen_identity)
    assert "private-" not in json.dumps(report)
    assert report["native_credentials"]["LUNA_API_KEY"] == "available"
    assert report["status"] == "stopped_before_transport"


@pytest.mark.parametrize("changed", ["approval", "frozen_input", "source_identity"])
def test_preflight_rejects_drift_before_vault_access(tmp_path: Path, changed: str) -> None:
    path = _allowance(tmp_path)
    identity = None
    if changed == "approval":
        allowance = json.loads(path.read_text())
        allowance["status"] = "proposed_unapproved"
        path.write_text(json.dumps(allowance))
    elif changed == "frozen_input":
        (path.parent / "queries.json").write_text("{}")
    else:
        identity = "changed-source"

    def forbidden(name: str) -> str | None:
        raise AssertionError("vault read before validation")

    with pytest.raises(ValueError):
        inspect_preflight(path, credential_reader=forbidden, identity=identity)


def test_current_runtime_rejects_prior_approved_source_before_vault_access(tmp_path: Path) -> None:
    from researchassistant.runtime.application_runtime import repository_identity

    path = _allowance(tmp_path)
    baseline = json.loads((path.parent / "prepared.json").read_text())["baseline"][
        "source_identity"
    ]
    assert repository_identity() != baseline

    def forbidden(name: str) -> str | None:
        raise AssertionError("vault accessed under an incompatible runtime")

    with pytest.raises(ValueError, match="current runtime source differs"):
        inspect_preflight(path, credential_reader=forbidden)
