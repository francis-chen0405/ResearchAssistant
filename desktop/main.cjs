"use strict";
const { app, BrowserWindow, dialog, shell, session } = require("electron");
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
const ownedProcesses = new Set();
function cleanupAcquisition() {
  if (process.platform !== "win32") {
    for (const pid of ownedProcesses) {
      try { process.kill(-pid, "SIGKILL"); } catch {}
    }
  }
  ownedProcesses.clear();
}

async function launch() {
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
  backend = spawn(executable, selfTest ? ["--self-test"] : [], { cwd: resources, env, windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });
  backend.stderr.resume(); // Never copy backend output into renderer or persistent diagnostics.
  backend.stdin.on("error", () => {});
  const origin = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("The local engine did not start in time.")), 30000);
    const lines = readline.createInterface({ input: backend.stdout });
    lines.on("line", (line) => {
      try {
        const message = JSON.parse(line);
        if (Number.isSafeInteger(message.owned_pid) && message.owned_pid > 1) {
          if (message.owned) ownedProcesses.add(message.owned_pid);
          else ownedProcesses.delete(message.owned_pid);
        }
      } catch {}
    });
    lines.once("line", (line) => {
      clearTimeout(timer);
      try {
        const result = JSON.parse(line);
        if (result.protocol !== 1 || !/^http:\/\/127\.0\.0\.1:\d+$/.test(result.origin)) throw new Error();
        resolve(result.origin);
      } catch { reject(new Error("Invalid local engine startup response.")); }
    });
    backend.once("error", () => { clearTimeout(timer); reject(new Error("The bundled local engine could not start.")); });
    backend.once("exit", () => { cleanupAcquisition(); stopped = true; clearTimeout(timer); reject(new Error("The local engine stopped during startup.")); });
    backend.stdin.write(JSON.stringify({ protocol: 1, token, resources }) + "\n");
  });
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
  backend.on("exit", () => { stopped = true; if (!quitting) { dialog.showErrorBox("ResearchAssistant", "The local engine stopped. Saved research can be reopened after restarting."); app.quit(); } });
  for (let attempt = 0; attempt < 100; attempt++) {
    try {
      const response = await fetch(`${origin}/api/health`, { headers: { Authorization: `Bearer ${token}` } });
      if (response.ok) break;
    } catch {}
    if (attempt === 99) throw new Error("The local engine health check failed.");
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  await window.loadURL(origin);
  window.show();
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on("second-instance", () => { if (window) { if (window.isMinimized()) window.restore(); window.focus(); } });
  app.whenReady().then(launch).catch((error) => { dialog.showErrorBox("ResearchAssistant", error.message); app.quit(); });
  app.on("window-all-closed", () => app.quit());
  app.on("before-quit", (event) => {
    if (!backend || stopped) return;
    event.preventDefault();
    if (quitting) return;
    quitting = true;
    backend.stdin.end();
    backend.once("exit", () => app.quit());
  });
}
