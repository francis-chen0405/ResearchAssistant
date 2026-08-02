"""Subprocess entry point that runs the production CLI with mocked provider HTTP."""

from __future__ import annotations

import os
import runpy
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cli  # noqa: E402
from store import read_cancellation_request  # noqa: E402


def _load_mvp3a_test_helpers() -> dict[str, object]:
    return runpy.run_path(str(Path(__file__).with_name("test_mvp3a_pipeline.py")))


def main() -> int:
    helpers = _load_mvp3a_test_helpers()
    mock_type = helpers["MockProviderHTTP"]
    mimo_clients = helpers["_mimo_clients"]
    now = helpers["NOW"]
    scenario = os.environ.get("MVP4_MOCK_SCENARIO", "released")
    kwargs: dict[str, object] = {}
    if scenario == "blocked":
        kwargs["invalidate_synthesis"] = True
    elif scenario == "failed":
        kwargs["planner_status"] = 401
    elif scenario == "second-process-cancel":
        db_path = Path(os.environ["MVP4_DB_PATH"])
        run_id = os.environ["MVP4_RUN_ID"]

        def wait_for_cancellation() -> None:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    read_cancellation_request(str(db_path), helpers["UUID"](run_id))
                except KeyError:
                    time.sleep(0.05)
                    continue
                return
            raise RuntimeError("timed out waiting for second-process cancellation")

        kwargs["on_planner_response"] = wait_for_cancellation
    mock = mock_type(**kwargs)
    production_runner = cli.run_mvp3b_pipeline

    def mocked_runner(*args: object, **kwargs: object) -> object:
        kwargs["clients"] = mimo_clients(mock)
        kwargs["clock"] = lambda: now
        return production_runner(*args, **kwargs)

    cli.run_mvp3b_pipeline = mocked_runner
    cli.repository_identity = lambda: os.environ.get(
        "MVP4_REPOSITORY_IDENTITY", "source-sha256:" + "a" * 64
    )
    return cli.main()


if __name__ == "__main__":
    raise SystemExit(main())
