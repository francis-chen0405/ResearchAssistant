"use strict";

// Offline regression for selection changes while configuration checks are in flight.
const { chromium } = require("./acquisition/node_modules/playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");

const waitFor = (predicate, message) => new Promise((resolve, reject) => {
  const timeout = setTimeout(() => reject(new Error(message)), 5000);
  const poll = () => {
    if (predicate()) {
      clearTimeout(timeout);
      resolve();
    } else {
      setTimeout(poll, 10);
    }
  };
  poll();
});

async function main() {
  const root = path.resolve(__dirname, "../web/out");
  if (!fs.existsSync(path.join(root, "index.html"))) {
    throw new Error("Build the static web app before running this smoke (web/out/index.html is missing).");
  }
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, "http://localhost").pathname;
    const file = path.join(root, pathname === "/" ? "index.html" : pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      response.writeHead(404).end();
      return;
    }
    response.setHeader("Content-Type", ({ ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json" })[path.extname(file)] || "application/octet-stream");
    fs.createReadStream(file).pipe(response);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1280, height: 860 }, reducedMotion: "reduce" });
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));

    const stageModels = {
      planner: "gpt-6-luna-xhigh",
      scout: "gpt-6-luna-high",
      gap_analysis: "gpt-6-luna-xhigh",
      search_agent: "gpt-6-luna-xhigh",
      source_selection: "gpt-6-luna-xhigh",
      extractor: "gpt-6-luna-high",
      analyst: "gpt-6-luna-xhigh",
    };
    const preferences = {
      modelProfile: "configurable-2026-09", stageModels, dbPath: "/example/history.sqlite3",
      maxTokens: 500000, maxCost: "0.20", maxCalls: 160, supportEnabled: true,
      challengeEnabled: false, sourceTarget: 10, useSerpSearch: true, useExa: true,
      useOpenAlex: true, useArxiv: false, usePubmed: false, useCrossref: true,
    };
    const releaseStaleResponses = [];
    let initialRequestStarted;
    const initialRequest = new Promise((resolve) => { initialRequestStarted = resolve; });
    let intermediateRequestStarted;
    const intermediateRequest = new Promise((resolve) => { intermediateRequestStarted = resolve; });
    let latestRequestStarted;
    const latestRequest = new Promise((resolve) => { latestRequestStarted = resolve; });
    const options = [
      ["gpt-6-luna-high", "GPT-6 Luna · High", "openai", "0.10", "0.50"],
      ["gpt-6-luna-xhigh", "GPT-6 Luna · XHigh", "openai", "0.10", "0.50"],
      ["mimo-v2.6-pro", "MiMo v2.6 Pro", "mimo", "0.435", "0.87"],
      ["mimo-v2.6-flash", "MiMo v2.6 Flash", "mimo", "0.14", "0.28"],
      ["gpt-6-sol-high", "GPT-6 Sol · High", "openai", "2.00", "10.00"],
      ["gpt-5.6-terra-high", "GPT-5.6 Terra · High", "openai", "2.00", "12.00"],
    ].map(([id, label, provider, input_per_million, output_per_million]) => ({ id, label, provider, input_per_million, output_per_million }));

    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname;
      let status = 200;
      let body = {};
      if (pathname === "/api/preferences") {
        body = preferences;
      } else if (pathname === "/api/model-options") {
        body = { choices: options, defaults: stageModels };
      } else if (pathname === "/api/configuration/check") {
        assert.equal(request.method(), "POST");
        const payload = request.postDataJSON();
        assert.equal(payload.model_profile, "configurable-2026-09");
        if (payload.stage_models.scout === "gpt-6-luna-high") {
          initialRequestStarted();
          await new Promise((resolve) => { releaseStaleResponses.push(() => {
            body = { configured: false, message: "Stale selection is incomplete.", default_db_path: preferences.dbPath, saved_credentials: [], saved_settings: [], firecrawl_enabled: false, service: { wigolo_ready: true, state: "healthy", message: "Ready" } };
            resolve();
          }); });
        } else if (payload.stage_models.scout === "gpt-6-sol-high" && payload.stage_models.analyst === "gpt-6-luna-xhigh") {
          intermediateRequestStarted();
          await new Promise((resolve) => { releaseStaleResponses.push(() => {
            status = 503;
            body = { detail: "Stale selection request failed." };
            resolve();
          }); });
        } else if (payload.stage_models.scout === "gpt-6-sol-high" && payload.stage_models.analyst === "gpt-6-luna-high") {
          latestRequestStarted();
          body = { configured: true, message: "Current selection is configured.", default_db_path: preferences.dbPath, saved_credentials: ["openai", "mimo"], saved_settings: [], firecrawl_enabled: false, service: { wigolo_ready: true, state: "healthy", message: "Ready" } };
        } else {
          status = 422;
          body = { detail: "Unexpected model selection in configuration race smoke." };
        }
      } else {
        status = 404;
        body = { detail: "Unexpected API request in configuration race smoke." };
      }
      try {
        await route.fulfill({ status, json: body });
      } catch {
        // A correctly canceled stale fetch may close the intercepted route first.
      }
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await initialRequest;
    await page.getByRole("button", { name: "Explore the workspace", exact: true }).click();
    await page.locator("#stage-model-scout").selectOption("gpt-6-sol-high");
    await intermediateRequest;
    await page.locator("#stage-model-analyst").selectOption("gpt-6-luna-high");
    await latestRequest;
    await page.getByText("Providers configured", { exact: true }).waitFor();

    for (const releaseResponse of releaseStaleResponses.splice(0)) releaseResponse();
    await page.waitForTimeout(100);
    await page.getByText("Providers configured", { exact: true }).waitFor();
    assert.equal(await page.getByText("Setup needed", { exact: true }).count(), 0, "Stale success and failure must not replace the newest selection state");
    assert.equal(await page.getByText("App connection unavailable", { exact: true }).count(), 0, "A stale failure must not mark the current selection offline");
    assert.deepEqual(pageErrors, []);
    console.log("Verified stale configuration success and failure are ignored after selection changes.");
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
