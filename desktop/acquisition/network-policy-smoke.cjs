// Offline real Chromium: all page requests terminate at generated fixtures.
const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const http = require("node:http");

(async () => {
  const { protectChromium, resolveDestination } = await import("./network-policy.mjs");
  const { createPublicProxy } = await import("./network-proxy.mjs");
  const requested = [];
  const blocked = [];
  const blockedSockets = [];
  const proxiedUrls = [];
  let sentinelRequests = 0;
  let sentinelConnections = 0;
  const sentinel = http.createServer((request, response) => {
    sentinelRequests++;
    response.writeHead(200, { "access-control-allow-origin": "*" });
    response.end("Private generated sentinel; must not be read");
  });
  sentinel.on("upgrade", (request, socket) => { sentinelRequests++; socket.destroy(); });
  sentinel.on("connection", () => { sentinelConnections++; });
  await new Promise((resolve, reject) => {
    sentinel.once("error", reject); sentinel.listen(0, "127.0.0.1", resolve);
  });
  const privateHttp = `http://127.0.0.1:${sentinel.address().port}`;
  const privateSocket = privateHttp.replace("http:", "ws:");
  const workerSource = `
    fetch(${JSON.stringify(privateHttp + "/worker")}).then(
      () => postMessage({kind:"fetch",outcome:"escaped"}),
      () => postMessage({kind:"fetch",outcome:"blocked"}));
    const socket = new WebSocket(${JSON.stringify(privateSocket + "/worker")});
    socket.onopen = () => postMessage({kind:"socket",outcome:"escaped"});
    socket.onclose = () => postMessage({kind:"socket",outcome:"blocked"});
  `;
  const nativeLaunch = chromium.launch.bind(chromium);
  chromium.launch = async options => {
    const browser = await nativeLaunch(options);
    const newContext = browser.newContext.bind(browser);
    browser.newContext = async contextOptions => {
      const context = await newContext(contextOptions);
      const routeSocket = context.routeWebSocket.bind(context);
      context.routeWebSocket = (pattern, handler) => routeSocket(pattern, socket => {
        blockedSockets.push(socket.url()); return handler(socket);
      });
      return context;
    };
    return browser;
  };
  protectChromium(chromium, async url => {
    requested.push(url);
    try {
      await resolveDestination(url, async () => [{ address: "93.184.216.34", family: 4 }]);
    } catch (error) { blocked.push(url); throw error; }
    if (url.endsWith("/redirect")) return new Response(null, {
      status: 302, headers: { location: privateHttp + "/redirected-private" },
    });
    if (url.endsWith("/worker-fixture")) return new Response("<html><body>Worker fixture</body></html>", {
      headers: { "content-type": "text/html" },
    });
    if (url.endsWith("/worker-public")) return new Response("Public worker rendering data");
    return new Response(`<!doctype html><html><body>Generated public fixture<script>
      window.outcome = "pending";
      fetch(${JSON.stringify(privateHttp + "/private")}).then(() => window.outcome = "escaped", () => window.outcome = "blocked");
      window.redirectOutcome = "pending";
      fetch("/redirect").then(() => window.redirectOutcome = "escaped", () => window.redirectOutcome = "blocked");
      window.websocketOutcome = "pending";
      const socket = new WebSocket(${JSON.stringify(privateSocket + "/private")});
      socket.onopen = () => window.websocketOutcome = "escaped";
      socket.onclose = () => window.websocketOutcome = "blocked";
      window.workerOutcome = "pending";
      navigator.serviceWorker.register("/sw.js").then(registration =>
        window.workerOutcome = registration?.active ? "escaped" : "blocked",
        () => window.workerOutcome = "blocked");
      window.dedicatedFetch = "unavailable"; window.dedicatedSocket = "unavailable";
      if (typeof Worker === "function") {
        window.dedicatedFetch = "pending"; window.dedicatedSocket = "pending";
        const worker = new Worker(URL.createObjectURL(new Blob([${JSON.stringify(workerSource)}], {type:"text/javascript"})));
        worker.onmessage = event => {
          window[event.data.kind === "fetch" ? "dedicatedFetch" : "dedicatedSocket"] = event.data.outcome;
        };
      }
    </script></body></html>`, { headers: { "content-type": "text/html" } });
  }, () => createPublicProxy({ fetch: async url => {
    proxiedUrls.push(url);
    await resolveDestination(url, async () => [{ address: "93.184.216.34", family: 4 }]);
    assert.equal(url, "http://source.example/worker-public");
    return new Response("Public worker rendering data", { headers: { "access-control-allow-origin": "*" } });
  } }));
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto("https://source.example/article");
    await page.waitForFunction(() => [window.outcome, window.redirectOutcome, window.websocketOutcome,
      window.workerOutcome, window.dedicatedFetch, window.dedicatedSocket]
      .every(value => value !== "pending"));
    assert.equal(await page.evaluate(() => window.outcome), "blocked");
    assert.equal(await page.evaluate(() => window.redirectOutcome), "blocked");
    assert.equal(await page.evaluate(() => window.websocketOutcome), "blocked");
    assert.equal(await page.evaluate(() => window.workerOutcome), "blocked");
    assert.equal(await page.evaluate(() => window.dedicatedFetch), "blocked");
    assert.equal(await page.evaluate(() => window.dedicatedSocket), "blocked");
    assert.equal(blockedSockets.length, 1);
    assert.equal(sentinelRequests, 0);
    assert.equal(sentinelConnections, 0);
    assert.ok(blocked.some(url => url.includes("127.0.0.1")));
    assert.ok(!requested.some(url => url.includes("sw.js")));
    assert.deepEqual(await page.evaluate(() => [typeof RTCPeerConnection, typeof WebTransport,
      typeof Worker, typeof SharedWorker]), ["undefined", "undefined", "function", "function"]);
    const workerPage = await context.newPage();
    await workerPage.goto("http://source.example/worker-fixture");
    const workerResults = await workerPage.evaluate(async ({ privateHttp, privateSocket }) => {
      async function check(shared) {
        const source = `async function run(port) {
          const results = {};
          try { results.public = await (await fetch("http://source.example/worker-public")).text(); }
          catch { results.public = "failed"; }
          try { await fetch(${JSON.stringify(privateHttp + "/worker-test")}); results.private = "escaped"; }
          catch { results.private = "blocked"; }
          const socket = new WebSocket(${JSON.stringify(privateSocket + "/worker-test")});
          results.socket = await new Promise(resolve => {
            socket.onopen = () => resolve("escaped"); socket.onclose = () => resolve("blocked");
          });
          const secureSocket = new WebSocket(${JSON.stringify(privateSocket.replace(/^ws:/, "wss:") + "/worker-test")});
          results.secureSocket = await new Promise(resolve => {
            secureSocket.onopen = () => resolve("escaped"); secureSocket.onclose = () => resolve("blocked");
          });
          port.postMessage(results);
        }
        ${shared ? "onconnect = event => run(event.ports[0]);" : "run(self);"}`;
        const url = URL.createObjectURL(new Blob([source], { type: "text/javascript" }));
        const worker = shared ? new SharedWorker(url) : new Worker(url);
        const port = shared ? worker.port : worker;
        try { return await new Promise((resolve, reject) => {
          const timer = setTimeout(() => reject(new Error("Worker deadline")), 10000);
          port.onmessage = event => { clearTimeout(timer); resolve(event.data); };
          if (shared) port.start();
        }); } finally {
          if (shared) port.close(); else worker.terminate(); URL.revokeObjectURL(url);
        }
      }
      return [await check(false), await check(true)];
    }, { privateHttp, privateSocket });
    assert.deepEqual(workerResults, Array.from({ length: 2 }, () => ({
      public: "Public worker rendering data", private: "blocked", socket: "blocked", secureSocket: "blocked",
    })));
    assert.ok(proxiedUrls.includes("http://source.example/worker-public"));
    assert.equal(sentinelRequests, 0); assert.equal(sentinelConnections, 0);
    console.log("PASS: real Chromium private HTTP/WebSockets are blocked; public dedicated/shared-worker rendering uses the proxy; zero private connections");
  } finally {
    if (browser) await browser.close();
    sentinel.closeAllConnections();
    await new Promise(resolve => sentinel.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
