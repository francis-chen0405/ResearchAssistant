"""Pinned acquisition staging must preserve reviewed upstream and policy bytes."""

import hashlib
import json
from pathlib import Path

import pytest

import desktop.build as build


def test_acquisition_staging_applies_policy_to_reviewed_upstream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = Path(__file__).resolve().parents[1] / "desktop/acquisition"
    upstream = source / "node_modules/wigolo/dist/cache/db.js"
    if not upstream.exists():
        pytest.skip("locked Wigolo dependencies are not installed")
    monkeypatch.setattr(build, "RESOURCES", tmp_path / "resources")
    build.stage_acquisition(source)
    staged = tmp_path / "resources/acquisition/node_modules/wigolo/dist/cache"
    expected = (
        'import { prepareCacheConnection } from "./ra-cache-policy.mjs";\n'
        + upstream.read_text().replace(
            "  instance = db;", "  prepareCacheConnection(db);\n  instance = db;"
        )
    )
    assert (staged / "db.js").read_text() == expected
    assert (staged / "ra-cache-policy.mjs").read_bytes() == (
        source / "cache-policy.mjs"
    ).read_bytes()
    assert hashlib.sha256(upstream.read_bytes()).hexdigest() == (
        "3fbee2a93d4424d2174fd758141b945d54aa198e24a030482c7101ce485385f1"
    )
    assert json.loads((staged.parents[1] / "package.json").read_text())["version"] == "0.2.1"


def test_acquisition_staging_refuses_unreviewed_upstream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    upstream = source / "node_modules/wigolo/dist/cache/db.js"
    upstream.parent.mkdir(parents=True)
    upstream.write_text("// unreviewed upstream")
    destination = tmp_path / "resources/acquisition"
    destination.mkdir(parents=True)
    preserved = destination / "preserved"
    preserved.write_text("previous verified resources")
    monkeypatch.setattr(build, "RESOURCES", destination.parent)
    with pytest.raises(RuntimeError, match="reviewed 0.2.1"):
        build.stage_acquisition(source)
    assert preserved.read_text() == "previous verified resources"
