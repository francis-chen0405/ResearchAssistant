"use strict";
const { app, BrowserWindow, shell, session } = require("electron");
const { spawn } = require("node:child_process");
const { randomBytes } = require("node:crypto");
const path = require("node:path");
const readline = require("node:readline");

const selfTest = process.argv.includes("--desktop-smoke");
app.setName("ResearchAssistant");
if (selfTest && process.env.RESEARCHASSISTANT_DATA_DIR) {
  app.setPath("userData", path.join(process.env.RESEARCHASSISTANT_DATA_DIR, "electron"));
}
let backend;
let window;
let quitting = false;
let stopped = false;
// EOF first: allow the 90s controller drain plus 60s for server/service teardown.
// This also bounds shutdown after ANY startup failure. Startup itself gets 30s.
const SHUTDOWN_TIMEOUT_MS = 150000;
const STARTUP_TIMEOUT_MS = 30000;
let shutdownTimer;
let startupTimer;
let lines;
const startupAbort = new AbortController();
const ownedProcesses = new Set();
function cleanupBackendGroup() {
  if (process.platform !== "win32" && Number.isSafeInteger(backend?.pid) && backend.pid > 1) {
    try { process.kill(-backend.pid, "SIGKILL"); } catch {}
  }
}
function cleanupAcquisition() {
  if (process.platform !== "win32") {
    for (const pid of ownedProcesses) {
      try { process.kill(-pid, "SIGKILL"); } catch {}
    }
  }
  ownedProcesses.clear();
}

function cancelStartup() {
  clearTimeout(startupTimer);
  startupTimer = undefined;
  startupAbort.abort();
}

function disposeBackendIO() {
  lines?.close();
  for (const stream of [backend?.stdin, backend?.stdout, backend?.stderr]) stream?.destroy();
}

function reportFailure(startup = false) {
  // Even Promise-returning parentless native dialogs can defer before-quit on macOS.
  // Emit only fixed, secret-free diagnostics; no modal UI may hold teardown hostage.
  console.error(startup ? "ResearchAssistant: the local engine could not start. Saved research can be reopened after restarting."
    : "ResearchAssistant: the local engine stopped. Saved research can be reopened after restarting.");
}

function backendExited(code) {
  if (stopped) return;
  stopped = true;
  clearTimeout(shutdownTimer);
  shutdownTimer = undefined;
  cancelStartup();
  cleanupBackendGroup(); // Retire orphan descendants after the root has drained/exited.
  cleanupAcquisition();
  disposeBackendIO();
  if (!quitting) reportFailure();
  // The engine has exited and ownership cleanup is finished. Renderer unload cannot
  // extend the deadline or veto the user's already accepted quit.
  app.exit(quitting && code === 0 ? 0 : 1);
}

function forceShutdown() {
  if (stopped) return;
  stopped = true; // Late exit/quit events must not restart shutdown or signal stale PIDs.
  shutdownTimer = undefined;
  // POSIX: spawn owns a new session; acquisition owns separate reported sessions.
  // Windows: kill the ChildProcess HANDLE, not a PID/name lookup. Python's enclosing
  // kill-on-close Job owns all descendants (including every acquisition generation).
  cleanupBackendGroup();
  if (backend.exitCode == null && backend.signalCode == null) {
    try { backend.kill("SIGKILL"); } catch {}
  }
  cleanupAcquisition();
  cancelStartup();
  disposeBackendIO();
  // Do not wait for child events, pipe EOF, renderer unload or another before-quit.
  // Failure exit status is not a completed research result; SQLite/audits are untouched.
  app.exit(1);
}

function beginQuit(event) {
  if (!backend || stopped) { quitting = true; cancelStartup(); return; }
  event.preventDefault();
  if (quitting) return;
  quitting = true;
  cancelStartup();
  // Arm before ending stdin: synchronous EOF/exit must be safe too.
  shutdownTimer = setTimeout(forceShutdown, SHUTDOWN_TIMEOUT_MS);
  if (stopped) { clearTimeout(shutdownTimer); shutdownTimer = undefined; return; }
  try { backend.stdin.end(); } catch {} // Broken pipe still has the same outer deadline.
}

function ensureLaunching() {
  if (quitting || stopped) throw new Error("Desktop startup was cancelled.");
}

async function launch() {
  if (quitting) return;
  const resources = app.isPackaged ? process.resourcesPath : path.join(__dirname, "build/resources");
  const executable = path.join(resources, "backend", process.platform === "win32" ? "researchassistant-backend.exe" : "researchassistant-backend");
  const token = randomBytes(32).toString("hex");
  // Provider credentials are loaded inside Python from the OS vault, never inherited here.
  const env = {};
  for (const key of ["HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG"]) {
    if (process.env[key]) env[key] = process.env[key];
  }
  if (selfTest && process.env.RESEARCHASSISTANT_DATA_DIR) {
    env.RESEARCHASSISTANT_DATA_DIR = process.env.RESEARCHASSISTANT_DATA_DIR;
  }
  backend = spawn(executable, selfTest ? ["--self-test"] : [], { cwd: resources, env, detached: process.platform !== "win32", windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });
  backend.once("exit", backendExited);
  backend.on("error", () => { if (!backend.pid) backendExited(); });
  backend.stderr.resume(); // Never copy backend output into renderer or persistent diagnostics.
  backend.stdin.on("error", () => {});
  startupTimer = setTimeout(() => {
    if (quitting || stopped) return;
    reportFailure(true);
    app.quit();
  }, STARTUP_TIMEOUT_MS);
  if (stopped) { cancelStartup(); return; }
  const origin = await new Promise((resolve, reject) => {
    lines = readline.createInterface({ input: backend.stdout });
    lines.on("line", (line) => {
      try {
        const message = JSON.parse(line);
        if (!stopped && Number.isSafeInteger(message.owned_pid) && message.owned_pid > 1 && message.owned_pid !== backend.pid && message.owned_pid !== process.pid && typeof message.owned === "boolean") {
          if (message.owned) {
            // Record ownership before permitting the launcher to leave our backend
            // group. EOF/quit never acknowledges a new detachment.
            ownedProcesses.add(message.owned_pid);
            if (!quitting && typeof message.ownership_request === "string" && /^[a-f0-9]{32}$/.test(message.ownership_request)) {
              backend.stdin.write(JSON.stringify({ owned_pid: message.owned_pid, ownership_ack: message.ownership_request }) + "\n");
            }
          } else ownedProcesses.delete(message.owned_pid);
        }
      } catch {}
    });
    lines.once("line", (line) => {
      retireStartupListeners();
      try {
        const result = JSON.parse(line);
        if (result.protocol !== 1 || !/^http:\/\/127\.0\.0\.1:\d+$/.test(result.origin)) throw new Error();
        resolve(result.origin);
      } catch { reject(new Error("Invalid local engine startup response.")); }
    });
    function failed() { retireStartupListeners(); reject(new Error("The bundled local engine could not start.")); }
    function retireStartupListeners() {
      backend.off("error", failed);
      backend.off("exit", failed);
      startupAbort.signal.removeEventListener("abort", failed);
    }
    backend.once("error", failed);
    backend.once("exit", failed);
    startupAbort.signal.addEventListener("abort", failed, { once: true });
    backend.stdin.write(JSON.stringify({ protocol: 1, token, resources }) + "\n");
  });
  ensureLaunching();
  const isolated = session.fromPartition("researchassistant-desktop");
  isolated.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  isolated.setPermissionCheckHandler(() => false);
  isolated.webRequest.onBeforeSendHeaders((details, callback) => {
    if (window && details.webContentsId === window.webContents.id && new URL(details.url).origin === origin) {
      callback({ requestHeaders: { ...details.requestHeaders, Authorization: `Bearer ${token}` } });
    } else callback({ cancel: true });
  });
  isolated.webRequest.onHeadersReceived((details, callback) => {
    callback({ responseHeaders: { ...details.responseHeaders,
      "Content-Security-Policy": ["default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"] } });
  });
  window = new BrowserWindow({ width: 1280, height: 860, show: false,
    webPreferences: { session: isolated, sandbox: true, contextIsolation: true, nodeIntegration: false, devTools: false } });
  window.webContents.on("will-navigate", (event, url) => { if (new URL(url).origin !== origin) event.preventDefault(); });
  window.webContents.setWindowOpenHandler(({ url }) => {
    try { if (new URL(url).protocol === "https:") void shell.openExternal(url); } catch {}
    return { action: "deny" };
  });
  for (let attempt = 0; attempt < 100; attempt++) {
    ensureLaunching();
    try {
      const response = await fetch(`${origin}/api/health`, { headers: { Authorization: `Bearer ${token}` }, signal: startupAbort.signal });
      if (response.ok) break;
    } catch {}
    ensureLaunching();
    if (attempt === 99) throw new Error("The local engine health check failed.");
    await new Promise((resolve) => {
      const done = () => { clearTimeout(timer); startupAbort.signal.removeEventListener("abort", done); resolve(); };
      const timer = setTimeout(done, 100);
      startupAbort.signal.addEventListener("abort", done, { once: true });
      if (startupAbort.signal.aborted) done();
    });
  }
  ensureLaunching();
  await window.loadURL(origin);
  ensureLaunching();
  clearTimeout(startupTimer);
  startupTimer = undefined;
  window.show();
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on("second-instance", () => { if (window) { if (window.isMinimized()) window.restore(); window.focus(); } });
  app.whenReady().then(launch).catch(() => { if (!quitting && !stopped) { reportFailure(true); app.quit(); } });
  app.on("window-all-closed", () => app.quit());
  app.on("before-quit", beginQuit);
}
