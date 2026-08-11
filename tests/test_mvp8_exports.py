from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from zipfile import ZipFile

import pytest

import brief_export
from brief_export import BriefExportFormat, export_released_brief
from orchestrator import ProviderRunStatus

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
    monkeypatch.setattr(brief_export, "inspect_provider_run", lambda *_args: _released())
    destination = tmp_path / f"brief{suffix}"

    exported = export_released_brief(
        tmp_path / "run.sqlite3",
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
    monkeypatch.setattr(brief_export, "inspect_provider_run", lambda *_args: _released())
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"

    export_released_brief(
        tmp_path / "run.sqlite3", str(RUN_ID), first, BriefExportFormat.MARKDOWN, generated_at=WHEN
    )
    export_released_brief(
        tmp_path / "run.sqlite3", str(RUN_ID), second, BriefExportFormat.MARKDOWN, generated_at=WHEN
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
    monkeypatch.setattr(brief_export, "inspect_provider_run", lambda *_args: invalid)

    with pytest.raises(ValueError, match="only released"):
        export_released_brief(
            tmp_path / "run.sqlite3",
            str(RUN_ID),
            tmp_path / "brief.md",
            BriefExportFormat.MARKDOWN,
            generated_at=WHEN,
        )
