"""Run with an isolated installed interpreter, never a checkout import path."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import httpx
from pypdf import PdfReader

import cli
import models
import store
from frontend.api import create_app, create_default_runtime
from providers.llm import LLMStage, load_prompt, load_prompt_file
from researchassistant.common.resources import pdf_font_resource, prompt_directory
from researchassistant.contracts import models as canonical_models
from researchassistant.contracts.models import (
    DiscoveryProvider,
    ResearchDirections,
    RunManifest,
    RunStatus,
    Stage,
    V2PipelineIdentity,
)
from researchassistant.evidence.pdf_render import render_pdf_text
from researchassistant.providers.bounded_resolver import resolve_host_addresses
from researchassistant.providers.normalization import normalize_pdf
from researchassistant.research import fixture_pipeline
from researchassistant.research.query_execution import freeze_query_execution
from researchassistant.runtime import cli as canonical_cli
from researchassistant.runtime.application_runtime import repository_identity
from researchassistant.storage import store as canonical_store


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    args = parser.parse_args()
    expected = json.loads(args.expected.read_text())
    assert (cli, models, store) == (
        canonical_cli,
        canonical_models,
        canonical_store,
    )
    for retired in (
        "orchestrator",
        "researchassistant.research.orchestrator",
        "researchassistant.research.historical_execution",
    ):
        assert importlib.util.find_spec(retired) is None, retired
    for facade, canonical in expected["facades"].items():
        assert importlib.import_module(facade) is importlib.import_module(canonical), facade
    # Exercise the optional viewer's real installed module/script entry points,
    # without installing Streamlit, opening a server or reading a database.
    viewer_smoke = """
import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock
from researchassistant.api import evidence_browser_app
ui = MagicMock()
ui.button.return_value = False
sys.modules['streamlit'] = ui
if sys.argv[1] == 'module':
    runpy.run_module('frontend.evidence_browser_app', run_name='__main__')
else:
    path = Path(evidence_browser_app.__file__).resolve().parents[2]
    runpy.run_path(str(path / 'frontend/evidence_browser_app.py'), run_name='__main__')
ui.title.assert_called_once_with('Evidence Browser')
ui.text_input.assert_any_call('Existing SQLite database')
ui.button.assert_called_once_with('Open evidence trail', use_container_width=True)
"""
    for launch in ("module", "script"):
        result = subprocess.run(
            [sys.executable, "-I", "-c", viewer_smoke, launch], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
    assert repository_identity() == expected["identity"]
    directory = prompt_directory()
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.iterdir()
        if path.name.endswith(".md")
    }
    assert hashes == expected["prompts"]
    for name in hashes:
        prompt = load_prompt_file(directory.joinpath(name))
        assert prompt.sha256 == hashes[name]
    for stage in LLMStage:
        assert load_prompt(stage).stage is stage
    assert hashlib.sha256(pdf_font_resource().read_bytes()).hexdigest() == expected["font"]
    app = create_app(create_default_runtime(), load_keychain_on_start=False)
    assert app.openapi()["paths"]

    async def request_health() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
        ) as client:
            response = await client.get("/api/health")
            assert response.status_code == 200, response.text
            assert response.json()["api_version"]

    asyncio.run(request_health())
    executable = Path(sys.executable).with_name(
        "researchassistant.exe" if os.name == "nt" else "researchassistant"
    )
    for launcher in (
        [str(executable)],
        [sys.executable, "-I", "-m", "researchassistant.runtime.cli"],
        [sys.executable, "-I", "-m", "cli"],
    ):
        help_result = subprocess.run([*launcher, "--help"], capture_output=True, text=True)
        assert help_result.returncode == 0, help_result.stderr
        assert "run-fixture" in help_result.stdout
    for name, status in (("basic_valid_run", "released"), ("invalid_release_run", "blocked")):
        result = fixture_pipeline.run_fixture_pipeline(
            args.fixtures / name, output_dir=Path.cwd() / name
        )
        assert result.status == status
        if result.final_brief:
            assert (
                hashlib.sha256(result.final_brief.encode()).hexdigest()
                == result.rendered_brief_hash
            )
    command = [
        str(executable),
        "run-fixture",
        str(args.fixtures / "basic_valid_run"),
        "--output-dir",
        str(Path.cwd() / "cli-fixture"),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0 and "result: released" in result.stdout, result.stderr
    # Fresh discovery binding reads both historical and new prompts, without transport.
    database = str(Path.cwd() / "fresh-binding.sqlite3")
    canonical_store.init_db(database)
    run_id = uuid4()
    now = datetime.now(UTC)
    canonical_store.insert_run(
        database,
        RunManifest(
            run_id=run_id,
            raw_claim="Offline installed claim",
            status=RunStatus.RUNNING,
            current_stage=Stage.CLAIM_PLANNER,
            created_at=now,
            updated_at=now,
        ),
    )
    canonical_store.insert_v2_pipeline_identity(database, run_id, V2PipelineIdentity(), now)
    arguments = (
        database,
        run_id,
        "Offline installed claim",
        ResearchDirections(),
        (DiscoveryProvider.OPENALEX,),
        lambda: datetime.now(UTC),
    )
    binding = freeze_query_execution(*arguments)
    assert binding.source_identity_hash == expected["identity"].removeprefix("source-sha256:")
    assert freeze_query_execution(*arguments) == binding
    pdf = render_pdf_text("Installed Unicode PDF: café — α 日本語\n" * 100)
    reader = PdfReader(BytesIO(pdf))
    parsed = normalize_pdf(pdf)
    assert parsed.media_type == "application/pdf"
    assert "Installed Unicode PDF" in parsed.text
    assert len(reader.pages) > 1
    assert "café" in reader.pages[0].extract_text()
    # The installed resolver starts its owned worker by an absolute installed
    # path. Localhost needs no internet and works from this unrelated directory.
    import ipaddress

    assert all(
        ipaddress.ip_address(value).is_loopback
        for value in resolve_host_addresses("localhost", timeout=5)
    )
    print(
        json.dumps(
            {
                "identity": repository_identity(),
                "prompts": len(hashes),
                "pdf_pages": len(reader.pages),
                "pdf_worker": "completed",
                "dns_worker": "completed and reaped",
                "api": "constructed without credentials",
                "fixtures": ["released", "blocked"],
                "binding": "fresh and replayed",
            }
        )
    )


if __name__ == "__main__":
    main()
