"""Proof-gated parent citation recovery for Cambridge review attachments."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import pytest
from test_seed_expansion_runtime import NOW, RUN, _candidate

from researchassistant.agents.adaptive_summary import _merge_survivors
from researchassistant.agents.v2_source_selection import build_v2_source_selection_input
from researchassistant.contracts.model_research import (
    ResearchDirections,
    V2AcquisitionProbeOutput,
    V2DiscoveryScoutOutput,
)
from researchassistant.contracts.models import SourceSnapshot
from researchassistant.evidence.paper_identity import confirmed_parent_article_citation

PARENT_TITLE = (
    "Intergenerational justice, the impending sixth mass extinction, reproduction and "
    "advanced biotechnologies, and humanity’s future"
)
PARENT_DOI = "10.1017/ext.2025.10005"
REVIEW_DOI = f"{PARENT_DOI}.pr8"
CAMBRIDGE_PDF = (
    "https://www.cambridge.org/core/services/aop-cambridge-core/content/view/"
    "E6DC15041C853B5FBD33658889707C4E/"
    "S2755095825100053a.pdf/div-title-intergenerational-justice-div.pdf"
)


def _snapshot(
    text: str | None = None,
    *,
    source_url: str = CAMBRIDGE_PDF,
) -> SourceSnapshot:
    captured_text = text or (
        f"{PARENT_TITLE}\nRobert Browne\nDOI: {PARENT_DOI}\n\n"
        "Abstract\nThe article text cites other research."
    )
    now = datetime(2026, 10, 24, tzinfo=UTC)
    return SourceSnapshot(
        run_id=uuid4(),
        retrieval_attempt_id=uuid4(),
        snapshot_id=uuid4(),
        source_url=source_url,
        retrieved_at=now,
        normalized_text=captured_text,
        snapshot_sha256=sha256(captured_text.encode()).hexdigest(),
        word_count=len(captured_text.split()),
        truncated=False,
        created_at=now,
    )


def _metadata_title(parent_title: str = PARENT_TITLE) -> str:
    return f"Review: {parent_title} — R1/PR8"


def test_confirms_cambridge_review_pdf_as_parent_article_from_header_evidence() -> None:
    assert confirmed_parent_article_citation(
        _snapshot(), _metadata_title(), REVIEW_DOI, "peer-review"
    ) == (PARENT_TITLE, PARENT_DOI)


def test_accepts_cambridge_first_page_heading_and_doi_url_format() -> None:
    wrapped_title = (
        "Page 1\nIntergenerational justice, the impending sixth\n"
        "mass extinction, reproduction and advanced\n"
        "biotechnologies, and humanity’s future\nRobert Kenneth Browne\n"
        "Cambridge Prisms: Extinction\nhttps://doi.org/10.1017/ext.2025.10005\n"
        "Received: 26 April 2025\nAbstract\nArticle content\n"
        "https://doi.org/10.1017/ext.2025.10005\n"
    )
    assert confirmed_parent_article_citation(
        _snapshot(wrapped_title), _metadata_title(), REVIEW_DOI, "peer-review"
    ) == (PARENT_TITLE, PARENT_DOI)


@pytest.mark.parametrize(
    ("title", "doi", "source_type", "source_url"),
    [
        (_metadata_title("A different article title"), REVIEW_DOI, "peer-review", CAMBRIDGE_PDF),
        (_metadata_title(), "10.1017/ext.2025.10006.pr8", "peer-review", CAMBRIDGE_PDF),
        (_metadata_title(), f"{PARENT_DOI}.pr7", "peer-review", CAMBRIDGE_PDF),
        (_metadata_title(), REVIEW_DOI, "article", CAMBRIDGE_PDF),
        (
            _metadata_title(),
            REVIEW_DOI,
            "peer-review",
            CAMBRIDGE_PDF.replace("www.cambridge.org", "example.org"),
        ),
    ],
)
def test_rejects_unmatched_or_untrusted_citation_metadata(
    title: str, doi: str, source_type: str, source_url: str
) -> None:
    assert (
        confirmed_parent_article_citation(_snapshot(source_url=source_url), title, doi, source_type)
        is None
    )


def test_rejects_review_pdf_when_snapshot_is_the_review_itself() -> None:
    review_text = (
        "Reviewer report\nComments to the author\n"
        f"The article {PARENT_TITLE} is interesting.\n"
        f"DOI: {PARENT_DOI}\n"
    )
    assert (
        confirmed_parent_article_citation(
            _snapshot(review_text), _metadata_title(), REVIEW_DOI, "peer-review"
        )
        is None
    )


def test_rejects_parent_doi_mentioned_only_in_body_references() -> None:
    text = f"{PARENT_TITLE}\nRobert Browne\nAbstract\nText cites DOI: {PARENT_DOI}\n"
    assert (
        confirmed_parent_article_citation(
            _snapshot(text), _metadata_title(), REVIEW_DOI, "peer-review"
        )
        is None
    )


def test_rejects_snapshot_with_invalid_hash() -> None:
    snapshot = _snapshot().model_copy(update={"snapshot_sha256": "0" * 64})
    assert (
        confirmed_parent_article_citation(snapshot, _metadata_title(), REVIEW_DOI, "peer-review")
        is None
    )


def _cambridge_selection_inputs() -> tuple[
    V2DiscoveryScoutOutput,
    V2AcquisitionProbeOutput,
    bytes,
    bytes,
]:
    item, cluster, (source, probe, survivor), _ = _candidate(
        "cambridge-review",
        doi=REVIEW_DOI,
        title=_metadata_title(),
        authors=("Review author",),
        year=2025,
        source_type="peer-review",
    )
    article_text = (
        "Page 1\nIntergenerational justice, the impending sixth\n"
        "mass extinction, reproduction and advanced\n"
        "biotechnologies, and humanity’s future\nRobert Kenneth Browne\n"
        "Cambridge Prisms: Extinction\nhttps://doi.org/10.1017/ext.2025.10005\n"
        "Received: 26 April 2025\nRevised: 06 August 2025\nAbstract\n"
        + "Animal welfare and de-extinction are discussed in this article. "
        * 40
    )
    digest = sha256(article_text.encode()).hexdigest()
    snapshot = source.snapshot.model_copy(
        update={
            "source_url": CAMBRIDGE_PDF,
            "normalized_text": article_text,
            "snapshot_sha256": digest,
            "word_count": len(article_text.split()),
        }
    )
    source = source.model_copy(update={"snapshot": snapshot})
    passage = probe.passages[0].model_copy(
        update={
            "snapshot_sha256": digest,
            "start_char": 0,
            "end_char": len(article_text),
            "text": article_text,
        }
    )
    probe = probe.model_copy(
        update={"snapshot_sha256": digest, "passages": (passage,), "preview": None}
    )
    survivor = survivor.model_copy(update={"snapshot_sha256": digest})
    item = item.model_copy(update={"source_url": CAMBRIDGE_PDF, "canonical_url": CAMBRIDGE_PDF})
    cluster = cluster.model_copy(
        update={"preferred_url": CAMBRIDGE_PDF, "canonical_url": CAMBRIDGE_PDF}
    )
    discovery = V2DiscoveryScoutOutput(
        run_id=RUN,
        directions=ResearchDirections(support_enabled=True, challenge_enabled=False),
        items=(item,),
        clusters=(cluster,),
        scout_batches=(),
        scout_audits=(),
        completed_at=NOW,
    )
    acquisition = V2AcquisitionProbeOutput(
        run_id=RUN,
        directions=discovery.directions,
        acquisitions=(source,),
        attempts=(),
        probes=(probe,),
        survivors=(survivor,),
        completed_at=NOW,
    )
    return (
        discovery,
        acquisition,
        discovery.model_dump_json().encode(),
        snapshot.model_dump_json().encode(),
    )


def test_fresh_selection_corrects_parent_citation_without_mutating_saved_inputs() -> None:
    discovery, acquisition, discovery_bytes, snapshot_bytes = _cambridge_selection_inputs()
    merged = _merge_survivors(RUN, ((1, discovery, acquisition),))

    selection = build_v2_source_selection_input(
        exact_claim="de-extinction harms animal welfare",
        merged_survivors=merged,
        discovery_outputs=(discovery,),
        acquisition_outputs=(acquisition,),
        gap_outputs=(),
        claim_aware=True,
        asserted_components=("de-extinction harms animal welfare",),
    )

    candidate = selection.survivors[0]
    assert (candidate.title, candidate.doi, candidate.source_type) == (
        PARENT_TITLE,
        PARENT_DOI,
        "article",
    )
    assert candidate.authors == ()
    assert candidate.publication_date is None
    assert discovery.model_dump_json().encode() == discovery_bytes
    assert acquisition.acquisitions[0].snapshot.model_dump_json().encode() == snapshot_bytes


def test_legacy_selection_preserves_review_metadata() -> None:
    discovery, acquisition, discovery_bytes, snapshot_bytes = _cambridge_selection_inputs()
    merged = _merge_survivors(RUN, ((1, discovery, acquisition),))

    selection = build_v2_source_selection_input(
        exact_claim="de-extinction harms animal welfare",
        merged_survivors=merged,
        discovery_outputs=(discovery,),
        acquisition_outputs=(acquisition,),
        gap_outputs=(),
        claim_aware=False,
    )

    candidate = selection.survivors[0]
    assert (candidate.title, candidate.doi, candidate.source_type) == (
        _metadata_title(),
        REVIEW_DOI,
        "peer-review",
    )
    assert candidate.authors == ("Review author",)
    assert candidate.publication_date == "2025-01-01"
    assert discovery.model_dump_json().encode() == discovery_bytes
    assert acquisition.acquisitions[0].snapshot.model_dump_json().encode() == snapshot_bytes
