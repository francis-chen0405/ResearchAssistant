"""DOCX exports reject unrepresentable text before writing any destination."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
import test_product_discovery_pipeline as product
from test_mvp8_exports import BRIEF, RUN_ID, WHEN, _database, _inspector, _released

from researchassistant.contracts.models import DiscoveryProvider, ResearchControls
from researchassistant.evidence import brief_export
from researchassistant.evidence.brief_export import (
    BriefExportFormat,
    BriefExportMetadata,
    DOCXTextCompatibilityError,
    _docx,
    export_released_brief,
)
from researchassistant.evidence.text_compatibility import xml_invalid_codepoints


@pytest.mark.parametrize("codepoint", [*range(0x20), 0xD800, 0xDFFF, 0xFFFE, 0xFFFF])
def test_docx_xml_character_boundaries(codepoint: int) -> None:
    text = chr(codepoint)
    metadata = BriefExportMetadata(
        run_id=str(RUN_ID),
        rendered_brief_hash="a" * 64,
        format=BriefExportFormat.DOCX,
        generated_at=WHEN,
        exporter_version="fixture",
    )
    if text in "\t\n\r":
        assert _docx(text, metadata)
    else:
        assert xml_invalid_codepoints(text) == (codepoint,)
        with pytest.raises(DOCXTextCompatibilityError, match="use Markdown"):
            _docx(text, metadata)


@pytest.mark.parametrize("text", ["\x00", "\x01", "\x0b", "\x0c", "\ufffe", "\uffff"])
def test_unsupported_docx_preserves_brief_hash_and_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, text: str
) -> None:
    released = _released()
    released.final_brief = BRIEF + text
    released.rendered_brief_hash = sha256(released.final_brief.encode("utf-8")).hexdigest()
    monkeypatch.setattr(brief_export, "inspect_provider_run", _inspector(released))
    database = _database(tmp_path)
    before = database.read_bytes()
    destination = tmp_path / "rejected.docx"
    with pytest.raises(DOCXTextCompatibilityError, match="DOCX XML cannot represent"):
        export_released_brief(database, str(RUN_ID), destination, BriefExportFormat.DOCX)
    assert not destination.exists()
    markdown = tmp_path / "preserved.md"
    exported = export_released_brief(database, str(RUN_ID), markdown, BriefExportFormat.MARKDOWN)
    assert markdown.read_bytes().endswith(released.final_brief.encode("utf-8"))
    assert exported.metadata.rendered_brief_hash == released.rendered_brief_hash
    assert database.read_bytes() == before


def test_docx_valid_markup_unicode_tabs_and_lines_are_well_formed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    released = _released()
    text = '< & > "quotes"\tRésumé 中文 😀\nالعربية\nsecond line'
    released.final_brief = BRIEF + text
    released.rendered_brief_hash = sha256(released.final_brief.encode("utf-8")).hexdigest()
    monkeypatch.setattr(brief_export, "inspect_provider_run", _inspector(released))
    database = _database(tmp_path)
    destination = tmp_path / "valid.docx"
    exported = export_released_brief(
        database, str(RUN_ID), destination, BriefExportFormat.DOCX, generated_at=WHEN
    )
    with ZipFile(destination) as archive:
        for name in archive.namelist():
            ElementTree.fromstring(archive.read(name))
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = [node.text or "" for node in root.findall(".//w:t", namespace)]
    assert all(line in paragraphs for line in text.splitlines())
    assert exported.metadata.rendered_brief_hash == released.rendered_brief_hash
    assert exported.content_sha256 == sha256(destination.read_bytes()).hexdigest()
    assert not xml_invalid_codepoints("\t\n\r \ud7ff\ue000\ufffd\U00010000\U0010ffff")


def test_actual_released_control_character_cannot_create_malformed_docx(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(product.production, "CLAIM", product.production.CLAIM + " \x01")
    database = tmp_path / "generated.sqlite3"
    result, _, _ = product._run(
        database, ResearchControls(discovery_providers=(DiscoveryProvider.EXA,))
    )
    assert result.state.value == "released", result.failure_reason
    before = database.read_bytes()
    destination = tmp_path / "released.docx"
    with pytest.raises(DOCXTextCompatibilityError, match="U\\+0001"):
        export_released_brief(database, str(result.run_id), destination, BriefExportFormat.DOCX)
    assert not destination.exists()
    assert database.read_bytes() == before
