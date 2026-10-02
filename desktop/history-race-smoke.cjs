"use strict";

// Offline acceptance for database switches and overlapping saved-run opens.
const { chromium } = require("./acquisition/node_modules/playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");

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
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));

    const databaseA = "/example/first.sqlite3";
    const databaseB = "/example/second.sqlite3";
    const databaseC = "/example/third.sqlite3";
    const runA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    const runB = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    const models = {
      planner: "gpt-6-luna-xhigh", scout: "gpt-6-luna-high", gap_analysis: "gpt-6-luna-xhigh",
      search_agent: "gpt-6-luna-xhigh", source_selection: "gpt-6-luna-xhigh",
      extractor: "gpt-6-luna-high", analyst: "gpt-6-luna-xhigh",
    };
    const preferences = {
      modelProfile: "configurable-2026-09", stageModels: models, dbPath: databaseA,
      maxTokens: 500000, maxCost: "0.20", maxCalls: 160, supportEnabled: true,
      challengeEnabled: false, sourceTarget: 10, useSerpSearch: true, useExa: true,
      useOpenAlex: true, useArxiv: false, usePubmed: false, useCrossref: true,
    };
    let releaseOldHistory = () => {};
    let oldHistoryStartedResolve = () => {};
    let newHistoryStartedResolve = () => {};
    const oldHistoryStarted = new Promise((resolve) => { oldHistoryStartedResolve = resolve; });
    const newHistoryStarted = new Promise((resolve) => { newHistoryStartedResolve = resolve; });
    const makeRun = (runId, claim) => ({
      run_id: runId, db_path: databaseB, raw_claim: claim, classification: "failed", exit_code: null,
      stage: "discovery", latest_checkpoint: null, completed_checkpoints: 0, total_checkpoints: 1,
      current_research_round: 1, progress_percent: 0, message: "Research stopped.", diagnostic_component: "smoke",
      model_calls_used: 0, retrieval_attempts_used: 0, total_tokens: null, total_cost_usd: null,
      known_token_subtotal: 0, known_cost_subtotal_usd: "0", token_usage_complete: false,
      cost_usage_complete: false, conservative_reserved_tokens: null, conservative_reserved_cost_usd: null,
      supporting: { stance: "supporting", status: "stopped", model_attempts: 0, retrieval_attempts: 0, usable_snapshots: 0, candidates: 0 },
      opposing: { stance: "opposing", status: "disabled", model_attempts: 0, retrieval_attempts: 0, usable_snapshots: 0, candidates: 0 },
      validation_errors: [], final_brief: null, rendered_brief_hash: null, provider_identity: null,
      model_identity: null, fingerprint: null,
      research_controls: { research_mode: "focused", sources_per_stance_per_round: 5, discovery_providers: ["arxiv"] },
      v2_diagnostics: null,
    });

    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const pathname = url.pathname;
      let status = 200;
      let body = {};
      if (pathname === "/api/preferences") {
        if (request.method() === "POST") Object.assign(preferences, request.postDataJSON());
        body = preferences;
      } else if (pathname === "/api/model-options") {
        body = { choices: [], defaults: models };
      } else if (pathname === "/api/configuration/check") {
        body = { configured: true, message: "Ready", default_db_path: databaseA, saved_credentials: ["openai"], saved_settings: [], firecrawl_enabled: false, service: { wigolo_ready: true, state: "healthy", message: "Ready" } };
      } else if (pathname === "/api/history") {
        const database = url.searchParams.get("db_path");
        if (database === databaseA) {
          oldHistoryStartedResolve();
          await new Promise((resolve) => { releaseOldHistory = () => { body = { items: [{ run_id: runA, raw_claim: "Stale database run", status: "failed", stage: "discovery", updated_at: "2026-09-20T00:00:00Z", completed_at: null }] }; resolve(); }; });
        } else if (database === databaseB) {
          newHistoryStartedResolve();
          body = { items: [
            { run_id: runA, raw_claim: "Delayed older run", status: "failed", stage: "discovery", updated_at: "2026-09-20T00:00:00Z", completed_at: null },
            { run_id: runB, raw_claim: "Latest selected run", status: "failed", stage: "discovery", updated_at: "2026-09-21T00:00:00Z", completed_at: null },
          ] };
        } else {
          body = { items: [] };
        }
      } else if (pathname === `/api/research/${runA}`) {
        if (url.searchParams.get("db_path") === databaseB) {
          await new Promise((resolve) => setTimeout(resolve, 700));
          body = makeRun(runA, "Delayed older run");
        } else {
          status = 404;
          body = { detail: "Run not in selected database" };
        }
      } else if (pathname === `/api/research/${runB}`) {
        body = makeRun(runB, "Latest selected run");
      } else {
        status = 404;
        body = { detail: "Unexpected API request in history race smoke." };
      }
      try {
        await route.fulfill({ status, json: body });
      } catch {
        // A correctly invalidated stale request may be canceled before fulfillment.
      }
    });

    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.getByRole("button", { name: "Saved research", exact: true }).click();
    await oldHistoryStarted;
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    const settingsDialog = page.getByRole("dialog");
    await settingsDialog.locator("details.advanced-details > summary").click();
    await settingsDialog.getByLabel("SQLite database", { exact: true }).fill(databaseB);
    await newHistoryStarted;
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: /Latest selected run/ }).waitFor();
    releaseOldHistory();
    await page.waitForTimeout(100);
    assert.equal(await page.getByRole("button", { name: /Stale database run/ }).count(), 0, "A late response from the previous database must not replace the selected database history");

    const olderRunButton = page.getByRole("button", { name: /Delayed older run/ });
    await olderRunButton.evaluate((element) => element.click());
    await page.getByRole("button", { name: /Latest selected run/ }).click();
    await page.getByText("No brief was released.", { exact: true }).waitFor();
    await page.waitForTimeout(900);
    assert.equal(await page.locator(".result-masthead h2").innerText(), "Latest selected run", "The latest selected history row must win over an older delayed snapshot");

    await page.getByRole("button", { name: "Settings", exact: true }).click();
    const changedDatabaseDialog = page.getByRole("dialog");
    await changedDatabaseDialog.locator("details.advanced-details > summary").click();
    await changedDatabaseDialog.getByLabel("SQLite database", { exact: true }).fill(databaseC);
    await page.locator(".result-masthead h2").waitFor({ state: "detached" });
    assert.equal(await page.locator(".result-masthead h2").count(), 0, "Changing databases clears a terminal run selected from the previous database");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Saved research", exact: true }).click();
    await page.getByText("Your saved research will appear here.", { exact: false }).waitFor();

    await page.getByRole("button", { name: "Settings", exact: true }).click();
    const restoreDatabaseDialog = page.getByRole("dialog");
    await restoreDatabaseDialog.locator("details.advanced-details > summary").click();
    await restoreDatabaseDialog.getByLabel("SQLite database", { exact: true }).fill(databaseB);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: /Delayed older run/ }).waitFor();
    await page.getByRole("button", { name: /Delayed older run/ }).click();
    await page.getByRole("button", { name: "Home", exact: true }).click();
    await page.locator(".welcome-view").waitFor();
    await page.waitForTimeout(900);
    assert.equal(await page.locator(".welcome-view").count(), 1, "A late run response must not override navigation away from history");
    assert.equal(await page.locator(".result-masthead h2").count(), 0, "An unselected delayed history run must not replace the current view");
    assert.deepEqual(errors, []);
    console.log("PASS: stale history responses, overlapping run opens, old-database selection cleanup, and navigation during run loading.");
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
