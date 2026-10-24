"""Both older evaluation commands protect frozen inputs and report publication."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from evaluations import output_publication, run_evaluations, source_discovery
from evaluations.evaluator import evaluate_corpus, verify_summary_agreement


@pytest.mark.parametrize("command", ["phase10", "discovery"])
@pytest.mark.parametrize("collision", ["input", "symlink", "hardlink", "same_reports", "existing"])
def test_cli_refuses_collisions_before_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    collision: str,
) -> None:
    source = (
        run_evaluations.DEFAULT_CORPUS_PATH
        if command == "phase10"
        else source_discovery.DEFAULT_MANIFEST
    )
    manifest = tmp_path / "frozen.json"
    shutil.copyfile(source, manifest)
    json_path = tmp_path / "report.json"
    summary_path = tmp_path / "report.md"
    if collision == "input":
        json_path = manifest
    elif collision == "symlink":
        json_path.symlink_to(manifest)
    elif collision == "hardlink":
        os.link(manifest, json_path)
    elif collision == "same_reports":
        summary_path = json_path
    else:
        json_path.write_bytes(b"previous immutable evidence")
    before = {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("output validation must precede any evaluation/provider work")

    if command == "phase10":
        monkeypatch.setattr(run_evaluations, "evaluate_corpus", forbidden)
        code = run_evaluations.main(
            [
                "--corpus",
                str(manifest),
                "--json-output",
                str(json_path),
                "--summary-output",
                str(summary_path),
                "--enable-live",
            ]
        )
    else:
        monkeypatch.setattr(source_discovery, "evaluate_manifest", forbidden)
        code = source_discovery.main(
            [
                "--manifest",
                str(manifest),
                "--json-output",
                str(json_path),
                "--summary-output",
                str(summary_path),
            ]
        )
    assert code == 2
    assert {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before


def test_regression_artifact_cannot_be_replaced_by_phase10_report(tmp_path: Path) -> None:
    root = tmp_path / "case"
    root.mkdir()
    manifest = root / "offline-corpus.json"
    shutil.copyfile(run_evaluations.DEFAULT_CORPUS_PATH, manifest)
    evidence = root / "regression-fixtures"
    shutil.copytree(run_evaluations.DEFAULT_CORPUS_PATH.parent / evidence.name, evidence)
    target = evidence / "integrity-attacks.json"
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert (
        run_evaluations.main(
            [
                "--corpus",
                str(manifest),
                "--json-output",
                str(target),
                "--summary-output",
                str(root / "summary.md"),
            ]
        )
        == 2
    )
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


@pytest.mark.slow
@pytest.mark.parametrize("command", ["phase10", "discovery"])
def test_failed_publication_preserves_concurrent_output_and_unrelated_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    original = output_publication.create_private_file
    sentinel = tmp_path / "keep.txt"
    sentinel.write_bytes(b"unrelated existing file")
    first, second = tmp_path / "report.json", tmp_path / "report.md"

    def fail_second(path: Path) -> int:
        if path == second:
            path.write_bytes(b"concurrent report owner")
            raise FileExistsError("concurrent writer")
        return original(path)

    monkeypatch.setattr(output_publication, "create_private_file", fail_second)
    main: Callable[[list[str]], int]
    main = run_evaluations.main if command == "phase10" else source_discovery.main
    assert main(["--json-output", str(first), "--summary-output", str(second)]) == 2
    assert not first.exists()
    assert second.read_bytes() == b"concurrent report owner"
    assert sentinel.read_bytes() == b"unrelated existing file"


@pytest.mark.slow
@pytest.mark.parametrize("command", ["phase10", "discovery"])
def test_fresh_reports_keep_existing_scoring_and_derived_summary(
    tmp_path: Path,
    command: str,
) -> None:
    first, second = tmp_path / "reports/report.json", tmp_path / "reports/report.md"
    main = run_evaluations.main if command == "phase10" else source_discovery.main
    assert main(["--json-output", str(first), "--summary-output", str(second)]) == 0
    machine = json.loads(first.read_bytes())
    human = second.read_text()
    if command == "phase10":
        report = evaluate_corpus(run_evaluations.DEFAULT_CORPUS_PATH)
        assert machine == report.model_dump(mode="json")
        assert verify_summary_agreement(report, human)
    else:
        report = source_discovery.EvaluationReport.model_validate(machine)
        assert human == source_discovery.render_report(report)
        assert report.synthetic_only and all(row.model_calls == 0 for row in report.scenarios)
