"""Offline read-only disposition inspection, including incomplete/unreleased runs."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from test_acquisition_usable_fallback import ALTERNATE, LANDING, _clustered, _policy
from test_mlp3_api import FakeController, FakeServices
from test_ranked_acquisition_integration import _fresh_case, _run_discovery
from test_v2_phase5_acquisition_probe import NOW, FixtureScraper, _prepare_db, _response

from researchassistant.agents.v2_acquisition import run_v2_acquisition_probe
from researchassistant.api import api
from researchassistant.contracts.source_leads import SourceLeadsPage
from researchassistant.providers.v2_budget import V2CancellationRequested
from researchassistant.storage.source_leads import read_source_leads
from researchassistant.storage.store import DatabaseCompatibilityError, insert_v2_artifact


def _captured(tmp_path: Path, *, cancelled: bool = False) -> tuple[str, UUID]:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    discovery = _clustered(run_id)
    insert_v2_artifact(path, "phase-4-discovery-scout", discovery, NOW)
    text = (
        "Methods describe 600 participants in a controlled study. "
        "Results found no significant difference in outcomes and discuss limitations. "
    ) * 30
    scraper = FixtureScraper(
        {LANDING: _response(LANDING, "OSF"), ALTERNATE: _response(ALTERNATE, text)}
    )
    if cancelled:

        def cancel() -> bool:
            return len(scraper.requests) >= 1

        with pytest.raises(V2CancellationRequested):
            run_v2_acquisition_probe(
                db_path=path,
                discovery_output=discovery,
                wigolo_provider=scraper,
                exact_claim="Does the intervention work?",
                policy=_policy(),
                clock=lambda: NOW,
                cancellation_requested=cancel,
            )
    else:
        run_v2_acquisition_probe(
            db_path=path,
            discovery_output=discovery,
            wigolo_provider=scraper,
            exact_claim="Does the intervention work?",
            policy=_policy(),
            clock=lambda: NOW,
        )
    return path, run_id


def test_unreleased_leads_preserve_shell_and_alternate_readability(tmp_path: Path) -> None:
    path, run_id = _captured(tmp_path)
    before = Path(path).read_bytes(), Path(path).stat().st_mtime_ns
    page = read_source_leads(path, run_id, limit=1)
    assert page.total == 2 and page.has_more
    other = read_source_leads(path, run_id, offset=1, limit=1)
    assert not other.has_more and page.items[0].lead_id != other.items[0].lead_id
    assert {lead.url for lead in (*page.items, *other.items)} == {LANDING, ALTERNATE}
    by_url = {lead.url: lead for lead in (*page.items, *other.items)}
    assert by_url[LANDING].capture_status == "unusable"
    assert by_url[LANDING].readable_alternate_url == ALTERNATE
    assert by_url[ALTERNATE].capture_status == "readable"
    assert by_url[ALTERNATE].readable_alternate_url is None
    for lead in (*page.items, *other.items):
        assert [step.status for step in lead.history if step.stage == "capture"] == [
            "unusable",
            "readable",
        ]
        assert any("Admission" in unknown for unknown in lead.unknowns)
        assert lead.search_directions == ("support",)
    assert "snippets" not in page.model_dump_json() and "OSF" not in page.model_dump_json()
    assert "not verified evidence" in page.notice
    assert (Path(path).read_bytes(), Path(path).stat().st_mtime_ns) == before


def test_cancelled_run_shows_saved_individual_capture_without_aggregate(tmp_path: Path) -> None:
    path, run_id = _captured(tmp_path, cancelled=True)
    page = read_source_leads(path, run_id)
    assert page.total == 2
    by_url = {lead.url: lead for lead in page.items}
    assert by_url[LANDING].capture_status == "unusable"
    assert by_url[ALTERNATE].capture_status == "unknown"
    assert all(lead.readable_alternate_url is None for lead in page.items)
    assert all(any(step.stage == "capture" for step in lead.history) for lead in page.items)
    assert all(not any(step.stage == "Probe" for step in lead.history) for lead in page.items)


def test_provider_pages_are_inspectable_before_scout_without_new_calls(tmp_path: Path) -> None:
    path = tmp_path / "pages.sqlite"
    run_id, _plan, _results = _fresh_case(path)
    before = path.read_bytes(), path.stat().st_mtime_ns
    page = read_source_leads(path, run_id)
    assert page.total == 20
    assert all(item.confidence == "unknown" for item in page.items)
    assert all(item.capture_status == "unknown" for item in page.items)
    assert all(item.disposition == "unknown" for item in page.items)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_ranked_capacity_reasons_are_visible_and_page_hits_do_not_repeat(tmp_path: Path) -> None:
    path = tmp_path / "ranking.sqlite"
    run_id, plan, results = _fresh_case(path)
    _run_discovery(path, run_id, plan, results, model_calls=8)
    page = read_source_leads(path, run_id)
    assert page.total == 20
    assert all(any(step.stage == "ranking" for step in lead.history) for lead in page.items)
    assert any(
        any(step.status == "not_scouted_budget" for step in lead.history) for lead in page.items
    )


def test_no_artifacts_empty_run_and_missing_database_stay_read_only(tmp_path: Path) -> None:
    run_id = uuid4()
    path = _prepare_db(tmp_path, run_id)
    assert read_source_leads(path, run_id).items == ()
    with pytest.raises(KeyError):
        read_source_leads(path, uuid4())
    missing = tmp_path / "absent.sqlite"
    with pytest.raises(DatabaseCompatibilityError):
        read_source_leads(missing, run_id)
    assert not missing.exists()


@pytest.mark.parametrize(("offset", "limit"), [(-1, 50), (6001, 50), (0, 0), (0, 101), (True, 50)])
def test_pagination_rejects_before_opening_database(
    tmp_path: Path, offset: int, limit: int
) -> None:
    with pytest.raises(ValueError, match="pagination"):
        read_source_leads(tmp_path / "missing.sqlite", uuid4(), offset=offset, limit=limit)
    assert not (tmp_path / "missing.sqlite").exists()


def test_http_leads_without_final_artifact_and_bounded_parameters(tmp_path: Path) -> None:
    path, run_id = _captured(tmp_path)
    app = api.create_app(
        api.ApiRuntime(controller=FakeController({}), services=FakeServices(), environment={}),
        load_keychain_on_start=False,
        allowed_hosts=("testserver",),
    )
    client = TestClient(app)
    url = f"/api/research/{run_id}/source-leads"
    response = client.get(url, params={"db_path": path, "limit": 1})
    assert response.status_code == 200
    assert SourceLeadsPage.model_validate(response.json()).total == 2
    assert client.get(url, params={"db_path": path, "limit": 101}).status_code == 422
    assert (
        client.get(f"/api/research/{uuid4()}/source-leads", params={"db_path": path}).status_code
        == 404
    )


def test_cross_run_payload_fails_even_with_recomputed_checksum(tmp_path: Path) -> None:
    path, run_id = _captured(tmp_path)
    # Corruption fixture removes immutability protection explicitly, never in product code.
    from hashlib import sha256

    with sqlite3.connect(path) as connection:
        triggers = connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='v2_artifacts'"
        ).fetchall()
        for name, _sql in triggers:
            connection.execute(f'DROP TRIGGER "{name}"')
        key, payload = connection.execute(
            "SELECT artifact_key,payload_json FROM v2_artifacts "
            "WHERE artifact_type='V2DiscoveryScoutOutput'"
        ).fetchone()
        data = json.loads(payload)
        data["items"][0]["run_id"] = str(uuid4())
        encoded = json.dumps(data)
        connection.execute(
            "UPDATE v2_artifacts SET payload_json=?,payload_sha256=? WHERE artifact_key=?",
            (encoded, sha256(encoded.encode()).hexdigest(), key),
        )
        for _name, sql in triggers:
            connection.execute(sql)
    with pytest.raises(sqlite3.IntegrityError, match="cross-run"):
        read_source_leads(path, run_id)


def test_fresh_reader_import_needs_no_execution_or_provider_modules(tmp_path: Path) -> None:
    path, run_id = _captured(tmp_path)
    script = """
import sys
from importlib.abc import MetaPathFinder
class Block(MetaPathFinder):
    def find_spec(self, fullname: str, path: object = None, target: object = None) -> None:
        if fullname.startswith(("researchassistant.agents", "researchassistant.research",
                                "agents.", "providers.")):
            raise AssertionError("Execution imported: " + fullname)
sys.meta_path.insert(0, Block())
from researchassistant.storage.source_leads import read_source_leads
from uuid import UUID
assert read_source_leads(sys.argv[1], UUID(sys.argv[2])).total == 2
"""
    subprocess.run(
        [sys.executable, "-c", script, path, str(run_id)],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.slow
def test_full_production_pipeline_leads_keep_admission_families_and_released_bytes(
    tmp_path: Path,
) -> None:
    from test_product_discovery_pipeline import _run

    from researchassistant.api.application_services.result_reads import read_result
    from researchassistant.contracts.models import DiscoveryProvider, ResearchControls

    path = tmp_path / "product-leads.sqlite"
    result, _model, _search = _run(
        path,
        ResearchControls(
            discovery_providers=(DiscoveryProvider.EXA,),
            seed_expansion_enabled=False,
        ),
    )
    released = read_result(path, result.run_id).model_dump_json()
    before = path.read_bytes(), path.stat().st_mtime_ns
    page = read_source_leads(path, result.run_id)
    admitted = [lead for lead in page.items if lead.disposition == "analyzer_admitted"]
    assert admitted and all(lead.source_family for lead in admitted)
    by_url = {lead.url: lead for lead in admitted}
    for suffix in (1, 4, 5):
        lead = by_url[f"https://example.test/regional-evaluation-{suffix}"]
        assert lead.capture_status == "readable"
        assert lead.readable_alternate_url is None
    for suffix in (2, 3):
        lead = by_url[f"https://example.test/regional-evaluation-{suffix}"]
        assert lead.capture_status == "unknown"
        assert lead.readable_alternate_url == "https://example.test/regional-evaluation-1"
    # With round-four admission repaired, the fixture's sixth source is admitted
    # directly instead of being retried as backfill after a constraint failure.
    assert len(admitted) == 6
    assert by_url["https://example.test/regional-evaluation-6"].source_family
    assert all(any(step.stage == "analysis" for step in lead.history) for lead in admitted)
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM v2_ledger_admissions WHERE discovery_round=4"
            ).fetchone()[0]
            == 1
        )
    assert read_result(path, result.run_id).model_dump_json() == released
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_inventory_byte_bound_fails_before_payload_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from researchassistant.storage import source_leads

    path, run_id = _captured(tmp_path)
    before = Path(path).read_bytes(), Path(path).stat().st_mtime_ns
    monkeypatch.setattr(source_leads, "_MAX_BYTES", 1)
    with pytest.raises(sqlite3.IntegrityError, match="bounded inspection"):
        read_source_leads(path, run_id)
    assert (Path(path).read_bytes(), Path(path).stat().st_mtime_ns) == before


@pytest.mark.parametrize("corruption", ("type", "key", "checksum", "snapshot"))
def test_corrupt_disposition_rows_fail_closed(tmp_path: Path, corruption: str) -> None:
    from hashlib import sha256

    path, run_id = _captured(tmp_path)
    with sqlite3.connect(path) as connection:
        triggers = connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='v2_artifacts'"
        ).fetchall()
        for name, _sql in triggers:
            connection.execute(f'DROP TRIGGER "{name}"')
        if corruption == "type":
            connection.execute(
                "UPDATE v2_artifacts SET artifact_type='wrong' "
                "WHERE artifact_key='phase-4-discovery-scout'"
            )
        elif corruption == "key":
            connection.execute(
                "UPDATE v2_artifacts SET artifact_key='unexpected-key' "
                "WHERE artifact_key='phase-4-discovery-scout'"
            )
        elif corruption == "checksum":
            connection.execute(
                "UPDATE v2_artifacts SET payload_sha256=? "
                "WHERE artifact_key='phase-4-discovery-scout'",
                ("0" * 64,),
            )
        else:
            key, payload = connection.execute(
                "SELECT artifact_key,payload_json FROM v2_artifacts "
                "WHERE artifact_type='V2AcquisitionProbeOutput'"
            ).fetchone()
            value = json.loads(payload)
            value["acquisitions"][0]["snapshot"]["normalized_text"] = "tampered"
            payload = json.dumps(value)
            connection.execute(
                "UPDATE v2_artifacts SET payload_json=?,payload_sha256=? WHERE artifact_key=?",
                (payload, sha256(payload.encode()).hexdigest(), key),
            )
        for _name, sql in triggers:
            connection.execute(sql)
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        read_source_leads(path, run_id)


def test_rendering_source_leads_cannot_issue_http_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    path, run_id = _captured(tmp_path)

    def no_transport(*args: object, **kwargs: object) -> None:
        raise AssertionError("read-only rendering started a provider call")

    monkeypatch.setattr(httpx.Client, "request", no_transport)
    assert read_source_leads(path, run_id).total == 2
