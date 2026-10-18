"""Real Electron forced quit with native Windows Jobs and disposable Python stubs."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if sys.platform != "win32":
        raise RuntimeError("This smoke requires native Windows process handles")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    electron = ROOT / "desktop/node_modules/electron/dist/electron.exe"
    with tempfile.TemporaryDirectory(prefix="RA Electron Windows ") as temporary:
        fixture = Path(temporary)
        record, trace = fixture / "owned.json", fixture / "trace.txt"
        stub = fixture / "stub.py"
        child_code = (
            "import subprocess, sys, time; "
            "c=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
            "print(c.pid,flush=True); time.sleep(60)"
        )
        stub.write_text(
            "import json, os, subprocess, sys, time\n"
            "from pathlib import Path\n"
            "from researchassistant.platform_support.windows_job import WindowsJob\n"
            "job=WindowsJob(); job.attach_current_process()\n"
            "pids=[]; children=[]\n"
            f"code={child_code!r}\n"
            "for _ in range(2):\n"
            " c=subprocess.Popen([sys.executable,'-u','-c',code],\n"
            "                    stdout=subprocess.PIPE,text=True)\n"
            " children.append(c); pids.extend([c.pid,int(c.stdout.readline())])\n"
            f"record=Path({str(record)!r})\n"
            "pending=record.with_suffix('.pending')\n"
            "pending.write_text(json.dumps([os.getpid(), *pids])); pending.replace(record)\n"
            "time.sleep(60)\n",  # Ignore EOF and never announce an origin.
            encoding="utf-8",
        )
        prelude = (
            "'use strict';\nconst testTimers=require('node:timers');\n"
            f"const log=t=>require('node:fs').appendFileSync({json.dumps(str(trace))},t+'\\n');\n"
            "const testApp=require('electron').app;\n"
            "const originalExit=testApp.exit.bind(testApp);\n"
            "testApp.exit=code=>{log('exit '+code);originalExit(code);};\n"
            "global.setTimeout=(fn,ms,...args)=>testTimers.setTimeout(()=>{log('timer '+ms);"
            "fn(...args);},ms>=30000?ms/60:ms);\n"
            "const cp=require('node:child_process'),originalSpawn=cp.spawn;\n"
            f"cp.spawn=(_file,_args,options)=>originalSpawn({json.dumps(sys.executable)},"
            f"['-u',{json.dumps(str(stub))}],options);\n"
        )
        (fixture / "build/resources").mkdir(parents=True)
        (fixture / "package.json").write_text(
            json.dumps(
                {
                    "name": "windows-shutdown-smoke",
                    "version": "0.0.0",
                    "main": "main.cjs",
                }
            ),
            encoding="utf-8",
        )
        (fixture / "main.cjs").write_text(
            prelude + (ROOT / "desktop/main.cjs").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        process = subprocess.Popen(
            [str(electron), str(fixture), "--desktop-smoke"],
            env={**os.environ, "RESEARCHASSISTANT_DATA_DIR": str(fixture / "data")},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        handles: list[int] = []
        started = time.monotonic()
        try:
            deadline = started + 15
            while not record.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert record.exists(), "Windows stub did not establish native ownership"
            pids = json.loads(record.read_text(encoding="utf-8"))
            assert len(pids) == 5
            for pid in pids:
                # Keep exact handles even if a PID is recycled after forced quit.
                handle = kernel.OpenProcess(0x00100001, False, pid)  # SYNCHRONIZE | TERMINATE
                assert handle
                handles.append(handle)
            assert process.wait(timeout=15) == 1
            assert time.monotonic() - started < 20
            for handle in handles:
                assert kernel.WaitForSingleObject(handle, 5000) == 0
            assert unrelated.poll() is None, "Unrelated sentinel must survive"
            observations = trace.read_text(encoding="utf-8")
            assert "timer 30000" in observations and "timer 150000" in observations
            assert "exit 1" in observations
            print(
                "PASS: real Electron Windows forced quit; five owned native handles exit; "
                "unrelated process survives (accelerated test clock; production main unchanged)"
            )
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            for handle in handles:
                if kernel.WaitForSingleObject(handle, 0) != 0:
                    kernel.TerminateProcess(handle, 1)
                kernel.CloseHandle(handle)
            unrelated.kill()
            unrelated.wait(timeout=10)


if __name__ == "__main__":
    main()
