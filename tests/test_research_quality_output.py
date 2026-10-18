"""Benchmark publication never overwrites frozen inputs or pre-existing outputs."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from evaluations.research_quality import DEFAULT_MANIFEST, main


@pytest.mark.parametrize("collision", ["manifest", "artifact", "symlink", "hardlink"])
def test_report_refuses_input_and_alias_collisions(tmp_path: Path, collision: str) -> None:
    root = tmp_path / "bundle"
    shutil.copytree(DEFAULT_MANIFEST.parent / "fixture_bundle", root)
    manifest = root / "manifest.json"
    output = tmp_path / "output"
    output.mkdir()
    target = output / "results.json"
    if collision == "manifest":
        manifest.rename(target)
        # Artifact paths are relative to the relocated manifest.
        for item in root.iterdir():
            shutil.copy2(item, output / item.name)
        manifest = target
    elif collision == "artifact":
        output = root
        target = output / "summary.md"
        shutil.copy2(root / "handoff.json", target)
    elif collision == "symlink":
        target.symlink_to(manifest)
    else:
        os.link(manifest, target)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert main(["--manifest", str(manifest), "--output-dir", str(output)]) == 2
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_failed_second_publication_removes_only_its_own_first_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from researchassistant.platform_support import private_files

    original = private_files.create_private_file
    unrelated = tmp_path / "keep.txt"
    unrelated.write_text("existing user file")

    def fail_second(path: Path) -> int:
        if path.name == "summary.md":
            path.write_text("concurrent owner")
            raise FileExistsError("concurrent output")
        return original(path)

    monkeypatch.setattr(private_files, "create_private_file", fail_second)
    fixture = DEFAULT_MANIFEST.parent / "fixture_bundle/manifest.json"
    assert main(["--manifest", str(fixture), "--output-dir", str(tmp_path)]) == 2
    assert not (tmp_path / "results.json").exists()
    assert (tmp_path / "summary.md").read_text() == "concurrent owner"
    assert unrelated.read_text() == "existing user file"
