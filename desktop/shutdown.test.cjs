"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { harness, FakeChild, flush } = require("./shutdown-test-support.cjs");
const origin = { protocol: 1, origin: "http://127.0.0.1:12345" };

async function started(options) {
  const h = harness(options);
  await h.start();
  h.line(origin);
  await flush();
  return h;
}

test("external sources permit credential-free HTTP(S) without opening an app window", async () => {
  const h = await started();
  const handler = h.state.windows[0].webContents.openHandler;
  for (const url of ["http://example.test/source", "https://example.test/source",
    "https://user:secret@example.test/source", "file:///tmp/source", "javascript:alert(1)", "invalid"]) {
    assert.equal(handler({ url }).action, "deny");
  }
  assert.deepEqual(h.state.externalUrls, ["http://example.test/source", "https://example.test/source"]);
  assert.equal(h.state.windows.length, 1);
});

test("normal quit allows the full drain, clears timers and releases streams", async () => {
  const h = await started();
  assert.equal(h.clock.pending.size, 0);
  assert.equal(h.state.spawnOptions.detached, true);
  h.app.quit();
  h.clock.advance(149999);
  assert.deepEqual(h.child.kills, []);
  h.child.exit();
  assert.equal(h.state.prevented, 1);
  assert.equal(h.child.ends, 1);
  assert.equal(h.clock.pending.size, 0);
  h.clock.advance(1000000);
  assert.deepEqual(h.state.exits, [0]);
  assert.equal(h.child.stdin.destroyed && h.child.stdout.destroyed && h.child.stderr.destroyed, true);
  assert.equal(h.child.listenerCount("exit"), 0);
});

test("stuck backend exits at exactly 150 seconds; repeated quit cannot extend it", async () => {
  const h = await started();
  h.app.quit();
  h.clock.advance(90000);
  h.app.quit(); h.app.quit();
  assert.equal(h.child.ends, 1);
  assert.equal(h.clock.pending.size, 1);
  h.clock.advance(59999);
  assert.deepEqual(h.state.exits, []);
  h.clock.advance(1);
  assert.deepEqual(h.state.signals, [[-4000, "SIGKILL"]]);
  assert.deepEqual(h.child.kills, ["SIGKILL"]);
  assert.deepEqual(h.state.exits, [1]);
  h.child.exit(); h.app.quit();
  h.clock.advance(1000000);
  assert.deepEqual(h.state.exits, [1]);
  assert.equal(h.clock.pending.size, 0);
});

for (const phase of ["bootstrap", "health", "window"]) {
  test(`startup ${phase} stall initiates bounded EOF shutdown`, async () => {
    const h = harness(phase === "health" ? { fetch: () => new Promise(() => {}) }
      : phase === "window" ? { loadURL: () => new Promise(() => {}) } : {});
    await h.start();
    if (phase !== "bootstrap") { h.line(origin); await flush(); }
    h.clock.advance(30000);
    await flush();
    assert.equal(h.child.ends, 1);
    assert.equal(h.state.prevented, 1);
    h.clock.advance(149999);
    assert.deepEqual(h.state.exits, []);
    h.clock.advance(1);
    assert.deepEqual(h.state.exits, [1]);
    assert.equal(h.clock.pending.size, 0);
    assert.equal(h.state.windows.some((w) => w.shown), false);
  });
}

test("quit before app ready cannot subsequently spawn a backend", async () => {
  const h = harness(); h.app.quit(); await h.start();
  assert.equal(h.state.spawnOptions, null);
  assert.equal(h.clock.pending.size, 0);
});

test("startup failure reports a fixed diagnostic without a native dialog", async () => {
  const h = harness({ messageBox: () => new Promise(() => {}) });
  await h.start(); h.clock.advance(30000);
  assert.equal(h.state.errors.length, 1);
  assert.equal(h.state.dialogs, 0);
  assert.match(h.state.errors[0][0], /could not start/);
  h.clock.advance(150000);
  assert.deepEqual(h.state.exits, [1]);
});

for (const failure of ["invalid response", "spawn error", "startup exit", "load error"]) {
  test(`${failure} releases resources and has no unbounded quit`, async () => {
    const h = harness(failure === "load error" ? { loadURL: async () => { throw Error("offline"); } } : {});
    await h.start();
    if (failure === "spawn error") { h.child.pid = undefined; h.child.emit("error", Error("ENOENT")); }
    else if (failure === "startup exit") h.child.exit(1);
    else h.line(failure === "invalid response" ? { protocol: 42 } : origin);
    await flush();
    if (failure === "invalid response" || failure === "load error") {
      assert.equal(h.child.ends, 1);
      h.clock.advance(150000);
      assert.deepEqual(h.state.exits, [1]);
    } else {
      assert.equal(h.clock.pending.size, 0);
      assert.deepEqual(h.state.signals, failure === "startup exit" ? [[-4000, "SIGKILL"]] : []);
    }
    assert.equal(h.state.windows.some((w) => w.shown), false);
  });
}

test("backend exit while the shutdown timer is being installed cancels that timer", async () => {
  const h = await started();
  h.clock.onSet = (delay) => { if (delay === 150000) h.child.exit(); };
  h.app.quit();
  assert.equal(h.clock.pending.size, 0);
  assert.equal(h.child.ends, 0);
  h.clock.advance(150000);
  assert.deepEqual(h.state.exits, [0]);
});

test("synchronous exit on stdin.end and thrown/broken stdin are bounded", async () => {
  const normal = await started();
  normal.child.onEnd = () => normal.child.exit();
  normal.app.quit();
  assert.equal(normal.clock.pending.size, 0);
  const broken = await started();
  broken.child.stdin.end = () => { throw Error("EPIPE"); };
  broken.app.quit(); broken.clock.advance(150000);
  assert.deepEqual(broken.state.exits, [1]);
});

for (const exit of ["normal", "forced"]) {
  test(`multiple acquisition owners cleaned on ${exit} exit; revoked/invalid owners untouched`, async () => {
    const h = await started();
    for (const pid of [5000, 6000, 7000]) h.line({ owned_pid: pid, owned: true });
    h.line({ owned_pid: 5000, owned: false });
    for (const pid of [0, 1, -500, 1234, 4000, 3.2, "8000"]) h.line({ owned_pid: pid, owned: true });
    h.line({ owned_pid: 9000, owned: "true" });
    h.app.quit();
    // Ownership reports can arrive during cooperative drain.
    h.line({ owned_pid: 8000, owned: true });
    if (exit === "normal") h.child.exit();
    else h.clock.advance(150000);
    assert.deepEqual(h.state.signals.map(([pid]) => pid), [-4000, -6000, -7000, -8000]);
    h.line({ owned_pid: 10000, owned: true }); h.app.quit();
    assert.equal(h.clock.pending.size, 0);
  });
}

test("Windows kills only the owned child HANDLE; never uses group/PID/name scans", async () => {
  const h = await started({ platform: "win32" });
  assert.equal(h.state.spawnOptions.detached, false);
  h.line({ owned_pid: 5000, owned: true }); h.line({ owned_pid: 6000, owned: true });
  h.app.quit(); h.clock.advance(150000);
  assert.deepEqual(h.state.signals, []);
  assert.deepEqual(h.child.kills, ["SIGKILL"]);
  assert.deepEqual(h.state.exits, [1]);
});

test("already observed OS root exit only cleans the owned group at the deadline", async () => {
  const h = await started(); h.app.quit();
  h.child.exitCode = 0; // exit callback delivery delayed
  h.clock.advance(150000);
  assert.deepEqual(h.child.kills, []);
  assert.deepEqual(h.state.signals, [[-4000, "SIGKILL"]]);
  assert.deepEqual(h.state.exits, [1]);
});

test("quit clears a pending health retry and aborts fetch without leaving timers", async () => {
  const h = await started({ fetch: async () => ({ ok: false }) });
  assert.equal(h.clock.pending.size, 2); // startup plus health retry
  h.app.quit(); await flush();
  assert.equal(h.clock.pending.size, 1); // only outer shutdown remains
  h.child.exit();
  assert.equal(h.clock.pending.size, 0);
});

test("signals throwing still release streams and exit without waiting", async () => {
  const child = new FakeChild(); child.kill = () => { throw Error("gone"); };
  const h = await started({ child, kill: () => { throw Error("gone"); } });
  h.app.quit(); h.clock.advance(150000);
  assert.deepEqual(h.state.exits, [1]);
  assert.equal(child.stdout.destroyed, true);
});

test("ownership is recorded before ACK; quit and invalid requests never release a gate", async () => {
  const h = await started();
  const request = "a".repeat(32);
  const writes = [];
  h.child.stdin.write = (line) => {
    const message = JSON.parse(line);
    writes.push(message);
    h.child.exit(1); // Immediate exit during ACK still cleans this registered group.
  };
  h.line({ owned_pid: 5000, owned: true, ownership_request: request });
  assert.deepEqual(writes, [{ owned_pid: 5000, ownership_ack: request }]);
  assert.deepEqual(h.state.signals.map(([pid]) => pid), [-4000, -5000]);

  const draining = await started();
  draining.child.stdin.write = (line) => writes.push(JSON.parse(line));
  for (const message of [
    { owned_pid: 6000, owned: true, ownership_request: "invalid" },
    { owned_pid: 1, owned: true, ownership_request: request },
    { owned_pid: 6000, owned: false, ownership_request: request },
  ]) draining.line(message);
  draining.app.quit();
  draining.line({ owned_pid: 7000, owned: true, ownership_request: request });
  assert.equal(writes.length, 1);
  draining.clock.advance(150000);
  assert.deepEqual(draining.state.signals.map(([pid]) => pid), [-4000, -7000]);
});
