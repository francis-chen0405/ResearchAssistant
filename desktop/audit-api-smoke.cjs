"use strict";

// Exercise the repository's TypeScript API client with isolated local responses.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("../web/node_modules/typescript");

function client(fetch) {
  let now = 0;
  const exports = {};
  const context = { exports, process: { env: { NEXT_PUBLIC_RESEARCH_API_URL: "" } }, fetch,
    AbortSignal: { timeout: () => undefined },
    Date: { now: () => now },
    setTimeout: (resolve, delay) => { now += delay; resolve(); },
  };
  const source = fs.readFileSync(path.join(__dirname, "../web/lib/api.ts"), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(compiled, context);
  return exports.researchApi;
}

const response = (body) => ({ ok: true, json: async () => body });
const diagnostic = (state) => ({ state, wigolo_ready: state === "healthy", message: state });

async function main() {
  const configSource = fs.readFileSync(path.join(__dirname, "../web/next.config.ts"), "utf8");
  const configCode = ts.transpileModule(configSource, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  for (const apiAddress of [undefined, "http://127.0.0.1:8765", ""]) {
    const exports = {};
    vm.runInNewContext(configCode, { exports, process: { env: {
      RESEARCHASSISTANT_DESKTOP: "1", NEXT_PUBLIC_RESEARCH_API_URL: apiAddress,
    } } });
    assert.equal(exports.default.output, "export");
    assert.equal(exports.default.env?.NEXT_PUBLIC_RESEARCH_API_URL, "", "Desktop exports must always use the app's own origin");
  }
  const webExports = {};
  vm.runInNewContext(configCode, { exports: webExports, process: { env: {} } });
  assert.equal(webExports.default.env, undefined, "Regular web builds preserve configurable API addresses");

  const states = ["starting", "starting", "healthy"];
  const requests = [];
  const api = client(async (url) => {
    requests.push(url);
    return response(diagnostic(states.shift()));
  });
  assert.equal((await api.startService()).wigolo_ready, true, "Starting must wait for exact health");
  assert.deepEqual(requests, ["/api/service/start", "/api/service", "/api/service"]);
  for (const state of ["wrong_service", "exited", "launch_failed"]) {
    let calls = 0;
    const failed = client(async () => { calls++; return response(diagnostic(state)); });
    assert.equal((await failed.startService()).state, state);
    assert.equal(calls, 1, "Terminal startup failures must not be retried");
  }
  const timedOut = client(async () => response(diagnostic("starting")));
  await assert.rejects(timedOut.startService(), /start.*time|starting.*time/i);

  let releaseFirst;
  let beganFirst;
  const firstBegan = new Promise((resolve) => { beganFirst = resolve; });
  const firstDone = new Promise((resolve) => { releaseFirst = resolve; });
  const writes = [];
  const saved = client(async (_url, init) => {
    const value = JSON.parse(init.body);
    if (value.sequence === 1) { beganFirst(); await firstDone; }
    writes.push(value.sequence);
    return response(value);
  });
  const first = saved.savePreferences({ sequence: 1 });
  await firstBegan;
  const second = saved.savePreferences({ sequence: 2 });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(writes, [], "Newer writes must wait for an older pending commit");
  releaseFirst();
  await Promise.all([first, second]);
  assert.deepEqual(writes, [1, 2]);

  let attempts = 0;
  const recovering = client(async () => {
    if (++attempts === 1) throw new Error("local write failed");
    return response({ saved: true });
  });
  await assert.rejects(recovering.savePreferences({}), /local write failed/);
  assert.equal((await recovering.savePreferences({})).saved, true);
  console.log("Verified bounded service readiness and ordered preference commits, including failure recovery.");
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
