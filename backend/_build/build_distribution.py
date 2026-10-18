"""Preserve the exact build configuration as an installed identity resource."""

from pathlib import Path

from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self) -> None:
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
