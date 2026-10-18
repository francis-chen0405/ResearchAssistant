"""Execute the actual Mac launcher against isolated process and transport doubles."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ZSH = shutil.which("zsh")
pytestmark = pytest.mark.skipif(os.name == "nt" or ZSH is None, reason="macOS zsh launcher")


def _executable(path: Path, program: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n" + program)
    path.chmod(0o700)


def _checkout(folder: Path, scenario: str) -> Path:
    folder.mkdir()
    launcher = folder / "Launch ResearchAssistant.command"
    text = (
        (ROOT / launcher.name)
        .read_text()
        .replace("time.monotonic() + 45", "time.monotonic() + 3.0")
    )
    for name, original in (("curl", "/usr/bin/curl"), ("lsof", "/usr/sbin/lsof")):
        text = text.replace(original, f'"{folder / "bin" / name}"')
    launcher.write_text(text)
    marker = repr(str(folder))
    _executable(
        folder / ".venv/bin/python",
        f"""import os, signal, sys, time
from pathlib import Path
root = Path({marker})
if sys.argv[1:3] != ['-m', 'researchassistant.api.api']:
    os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])
(root / 'api.pid').write_text(str(os.getpid()))
def stop(signum: int, frame: object) -> None:
    (root / 'api.stopped').write_text('owned API stopped')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
while True:
    time.sleep(0.02)
""",
    )
    _executable(
        folder / "frontend/node_modules/.bin/next",
        f"""import os, signal, time
from pathlib import Path
root = Path({marker})
(root / 'web.pid').write_text(str(os.getpid()))
def stop(signum: int, frame: object) -> None:
    (root / 'web.stopped').write_text('owned web stopped')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
while True:
    time.sleep(0.02)
""",
    )
    (folder / "frontend/.next").mkdir()
    (folder / "frontend/.next/BUILD_ID").write_text("offline")
    _executable(
        folder / "bin/lsof",
        f"""import sys
scenario = {scenario!r}
if any('3000' in arg for arg in sys.argv):
    raise SystemExit(1 if scenario in ('web_refused', 'owned_api') else 0)
raise SystemExit(1)
""",
    )
    _executable(
        folder / "bin/curl",
        f"""import json, sys, time
from pathlib import Path
root = Path({marker})
scenario = {scenario!r}
args = sys.argv[1:]
if '--max-time' not in args or '--connect-timeout' not in args:
    time.sleep(20)
    raise SystemExit(99)
timeout = float(args[args.index('--max-time') + 1])
connect_timeout = float(args[args.index('--connect-timeout') + 1])
with (root / 'requests.jsonl').open('a') as output:
    row = {{'timeout': timeout, 'connect': connect_timeout, 'url': args[-1]}}
    output.write(json.dumps(row) + '\\n')
api = '8765' in args[-1]
if api:
    if scenario == 'api_stall':
        time.sleep(timeout)
        raise SystemExit(28)
    if scenario == 'owned_api' and not (root / 'api.pid').exists():
        raise SystemExit(7)
    print('{{"api_version":"mlp-5-v2-phase13-analyzer-admission"}}')
elif scenario == 'web_stall':
    time.sleep(timeout)
    raise SystemExit(28)
elif scenario in ('web_refused', 'owned_api'):
    raise SystemExit(7)
""",
    )
    for command in ("open", "osascript"):
        _executable(
            folder / ".venv/bin" / command,
            f"from pathlib import Path\nPath({marker}, {command!r}).write_text('called')\n",
        )
    return launcher


@pytest.mark.parametrize(
    "scenario", ("api_stall", "web_stall", "web_refused", "owned_api", "ready")
)
def test_checkout_readiness_has_one_deadline_and_preserves_process_ownership(
    tmp_path: Path, scenario: str
) -> None:
    launcher = _checkout(tmp_path / "checkout with spaces", scenario)
    sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    process = subprocess.Popen(
        [ZSH, str(launcher)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True
    )
    started = time.monotonic()
    try:
        _output, errors = process.communicate(timeout=8)
        assert time.monotonic() - started < 6, errors.decode()
        assert process.returncode == (0 if scenario == "ready" else 1), errors.decode()
        assert (launcher.parent / "open").exists() is (scenario == "ready")
        if scenario != "ready":
            assert (launcher.parent / "osascript").exists()
        requests = [
            json.loads(line)
            for line in (launcher.parent / "requests.jsonl").read_text().splitlines()
        ]
        assert requests and all(0 < row["timeout"] <= 2.0 for row in requests)
        assert all(row["timeout"] == row["connect"] for row in requests)
        if scenario in ("web_refused", "owned_api"):
            expected = ["web"] if scenario == "web_refused" else ["api", "web"]
            assert all((launcher.parent / (name + ".pid")).exists() for name in expected)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and any(
                not (launcher.parent / (name + ".stopped")).exists() for name in expected
            ):
                time.sleep(0.01)
            assert all((launcher.parent / (name + ".stopped")).exists() for name in expected)
        assert sentinel.poll() is None
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate(timeout=2)
        sentinel.terminate()
        sentinel.wait(timeout=2)
