// Load before the locked Wigolo entry point; do not modify installed dependencies.
import { chromium, firefox, webkit } from "playwright";
import { registerHooks } from "node:module";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { exposeNetworkPolicy, protectChromium } from "./network-policy.mjs";

const sourceHashes = new Map(Object.entries({
  "router.js": "d3459edd5b8cd5790bcec48b3aae7b9ef02e09a1582ed18b57b50cc20bac85b9",
  "http-client.js": "708dc18a71974a8722cac462786c29f42f529bdaeeac7793db939eda942038ac",
  "browser-pool.js": "34dabb86d958dc7b4a493fb6b1c64e46a44c972cbb9abdc7e19684a47552dfad",
}).map(([name, hash]) => [new URL(`./node_modules/wigolo/dist/fetch/${name}`, import.meta.url).href, hash]));
for (const [url, hash] of sourceHashes) {
  if (createHash("sha256").update(readFileSync(new URL(url))).digest("hex") !== hash) {
    throw new Error("Protected acquisition requires the reviewed Wigolo 0.2.1 sources");
  }
}
const policyUrl = new URL("./network-policy.mjs", import.meta.url).href;
registerHooks({ load(url, context, nextLoad) {
  const result = nextLoad(url, context);
  // Scope fetch replacement to the two source-fetch owners, preserving ordinary
  // runtime/model-download behavior elsewhere in the locked upstream package.
  if (sourceHashes.has(url) && !url.endsWith("browser-pool.js")) {
    return { ...result, source: `import { pinnedFetch as fetch } from ${JSON.stringify(policyUrl)};\n${result.source}` };
  }
  return result;
} });
const { SmartRouter } = await import("./node_modules/wigolo/dist/fetch/router.js");
protectChromium(chromium);
for (const browser of [firefox, webkit]) {
  browser.launch = async () => { throw new Error("Only the protected Chromium runtime is enabled"); };
  browser.launchPersistentContext = browser.launch;
  browser.connect = browser.launch;
}
// The pinned application policy uses HTTP and Chromium. Native TLS/cloud escape
// transports cannot bypass the reviewed outbound boundary through saved settings.
SmartRouter.prototype.tryTlsTier = async () => ({ ok: false });
SmartRouter.prototype.tryEscapeHatch = async () => null;
exposeNetworkPolicy();
