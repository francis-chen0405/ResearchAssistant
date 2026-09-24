"use strict";

// Deterministic offline acceptance for the live status-polling loop. The browser
// drives the real exported page while every application API request is mocked.
const { chromium } = require("./acquisition/node_modules/playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");

const WAIT = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function main() {
  const root = path.resolve(__dirname, "../web/out");
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, "http://localhost").pathname;
    const file = path.join(root, pathname === "/" ? "index.html" : pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      response.writeHead(404).end();
      return;
    }
    response.setHeader("Content-Type", ({ ".html": "text/html", ".js": "text/javascript", ".css": "text/css" })[path.extname(file)] || "application/octet-stream");
    fs.createReadStream(file).pipe(response);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1280, height: 860 }, reducedMotion: "reduce" });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));

    const database = "/example/history.sqlite3";
    const runId = "22222222-2222-4222-8222-222222222222";
    const replacementRunId = "33333333-3333-4333-8333-333333333333";
    let preferences = {
      modelProfile: "configurable-2026-09",
      stageModels: {
        planner: "gpt-5.6-luna-xhigh",
        scout: "gpt-5.6-luna-high",
        gap_analysis: "gpt-5.6-luna-xhigh",
        search_agent: "gpt-5.6-luna-xhigh",
        source_selection: "gpt-5.6-luna-xhigh",
        extractor: "gpt-5.6-luna-high",
        analyst: "gpt-5.6-luna-xhigh",
      },
      dbPath: database,
      maxTokens: 500000,
      maxCost: "0.20",
      maxCalls: 160,
      supportEnabled: true,
      challengeEnabled: false,
      sourceTarget: 10,
      useSerpSearch: true,
      useExa: true,
      useOpenAlex: true,
      useArxiv: false,
      usePubmed: false,
      useCrossref: true,
    };
    let run = null;
    let started = null;
    let snapshotCalls = 0;
    let activeSnapshots = 0;
    let maxActiveSnapshots = 0;
    let snapshotStartedResolve = () => {};
    let snapshotStarted = Promise.resolve();
    const armSnapshotStart = () => {
      snapshotStarted = new Promise((resolve) => { snapshotStartedResolve = resolve; });
    };
    const progress = { status: "running", model_attempts: 1, retrieval_attempts: 1, usable_snapshots: 1, candidates: 1 };
    const makeSnapshot = (classification, snapshotRunId = runId) => ({
      run_id: snapshotRunId,
      db_path: database,
      raw_claim: started?.raw_claim ?? "A deterministic polling test claim",
      classification,
      exit_code: classification === "released" ? 0 : null,
      stage: classification === "released" ? "validation" : "discovery",
      latest_checkpoint: null,
      completed_checkpoints: classification === "released" ? 1 : 0,
      total_checkpoints: 1,
      current_research_round: 1,
      progress_percent: classification === "released" ? 100 : 10,
      message: classification === "released" ? "Research released." : "Finding sources.",
      diagnostic_component: "poll-smoke",
      model_calls_used: 1,
      retrieval_attempts_used: 1,
      total_tokens: null,
      total_cost_usd: null,
      known_token_subtotal: 0,
      known_cost_subtotal_usd: "0",
      token_usage_complete: false,
      cost_usage_complete: false,
      conservative_reserved_tokens: null,
      conservative_reserved_cost_usd: null,
      supporting: { ...progress, stance: "supporting" },
      opposing: { ...progress, stance: "opposing" },
      validation_errors: [],
      final_brief: classification === "released" ? "# Poll smoke result\n" : null,
      rendered_brief_hash: classification === "released" ? "b".repeat(64) : null,
      provider_identity: null,
      model_identity: null,
      fingerprint: null,
      research_controls: { research_mode: "balanced", sources_per_stance_per_round: 10, discovery_providers: ["arxiv"] },
      v2_diagnostics: null,
    });

    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const pathname = url.pathname;
      let status = 200;
      let body = {};

      if (pathname === "/api/preferences") {
        if (request.method() === "POST") preferences = request.postDataJSON();
        body = preferences;
      } else if (pathname === "/api/model-options") {
        body = {
          choices: [
            ["gpt-5.6-luna-high", "GPT-5.6 Luna · High", "openai"],
            ["gpt-5.6-luna-xhigh", "GPT-5.6 Luna · XHigh", "openai"],
            ["mimo-v2.6-pro", "MiMo v2.6 Pro", "mimo"],
            ["mimo-v2.6-flash", "MiMo v2.6 Flash", "mimo"],
            ["gpt-6-sol-high", "GPT-6 Sol · High", "openai"],
            ["gpt-5.6-terra-high", "GPT-5.6 Terra · High", "openai"],
          ].map(([id, label, provider]) => ({ id, label, provider, input_per_million: "0.20", output_per_million: "1.20" })),
          defaults: preferences.stageModels,
        };
      } else if (pathname === "/api/configuration/check") {
        assert.equal(request.method(), "POST");
        const payload = request.postDataJSON();
        assert.equal(payload.model_profile, "configurable-2026-09");
        assert.deepEqual(payload.stage_models, preferences.stageModels);
        body = {
          configured: true,
          message: "Offline polling test configuration",
          default_db_path: database,
          saved_credentials: ["mimo", "openai"],
          saved_settings: [],
          firecrawl_enabled: false,
          service: { wigolo_ready: true, state: "healthy", message: "Research tools ready" },
        };
      } else if (pathname === "/api/research/start") {
        started = request.postDataJSON();
        run = "running";
        body = { started: true, run_id: runId, classification: "starting", message: "Research started." };
      } else if (pathname === "/api/history") {
        body = {
          items: [{
            run_id: replacementRunId,
            raw_claim: "A saved replacement run",
            status: "released",
            stage: "validation",
            updated_at: "2026-09-20T00:00:00Z",
          }],
        };
      } else if (pathname === `/api/research/${replacementRunId}`) {
        body = makeSnapshot("released", replacementRunId);
      } else if (pathname === `/api/research/${runId}`) {
        const call = ++snapshotCalls;
        activeSnapshots += 1;
        maxActiveSnapshots = Math.max(maxActiveSnapshots, activeSnapshots);
        snapshotStartedResolve();
        snapshotStartedResolve = () => {};
        try {
          if (call === 1) {
            await WAIT(25);
            status = 503;
            body = { detail: "Temporary status outage" };
          } else if (call === 2) {
            // This exceeds the old 1.5s interval, which would overlap call 3.
            await WAIT(1800);
            body = makeSnapshot("running");
          } else if (call === 3) {
            await WAIT(25);
            run = "released";
            body = makeSnapshot("released");
          } else {
            // The second run is intentionally left in flight until the page unmounts.
            await WAIT(5000);
            body = makeSnapshot(run ?? "running");
          }
        } finally {
          activeSnapshots -= 1;
        }
      } else {
        status = 404;
        body = { detail: "Unknown mocked API" };
      }
      try {
        await route.fulfill({ status, json: body });
      } catch {
        // Page reload/unmount can abort an intentionally delayed request.
      }
    });

    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.getByRole("button", { name: "Research", exact: true }).click();
    await page.getByLabel("Your research question", { exact: true }).fill("Can a delayed poll overlap its successor?");
    await page.getByRole("checkbox").check();
    armSnapshotStart();
    await page.getByRole("button", { name: "Begin research", exact: true }).click();
    await snapshotStarted;
    await page.getByText("Temporary status outage", { exact: true }).waitFor();
    await page.getByText("Poll smoke result", { exact: true }).waitFor({ timeout: 10000 });

    assert.equal(maxActiveSnapshots, 1, "Delayed status responses must never overlap");
    const verifiedSameRunConcurrency = maxActiveSnapshots;
    const terminalCallCount = snapshotCalls;
    await WAIT(1800);
    assert.equal(snapshotCalls, terminalCallCount, "Terminal status must stop follow-up polling");

    await page.getByRole("button", { name: "Start new research", exact: true }).click();
    await page.getByLabel("Your research question", { exact: true }).fill("Does replacement cancel scheduled polling?");
    await page.getByRole("checkbox").check();
    armSnapshotStart();
    await page.getByRole("button", { name: "Begin research", exact: true }).click();
    await snapshotStarted;
    const callsBeforeReplacement = snapshotCalls;
    await page.getByRole("button", { name: "Saved research", exact: true }).click();
    await page.getByText("A saved replacement run", { exact: true }).click();
    await page.getByText("Poll smoke result", { exact: true }).waitFor();
    await WAIT(1800);
    assert.equal(snapshotCalls, callsBeforeReplacement, "Run replacement must cancel old follow-up polling");

    await page.getByRole("button", { name: "Start new research", exact: true }).click();
    await page.getByLabel("Your research question", { exact: true }).fill("Does unmount cancel scheduled polling?");
    await page.getByRole("checkbox").check();
    armSnapshotStart();
    await page.getByRole("button", { name: "Begin research", exact: true }).click();
    await snapshotStarted;
    const callsBeforeUnmount = snapshotCalls;
    await page.reload();
    await page.getByRole("heading", { name: "Research a claim." }).waitFor();
    await WAIT(1800);
    assert.equal(snapshotCalls, callsBeforeUnmount, "Unmount must cancel the delayed follow-up");
    assert.deepEqual(errors, []);
    console.log(`PASS: ${snapshotCalls} deterministic snapshots, max same-run concurrency ${verifiedSameRunConcurrency}, terminal stop, run replacement and unmount cleanup.`);
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
