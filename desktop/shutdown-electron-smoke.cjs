"use strict";
// Real Electron startup failure + forced quit. Copies current main.cjs unchanged
// after a test-only clock/spawn prelude; no production flags or runtime data access.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn, execFileSync } = require("node:child_process");

(async () => {
  if (process.platform === "win32") {
    console.log("SKIP: POSIX stub; native Windows ownership is tested with Python Jobs");
    return;
  }
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), "RA Electron shutdown "));
  const record = path.join(fixture, "owned.json");
  const stub = path.join(fixture, "stub.cjs");
  const trace = path.join(fixture, "trace.txt");
  let desktop;
  let timer;
  let verified = false;
  try {
    fs.mkdirSync(path.join(fixture, "build/resources"), { recursive: true });
    fs.writeFileSync(path.join(fixture, "package.json"), JSON.stringify({ name: "shutdown-offline-smoke", version: "0.0.0", main: "main.cjs" }));
    fs.writeFileSync(stub, `
      const fs = require('node:fs'), { spawn } = require('node:child_process');
      process.stdin.resume(); // Ignore EOF and never announce an origin.
      const children = [0, 1].map(() => spawn(process.execPath, ['-e', 'setInterval(()=>{},1000)'], {stdio:'ignore'}));
      fs.writeFileSync(${JSON.stringify(record)}, JSON.stringify([process.pid, ...children.map(c=>c.pid)]));
      setInterval(()=>{},1000);
    `);
    const prelude = `
      "use strict";
      const testTimers = require('node:timers');
      const testLog = (text) => require('node:fs').appendFileSync(${JSON.stringify(trace)}, text+'\\n');
      const testApp = require('electron').app;
      testApp.on('before-quit', () => testLog('before-quit'));
      const testExit = testApp.exit.bind(testApp);
      testApp.exit = (code) => { testLog('exit '+code); testExit(code); };
      global.setTimeout = (fn, ms, ...args) => testTimers.setTimeout(() => { testLog('timer '+ms); fn(...args); }, ms >= 30000 ? ms / 60 : ms);
      const testChildProcess = require('node:child_process'), testSpawn = testChildProcess.spawn;
      testChildProcess.spawn = (_file, _args, options) => testSpawn(${JSON.stringify(process.execPath)}, [${JSON.stringify(stub)}], options);
    `;
    fs.writeFileSync(path.join(fixture, "main.cjs"), prelude + fs.readFileSync(path.join(__dirname, "main.cjs"), "utf8"));
    const started = Date.now();
    desktop = spawn(require("electron"), [fixture, "--desktop-smoke"], {
      env: { ...process.env, RESEARCHASSISTANT_DATA_DIR: path.join(fixture, "data") }, stdio: "ignore",
    });
    const code = await new Promise((resolve, reject) => {
      timer = setTimeout(() => reject(Error("Real Electron ignored the shutdown deadline: " + (fs.existsSync(trace) ? fs.readFileSync(trace, 'utf8') : 'no lifecycle events'))), 15000);
      desktop.once("exit", resolve); desktop.once("error", reject);
    });
    assert.equal(code, 1);
    const lifecycle = fs.readFileSync(trace, "utf8");
    for (const event of ["timer 30000", "before-quit", "timer 150000", "exit 1"]) assert.ok(lifecycle.includes(event));
    assert.ok(Date.now() - started < 15000);
    const pids = JSON.parse(fs.readFileSync(record, "utf8"));
    assert.equal(pids.length, 3);
    for (const pid of pids) {
      let status = "";
      try { status = execFileSync("ps", ["-o", "stat=", "-p", String(pid)], { encoding: "utf8" }).trim(); } catch {}
      assert.ok(!status || status.startsWith("Z"), "Owned stub descendant survived real Electron quit");
    }
    verified = true;
    console.log("PASS: real Electron startup stall, no blocking native error dialog, deadline exit 1, owned backend/descendants gone (accelerated clock)");
  } finally {
    clearTimeout(timer);
    if (desktop && desktop.exitCode === null && desktop.signalCode === null) desktop.kill("SIGKILL");
    if (!verified && fs.existsSync(record)) {
      const [pid] = JSON.parse(fs.readFileSync(record, "utf8"));
      try { process.kill(-pid, "SIGKILL"); } catch {}
    }
    fs.rmSync(fixture, { recursive: true, force: true });
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
