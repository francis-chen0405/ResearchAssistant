from __future__ import annotations

import pathlib
import tomllib

from researchassistant.runtime.cli import _build_parser

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_phase0_scaffold_exists() -> None:
    expected_paths = [
        "AGENTS.md",
        "DECISIONS.md",
        "STATUS.md",
        "HANDOFF.md",
        "README.md",
        "pyproject.toml",
        ".agent/PLANS.md",
        ".agent/plans/phase-00-foundation.md",
        ".agents/PLANS/phase-00-foundation.md",
        "providers/.gitkeep",
        "prompts/.gitkeep",
        "tests/fixtures/.gitkeep",
    ]

    missing = [path for path in expected_paths if not (ROOT / path).exists()]

    assert missing == []


def test_pyproject_declares_phase_dependencies() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["requires-python"] == ">=3.11,<3.13"
    assert pyproject["project"]["name"] == "researchassistant"
    assert pyproject["project"]["version"] == "0.1.0"
    assert pyproject["project"]["dependencies"] == [
        "fastapi>=0.115,<1.0",
        "httpx>=0.27,<1.0",
        "markdown-it-py>=3.0,<4.0",
        "pydantic>=2.0,<3.0",
        "pypdf>=5.0,<6.0",
        "reportlab>=4.4.9,<5.0",
        "uvicorn>=0.30,<1.0",
    ]
    assert pyproject["project"]["optional-dependencies"]["dev"] == [
        "httpx2>=2.0,<3.0",
        "pytest>=8.0,<9.0",
        "pytest-cov>=6.0,<7.0",
        "ruff>=0.8,<1.0",
    ]
    assert (ROOT / "requirements-legacy.txt").read_text(encoding="utf-8").splitlines() == [
        "-r requirements.txt",
        "streamlit>=1.37,<2.0",
    ]


def test_cli_help_uses_package_branding() -> None:
    help_text = _build_parser().format_help()

    assert help_text.startswith("usage: ResearchAssistant")
    assert "Command-line interface for ResearchAssistant." in help_text
