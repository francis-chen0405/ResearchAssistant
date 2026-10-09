from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import BinaryIO
from uuid import UUID

import pytest

import researchassistant.evidence.brief_export as brief_export
from researchassistant.evidence.brief_export import BriefExportFormat, export_released_brief
from researchassistant.research.orchestrator import ProviderRunStatus
from researchassistant.storage.store import init_db


def _released_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, UUID]:
    run_id = UUID("11111111-1111-4111-8111-111111111111")
    brief = "# Released brief\n\nA validated finding.\n"
    result = SimpleNamespace(
        run_id=run_id,
        status=ProviderRunStatus.RELEASED,
        validation_result=SimpleNamespace(valid=True),
        final_brief=brief,
        rendered_brief_hash=sha256(brief.encode("utf-8")).hexdigest(),
    )
    monkeypatch.setattr(
        brief_export,
        "inspect_provider_run",
        lambda *_args, **_kwargs: result,
    )
    database = tmp_path / "run.sqlite3"
    init_db(str(database))
    return database, run_id


def test_export_refuses_dangling_symlink_without_writing_its_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database, run_id = _released_database(monkeypatch, tmp_path)
    target = tmp_path / "must-not-be-created.md"
    link = tmp_path / "export.md"
    link.symlink_to(target.name)

    with pytest.raises(FileExistsError):
        export_released_brief(
            database,
            str(run_id),
            link,
            BriefExportFormat.MARKDOWN,
            generated_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
        )

    assert link.is_symlink()
    assert not target.exists()


def test_export_does_not_overwrite_file_created_after_initial_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database, run_id = _released_database(monkeypatch, tmp_path)
    destination = tmp_path / "export.md"
    competitor_bytes = b"created by another process"

    def create_competing_file(_brief: str, _metadata: object) -> bytes:
        destination.write_bytes(competitor_bytes)
        return b"our rendered export"

    monkeypatch.setattr(brief_export, "_render_export", create_competing_file)

    with pytest.raises(FileExistsError):
        export_released_brief(
            database,
            str(run_id),
            destination,
            BriefExportFormat.MARKDOWN,
            generated_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
        )

    assert destination.read_bytes() == competitor_bytes


def test_export_removes_partial_file_after_write_setup_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database, run_id = _released_database(monkeypatch, tmp_path)
    destination = tmp_path / "export.md"
    original_fdopen = brief_export.os.fdopen

    def write_partial_then_fail(descriptor: int, mode: str) -> BinaryIO:
        output = original_fdopen(descriptor, mode)
        output.write(b"partial report")
        output.flush()
        output.close()
        raise OSError("simulated interrupted write")

    monkeypatch.setattr(brief_export.os, "fdopen", write_partial_then_fail)

    with pytest.raises(OSError, match="simulated interrupted write"):
        export_released_brief(
            database,
            str(run_id),
            destination,
            BriefExportFormat.MARKDOWN,
            generated_at=datetime(2026, 8, 10, 12, tzinfo=UTC),
        )

    assert not destination.exists()
