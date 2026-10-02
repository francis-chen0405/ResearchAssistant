"""Read-only lineage warnings do not rewrite immutable source-family identities."""

from uuid import uuid4

import pytest

from study_lineage import build_study_lineage_notices
from tests.test_v2_phase8_source_selection import _candidate


def test_possible_mirror_is_disclosed_without_merging_families() -> None:
    first = _candidate(uuid4(), family="exa-family", probe_score=7).model_copy(
        update={
            "title": "Working Paper: Automated License Plate Readers, Vehicle Theft, and Clearance"
        }
    )
    second = _candidate(uuid4(), family="pdf-family", probe_score=7).model_copy(
        update={"title": "Automated License Plate Readers, Vehicle Theft, and Clearance"}
    )
    notices = build_study_lineage_notices((first, second))
    assert len(notices) == 1
    assert notices[0].basis == "matching_title"
    assert notices[0].source_ids == (first.source_id, second.source_id)
    assert "may report the same study" in notices[0].explanation
    assert (first.source_family_id, second.source_family_id) == ("exa-family", "pdf-family")


def test_same_dated_slug_and_publisher_suffix_disclose_possible_mirror() -> None:
    title = "In Louisville, half of the people charged last year were Black"
    first = _candidate(uuid4(), family="lpm-family", probe_score=7).model_copy(
        update={
            "title": title,
            "source_url": "https://lpm.org/investigate/2026-01-27/in-louisville-people-charged-last-year",
        }
    )
    second = _candidate(uuid4(), family="afro-family", probe_score=7).model_copy(
        update={
            "title": f"{title} - Afro-Conscious Media",
            "source_url": "https://afroconsciousmedia.com/2026/01/27/in-louisville-people-charged-last-year",
        }
    )

    notices = build_study_lineage_notices((first, second))

    assert len(notices) == 1
    assert notices[0].source_ids == (first.source_id, second.source_id)
    assert "may be mirrors" in notices[0].explanation.casefold()
    assert (first.source_family_id, second.source_family_id) == ("lpm-family", "afro-family")


def test_matching_headline_without_matching_dated_slug_is_not_a_mirror_notice() -> None:
    title = "In Louisville, half of the people charged last year were Black"
    first = _candidate(uuid4(), family="lpm-family", probe_score=7).model_copy(
        update={
            "title": title,
            "source_url": "https://lpm.org/investigate/2026-01-27/in-louisville-people-charged-last-year",
        }
    )
    second = _candidate(uuid4(), family="independent-family", probe_score=7).model_copy(
        update={
            "title": f"{title} - Afro-Conscious Media",
            "source_url": "https://other.test/reports/louisville-arrests",
        }
    )

    assert build_study_lineage_notices((first, second)) == ()


def test_unverified_publisher_suffix_is_not_stripped_for_mirror_matching() -> None:
    title = "In Louisville, half of the people charged last year were Black"
    first = _candidate(uuid4(), family="lpm-family", probe_score=7).model_copy(
        update={
            "title": title,
            "source_url": "https://lpm.org/investigate/2026-01-27/in-louisville-people-charged-last-year",
        }
    )
    second = _candidate(uuid4(), family="unrelated-host-family", probe_score=7).model_copy(
        update={
            "title": f"{title} - A Different Publisher",
            "source_url": "https://other.test/2026/01/27/in-louisville-people-charged-last-year",
        }
    )

    assert build_study_lineage_notices((first, second)) == ()


def test_matching_normalized_doi_discloses_shared_identifier() -> None:
    first = _candidate(uuid4(), family="a", probe_score=7).model_copy(
        update={"doi": "https://doi.org/10.1007/S11292-011-9133-9"}
    )
    second = _candidate(uuid4(), family="b", probe_score=7).model_copy(
        update={"doi": "10.1007/s11292-011-9133-9"}
    )
    notices = build_study_lineage_notices((first, second))
    assert len(notices) == 1
    assert notices[0].basis == "matching_doi"
    assert "same DOI" in notices[0].explanation


@pytest.mark.parametrize("doi", [None, "invalid-doi", "https://evil.test/10.1000/example"])
def test_shared_domain_or_generic_title_is_not_a_study_identity(doi: str | None) -> None:
    first = _candidate(uuid4(), family="a", probe_score=7).model_copy(
        update={"title": "Results", "doi": doi}
    )
    second = _candidate(uuid4(), family="b", probe_score=7).model_copy(
        update={"title": "Results", "doi": doi}
    )
    assert build_study_lineage_notices((first, second)) == ()


def test_conflicting_dois_override_matching_title_hint() -> None:
    title = "A randomized evaluation of license plate reader patrols"
    first = _candidate(uuid4(), family="a", probe_score=7).model_copy(
        update={"title": title, "doi": "10.1000/first"}
    )
    second = _candidate(uuid4(), family="b", probe_score=7).model_copy(
        update={"title": title, "doi": "10.1000/second"}
    )
    assert build_study_lineage_notices((first, second)) == ()
