from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from zipfile import ZipFile

import pytest

import researchassistant.evidence.brief_export as brief_export
import researchassistant.storage.store as store
from researchassistant.evidence.brief_export import BriefExportFormat, export_released_brief
from researchassistant.research.orchestrator import ProviderRunStatus
from researchassistant.storage.store import DatabaseCompatibilityResult, init_db

RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
BRIEF = (
    "# Research Brief\n\nClaim under review: A precise claim.\n\n"
    "## Supporting Evidence\n"
    "- Direct supporting evidence: The approved factual sentence remains exact. "
    "[source: https://example.test/source]\n"
)
WHEN = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def _released() -> SimpleNamespace:
    rendered_hash = sha256(BRIEF.encode("utf-8")).hexdigest()
    return SimpleNamespace(
        run_id=RUN_ID,
        status=ProviderRunStatus.RELEASED,
        validation_result=SimpleNamespace(valid=True),
        final_brief=BRIEF,
        rendered_brief_hash=rendered_hash,
    )


def _inspector(result: SimpleNamespace) -> Callable[..., SimpleNamespace]:
    def inspect(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return result

    return inspect


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "run.sqlite3"
    init_db(str(database))
    return database


@pytest.mark.parametrize(
    ("export_format", "suffix"),
    [
        (BriefExportFormat.MARKDOWN, ".md"),
        (BriefExportFormat.PDF, ".pdf"),
        (BriefExportFormat.DOCX, ".docx"),
    ],
)
def test_export_released_brief_is_local_and_traceable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    export_format: BriefExportFormat,
    suffix: str,
) -> None:
    monkeypatch.setattr(brief_export, "inspect_provider_run", _inspector(_released()))
    destination = tmp_path / f"brief{suffix}"
    database = _database(tmp_path)

    exported = export_released_brief(
        database,
        str(RUN_ID),
        destination,
        export_format,
        generated_at=WHEN,
    )

    assert destination.is_file()
    assert exported.metadata.run_id == str(RUN_ID)
    assert exported.metadata.rendered_brief_hash == sha256(BRIEF.encode("utf-8")).hexdigest()
    assert exported.metadata.generated_at == WHEN
    if export_format is BriefExportFormat.MARKDOWN:
        content = destination.read_text(encoding="utf-8")
        assert "generated_at: 2026-08-10T12:00:00Z" in content
        assert "The approved factual sentence remains exact." in content
        assert "Human review required" in content
    if export_format is BriefExportFormat.PDF:
        assert destination.read_bytes().startswith(b"%PDF-1.4")
    if export_format is BriefExportFormat.DOCX:
        with ZipFile(destination) as archive:
            assert "word/document.xml" in archive.namelist()
            assert str(RUN_ID) in archive.read("docProps/core.xml").decode("utf-8")


def test_markdown_export_is_deterministic_for_fixed_generation_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(brief_export, "inspect_provider_run", _inspector(_released()))
    database = _database(tmp_path)
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"

    export_released_brief(
        database, str(RUN_ID), first, BriefExportFormat.MARKDOWN, generated_at=WHEN
    )
    export_released_brief(
        database, str(RUN_ID), second, BriefExportFormat.MARKDOWN, generated_at=WHEN
    )

    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize(
    "status",
    [
        ProviderRunStatus.BLOCKED,
        ProviderRunStatus.FAILED,
        ProviderRunStatus.CANCELLED,
        ProviderRunStatus.RUNNING,
    ],
)
def test_export_rejects_nonreleased_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: ProviderRunStatus
) -> None:
    invalid = _released()
    invalid.status = status
    invalid.validation_result = SimpleNamespace(valid=False)
    monkeypatch.setattr(brief_export, "inspect_provider_run", _inspector(invalid))

    with pytest.raises(ValueError, match="only released"):
        export_released_brief(
            _database(tmp_path),
            str(RUN_ID),
            tmp_path / "brief.md",
            BriefExportFormat.MARKDOWN,
            generated_at=WHEN,
        )


def test_export_reuses_one_validated_snapshot_and_closes_it_before_render(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database = _database(tmp_path)
    opened: list[sqlite3.Connection] = []
    validation_count = 0
    original_connect = store.connect_database
    original_validate = store._validate_read_only_schema

    def track_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = original_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    def count_validation(connection: sqlite3.Connection) -> DatabaseCompatibilityResult:
        nonlocal validation_count
        validation_count += 1
        return original_validate(connection)

    def assert_closed_before_render(_text: str, _metadata: object) -> bytes:
        assert validation_count == 1
        assert len(opened) == 1
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            opened[0].execute("SELECT 1")
        return b"rendered after snapshot release"

    monkeypatch.setattr(store, "connect_database", track_connect)
    monkeypatch.setattr(store, "_validate_read_only_schema", count_validation)
    monkeypatch.setattr(brief_export, "inspect_provider_run", _inspector(_released()))
    monkeypatch.setattr(brief_export, "_render_export", assert_closed_before_render)

    export_released_brief(
        database,
        str(RUN_ID),
        tmp_path / "brief.md",
        BriefExportFormat.MARKDOWN,
        generated_at=WHEN,
    )

    assert validation_count == 1
