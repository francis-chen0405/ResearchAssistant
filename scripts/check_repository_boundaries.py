"""Fast, standard-library-only checks for the current repository layout."""

from __future__ import annotations

import ast
import json
import subprocess
from collections import Counter
from importlib.util import resolve_name
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Deliberately independent of the runtime/build lists: changing a bundle must not
# silently authorize another tracked root implementation.
SUPPORTED_ROOT_PYTHON: frozenset[str] = frozenset()
SUPPORTED_ROOT_FILES = frozenset({"README.md"})
SUPPORTED_ROOT_DIRECTORIES = frozenset(
    {
        "backend",
        "frontend",
        "desktop",
        "tests",
        "evaluations",
        "docs",
        "scripts",
        ".github",
        ".agent",
        ".agents",
    }
)
BASELINE = ROOT / "scripts/dependency-boundary-baseline.json"


def root_python_violations(root: Path) -> list[str]:
    tracked = (
        subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "*.py"],
            check=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    return [
        f"unsupported tracked root Python file: {name}"
        for name in sorted(set(tracked))
        if name and "/" not in name and name not in SUPPORTED_ROOT_PYTHON and (root / name).exists()
    ]


def root_layout_violations(root: Path) -> list[str]:
    """Check tracked owners, respecting pending working-tree removals during review."""
    tracked = (
        subprocess.run(["git", "-C", str(root), "ls-files", "-z"], check=True, capture_output=True)
        .stdout.decode("utf-8")
        .split("\0")
    )
    return [
        f"unsupported tracked root owner: {name}"
        for name in sorted(
            {path.split("/", 1)[0] for path in tracked if path and (root / path).exists()}
        )
        if name not in SUPPORTED_ROOT_FILES | SUPPORTED_ROOT_DIRECTORIES
    ]


def imported_names(source: str, package: str) -> list[str]:
    """Include lazy and TYPE_CHECKING imports, resolving relative imports."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = resolve_name("." * node.level + module, package)
            names.extend(f"{module}.{alias.name}" for alias in node.names)
    return names


def restricted_imports(root: Path) -> Counter[tuple[str, str]]:
    observed: Counter[tuple[str, str]] = Counter()
    for layer, forbidden in (
        ("contracts", ("providers", "agents", "research", "orchestrator")),
        ("storage", ("agents", "research", "orchestrator")),
    ):
        source = root / "backend/src"
        for path in sorted((source / "researchassistant" / layer).rglob("*.py")):
            relative = path.relative_to(root)
            package = ".".join(path.relative_to(source).parts[:-1])
            for target in imported_names(path.read_text(encoding="utf-8"), package):
                if any(
                    target == prefix or target.startswith(prefix + ".")
                    for name in forbidden
                    for prefix in (name, "researchassistant." + name)
                ):
                    observed[(relative.as_posix(), target)] += 1
    return observed


def dependency_violations(root: Path, baseline_path: Path) -> list[str]:
    baseline: Counter[tuple[str, str]] = Counter()
    for exception in json.loads(baseline_path.read_text(encoding="utf-8")):
        key = (exception["source"], exception["import"])
        if key in baseline or not exception["reason"].strip() or exception["count"] != 1:
            raise ValueError(f"invalid or duplicate dependency exception: {key}")
        baseline[key] = exception["count"]
    observed = restricted_imports(root)
    diagnostics = [
        f"new restricted import: {source} -> {target} ({count} additional occurrence(s))"
        for (source, target), count in sorted((observed - baseline).items())
    ]
    diagnostics.extend(
        f"remove stale baseline exception: {source} -> {target} ({count} occurrence(s))"
        for (source, target), count in sorted((baseline - observed).items())
    )
    return diagnostics


def main() -> int:
    diagnostics = (
        root_python_violations(ROOT)
        + root_layout_violations(ROOT)
        + dependency_violations(ROOT, BASELINE)
    )
    if diagnostics:
        print("Repository boundary violations:\n" + "\n".join(diagnostics))
        return 1
    print("Repository root and dependency boundaries passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
