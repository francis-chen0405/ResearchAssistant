"""Preserve the exact build configuration as an installed identity resource."""

from distutils.dir_util import remove_tree
from pathlib import Path

from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self) -> None:
        if not self.editable_mode:
            destination = Path(self.build_lib)
            managed = Path.cwd() / "build"
            if (
                managed.is_symlink()
                or destination.is_symlink()
                or destination.resolve() == managed.resolve()
                or not destination.resolve().is_relative_to(managed.resolve())
            ):
                raise ValueError("wheel output must be below the managed build directory")
            # Setuptools copies new files but does not remove deleted modules from
            # a reused build/lib tree. A wheel must contain only current sources.
            if destination.exists():
                # Its remover also clears setuptools' cached created-directory
                # state, so repeated builds in one process recreate package dirs.
                remove_tree(str(destination))
                if destination.exists():
                    raise RuntimeError("could not clean the managed wheel build directory")
        super().run()
        if not self.editable_mode:
            destination = Path(self.build_lib) / "researchassistant/_distribution/pyproject.toml"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(Path("pyproject.toml").read_bytes())

    def get_outputs(self, include_bytecode: bool = True) -> list[str]:
        outputs = super().get_outputs(include_bytecode)
        if not self.editable_mode:
            outputs.append(
                str(Path(self.build_lib) / "researchassistant/_distribution/pyproject.toml")
            )
        return outputs
