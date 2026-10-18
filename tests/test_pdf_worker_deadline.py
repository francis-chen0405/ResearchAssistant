"""A real owned subprocess bounds parser stalls, including its first/final page."""

from __future__ import annotations

import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from researchassistant.providers import normalization


@pytest.mark.parametrize("phase", ["constructor", "pages", "extract"])
def test_stalled_pdf_parser_is_killed_at_overall_deadline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, phase: str
) -> None:
    original = subprocess.Popen
    processes: list[subprocess.Popen[bytes]] = []
    marker = tmp_path / "parser-phase-entered"
    script = f"""
import time
from pathlib import Path
from researchassistant.providers import normalization, pdf_worker
class Page:
    def extract_text(self) -> str:
        if {phase!r} == "extract":
            Path({str(marker)!r}).write_text("extract")
            time.sleep(10)
        return "A valid generated source sentence."
class Reader:
    is_encrypted = False
    def __init__(self, *args: object, **kwargs: object) -> None:
        if {phase!r} == "constructor":
            Path({str(marker)!r}).write_text("constructor")
            time.sleep(10)
    @property
    def pages(self) -> list[Page]:
        if {phase!r} == "pages":
            Path({str(marker)!r}).write_text("pages")
            time.sleep(10)
        return [Page()]
normalization.PdfReader = Reader
pdf_worker.main()
"""

    def spawn(command: list[str], **kwargs: object) -> subprocess.Popen[bytes]:
        process = original([sys.executable, "-c", script], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(normalization.subprocess, "Popen", spawn)
    started = time.monotonic()
    with pytest.raises(normalization.NormalizationError) as error:
        normalization.normalize_pdf(b"generated fixture", deadline_seconds=1.5)
    assert error.value.code == normalization.NormalizationFailureCode.PDF_TIMEOUT
    assert time.monotonic() - started < 5
    assert marker.read_text() == phase
    assert len(processes) == 1 and processes[0].poll() is not None


def test_pdf_worker_returns_deterministic_generated_text() -> None:
    buffer = BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(72, 700, "An exact generated source sentence.")
    canvas.save()
    first = normalization.normalize_pdf(buffer.getvalue())
    second = normalization.normalize_pdf(buffer.getvalue())
    assert first == second
    assert first.text == "Page 1\nAn exact generated source sentence."
    assert first.pdf_policy_version == "ra-digital-pdf-v2"
