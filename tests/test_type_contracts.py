from __future__ import annotations

import ast
import os
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".codebase-memory",
        ".git",
        ".hypothesis",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "env",
        "htmlcov",
        "node_modules",
        "site-packages",
        "venv",
    }
)


def _repository_python_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for directory, directory_names, filenames in os.walk(REPOSITORY_ROOT, topdown=True):
        directory_names[:] = sorted(
            name for name in directory_names if name not in EXCLUDED_DIRECTORY_NAMES
        )
        current_directory = Path(directory)
        files.extend(current_directory / name for name in sorted(filenames) if name.endswith(".py"))
    return tuple(sorted(files, key=lambda path: path.relative_to(REPOSITORY_ROOT).as_posix()))


class _TypeContractVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: Path) -> None:
        self._relative_path = relative_path
        self._scope: list[str] = []
        self._definition_context = ["module"]
        self.diagnostics: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node.name)
        self._definition_context.append("class")
        self.generic_visit(node)
        self._definition_context.pop()
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified_name = ".".join((*self._scope, node.name))
        positional_parameters = (*node.args.posonlyargs, *node.args.args)
        parameters = (*positional_parameters, *node.args.kwonlyargs)
        is_static_method = any(
            (isinstance(decorator, ast.Name) and decorator.id == "staticmethod")
            or (isinstance(decorator, ast.Attribute) and decorator.attr == "staticmethod")
            for decorator in node.decorator_list
        )
        receiver = (
            positional_parameters[0]
            if self._definition_context[-1] == "class"
            and not is_static_method
            and positional_parameters
            and positional_parameters[0].arg in {"self", "cls"}
            else None
        )
        for parameter in parameters:
            if parameter.annotation is None and parameter is not receiver:
                self._record(node, qualified_name, f"parameter {parameter.arg!r}")
        if node.args.vararg is not None and node.args.vararg.annotation is None:
            self._record(node, qualified_name, f"parameter '*{node.args.vararg.arg}'")
        if node.args.kwarg is not None and node.args.kwarg.annotation is None:
            self._record(node, qualified_name, f"parameter '**{node.args.kwarg.arg}'")
        if node.returns is None:
            self._record(node, qualified_name, "return")

        self._scope.append(node.name)
        self._definition_context.append("function")
        self.generic_visit(node)
        self._definition_context.pop()
        self._scope.pop()

    def _record(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        qualified_name: str,
        missing: str,
    ) -> None:
        self.diagnostics.append(
            f"{self._relative_path.as_posix()}:{node.lineno}: "
            f"{qualified_name}: missing {missing} annotation"
        )


def test_every_repository_python_function_has_complete_type_annotations() -> None:
    diagnostics: list[str] = []
    python_files = _repository_python_files()
    assert python_files, "no repository-owned Python files were discovered"

    for path in python_files:
        relative_path = path.relative_to(REPOSITORY_ROOT)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path.as_posix())
        except (SyntaxError, UnicodeError) as exc:
            diagnostics.append(
                f"{relative_path.as_posix()}:{getattr(exc, 'lineno', 1) or 1}: "
                f"unable to parse repository-owned Python file: {exc}"
            )
            continue

        visitor = _TypeContractVisitor(relative_path)
        visitor.visit(tree)
        diagnostics.extend(visitor.diagnostics)

    assert not diagnostics, "Repository type-contract violations:\n" + "\n".join(
        sorted(diagnostics)
    )
