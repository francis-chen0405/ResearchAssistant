"""Repository guardrails also run directly before the full CI suite."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.check_repository_boundaries import (
    BASELINE,
    ROOT,
    dependency_violations,
    imported_names,
    root_layout_violations,
    root_python_violations,
)


@pytest.mark.core
def test_repository_root_and_dependency_boundaries() -> None:
    assert not root_python_violations(ROOT)
    assert not root_layout_violations(ROOT)
    assert not dependency_violations(ROOT, BASELINE)


@pytest.mark.core
def test_root_allowlist_rejects_staged_and_committed_copies(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name in ("cli.py", "models.py", "orchestrator.py", "store.py", "model_evidence.py"):
        (tmp_path / name).write_text("# source\n", encoding="utf-8")
    (tmp_path / "untracked.py").write_text("# not tracked\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "*.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "rm", "--cached", "untracked.py"], check=True)
    expected = [
        f"unsupported tracked root Python file: {name}"
        for name in ("cli.py", "model_evidence.py", "models.py", "orchestrator.py", "store.py")
    ]
    assert root_python_violations(tmp_path) == expected
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Boundary Test",
            "-c",
            "user.email=boundary@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    assert root_python_violations(tmp_path) == expected
    subprocess.run(["git", "-C", str(tmp_path), "rm", "model_evidence.py"], check=True)
    assert root_python_violations(tmp_path) == [
        row for row in expected if not row.endswith(": model_evidence.py")
    ]
    for name in ("cli.py", "models.py", "orchestrator.py", "store.py"):
        subprocess.run(["git", "-C", str(tmp_path), "rm", name], check=True)
    assert not root_python_violations(tmp_path)


@pytest.mark.core
@pytest.mark.parametrize(
    ("layer", "source", "target"),
    [
        ("contracts", "import providers.search as search", "providers.search"),
        ("contracts", "from providers import search", "providers.search"),
        ("contracts", "from agents.v2_acquisition import acquire", "agents.v2_acquisition.acquire"),
        ("storage", "def read():\n    from agents import v2_extraction", "agents.v2_extraction"),
        ("contracts", "if TYPE_CHECKING:\n    import providers.search", "providers.search"),
        (
            "contracts",
            "from ..providers.search import SearchResult",
            "researchassistant.providers.search.SearchResult",
        ),
        ("storage", "from .. import agents", "researchassistant.agents"),
        (
            "contracts",
            "def validate():\n    from ..research.query_compiler import compile_query",
            "researchassistant.research.query_compiler.compile_query",
        ),
        (
            "storage",
            "if TYPE_CHECKING:\n    from researchassistant.research.orchestrator import Result",
            "researchassistant.research.orchestrator.Result",
        ),
        (
            "storage",
            "from orchestrator import inspect_provider_run",
            "orchestrator.inspect_provider_run",
        ),
    ],
)
def test_boundary_check_catches_import_forms(
    tmp_path: Path, layer: str, source: str, target: str
) -> None:
    path = tmp_path / f"backend/src/researchassistant/{layer}/example.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text("[]", encoding="utf-8")
    assert dependency_violations(tmp_path, baseline) == [
        f"new restricted import: backend/src/researchassistant/{layer}/example.py -> {target} "
        "(1 additional occurrence(s))"
    ]


@pytest.mark.core
def test_boundary_baseline_is_exact_and_ratchets_down(tmp_path: Path) -> None:
    path = tmp_path / "backend/src/researchassistant/contracts/example.py"
    path.parent.mkdir(parents=True)
    path.write_text("from providers.search import SearchResponse", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            [
                {
                    "source": "backend/src/researchassistant/contracts/example.py",
                    "import": "providers.search.SearchResponse",
                    "count": 1,
                    "reason": "Fixture of a reviewed existing exception.",
                }
            ]
        ),
        encoding="utf-8",
    )
    assert not dependency_violations(tmp_path, baseline)
    path.write_text("from providers.search import SearchResponse, SearchResult", encoding="utf-8")
    assert "SearchResult" in dependency_violations(tmp_path, baseline)[0]
    path.write_text("from providers.search import SearchResponse\n" * 2, encoding="utf-8")
    assert "additional occurrence" in dependency_violations(tmp_path, baseline)[0]
    path.write_text("", encoding="utf-8")
    assert "remove stale baseline exception" in dependency_violations(tmp_path, baseline)[0]


@pytest.mark.core
def test_boundary_parser_resolves_nested_relative_packages() -> None:
    assert imported_names("from ...providers import search", "researchassistant.contracts.sub") == [
        "researchassistant.providers.search"
    ]


@pytest.mark.core
def test_folder_git_rules_work_without_checkout_local_exclusions(tmp_path: Path) -> None:
    from scripts.check_repository_boundaries import SUPPORTED_ROOT_DIRECTORIES

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    ignored: list[str] = []
    text_paths: list[str] = []
    for name in sorted(SUPPORTED_ROOT_DIRECTORIES):
        folder = tmp_path / name
        folder.mkdir()
        for rule in (".gitignore", ".gitattributes"):
            (folder / rule).write_bytes((ROOT / name / rule).read_bytes())
        ignored.extend(
            f"{name}/{path}"
            for path in (
                ".env",
                ".env.local",
                ".venv/bin/python",
                "build/payload",
                "node_modules/lib.js",
            )
        )
        text_paths.append(f"{name}/sample.py")
    result = subprocess.run(
        ["git", "-C", str(tmp_path), "check-ignore", "--no-index", "--stdin"],
        input="\n".join(ignored) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == ignored
    attributes = subprocess.run(
        ["git", "-C", str(tmp_path), "check-attr", "eol", "--stdin"],
        input="\n".join(text_paths) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    assert attributes.stdout.splitlines() == [f"{name}: eol: lf" for name in text_paths]
    permitted = subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "check-ignore",
            "--no-index",
            "--quiet",
            "backend/.env.example",
        ],
        check=False,
    )
    assert permitted.returncode == 1
