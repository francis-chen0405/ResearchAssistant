from __future__ import annotations

import pathlib
import tomllib

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

    assert pyproject["project"]["requires-python"] == ">=3.11"
    assert pyproject["project"]["dependencies"] == [
        "httpx>=0.27,<1.0",
        "markdown-it-py>=3.0,<4.0",
        "pydantic>=2.0,<3.0",
        "pypdf>=5.0,<6.0",
        "python-dotenv>=1.0,<2.0",
        "streamlit>=1.37,<2.0",
    ]
    assert pyproject["project"]["optional-dependencies"]["dev"] == [
        "pytest>=8.0,<9.0",
        "pytest-cov>=6.0,<7.0",
        "ruff>=0.8,<1.0",
    ]
