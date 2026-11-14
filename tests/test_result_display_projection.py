"""Result-page source labels and the read-only export route (display projection only)."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import researchassistant.evidence.brief_export as brief_export
from researchassistant.api import api
from researchassistant.contracts.provider_results import ProviderRunStatus
from researchassistant.evidence.report_presentation import source_display, source_labels
from researchassistant.storage.store import init_db


def _item(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "source_url": "https://example.org/study",
        "source_type": None,
        "authors": (),
        "publication_date": None,
        "publication_venue": None,
        "verified_publication": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.core
def test_export_labels_keep_their_recorded_wording() -> None:
    assert source_labels(_item(source_type="clinical trial"))[1] != "Randomized trial"
    assert source_labels(_item(source_url="https://notflocksafety.com/a"))[2] is None
    kind, _, conflict = source_labels(_item(source_url="https://blog.flocksafety.com/a"))
    assert kind == "Vendor blog"
    assert conflict is not None and "commercial interest" in conflict
    trial = source_labels(_item(source_type="randomized_trial"))
    assert trial == ("Publication type not recorded", "Randomized trial", None)
    assert source_labels(_item(source_type="working_paper"))[1] == "Study design not recorded"
    for recorded in (
        "nonrandomized working paper",
        "non-randomized working paper",
        "not randomized working paper",
    ):
        assert source_labels(_item(source_type=recorded))[:2] == (
            "Working paper",
            "Observational study",
        )
    assert source_labels(_item())[0] == "Source type not recorded"


@pytest.mark.core
def test_result_page_labels_omit_missing_values_instead_of_printing_not_recorded() -> None:
    labels = source_display(
        title="A study",
        display_title="A study",
        source_url="https://www.texasprivacycoalition.com/reports/a",
    )
    assert labels.source_kind is None
    assert labels.study_design is None
    assert labels.year is None
    assert labels.lead_author is None
    assert labels.publisher_interest is None
    # Generic rule: a long registrable label is shown as the readable domain.
    assert labels.source_name == "texasprivacycoalition.com"


@pytest.mark.core
def test_generic_host_rule_uses_acronyms_and_the_one_publisher_table() -> None:
    def name(url: str, title: str = "A title") -> str | None:
        return source_display(title=title, display_title=title, source_url=url).source_name

    assert name("https://www.ojp.gov/library/a") == "Office of Justice Programs"
    assert name("https://nij.ojp.gov/library/a") == "National Institute of Justice"
    assert name("https://www.cdc.gov/a") == "CDC"
    assert name("https://www.example-institute.org/a") == "Example Institute"
    assert name("https://static1.squarespace.com/file.pdf") is None
    titled = source_display(
        title="Report title | Example Agency",
        display_title="Report title | Example Agency",
        source_url="https://static1.squarespace.com/file",
    )
    assert (titled.heading, titled.source_name) == ("Report title", "Example Agency")


@pytest.mark.core
def test_author_prefixes_and_uploader_handles_are_not_authors() -> None:
    lum = _item(authors=("Author(s) Cynthia Lum, Julie Hibdon, Breanne Cave",))
    handle = _item(authors=("nballard",))
    listed = _item(authors=("Bruce Taylor, Christopher Koper, Daniel Woods",))

    def lead(item: SimpleNamespace) -> str | None:
        return source_display(
            title="t", display_title="t", source_url=item.source_url, item=item
        ).lead_author

    assert lead(lum) == "Cynthia Lum et al."
    assert lead(handle) is None
    assert lead(listed) == "Bruce Taylor et al."


@pytest.mark.core
def test_verified_publication_and_social_headings_take_priority() -> None:
    verified = _item(
        source_url="https://mirror.example/file.pdf",
        authors=("Unverified name",),
        verified_publication=SimpleNamespace(
            title="Verified publication",
            authors=("A. Author",),
            publication_date="2024-02-01",
            venue="Journal",
        ),
    )
    labels = source_display(
        title="paper.pdf",
        display_title="PDF file: file.pdf",
        source_url=verified.source_url,
        item=verified,
    )
    assert (labels.heading, labels.source_name, labels.year) == (
        "Verified publication",
        "Journal",
        "2024",
    )
    assert labels.lead_author == "A. Author"
    social = source_display(
        title="An unreliable first line of a post",
        display_title="An unreliable first line of a post",
        source_url="https://www.linkedin.com/posts/example",
    )
    assert social.heading == "Post on LinkedIn"
    assert social.source_kind == "Social post"


RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
BRIEF = "# Research Brief\n\nClaim under review: A precise claim.\n"


@pytest.mark.core
@pytest.mark.parametrize(
    ("export_format", "media", "prefix"),
    [
        ("pdf", "application/pdf", b"%PDF-1.4"),
        ("docx", "application/vnd.openxmlformats", b"PK"),
        ("markdown", "text/markdown", b"<!-- ResearchAssistant export"),
    ],
)
def test_export_route_returns_a_revalidated_file_without_writing_the_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    export_format: str,
    media: str,
    prefix: bytes,
) -> None:
    released = SimpleNamespace(
        run_id=RUN_ID,
        status=ProviderRunStatus.RELEASED,
        validation_result=SimpleNamespace(valid=True),
        final_brief=BRIEF,
        rendered_brief_hash=sha256(BRIEF.encode("utf-8")).hexdigest(),
    )
    monkeypatch.setattr(brief_export, "inspect_provider_run", lambda *_a, **_k: released)
    database = tmp_path / "run.sqlite3"
    init_db(str(database))
    before = database.read_bytes()
    listing = sorted(path.name for path in tmp_path.iterdir())
    runtime = api.ApiRuntime(
        controller=SimpleNamespace(), services=SimpleNamespace(), environment={}
    )
    client = TestClient(
        api.create_app(runtime, load_keychain_on_start=False, allowed_hosts=("testserver",))
    )

    response = client.get(
        f"/api/research/{RUN_ID}/export",
        params={"db_path": str(database), "format": export_format},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(media)
    assert response.content.startswith(prefix)
    assert f"research-brief-{RUN_ID}" in response.headers["content-disposition"]
    assert database.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == listing


@pytest.mark.core
def test_export_route_refuses_unreleased_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    failed = SimpleNamespace(
        run_id=RUN_ID,
        status=ProviderRunStatus.FAILED,
        validation_result=None,
        final_brief=None,
        rendered_brief_hash=None,
    )
    monkeypatch.setattr(brief_export, "inspect_provider_run", lambda *_a, **_k: failed)
    database = tmp_path / "run.sqlite3"
    init_db(str(database))
    runtime = api.ApiRuntime(
        controller=SimpleNamespace(), services=SimpleNamespace(), environment={}
    )
    client = TestClient(
        api.create_app(runtime, load_keychain_on_start=False, allowed_hosts=("testserver",))
    )

    response = client.get(
        f"/api/research/{RUN_ID}/export", params={"db_path": str(database), "format": "pdf"}
    )

    assert response.status_code == 400
    assert "released" in response.text
