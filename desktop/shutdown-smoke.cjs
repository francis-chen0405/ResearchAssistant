"use strict";
// Native POSIX process smoke for the actual main.cjs with a disposable stub backend.
// Only the injected test clock is accelerated (30s -> 0.5s, 150s -> 2.5s).
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn, execFileSync } = require("node:child_process");
const { harness, flush } = require("./shutdown-test-support.cjs");
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function running(pid) {
  try {
    const status = execFileSync("ps", ["-o", "stat=", "-p", String(pid)], { encoding: "utf8" }).trim();
    return status.length > 0 && !status.startsWith("Z");
  } catch { return false; }
}

async function until(check) {
  const end = Date.now() + 8000;
  while (!check()) { assert.ok(Date.now() < end, "Native shutdown deadline exceeded"); await delay(20); }
}

(async () => {
  if (process.platform === "win32") {
    console.log("SKIP: POSIX native groups; run tests/test_desktop_shutdown.py for native Windows Jobs");
    return;
  }
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "RA shutdown "));
  const script = path.join(temporary, "backend.cjs");
  fs.writeFileSync(script, `
    const fs = require('node:fs'), { spawn } = require('node:child_process');
    const mode = process.argv[2], pids = process.argv[3];
    process.stdin.resume();
    const childCode = "const {spawn}=require('node:child_process'); const c=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:'ignore'}); console.log(c.pid); setInterval(()=>{},1000);";
    async function child(detached) {
      const c = spawn(process.execPath, ['-e', childCode], {detached, stdio:['ignore','pipe','ignore']});
      const grandchild = await new Promise(r => c.stdout.once('data', data => r(Number(String(data).trim()))));
      c.stdout.resume();
      fs.appendFileSync(pids, c.pid + ',' + grandchild + '\\n');
      return c.pid;
    }
    (async () => {
      await child(false); // inherited backend group
      if (mode !== 'startup') {
        console.log(JSON.stringify({protocol:1,origin:'http://127.0.0.1:12345'}));
        for (let i=0; i<2; i++) console.log(JSON.stringify({owned_pid:await child(true),owned:true}));
      }
      fs.writeFileSync(pids+'.ready', 'ready');
      if (mode === 'normal') process.stdin.once('end', () => process.exit(0));
    })();
    setInterval(()=>{},1000);
  `);
  const unrelated = spawn(process.execPath, ["-e", "setInterval(()=>{},1000)"], { detached: true, stdio: "ignore" });
  const owned = [];
  try {
    for (const mode of ["normal", "stuck", "startup"]) {
      const pidFile = path.join(temporary, mode + ".pids");
      let child;
      const timers = new Set();
      const clock = {
        setTimeout(callback, ms) {
          const id = setTimeout(() => { timers.delete(id); callback(); }, ms / 60);
          timers.add(id); return id;
        },
        clearTimeout(id) { clearTimeout(id); timers.delete(id); },
      };
      const h = harness({ platform: process.platform, clock, kill: (pid, signal) => process.kill(pid, signal),
        spawn: (_executable, _args, options) => {
          child = spawn(process.execPath, [script, mode, pidFile], { ...options, cwd: temporary, env: {} });
          owned.push(child); return child;
        } });
      await h.start();
      await until(() => fs.existsSync(pidFile + ".ready"));
      if (mode !== "startup") {
        await until(() => h.state.windows.some((w) => w.shown));
        h.app.quit(); h.app.quit();
      }
      await until(() => child.exitCode !== null || child.signalCode !== null);
      await flush();
      if (mode === "normal") assert.deepEqual(h.state.exits, [0]);
      else { assert.deepEqual(h.state.exits, [1]); assert.equal(child.signalCode, "SIGKILL"); }
      assert.equal(timers.size, 0);
      const pids = fs.readFileSync(pidFile, "utf8").trim().split(/[\n,]/).map(Number);
      await until(() => pids.every((pid) => !running(pid)));
      assert.equal(running(unrelated.pid), true, "Unrelated sentinel must survive");
      assert.equal(child.stdin.destroyed && child.stdout.destroyed && child.stderr.destroyed, true);
      console.log(`PASS: native ${mode}, backend/descendants/owned acquisition groups gone, unrelated process alive, resources released`);
    }
    // Reproduce the review defect with the actual manager, not a detached stub.
    const repository = path.resolve(__dirname, "..");
    const localPython = path.join(repository, ".venv", "bin", "python");
    const python = fs.existsSync(localPython) ? localPython
      : execFileSync("python", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
    const managerScript = path.join(temporary, "manager.py");
    fs.writeFileSync(managerScript, `
import json, os, signal, subprocess, sys, time
from pathlib import Path
from threading import Thread
from frontend.service_manager import ServiceDiagnostic, WigoloLaunchConfig, WigoloServiceManager
from researchassistant.platform_support import acquisition_supervisor
from researchassistant.platform_support.desktop_ownership import DesktopOwnership
mode, record = sys.argv[1:]
record = Path(record)
sys.stdin.readline() # actual shell bootstrap
class Ownership(DesktopOwnership):
    def write_message(self, message):
        super().write_message(message)
        if mode == 'after-report' and message.get('owned') is True:
            os.kill(os.getpid(), signal.SIGSTOP)
ownership = Ownership(sys.stdout)
def handoff(pid, owned):
    if owned:
        record.write_text(str(pid))
        if mode == 'before-report': os.kill(os.getpid(), signal.SIGSTOP)
    ownership(pid, owned)
    if owned and mode == 'after-ack': os.kill(os.getpid(), signal.SIGSTOP)
def parent_input():
    try:
        for line in sys.stdin: ownership.accept_acknowledgement(line)
    finally: ownership.close()
Thread(target=parent_input, daemon=True).start()
ownership.write_message({'protocol': 1, 'origin': 'http://127.0.0.1:12345'})
child_code = (
    "import os, pathlib, subprocess, sys, time; "
    "c=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
    f"pathlib.Path({str(record)+'.executed'!r}).write_text(str(os.getpgrp())+','+str(c.pid)); "
    "time.sleep(60)"
)
supervisor = (sys.executable, str(Path(acquisition_supervisor.__file__).resolve()))
if mode == 'immediate-stop':
    supervisor = (sys.executable, '-c', "import runpy,sys,time; time.sleep(.2); "
        + f"sys.argv=[{acquisition_supervisor.__file__!r}, *sys.argv[1:]]; "
        + "runpy.run_path(sys.argv[0], run_name='__main__')")
manager = WigoloServiceManager(
    launch=WigoloLaunchConfig(command=(sys.executable, '-c', child_code), data_dir=record.parent),
    base_environment={}, ownership_changed=handoff,
    supervisor_command=supervisor,
)
manager.probe = lambda: ServiceDiagnostic(state='unhealthy', wigolo_ready=False,
    searxng_readiness='unavailable', message='offline')
manager.start()
if mode == 'immediate-stop':
    manager.stop()
    Path(str(record)+'.stopped').write_text('stopped')
if mode == 'root-exit':
    end = time.monotonic()+5
    while not Path(str(record)+'.executed').exists() and time.monotonic()<end: time.sleep(.01)
    os._exit(1)
time.sleep(60)
`);
    for (const mode of ["before-report", "after-report", "after-ack", "running", "root-exit", "immediate-stop"]) {
      const record = path.join(temporary, mode + ".pids");
      const timers = new Set();
      let child;
      const clock = {
        setTimeout(callback, ms) {
          const id = setTimeout(() => { timers.delete(id); callback(); }, ms / (ms === 30000 ? 10 : 60));
          timers.add(id); return id;
        },
        clearTimeout(id) { clearTimeout(id); timers.delete(id); },
      };
      const h = harness({ platform: process.platform, clock, kill: (pid, signal) => process.kill(pid, signal),
        spawn: (_executable, _args, options) => {
          child = spawn(python, [managerScript, mode, record], { ...options, cwd: repository, env: { PYTHONPATH: repository } });
          owned.push(child); return child;
        } });
      await h.start();
      await until(() => fs.existsSync(record));
      const acquisition = Number(fs.readFileSync(record, "utf8"));
      if (mode !== "root-exit") {
        await until(() => h.state.windows.some((w) => w.shown));
        if (mode === "running") await until(() => fs.existsSync(record + ".executed"));
        else if (mode === "immediate-stop") await until(() => fs.existsSync(record + ".stopped"));
        else {
          await until(() => execFileSync("ps", ["-o", "stat=", "-p", String(child.pid)], { encoding: "utf8" }).includes("T"));
          assert.equal(fs.existsSync(record + ".executed"), false, "Gate must prevent early execution");
          assert.equal(Number(execFileSync("ps", ["-o", "pgid=", "-p", String(acquisition)], { encoding: "utf8" }).trim()), child.pid);
        }
        h.app.quit();
      }
      await until(() => h.state.exits.length > 0);
      await until(() => !running(acquisition));
      if (fs.existsSync(record + ".executed")) {
        const [group, grandchild] = fs.readFileSync(record + ".executed", "utf8").split(",").map(Number);
        fs.appendFileSync(record, "," + grandchild);
        assert.equal(group, acquisition);
        await until(() => !running(grandchild));
      }
      assert.deepEqual(h.state.exits, [1]);
      assert.equal(timers.size, 0);
      assert.equal(running(unrelated.pid), true);
      console.log(`PASS: actual manager ${mode}, gated/acknowledged acquisition and descendants gone`);
    }
  } finally {
    for (const child of owned) {
      if (child.exitCode === null && child.signalCode === null) { try { process.kill(-child.pid, "SIGKILL"); } catch {} }
    }
    // All entries were created by this smoke; no system/process-name discovery.
    for (const file of fs.readdirSync(temporary).filter((name) => name.endsWith(".pids"))) {
      for (const pid of fs.readFileSync(path.join(temporary, file), "utf8").trim().split(/[\n,]/).map(Number)) {
        try { process.kill(-pid, "SIGKILL"); } catch {}
        if (running(pid)) { try { process.kill(pid, "SIGKILL"); } catch {} }
      }
    }
    unrelated.kill("SIGKILL");
    fs.rmSync(temporary, { recursive: true, force: true });
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
