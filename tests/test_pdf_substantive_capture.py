"""Later-page PDF findings survive bounded capture and remain source-owned."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

from reportlab.pdfgen.canvas import Canvas

from researchassistant.contracts.discovery_v2 import V2PreviewRequest, discovery_id
from researchassistant.contracts.research_directions import ResearchDirection, ResearchDirections
from researchassistant.contracts.scraping import ScrapeResponse
from researchassistant.evidence.evidence_core import build_source_snapshot
from researchassistant.evidence.source_excerpt import (
    EXTRACTION_EXCERPT_BYTES,
    extraction_source_view,
)
from researchassistant.providers.normalization import (
    PDF_CAPTURE_WORD_LIMIT,
    PDF_NORMALIZATION_VERSION,
    PDF_OMISSION_MARKER,
    PDF_POLICY_VERSION,
    _document_from_pdf_pages,
    locate_exact_quotes,
    normalize_pdf,
)
from researchassistant.research.source_preview import build_claim_preview

FINDING = (
    "Measured biodiversity loss preceded a higher recorded extinction risk in the controlled study."
)


def _later_finding_pdf() -> bytes:
    output = BytesIO()
    canvas = Canvas(output)
    for page in range(1, 31):
        heading = (
            "Key findings"
            if page == 25
            else ("Acknowledgements" if page <= 12 else "Assessment text")
        )
        canvas.drawString(72, 765, heading)
        for line in range(50):
            if page == 25 and line == 15:
                text = FINDING
            else:
                text = " ".join(
                    f"section{page} detail{line} observation{part}" for part in range(3)
                )
            canvas.drawString(72, 745 - line * 12, text)
        canvas.showPage()
    canvas.save()
    return output.getvalue()


def test_later_finding_reaches_bounded_snapshot_and_numbered_model_view() -> None:
    payload = _later_finding_pdf()
    document = normalize_pdf(payload)
    assert document.pdf_policy_version == PDF_POLICY_VERSION
    assert document.normalization_version == PDF_NORMALIZATION_VERSION
    assert 3000 < document.word_count <= PDF_CAPTURE_WORD_LIMIT
    assert document.truncated is True
    assert "Page 1\n" in document.text
    assert "Page 25\n" in document.text
    assert "Page 30\n" in document.text
    assert FINDING in document.text
    assert document.sha256 == hashlib.sha256(document.text.encode("utf-8")).hexdigest()
    response = ScrapeResponse(
        resolved_url="https://example.org/generated-report.pdf",
        content_type="application/pdf",
        text=document.text,
        snapshot_sha256=document.sha256,
        word_count=document.word_count,
        truncated=document.truncated,
        normalization_version=document.normalization_version,
    )
    assert response.word_count == document.word_count

    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.org/generated-report.pdf",
        retrieved_at=datetime(2026, 10, 21, tzinfo=UTC),
        normalized_text=document.text,
        truncated=document.truncated,
        normalization_version=document.normalization_version,
        created_at=datetime(2026, 10, 21, tzinfo=UTC),
    )
    assert snapshot.snapshot_sha256 == document.sha256
    exact = locate_exact_quotes(snapshot.normalized_text, (FINDING,))
    assert snapshot.normalized_text[exact[0].start_char : exact[0].end_char] == FINDING
    assert snapshot.normalized_text.rfind("Page 25\n", 0, exact[0].start_char) >= 0

    preview_key = "synthetic-later-pdf-finding"
    preview = build_claim_preview(
        V2PreviewRequest(
            run_id=snapshot.run_id,
            artifact_id=discovery_id(snapshot.run_id, "V2PreviewRequest", preview_key),
            identity_key=preview_key,
            exact_claim="Biodiversity loss increases the risk of species extinction.",
            direction=ResearchDirection.SUPPORT,
            directions=ResearchDirections(),
            source_id=uuid4(),
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_sha256,
            preview_identity="source-claim-preview-v2",
        ),
        snapshot,
    )
    assert any(FINDING in span.text for span in preview.spans)

    excerpt, selected = extraction_source_view(
        snapshot.normalized_text, tuple(span.text for span in preview.spans)
    )
    assert FINDING in excerpt
    assert selected
    assert len(excerpt.encode("utf-8")) <= EXTRACTION_EXCERPT_BYTES
    assert len(excerpt.encode("utf-8")) < len(snapshot.normalized_text.encode("utf-8"))


def test_tiny_pdf_capture_still_samples_later_pages_with_explicit_incompleteness() -> None:
    document = normalize_pdf(_later_finding_pdf(), max_words=90)
    assert document.word_count <= 90
    assert document.truncated is True
    assert "Page 1\n" in document.text
    assert "Page 30\n" in document.text


def test_later_page_finding_beyond_its_opening_survives_crowded_capture() -> None:
    finding = "Measured biodiversity loss preceded higher recorded extinction risk."
    pages: list[tuple[int, str]] = []
    for page in range(1, 101):
        heading = "Key findings" if page == 25 else "Assessment text"
        words = [f"detail{page}_{index}" for index in range(500)]
        if page == 25:
            words[400 : 400 + len(finding.split())] = finding.split()
        pages.append((page, f"{heading}\n{' '.join(words)}"))

    document = _document_from_pdf_pages(pages, max_words=PDF_CAPTURE_WORD_LIMIT, omitted=False)

    assert document.truncated is True
    assert document.word_count <= PDF_CAPTURE_WORD_LIMIT
    assert finding in document.text
    page_25 = document.text.split("Page 25\n", 1)[1].split("\n\nPage 26\n", 1)[0]
    assert PDF_OMISSION_MARKER in page_25
    assert page_25.index(PDF_OMISSION_MARKER) < page_25.index(finding)
    offset = locate_exact_quotes(document.text, (finding,))[0]
    assert document.text[offset.start_char : offset.end_char] == finding

    snapshot = build_source_snapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url="https://example.org/crowded-report.pdf",
        retrieved_at=datetime(2026, 10, 21, tzinfo=UTC),
        normalized_text=document.text,
        truncated=document.truncated,
        normalization_version=document.normalization_version,
        created_at=datetime(2026, 10, 21, tzinfo=UTC),
    )
    preview_key = "crowded-later-pdf-finding"
    preview = build_claim_preview(
        V2PreviewRequest(
            run_id=snapshot.run_id,
            artifact_id=discovery_id(snapshot.run_id, "V2PreviewRequest", preview_key),
            identity_key=preview_key,
            exact_claim="Biodiversity loss increases the risk of species extinction.",
            direction=ResearchDirection.SUPPORT,
            directions=ResearchDirections(),
            source_id=uuid4(),
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_sha256,
            preview_identity="source-claim-preview-v2",
        ),
        snapshot,
    )
    assert any(finding in span.text for span in preview.spans)
    excerpt, _selected = extraction_source_view(
        snapshot.normalized_text, tuple(span.text for span in preview.spans)
    )
    assert finding in excerpt
    assert len(excerpt.encode("utf-8")) <= EXTRACTION_EXCERPT_BYTES
