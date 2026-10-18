"""Resource relocation must preserve policy bytes and exact executable identity."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from providers.config import ProviderConfigurationError
from providers.llm import load_prompt_file
from researchassistant.common.resources import PROMPT_NAMES, prompt_directory
from researchassistant.research.discovery_policy import discovery_contract_schema_hash
from researchassistant.runtime import application_runtime
from scripts.verify_distribution import expected_payloads

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/src"


def test_all_historical_prompt_bytes_are_present_in_one_canonical_directory() -> None:
    recorded = json.loads((ROOT / "tests/fixtures/packaging/prompt-hashes.json").read_text())
    resources = prompt_directory()
    actual = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in resources.iterdir()
        if path.name.endswith(".md")
    }
    assert set(PROMPT_NAMES) == recorded.keys()
    assert actual == recorded
    assert not list((ROOT / "prompts").glob("*.md"))
    for name, digest in recorded.items():
        assert load_prompt_file(resources.joinpath(name)).sha256 == digest


def _installed_surface(root: Path) -> None:
    for name, payload in expected_payloads(ROOT).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def test_wheel_configuration_resource_preserves_source_identity(tmp_path: Path) -> None:
    _installed_surface(tmp_path)
    assert application_runtime.repository_identity(
        tmp_path
    ) == application_runtime.repository_identity(ROOT)
    assert discovery_contract_schema_hash(tmp_path) == discovery_contract_schema_hash(ROOT)
    configuration = tmp_path / "researchassistant/_distribution/pyproject.toml"
    configuration.write_bytes(configuration.read_bytes() + b"\n# changed build configuration\n")
    assert application_runtime.repository_identity(
        tmp_path
    ) != application_runtime.repository_identity(ROOT)


@pytest.mark.parametrize("name", PROMPT_NAMES)
def test_frozen_identity_rejects_every_missing_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    _installed_surface(tmp_path)
    source_identity = application_runtime.repository_identity(ROOT)
    executable = tmp_path / "frozen-backend"
    executable.write_bytes(b"fixture executable")
    monkeypatch.setattr(application_runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(application_runtime.sys, "executable", str(executable))
    frozen = application_runtime.repository_identity(tmp_path)
    assert frozen != source_identity
    (tmp_path / "researchassistant/prompts" / name).unlink()
    with pytest.raises(ProviderConfigurationError, match="identity surface is incomplete"):
        application_runtime.repository_identity(tmp_path)


def test_prompt_and_font_tampering_change_installed_identity(tmp_path: Path) -> None:
    _installed_surface(tmp_path)
    original = application_runtime.repository_identity(tmp_path)
    prompt = tmp_path / "researchassistant/prompts/search_agent.md"
    prompt.write_bytes(prompt.read_bytes() + b"\nchanged prompt\n")
    changed = application_runtime.repository_identity(tmp_path)
    assert changed != original
    assert discovery_contract_schema_hash(tmp_path) != discovery_contract_schema_hash(ROOT)
    font = tmp_path / "researchassistant/evidence/fonts/unifont-15.0.01.ttf"
    font.write_bytes(font.read_bytes() + b"changed font")
    assert application_runtime.repository_identity(tmp_path) not in {original, changed}
    shutil.copyfile(SOURCE / "researchassistant/prompts/search_agent.md", prompt)
    shutil.copyfile(SOURCE / "researchassistant/evidence/fonts/unifont-15.0.01.ttf", font)
    assert application_runtime.repository_identity(tmp_path) == original


def test_frozen_resources_use_backend_owned_source_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from researchassistant.common.resources import pdf_font_resource

    source = tmp_path / "backend/src"
    for name, payload in expected_payloads(ROOT).items():
        if name == "researchassistant/_distribution/pyproject.toml":
            path = tmp_path / "backend/pyproject.toml"
        else:
            path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    monkeypatch.setattr(application_runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(application_runtime.sys, "_MEIPASS", str(tmp_path), raising=False)
    resources = prompt_directory()
    assert resources == source / "researchassistant/prompts"
    assert (
        pdf_font_resource().read_bytes()
        == (ROOT / "backend/src/researchassistant/evidence/fonts/unifont-15.0.01.ttf").read_bytes()
    )
    assert {path.name for path in resources.iterdir()} == set(PROMPT_NAMES)
