"""Measure offline fixture failures on Windows without relaxing their assertions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def main() -> None:
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Diagnostics require the disposable Windows runner")
    from test_mvp4_cli import _command, _environment
    from test_product_discovery_pipeline import _run

    from researchassistant.contracts.models import DiscoveryProvider, ResearchControls
    from researchassistant.storage.source_leads import read_source_leads

    output = ROOT / "desktop/build/windows-evidence/diagnostics.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {"revision": os.environ.get("GITHUB_SHA")}
    with tempfile.TemporaryDirectory(prefix="RA Windows fixtures ") as temporary:
        folder = Path(temporary)
        database, run_id = folder / "cli.sqlite3", uuid4()
        started = time.monotonic()
        result = subprocess.run(
            _command(database, run_id),
            cwd=ROOT,
            env=_environment(database, run_id),
            capture_output=True,
            text=True,
            timeout=180,
        )
        report["cli"] = {
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "returncode": result.returncode,
            "released_status": "status: released" in result.stdout,
            "has_rendered_hash": "rendered hash:" in result.stdout,
        }
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        started = time.monotonic()
        pipeline, _model, _search = _run(
            folder / "leads.sqlite3",
            ResearchControls(
                discovery_providers=(DiscoveryProvider.EXA,), seed_expansion_enabled=False
            ),
        )
        leads = read_source_leads(pipeline.db_path, pipeline.run_id)
        report["leads"] = {
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "state": pipeline.state.value,
            "items": [
                {
                    "url": item.url,
                    "disposition": item.disposition,
                    "reason": item.reason,
                    "analysis": [
                        step.model_dump(mode="json")
                        for step in item.history
                        if step.stage in {"analysis", "Analyzer Admission"}
                    ],
                }
                for item in leads.items
            ],
        }
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, sort_keys=True))
        assert result.returncode == 0 and report["cli"]["released_status"]


if __name__ == "__main__":
    main()
