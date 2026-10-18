// Application-owned boundary for the locked Wigolo 0.2.1 runtime.
import dns from "node:dns/promises";
import http from "node:http";
import https from "node:https";
import net from "node:net";
import { brotliDecompressSync, gunzipSync, inflateSync } from "node:zlib";
import ipaddr from "ipaddr.js";
import { createPublicProxy } from "./network-proxy.mjs";

export const NETWORK_POLICY = "ra-public-network-v1";
const MAX_BYTES = 25 * 1024 * 1024;

function publicAddress(value) {
  try { return ipaddr.parse(value).range() === "unicast"; } catch { return false; }
}

export async function resolveDestination(value, lookup = dns.lookup) {
  const url = new URL(value);
  const host = url.hostname.replace(/^\[|\]$/g, "").replace(/\.$/, "");
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || !host) {
    throw new Error("Source must be a credential-free HTTP(S) URL");
  }
  if (host === "localhost" || /\.(localhost|local|localdomain|internal|home|lan)$/i.test(host)) {
    throw new Error("Private source hostname blocked");
  }
  const addresses = net.isIP(host) ? [{ address: host, family: net.isIP(host) }]
    : await lookup(host, { all: true, verbatim: true });
  if (!addresses.length || addresses.some(item => !publicAddress(item.address))) {
    throw new Error("Source must resolve exclusively to public addresses");
  }
  return { url, address: addresses[0].address, family: addresses[0].family };
}

export async function pinnedFetch(value, options = {}, dependencies = {}) {
  const signal = AbortSignal.any([options.signal ?? new AbortController().signal, AbortSignal.timeout(30000)]);
  const destination = await Promise.race([
    resolveDestination(value, dependencies.lookup),
    new Promise((_, reject) => {
      if (signal.aborted) reject(signal.reason);
      else signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    }),
  ]);
  signal.throwIfAborted();
  const { url, address, family } = destination;
  const headers = new Headers(options.headers);
  // Preserve original Host/SNI. Never forward proxy credentials or a caller's
  // conflicting Host header to another destination.
  headers.delete("host");
  headers.delete("proxy-authorization");
  headers.set("accept-encoding", "identity");
  const send = dependencies.request ?? (url.protocol === "https:" ? https.request : http.request);
  return new Promise((resolve, reject) => {
    const request = send(url, {
      method: options.method ?? "GET", headers: Object.fromEntries(headers), signal,
      agent: false, rejectUnauthorized: true,
      // DNS is never consulted again by the socket connection.
      lookup: (_host, lookupOptions, callback) => {
        if (lookupOptions.all) callback(null, [{ address, family }]);
        else callback(null, address, family);
      },
    }, response => {
      const chunks = [];
      let size = 0;
      response.on("data", chunk => {
        size += chunk.length;
        if (size > MAX_BYTES) {
          const error = new Error("Source body exceeds byte limit");
          reject(error); request.destroy(error);
        }
        else chunks.push(chunk);
      });
      response.on("error", reject);
      response.on("aborted", () => reject(new Error("Source response was interrupted")));
      response.on("end", () => {
        try {
          let body = Buffer.concat(chunks);
          const resultHeaders = new Headers();
          for (const [key, value] of Object.entries(response.headers)) {
            if (value !== undefined) resultHeaders.set(key, Array.isArray(value) ? value.join(", ") : value);
          }
          const encoding = resultHeaders.get("content-encoding")?.toLowerCase();
          const decode = { gzip: gunzipSync, deflate: inflateSync, br: brotliDecompressSync }[encoding];
          if (decode) body = decode(body, { maxOutputLength: MAX_BYTES });
          else if (encoding && encoding !== "identity") throw new Error("Unsupported source encoding");
          resultHeaders.delete("content-encoding");
          resultHeaders.delete("content-length");
          resultHeaders.delete("transfer-encoding");
          const status = response.statusCode;
          resolve(new Response([204, 205, 304].includes(status) || options.method === "HEAD" ? null : body,
            { status, headers: resultHeaders }));
        } catch (error) { reject(error); }
      });
    });
    request.on("error", reject);
    if (options.body !== undefined && options.body !== null) {
      if (!(typeof options.body === "string" || Buffer.isBuffer(options.body) || options.body instanceof Uint8Array)) {
        request.destroy(new Error("Unsupported source request body"));
        return;
      }
      if (Buffer.byteLength(options.body) > MAX_BYTES) {
        request.destroy(new Error("Source request exceeds byte limit"));
        return;
      }
      request.write(options.body);
    }
    request.end();
  });
}

export async function protectContext(context, fetchSource = pinnedFetch) {
  try {
    await context.addInitScript(() => {
      // Rendering research text does not require peer-to-peer transports. Keep
      // them unavailable in every page/frame before untrusted scripts execute.
      for (const name of ["RTCPeerConnection", "webkitRTCPeerConnection", "mozRTCPeerConnection",
        "WebTransport"]) {
        Object.defineProperty(globalThis, name, { value: undefined, writable: false, configurable: false });
      }
    });
    await context.route("**/*", async route => {
      try {
        const request = route.request();
        const response = await fetchSource(request.url(), {
          method: request.method(), headers: await request.allHeaders(),
          body: request.postDataBuffer(),
        });
        await route.fulfill({ status: response.status,
          headers: Object.fromEntries(response.headers), body: Buffer.from(await response.arrayBuffer()) });
      } catch { await route.abort("blockedbyclient").catch(() => {}); }
    });
    // A handler that never connects to the server blocks browser WebSockets.
    await context.routeWebSocket("**/*", socket => Promise.resolve(socket.close()).catch(() => {}));
    return context;
  } catch (error) {
    await context.close();
    throw error;
  }
}

export function protectChromium(chromium, fetchSource = pinnedFetch, proxyFactory = createPublicProxy) {
  const launch = chromium.launch.bind(chromium);
  chromium.launch = async options => {
    const proxy = await proxyFactory();
    try {
      const proxyOptions = { server: proxy.url, bypass: "<-loopback>" };
      const browser = await launch({ ...options, proxy: proxyOptions, args: [...(options?.args ?? []),
        "--proxy-bypass-list=<-loopback>", "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
        "--disable-quic", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--disable-background-networking", "--disable-features=WebTransport,SpeculationRulesPrefetch,Prerender2"] });
      browser.on?.("disconnected", () => { void proxy.close().catch(() => {}); });
      const close = browser.close.bind(browser);
      browser.close = async (...args) => { try { return await close(...args); } finally { await proxy.close(); } };
      const newContext = browser.newContext.bind(browser);
      browser.newContext = async contextOptions => protectContext(await newContext({ ...contextOptions,
        proxy: proxyOptions, serviceWorkers: "block", acceptDownloads: false, ignoreHTTPSErrors: false }), fetchSource);
      return browser;
    } catch (error) { await proxy.close(); throw error; }
  };
  chromium.connectOverCDP = async () => { throw new Error("Unowned browser connections blocked"); };
  chromium.connect = chromium.connectOverCDP;
  chromium.launchPersistentContext = async () => { throw new Error("Persistent browser contexts blocked"); };
}

export function exposeNetworkPolicy(Server = http.Server) {
  const emit = Server.prototype.emit;
  Server.prototype.emit = function(event, ...args) {
    if (event === "request" && args[0].method === "GET" && args[0].url === "/ra/network-policy") {
      args[1].writeHead(200, { "content-type": "application/json" });
      args[1].end(JSON.stringify({ identity: NETWORK_POLICY }));
      return true;
    }
    return emit.call(this, event, ...args);
  };
}
