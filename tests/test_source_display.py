"""Result-page source headings preserve real titles and avoid citation-as-title junk."""

from researchassistant.evidence.source_display import display_source_title


def test_captured_descriptive_title_is_preserved() -> None:
    title = "Surveillance Inequality: Race, Poverty, and ALPR Deployment"

    assert (
        display_source_title(
            title=title,
            source_url="https://example.org/report.pdf",
        )
        == title
    )


def test_pdf_article_number_title_uses_host_and_filename() -> None:
    assert (
        display_source_title(
            title="S2056608520000082jra 1..28",
            source_url="https://fbaum.unc.edu/articles/JREP-2020-RaceAndPlace.pdf",
        )
        == "PDF file: JREP-2020-RaceAndPlace.pdf (fbaum.unc.edu)"
    )


def test_pdf_reporter_citation_title_uses_host_and_decoded_filename() -> None:
    assert (
        display_source_title(
            title="751 F.3d 1039, *; 2014 U.S. App. LEXIS 8824, **",
            source_url="https://www.drivecms.com/uploads/court/Green.9th%20Cir%20Op.pdf",
        )
        == "PDF file: Green.9th Cir Op.pdf (drivecms.com)"
    )


def test_readable_case_title_with_reporter_citation_is_preserved() -> None:
    title = "Green v. City, 751 F.3d 1039"

    assert (
        display_source_title(
            title=title,
            source_url="https://example.org/Green.pdf",
        )
        == title
    )


def test_missing_pdf_title_falls_back_without_inventing_paper_title() -> None:
    assert (
        display_source_title(
            title=None,
            source_url="https://example.org/files/research.pdf?download=1",
        )
        == "PDF file: research.pdf (example.org)"
    )


def test_non_pdf_title_is_not_replaced_by_url() -> None:
    title = "The actual report title"

    assert display_source_title(title=title, source_url="https://example.org/report") == title
