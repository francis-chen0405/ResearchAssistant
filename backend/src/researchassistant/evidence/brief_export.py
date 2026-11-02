"""Local, traceable exports for already released research briefs."""

from __future__ import annotations

import os
import zipfile
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID
from xml.sax.saxutils import escape

from pydantic import ConfigDict, Field, field_validator

from researchassistant.agents.v2_final_output import (
    V2_FINAL_OUTPUT_ARTIFACT_KEY,
    V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY,
    V2_FINAL_OUTPUT_PHASE13_ARTIFACT_KEY,
    render_v2_final_output,
)
from researchassistant.contracts.models import (
    DEFAULT_RESEARCH_CONTROLS,
    ResearchControls,
    StrictModel,
    V2FinalResearchOutput,
)
from researchassistant.contracts.provider_results import ProviderRunStatus
from researchassistant.evidence.released_output import validate_saved_output
from researchassistant.evidence.text_compatibility import xml_invalid_codepoints
from researchassistant.storage.provider_history import inspect_provider_run
from researchassistant.storage.store import (
    DatabaseReader,
    open_read_only_store,
    read_provider_run_contract,
    read_run,
    read_v2_artifact,
)

if TYPE_CHECKING:
    from researchassistant.api.inspection_contracts import V2EvidenceDisplay

EXPORTER_VERSION = "mvp8-local-export-v2"


class BriefExportFormat(StrEnum):
    MARKDOWN = "markdown"
    PDF = "pdf"
    DOCX = "docx"


class DOCXTextCompatibilityError(ValueError):
    """Released text cannot be represented in a DOCX XML document."""


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
    with open_read_only_store(db_path) as store:
        v2_output = _read_v2_final_output(store.connection, parsed_run_id)
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
            result = inspect_provider_run(db_path, parsed_run_id, source=store.connection)
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

        # Keep the signed release immutable; new exports are rendered from the
        # same admitted-evidence projection used by the result API.
        if v2_output is not None:
            from researchassistant.api.application_services.result_reads import (
                read_evidence,
            )

            try:
                display = read_evidence(db_path, parsed_run_id, source=store.connection)
            except KeyError:
                display = None
            export_brief = (display.reading_aid_markdown if display else None) or _v2_reading_aid(
                v2_output, display
            )
        else:
            export_brief = final_brief
        timestamp = generated_at or datetime.now(UTC)
        controls = _read_controls(store.connection, parsed_run_id)
    metadata = BriefExportMetadata(
        run_id=str(parsed_run_id),
        rendered_brief_hash=rendered_hash,
        format=export_format,
        generated_at=timestamp,
        exporter_version=EXPORTER_VERSION,
        research_controls=controls,
    )
    destination = Path(output_path).expanduser().absolute()
    if destination.suffix.lower() != _suffix_for(export_format):
        raise ValueError(f"export path must end in {_suffix_for(export_format)}")
    if os.path.lexists(destination):
        raise FileExistsError(f"refusing to overwrite existing export: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = _render_export(export_brief, metadata)
    # O_EXCL makes the no-overwrite guarantee hold even if another process creates
    # this path after the check above. Keeping the user-selected path unresolved
    # also ensures a dangling symlink is rejected instead of writing its target.
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
    identity = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        try:
            current = destination.lstat()
        except FileNotFoundError:
            pass
        else:
            if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                destination.unlink()
        raise
    return BriefExportResult(
        metadata=metadata,
        output_path=str(destination),
        content_sha256=sha256(payload).hexdigest(),
    )


def _v2_reading_aid(
    output: V2FinalResearchOutput, evidence: V2EvidenceDisplay | None = None
) -> str:
    """Describe saved fields without changing the signed release or inferring study identity."""
    if evidence is not None and evidence.reading_aid_markdown:
        return evidence.reading_aid_markdown
    lines = [
        "# Reading aid",
        "",
        f"Claim under review: {output.exact_claim}",
        "",
        "## Bottom line",
    ]
    if evidence is None:
        lines.append(
            "The detailed evidence is unavailable, so a conclusion cannot be assessed here."
        )
    elif evidence.items:
        lines.append(
            "The claim is not established by the admitted evidence. The available assessment "
            "does not establish the balance of evidence across independent studies."
        )
    else:
        lines.append(
            "No evidence was admitted for this result, so the claim cannot be established from it."
        )
    if evidence and evidence.items:
        lines.append(
            "Study identity and evidence balance have not been verified. "
            "Examples are selected by recorded claim fit, with a stable "
            "identifier used to break ties; they are not necessarily "
            "representative."
        )
        for relationship in ("supports", "challenges", "qualifies"):
            candidates = sorted(
                (
                    item
                    for item in evidence.items
                    if item.relationship_to_claim.value == relationship
                ),
                key=lambda item: (-(item.claim_fit or 0), str(item.ledger_claim_id)),
            )
            if candidates:
                item = candidates[0]
                label = {
                    "supports": "Supporting finding",
                    "challenges": "Contrasting finding",
                    "qualifies": "Qualification",
                }[relationship]
                lines.append(
                    f"- {label}: {item.approved_factual_statement} (Read at: {item.source_url}.)"
                )
    if evidence and evidence.study_opening:
        lines = lines[:5]
        for assertion in evidence.study_opening:
            item = next(
                item for item in evidence.items if item.ledger_claim_id == assertion.ledger_claim_id
            )
            lines.append(f"{assertion.text} (Read at: {item.source_url})")
    elif evidence and evidence.publication_opening:
        lines = lines[:5]
        for sentence in evidence.publication_opening:
            citations = [
                item.source_url
                for item in evidence.items
                if item.ledger_claim_id in sentence.ledger_claim_ids
            ]
            lines.append(f"{sentence.text} (Read at: {', '.join(citations)})")
        lines.append(
            "Grouped by verified publication; separate publications do not "
            "establish independent studies."
        )
    if not output.claim_coverage_map:
        lines.append("Claim coverage was not assessed; the reason was not recorded.")
    elif (
        (
            evidence
            and evidence.post_analysis_assessment
            and evidence.post_analysis_assessment.coverage_incomplete
        )
        or output.unresolved_material_gaps
        or any(
            item.coverage_state.value not in {"covered", "not_applicable"}
            for item in output.claim_coverage_map
        )
    ):
        lines.append("Coverage was assessed and gaps or incomplete dimensions remain.")
    else:
        lines.append(
            "Coverage was assessed and no gaps were recorded; this does not "
            "prove complete coverage."
        )
    direction = (
        "supporting and challenging evidence"
        if output.directions.support_enabled and output.directions.challenge_enabled
        else "supporting evidence only"
        if output.directions.support_enabled
        else "challenging evidence only"
    )
    lines.extend(("", f"Research direction: {direction}"))
    stop_labels = {
        "budget": (
            "A research limit stopped further work. Recorded allowances and "
            "usage are listed below; the specific exhausted limit was not "
            "identified."
        ),
        "hard_round_limit": "The research round limit stopped further searching.",
        "cancelled": "Research was cancelled before further work could be completed.",
        "sufficient_source_pool": (
            "The earlier search considered its source pool sufficient; this "
            "did not establish evidence sufficiency."
        ),
        "no_useful_new_direction": "No useful new search direction was identified.",
        "no_actionable_material_gap": "No actionable gap was identified for another search.",
        "no_productive_new_search": "No productive new search was identified.",
        "duplicate_heavy": "Search results substantially overlapped.",
        "provider_eligibility_exhausted": "No eligible search provider remained.",
        "degraded_gap_search_agent": "The follow-up search could not be completed.",
        "invalid_search_agent_plan": "The follow-up search plan could not be used.",
    }
    lines.extend(
        (
            "",
            "## Earlier search decision",
            stop_labels.get(
                output.stopping.reason.value,
                "The reason the search stopped was not recorded in a recognizable form.",
            ),
        )
    )
    if evidence:
        lines.extend(evidence.budget_context)
    queue_stop_labels = {
        "physical_call_ceiling": "The recorded call limit prevented source analysis.",
        "token_reserve": "The recorded token allowance could not reserve source analysis.",
        "cost_reserve": "The recorded money allowance could not reserve source analysis.",
        "backfill_replaced": "Another source was selected for the available analysis slot.",
    }
    local_stop_labels = {
        "source_budget_blocked": (
            "A source-specific allowance prevented further analysis; its "
            "amount was not recorded here."
        ),
        "token_cap_blocked": (
            "A source-specific token limit prevented further analysis; its "
            "amount was not recorded here."
        ),
        "physical_call_cap_blocked": (
            "A source-specific call limit prevented further analysis; its "
            "amount was not recorded here."
        ),
    }
    for outcome in evidence.source_budget_outcomes if evidence else ():
        source = next(
            (item for item in output.all_surviving_sources if item.source_id == outcome.source_id),
            None,
        )
        label = local_stop_labels.get(
            outcome.outcome,
            "A source-specific limit prevented further analysis; its details were not recorded.",
        )
        lines.append(f"- {source.title if source and source.title else 'Source'}: {label}")
    for source in output.all_surviving_sources:
        if source.status.value == "budget_prevented_analysis" and not any(
            outcome.source_id == source.source_id
            for outcome in (evidence.source_budget_outcomes if evidence else ())
        ):
            reason = source.budget_prevented_reason.value if source.budget_prevented_reason else ""
            explanation = queue_stop_labels.get(
                reason, "The limit that prevented source analysis was not recorded."
            )
            lines.append(f"- {source.title or 'Source'}: {explanation}")
    lines.extend(("", "## Admitted evidence and reading locations"))
    if evidence and evidence.items:
        for item in evidence.items:
            publication = item.verified_publication
            if publication:
                title = publication.title or "Title not recorded"
                author = ", ".join(publication.authors) or "Author not recorded"
                date = publication.publication_date or "Year not recorded"
                venue = publication.venue or "Venue not recorded"
                basis = (
                    "Crossref DOI lookup"
                    if publication.verification == "crossref_doi"
                    else "reviewed authoritative identifier"
                )
                citation = (
                    f"{title}; {author}; {date}; {venue}; {publication.canonical_url} ({basis})"
                )
            else:
                citation = (
                    f"Recorded title: {item.title or 'Not recorded'}; "
                    "Publication identity is not verified here"
                )
            lines.append(
                f"- {item.approved_factual_statement}\n  {citation}. Read at: {item.source_url}."
            )
            lines.append("  Recorded passage (may be incomplete; check the source context):")
            lines.append("  " + item.quote_passage)
            if item.limitations:
                lines.append("  Recorded limitations: " + " ".join(item.limitations))
            lines.append("  Recorded source type: " + (item.source_type or "Not recorded"))
    else:
        lines.append("- Detailed admitted passages are unavailable or none were admitted.")
    lines.extend(
        (
            "",
            "## Original released brief",
            (
                "The original released brief and its recorded hash remain "
                "unchanged in the research history. This report is generated from "
                "saved evidence."
            ),
        )
    )
    return "\n".join(lines)


def _read_v2_final_output(source: DatabaseReader, run_id: UUID) -> V2FinalResearchOutput | None:
    for artifact_key in (
        V2_FINAL_OUTPUT_ARTIFACT_KEY,
        V2_FINAL_OUTPUT_PHASE13_ARTIFACT_KEY,
        V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY,
    ):
        try:
            artifact = read_v2_artifact(source, run_id, artifact_key)
        except KeyError:
            continue
        break
    else:
        return None
    if artifact.artifact_type != V2FinalResearchOutput.__name__:
        raise ValueError("v2 final output artifact has an unexpected type")
    return validate_saved_output(
        V2FinalResearchOutput.model_validate_json(artifact.payload_json),
        run_id,
        read_run(source, run_id),
    )


def _parse_run_id(value: str) -> UUID:
    return UUID(value)


def _read_controls(source: DatabaseReader, run_id: UUID) -> ResearchControls:
    try:
        contract = read_provider_run_contract(source, run_id)
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
        "> **Human review required:** The recorded hash identifies the saved released brief. "
        "Deterministic validation does not establish factual infallibility.\n\n"
    )
    return trace + warning + brief


def _pdf(text: str) -> bytes:
    # Inspection sessions have closed before any slow layout/font embedding.
    from researchassistant.evidence.pdf_render import render_pdf_text

    return render_pdf_text(text)


def _docx(text: str, metadata: BriefExportMetadata) -> bytes:
    from io import BytesIO

    unsupported = xml_invalid_codepoints(text)
    if unsupported:
        codes = ", ".join(f"U+{value:04X}" for value in unsupported[:12])
        raise DOCXTextCompatibilityError(
            f"DOCX XML cannot represent {codes}; use Markdown to preserve the original text"
        )
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
