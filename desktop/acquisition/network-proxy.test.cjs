const { test } = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const net = require("node:net");
const { once } = require("node:events");

async function exchange(proxy, data) {
  const socket = net.connect({ host: "127.0.0.1", port: Number(new URL(proxy.url).port) });
  const chunks = [];
  socket.setTimeout(5000, () => socket.destroy(new Error("Test exchange deadline")));
  socket.on("data", chunk => chunks.push(chunk));
  await once(socket, "connect");
  socket.write(data);
  await once(socket, "close");
  return Buffer.concat(chunks).toString();
}

test("forward proxy preserves original URL and body while removing proxy credentials", async () => {
  const { createPublicProxy } = await import("./network-proxy.mjs");
  let forwarded = 0;
  const proxy = await createPublicProxy({ fetch: async (url, options) => {
    forwarded++;
    assert.equal(url, "http://source.example/article");
    assert.equal(options.method, "POST");
    assert.equal(options.body.toString(), "hello");
    assert.equal(options.headers.get("proxy-authorization"), null);
    assert.equal(options.headers.get("host"), null);
    assert.equal(options.headers.get("x-connection-secret"), null);
    return new Response("Rendered source", { headers: { "content-type": "text/plain" } });
  } });
  try {
    const result = await new Promise((resolve, reject) => {
      const request = http.request(proxy.url, { method: "POST", path: "http://source.example/article",
        headers: { "proxy-authorization": "Basic generated", host: "wrong.example",
          connection: "close, x-connection-secret", "x-connection-secret": "generated" } }, response => {
        let body = ""; response.on("data", chunk => { body += chunk; }); response.on("end", () => resolve(body));
      });
      request.on("error", reject); request.end("hello");
    });
    assert.equal(result, "Rendered source"); assert.equal(forwarded, 1);
  } finally { await proxy.close(); }
});

test("proxy rejects private, mixed DNS and invalid CONNECT/upgrade targets before dialing", async () => {
  const { createPublicProxy } = await import("./network-proxy.mjs");
  const proxy = await createPublicProxy({
    lookup: async host => host === "mixed.example" ? [{ address: "93.184.216.34", family: 4 },
      { address: "10.0.0.1", family: 4 }] : [{ address: "127.0.0.1", family: 4 }],
    connect: () => assert.fail("Rejected target reached a socket"),
  });
  try {
    for (const target of ["127.0.0.1:443", "private.example:443", "mixed.example:443", "[::1]:443",
      "user@source.example:443", "source.example:443/path", "source.example:0", "source.example:99999"]) {
      assert.match(await exchange(proxy, `CONNECT ${target} HTTP/1.1\r\nHost: ${target}\r\n\r\n`), /502 Bad Gateway/);
    }
    for (const target of ["http://127.0.0.1/secret", "http://mixed.example/secret"]) {
      assert.match(await exchange(proxy, `GET ${target} HTTP/1.1\r\nHost: private.example\r\nConnection: close\r\n\r\n`), /502 Bad Gateway/);
      assert.match(await exchange(proxy, `GET ${target} HTTP/1.1\r\nHost: private.example\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n`), /502 Bad Gateway/);
    }
  } finally { await proxy.close(); }
});

test("CONNECT pins one public DNS result, preserves tunnel bytes and closes owned sockets", async () => {
  const { createPublicProxy } = await import("./network-proxy.mjs");
  const peers = new Set();
  const echo = net.createServer(socket => {
    peers.add(socket); socket.once("close", () => peers.delete(socket)); socket.pipe(socket);
  });
  await new Promise(resolve => echo.listen(0, "127.0.0.1", resolve));
  let resolutions = 0, dials = 0;
  const proxy = await createPublicProxy({ lookup: async host => {
    assert.equal(host, "source.example"); resolutions++;
    return [{ address: resolutions === 1 ? "93.184.216.34" : "127.0.0.1", family: 4 }];
  }, connect: options => {
    dials++; assert.deepEqual(options, { host: "93.184.216.34", family: 4, port: 443 });
    // Only this test adapter maps the validated public peer onto our owned echo.
    const socket = net.connect({ host: "127.0.0.1", port: echo.address().port });
    Object.defineProperty(socket, "remoteAddress", { value: "93.184.216.34" });
    return socket;
  } });
  let client;
  try {
    client = net.connect({ host: "127.0.0.1", port: Number(new URL(proxy.url).port) });
    await once(client, "connect");
    client.write("CONNECT source.example:443 HTTP/1.1\r\nHost: source.example:443\r\n\r\n");
    assert.match((await once(client, "data"))[0].toString(), /200 Connection Established/);
    const tlsBytes = Buffer.from("160301000a0100000667656e657261", "hex");
    client.write(tlsBytes);
    assert.deepEqual((await once(client, "data"))[0], tlsBytes);
    assert.equal(resolutions, 1); assert.equal(dials, 1);
    const ended = once(client, "close");
    await proxy.close(); await ended;
    await assert.rejects(new Promise((resolve, reject) => {
      const socket = net.connect({ host: "127.0.0.1", port: Number(new URL(proxy.url).port) });
      socket.once("connect", () => { socket.destroy(); resolve(); }); socket.once("error", reject);
    }), /ECONNREFUSED/);
  } finally {
    client?.destroy(); await proxy.close(); for (const socket of peers) socket.destroy();
    await new Promise(resolve => echo.close(resolve));
  }
});

test("CONNECT rejects a socket whose peer disagrees with its validated address", async () => {
  const { createPublicProxy } = await import("./network-proxy.mjs");
  const peers = new Set();
  let contentBytes = 0;
  const sentinel = net.createServer(socket => {
    peers.add(socket); socket.once("close", () => peers.delete(socket));
    socket.on("data", chunk => { contentBytes += chunk.length; });
  });
  await new Promise(resolve => sentinel.listen(0, "127.0.0.1", resolve));
  const proxy = await createPublicProxy({ lookup: async () => [{ address: "93.184.216.34", family: 4 }],
    connect: () => net.connect({ host: "127.0.0.1", port: sentinel.address().port }) });
  try {
    assert.match(await exchange(proxy, "CONNECT source.example:443 HTTP/1.1\r\nHost: source.example\r\n\r\n"), /502 Bad Gateway/);
    assert.equal(contentBytes, 0);
  } finally {
    await proxy.close(); for (const socket of peers) socket.destroy();
    await new Promise(resolve => sentinel.close(resolve));
  }
});

test("closing the proxy aborts pending DNS and prevents a late connection", async () => {
  const { createPublicProxy } = await import("./network-proxy.mjs");
  let finishLookup, startedLookup;
  const started = new Promise(resolve => { startedLookup = resolve; });
  const proxy = await createPublicProxy({ lookup: () => {
    startedLookup(); return new Promise(resolve => { finishLookup = resolve; });
  }, connect: () => assert.fail("Closed proxy dialed a late DNS result") });
  const client = net.connect({ host: "127.0.0.1", port: Number(new URL(proxy.url).port) });
  try {
    await once(client, "connect");
    client.write("CONNECT source.example:443 HTTP/1.1\r\nHost: source.example\r\n\r\n");
    await started;
    const ended = once(client, "close");
    await proxy.close(); await ended;
    finishLookup([{ address: "93.184.216.34", family: 4 }]);
    await new Promise(resolve => setImmediate(resolve));
  } finally { client.destroy(); await proxy.close(); }
});
