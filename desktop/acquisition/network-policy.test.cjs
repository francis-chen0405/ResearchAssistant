const { test } = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

test("locked upstream fetch and PDF probe load the protected policy", () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "ra-network-upstream-"));
  try {
    const result = spawnSync(process.execPath, ["--input-type=module", "-e", `
      import assert from "node:assert/strict";
      import dns from "node:dns/promises";
      const ordinaryFetch = globalThis.fetch;
      await import(${JSON.stringify(pathToFileURL(path.join(__dirname, "network-preload.mjs")).href)});
      assert.equal(globalThis.fetch, ordinaryFetch);
      let resolutions = 0;
      dns.lookup = async () => { resolutions++; return [{ address: "127.0.0.1", family: 4 }]; };
      const { httpFetch } = await import(${JSON.stringify(pathToFileURL(path.join(__dirname, "node_modules/wigolo/dist/fetch/http-client.js")).href)});
      await assert.rejects(httpFetch("http://source.example"), /public addresses/);
      const { SmartRouter } = await import(${JSON.stringify(pathToFileURL(path.join(__dirname, "node_modules/wigolo/dist/fetch/router.js")).href)});
      const router = new SmartRouter({ httpClient: { fetch() { throw new Error("unused"); } } });
      assert.equal(await router.pdfProbe("http://source.example"), false);
      assert.ok(resolutions >= 2);
      console.log("upstream-boundary-passed");
    `], { env: { ...Object.fromEntries(Object.entries(process.env).filter(([key]) =>
      ["PATH", "HOME", "USERPROFILE", "SystemRoot", "WINDIR", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA"].includes(key))),
      WIGOLO_DATA_DIR: temporary }, encoding: "utf8", timeout: 10000 });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /upstream-boundary-passed/);
  } finally { fs.rmSync(temporary, { recursive: true, force: true }); }
});

test("public socket lookup is pinned and retains TLS identity", async () => {
  const { pinnedFetch } = await import("./network-policy.mjs");
  let resolutions = 0;
  let sent = 0;
  const response = await pinnedFetch("https://source.example/paper", {}, {
    lookup: async () => { resolutions++; return [{ address: "93.184.216.34", family: 4 }]; },
    request: (url, options, received) => {
      assert.equal(url.hostname, "source.example");
      assert.equal(options.rejectUnauthorized, true);
      assert.equal(options.agent, false);
      for (let i = 0; i < 2; i++) options.lookup(url.hostname, {}, (error, address) => {
        assert.equal(error, null); assert.equal(address, "93.184.216.34");
      });
      const request = new EventEmitter();
      request.end = () => queueMicrotask(() => {
        sent++;
        const wire = new EventEmitter(); wire.statusCode = 200; wire.headers = {};
        received(wire); wire.emit("data", Buffer.from("Public content")); wire.emit("end");
      });
      return request;
    },
  });
  assert.equal(await response.text(), "Public content");
  assert.equal(resolutions, 1); assert.equal(sent, 1);
});

for (const addresses of [["127.0.0.1"], ["93.184.216.34", "10.0.0.1"], ["::ffff:127.0.0.1"], ["::1"]]) {
  test(`private or mixed DNS set is rejected before a request: ${addresses}`, async () => {
    const { pinnedFetch } = await import("./network-policy.mjs");
    await assert.rejects(pinnedFetch("https://source.example", {}, {
      lookup: async () => addresses.map(address => ({ address, family: address.includes(":") ? 6 : 4 })),
      request: () => assert.fail("private destination reached transport"),
    }), /public addresses/);
  });
}

test("browser requests use the pinned fetch and private redirects cannot continue", async () => {
  const { protectChromium } = await import("./network-policy.mjs");
  let routeHandler, webSocketHandler, contextOptions;
  const context = { addInitScript: async () => {}, route: async (_, handler) => { routeHandler = handler; },
    routeWebSocket: async (_, handler) => { webSocketHandler = handler; } };
  const browser = { close: async () => {}, newContext: async options => { contextOptions = options; return context; } };
  const chromium = { launch: async () => browser };
  const urls = [];
  protectChromium(chromium, async url => {
    urls.push(url);
    if (url.includes("127.0.0.1")) throw new Error("Private destination");
    return new Response(null, { status: 302, headers: { location: "http://127.0.0.1/secret" } });
  }, async () => ({ url: "http://127.0.0.1:32123", close: async () => {} }));
  await (await chromium.launch()).newContext({ ignoreHTTPSErrors: true, serviceWorkers: "allow" });
  assert.deepEqual(contextOptions.proxy, { server: "http://127.0.0.1:32123", bypass: "<-loopback>" });
  assert.equal(contextOptions.serviceWorkers, "block");
  assert.equal(contextOptions.ignoreHTTPSErrors, false);
  let fulfilled = 0, blocked = 0;
  for (const url of ["https://source.example", "http://127.0.0.1/secret"]) {
    await routeHandler({ request: () => ({ url: () => url, method: () => "GET",
      allHeaders: async () => ({}), postDataBuffer: () => null }),
      fulfill: async () => { fulfilled++; }, abort: async () => { blocked++; } });
  }
  assert.equal(fulfilled, 1); assert.equal(blocked, 1); assert.equal(urls.length, 2);
  let closed = false;
  webSocketHandler({ close: () => { closed = true; } }); assert.ok(closed);
  await assert.rejects(chromium.connectOverCDP("http://127.0.0.1"), /Unowned/);
});

test("failed browser launches and browser disconnection close their owned proxies", async () => {
  const { protectChromium } = await import("./network-policy.mjs");
  let closed = 0;
  const proxyFactory = async () => ({ url: "http://127.0.0.1:32123", close: async () => { closed++; } });
  const failed = { launch: async () => { throw new Error("Generated launch failure"); } };
  protectChromium(failed, undefined, proxyFactory);
  await assert.rejects(failed.launch(), /Generated launch failure/);
  assert.equal(closed, 1);
  const browser = new EventEmitter(); browser.close = async () => {}; browser.newContext = async () => {};
  const chromium = { launch: async options => {
    assert.equal(options.proxy.server, "http://127.0.0.1:32123");
    assert.ok(options.args.includes("--proxy-bypass-list=<-loopback>"));
    return browser;
  } };
  protectChromium(chromium, undefined, proxyFactory);
  await chromium.launch({ proxy: { server: "http://wrong.example" } });
  browser.emit("disconnected"); assert.equal(closed, 2);
});
