"use strict";
// Test-only dependencies around the real main.cjs; never included in the app bundle.
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const { EventEmitter } = require("node:events");
const { PassThrough } = require("node:stream");

class FakeClock {
  now = 0;
  next = 0;
  pending = new Map();
  onSet;
  setTimeout = (callback, delay) => {
    const id = ++this.next;
    this.pending.set(id, { at: this.now + delay, callback });
    this.onSet?.(delay);
    return id;
  };
  clearTimeout = (id) => this.pending.delete(id);
  advance(ms) {
    const end = this.now + ms;
    while (true) {
      const next = [...this.pending].sort((a, b) => a[1].at - b[1].at)[0];
      if (!next || next[1].at > end) break;
      this.pending.delete(next[0]);
      this.now = next[1].at;
      next[1].callback();
    }
    this.now = end;
  }
}

class FakeChild extends EventEmitter {
  pid = 4000;
  exitCode = null;
  signalCode = null;
  stdin = new PassThrough();
  stdout = new PassThrough();
  stderr = new PassThrough();
  kills = [];
  ends = 0;
  constructor() {
    super();
    this.stdin.end = () => { this.ends++; this.onEnd?.(); };
  }
  kill(signal) { this.kills.push(signal); return true; }
  exit(code = 0) { this.exitCode = code; this.emit("exit", code, null); }
}

function harness(options = {}) {
  const clock = options.clock || new FakeClock();
  const child = options.child || new FakeChild();
  const app = new EventEmitter();
  let ready;
  const readiness = new Promise((resolve) => { ready = resolve; });
  const state = { prevented: 0, quits: 0, exits: [], signals: [], errors: [], dialogs: 0, windows: [], spawnOptions: null };
  app.setName = () => {};
  app.setPath = () => {};
  app.requestSingleInstanceLock = () => options.singleInstance !== false;
  app.whenReady = () => readiness;
  app.quit = () => {
    state.quits++;
    app.emit("before-quit", { preventDefault: () => { state.prevented++; } });
  };
  app.exit = (code) => { state.exits.push(code); options.onExit?.(code); };
  class BrowserWindow {
    webContents = new EventEmitter();
    constructor() { state.windows.push(this); this.webContents.setWindowOpenHandler = () => {}; }
    async loadURL() { if (options.loadURL) await options.loadURL(); }
    show() { this.shown = true; }
  }
  const isolated = { setPermissionRequestHandler() {}, setPermissionCheckHandler() {},
    webRequest: { onBeforeSendHeaders() {}, onHeadersReceived() {} } };
  const context = vm.createContext({
    __dirname, AbortController, console: { error: (...args) => state.errors.push(args) },
    process: { argv: [], env: {}, pid: 1234, platform: options.platform || "darwin", kill: (pid, signal) => {
      state.signals.push([pid, signal]); options.kill?.(pid, signal);
    } },
    setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout,
    fetch: options.fetch || (async () => ({ ok: true })),
    require: (id) => {
      if (id === "electron") return { app, BrowserWindow, session: { fromPartition: () => isolated },
        dialog: { showErrorBox: () => { state.dialogs++; throw Error("Synchronous dialogs can block the shutdown deadline"); },
          showMessageBox: () => { state.dialogs++; return options.messageBox?.() || Promise.resolve(); } }, shell: {} };
      if (id === "node:child_process") return { spawn: (...args) => {
        state.spawnOptions = args[2]; return options.spawn ? options.spawn(...args) : child;
      } };
      return require(id);
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "main.cjs"), "utf8"), context);
  return { app, child, clock, state, context, ready,
    async start() { ready(); await flush(); },
    line(message) { child.stdout.write(JSON.stringify(message) + "\n"); },
  };
}

async function flush() { for (let i = 0; i < 12; i++) await Promise.resolve(); }
module.exports = { harness, FakeChild, FakeClock, flush };
