"""Local, traceable exports for already released research briefs."""

from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from uuid import UUID
from xml.sax.saxutils import escape

from pydantic import ConfigDict, Field, field_validator

from agents.v2_final_output import V2_FINAL_OUTPUT_ARTIFACT_KEY, render_v2_final_output
from models import DEFAULT_RESEARCH_CONTROLS, ResearchControls, StrictModel, V2FinalResearchOutput
from orchestrator import ProviderRunStatus, inspect_provider_run
from store import open_read_only_store, read_provider_run_contract, read_v2_artifact

EXPORTER_VERSION = "mvp8-local-export-v1"


class BriefExportFormat(StrEnum):
    MARKDOWN = "markdown"
    PDF = "pdf"
    DOCX = "docx"


class BriefExportMetadata(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    rendered_brief_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    format: BriefExportFormat
    generated_at: datetime
    exporter_version: str = Field(min_length=1)
    research_controls: ResearchControls = DEFAULT_RESEARCH_CONTROLS

    _generated_at_is_aware = field_validator("generated_at")(
        lambda value: _require_aware(value, "generated_at")
    )


class BriefExportResult(StrictModel):
    metadata: BriefExportMetadata
    output_path: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def export_released_brief(
    db_path: str | Path,
    run_id: str,
    output_path: str | Path,
    export_format: BriefExportFormat,
    *,
    generated_at: datetime | None = None,
) -> BriefExportResult:
    """Write one local report only after re-verifying a released persisted run."""
    parsed_run_id = _parse_run_id(run_id)
    v2_output = _read_v2_final_output(db_path, parsed_run_id)
    if v2_output is not None:
        if not v2_output.release_validation.valid:
            raise ValueError("only released runs with valid final validation may be exported")
        final_brief = render_v2_final_output(v2_output)
        rendered_hash = v2_output.release_validation.rendered_output_hash
        if (
            rendered_hash is None
            or sha256(final_brief.encode("utf-8")).hexdigest() != rendered_hash
        ):
            raise ValueError("released v2 brief hash does not match reconstructed brief")
    else:
        result = inspect_provider_run(db_path, parsed_run_id)
        if result.status is not ProviderRunStatus.RELEASED:
            raise ValueError("only released runs with valid final validation may be exported")
        if result.validation_result is None or not result.validation_result.valid:
            raise ValueError("only released runs with valid final validation may be exported")
        if result.final_brief is None or result.rendered_brief_hash is None:
            raise ValueError("released run has no reconstructable final brief")
        final_brief = result.final_brief
        rendered_hash = result.rendered_brief_hash
        if sha256(final_brief.encode("utf-8")).hexdigest() != rendered_hash:
            raise ValueError("released brief hash does not match reconstructed brief")

    timestamp = generated_at or datetime.now(UTC)
    controls = _read_controls(db_path, parsed_run_id)
    metadata = BriefExportMetadata(
        run_id=str(parsed_run_id),
        rendered_brief_hash=rendered_hash,
        format=export_format,
        generated_at=timestamp,
        exporter_version=EXPORTER_VERSION,
        research_controls=controls,
    )
    destination = Path(output_path).resolve()
    if destination.suffix.lower() != _suffix_for(export_format):
        raise ValueError(f"export path must end in {_suffix_for(export_format)}")
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing export: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = _render_export(final_brief, metadata)
    destination.write_bytes(payload)
    return BriefExportResult(
        metadata=metadata,
        output_path=str(destination),
        content_sha256=sha256(payload).hexdigest(),
    )


def _read_v2_final_output(db_path: str | Path, run_id: UUID) -> V2FinalResearchOutput | None:
    if not Path(db_path).is_file():
        return None
    with open_read_only_store(db_path) as store:
        try:
            artifact = read_v2_artifact(store.connection, run_id, V2_FINAL_OUTPUT_ARTIFACT_KEY)
        except KeyError:
            return None
    if artifact.artifact_type != V2FinalResearchOutput.__name__:
        raise ValueError("v2 final output artifact has an unexpected type")
    return V2FinalResearchOutput.model_validate_json(artifact.payload_json)


def _parse_run_id(value: str) -> UUID:
    return UUID(value)


def _read_controls(db_path: str | Path, run_id: UUID) -> ResearchControls:
    if not Path(db_path).is_file():
        return DEFAULT_RESEARCH_CONTROLS
    with open_read_only_store(db_path) as store:
        try:
            contract = read_provider_run_contract(store.connection, run_id)
        except KeyError:
            return DEFAULT_RESEARCH_CONTROLS
    return ResearchControls.from_policy_identity(contract.policy_identity)


def _require_aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value


def _suffix_for(export_format: BriefExportFormat) -> str:
    return {
        BriefExportFormat.MARKDOWN: ".md",
        BriefExportFormat.PDF: ".pdf",
        BriefExportFormat.DOCX: ".docx",
    }[export_format]


def _render_export(brief: str, metadata: BriefExportMetadata) -> bytes:
    if metadata.format is BriefExportFormat.MARKDOWN:
        return _markdown(brief, metadata).encode("utf-8")
    if metadata.format is BriefExportFormat.PDF:
        return _pdf(_markdown(brief, metadata))
    if metadata.format is BriefExportFormat.DOCX:
        return _docx(_markdown(brief, metadata), metadata)
    raise ValueError(f"unsupported export format: {metadata.format}")


def _markdown(brief: str, metadata: BriefExportMetadata) -> str:
    timestamp = metadata.generated_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    trace = (
        "<!-- ResearchAssistant export\n"
        f"run_id: {metadata.run_id}\n"
        f"rendered_brief_hash: {metadata.rendered_brief_hash}\n"
        f"generated_at: {timestamp}\n"
        f"exporter_version: {metadata.exporter_version}\n"
        f"research_controls: {metadata.research_controls.canonical_json()}\n"
        "-->\n\n"
    )
    warning = (
        "> **Human review required:** This locally exported report preserves the "
        "released brief. Deterministic validation does not establish factual infallibility.\n\n"
    )
    return trace + warning + brief


def _pdf(text: str) -> bytes:
    lines = [line.encode("latin-1", "replace").decode("latin-1") for line in text.splitlines()]
    body = ["BT", "/F1 9 Tf", "50 760 Td", "12 TL"]
    for line in lines:
        body.append(f"({_escape_pdf_text(line)}) Tj")
        body.append("T*")
    body.append("ET")
    stream = "\n".join(body).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(output)


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _docx(text: str, metadata: BriefExportMetadata) -> bytes:
    from io import BytesIO

    paragraphs = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>'
        for line in text.splitlines()
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body></w:document>"
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        "<cp:coreProperties "
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Research Brief</dc:title>'
        "<dc:description>"
        f"run_id={metadata.run_id}; rendered_brief_hash={metadata.rendered_brief_hash}; "
        f"exporter_version={metadata.exporter_version}</dc:description>"
        "</cp:coreProperties>"
    )
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES)
        archive.writestr("_rels/.rels", _DOCX_RELATIONSHIPS)
        archive.writestr("word/document.xml", document)
        archive.writestr("docProps/core.xml", core)
    return payload.getvalue()


_DOCX_CONTENT_TYPES = (
    '<?xml version="1.0"?><Types '
    'xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/docProps/core.xml" '
    'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    "</Types>"
)
_DOCX_RELATIONSHIPS = (
    '<?xml version="1.0"?><Relationships '
    'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    '<Relationship Id="rId2" '
    'Type="http://schemas.openxmlformats.org/package/2006/relationships/'
    'metadata/core-properties" '
    'Target="docProps/core.xml"/></Relationships>'
)
