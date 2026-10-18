// Owned loopback forward proxy. CONNECT preserves Chromium's end-to-end TLS.
import http from "node:http";
import net from "node:net";
import { pinnedFetch, resolveDestination } from "./network-policy.mjs";

const MAX_BYTES = 25 * 1024 * 1024;
const TIMEOUT_MS = 30000;

function checkedAuthority(authority) {
  if (!/^(?:\[[0-9a-f:.]+\]|[^\s:/@?#]+):\d{1,5}$/i.test(authority)) {
    throw new Error("Invalid CONNECT authority");
  }
  const url = new URL(`https://${authority}`);
  const port = Number(authority.slice(authority.lastIndexOf(":") + 1));
  if (port < 1 || port > 65535) throw new Error("Invalid CONNECT port");
  return url;
}

function sameAddress(actual, expected) {
  return actual === expected || actual === `::ffff:${expected}`;
}

export async function createPublicProxy(dependencies = {}) {
  const lookup = dependencies.lookup;
  const dial = dependencies.connect ?? net.connect;
  const fetchSource = dependencies.fetch ?? ((url, options) => pinnedFetch(url, options, { lookup }));
  const sockets = new Set();
  const operations = new Set();
  let closed = false;
  let closePromise;
  const ownSocket = socket => {
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
    socket.on("error", () => {});
    return socket;
  };
  const server = http.createServer(async (request, response) => {
    const abort = new AbortController();
    operations.add(abort);
    const timer = setTimeout(() => abort.abort(new Error("Proxy deadline exceeded")), TIMEOUT_MS);
    response.once("close", () => abort.abort());
    try {
      if (closed) throw new Error("Proxy closed");
      const url = new URL(request.url);
      if (url.protocol !== "http:") throw new Error("HTTPS requires CONNECT");
      const chunks = [];
      let bytes = 0;
      const interrupted = () => request.destroy();
      abort.signal.addEventListener("abort", interrupted, { once: true });
      try {
        for await (const chunk of request) {
          bytes += chunk.length;
          if (bytes > MAX_BYTES) throw new Error("Proxy request exceeds byte limit");
          chunks.push(chunk);
        }
      } finally { abort.signal.removeEventListener("abort", interrupted); }
      abort.signal.throwIfAborted();
      const headers = new Headers();
      const connectionHeaders = new Set((request.headers.connection ?? "").toLowerCase().split(",").map(value => value.trim()));
      for (const [name, value] of Object.entries(request.headers)) {
        if (value !== undefined && !connectionHeaders.has(name) && ![
          "host", "connection", "proxy-connection", "proxy-authorization", "keep-alive", "transfer-encoding", "upgrade",
        ].includes(name)) headers.set(name, Array.isArray(value) ? value.join(", ") : value);
      }
      const result = await fetchSource(url.href, { method: request.method, headers,
        body: bytes ? Buffer.concat(chunks) : undefined, signal: abort.signal });
      abort.signal.throwIfAborted();
      const resultHeaders = Object.fromEntries(result.headers);
      for (const name of ["connection", "keep-alive", "transfer-encoding", "upgrade", "proxy-authenticate"]) delete resultHeaders[name];
      response.writeHead(result.status, resultHeaders);
      response.end(Buffer.from(await result.arrayBuffer()));
    } catch {
      if (!response.headersSent && !response.destroyed) response.writeHead(502, { connection: "close" });
      response.end();
    } finally { clearTimeout(timer); operations.delete(abort); }
  });
  server.maxConnections = 16;
  server.headersTimeout = TIMEOUT_MS;
  server.requestTimeout = TIMEOUT_MS;
  server.on("connection", ownSocket);
  // Browser WebSockets can use CONNECT for wss:// or an HTTP upgrade for ws://.
  // Both socket paths share the same pinned destination and byte/time bounds.
  const tunnel = async (request, client, head, upgrade) => {
    const abort = new AbortController();
    operations.add(abort);
    let upstream;
    const stop = () => { abort.abort(); client.destroy(); upstream?.destroy(); };
    const timer = setTimeout(stop, TIMEOUT_MS);
    client.once("close", stop);
    try {
      if (closed) throw new Error("Proxy closed");
      const url = upgrade ? new URL(request.url) : checkedAuthority(request.url);
      if (upgrade && url.protocol !== "ws:" && url.protocol !== "http:") throw new Error("Invalid upgrade URL");
      // ws:// uses the same address policy as ordinary HTTP.
      const policyUrl = upgrade ? new URL(url.href.replace(/^ws:/, "http:")) : url;
      const destination = await Promise.race([
        resolveDestination(policyUrl.href, lookup),
        new Promise((_, reject) => abort.signal.addEventListener("abort", () => reject(new Error("Proxy closed")), { once: true })),
      ]);
      abort.signal.throwIfAborted();
      upstream = ownSocket(dial({ host: destination.address, family: destination.family,
        port: Number(url.port || (upgrade ? 80 : 443)) }));
      await new Promise((resolve, reject) => {
        upstream.once("connect", resolve); upstream.once("error", reject); upstream.once("close", () => reject(new Error("Proxy connection closed")));
      });
      abort.signal.throwIfAborted();
      if (!sameAddress(upstream.remoteAddress, destination.address)) throw new Error("Proxy peer differs from validated address");
      upstream.once("close", stop);
      if (upgrade) {
        const headers = { ...request.headers, host: url.host };
        delete headers["proxy-authorization"]; delete headers["proxy-connection"];
        const lines = Object.entries(headers).flatMap(([name, value]) =>
          (Array.isArray(value) ? value : [value]).map(item => `${name}: ${item}`));
        upstream.write(`${request.method} ${url.pathname}${url.search} HTTP/1.1\r\n${lines.join("\r\n")}\r\n\r\n`);
      } else client.write("HTTP/1.1 200 Connection Established\r\n\r\n");
      let sent = head.length, received = 0;
      if (sent > MAX_BYTES) throw new Error("Proxy tunnel exceeds byte limit");
      client.on("data", chunk => { sent += chunk.length; if (sent > MAX_BYTES) stop(); });
      upstream.on("data", chunk => { received += chunk.length; if (received > MAX_BYTES) stop(); });
      if (head.length) upstream.write(head);
      client.pipe(upstream); upstream.pipe(client);
      // Keep the deadline and operation owner until the tunnel actually closes.
      await new Promise(resolve => client.once("close", resolve));
    } catch {
      if (!client.destroyed) client.end("HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\nContent-Length: 0\r\n\r\n", () => client.destroy());
      upstream?.destroy();
    } finally { clearTimeout(timer); operations.delete(abort); client.removeListener("close", stop); }
  };
  server.on("connect", (request, client, head) => { void tunnel(request, client, head, false); });
  server.on("upgrade", (request, client, head) => { void tunnel(request, client, head, true); });
  try {
    await new Promise((resolve, reject) => {
      server.once("error", reject); server.listen(0, "127.0.0.1", resolve);
    });
  } catch (error) { server.close(); throw error; }
  return {
    url: `http://127.0.0.1:${server.address().port}`,
    close() {
      if (closePromise) return closePromise;
      closed = true;
      for (const abort of operations) abort.abort();
      for (const socket of sockets) socket.destroy();
      closePromise = new Promise(resolve => server.close(resolve));
      return closePromise;
    },
  };
}
