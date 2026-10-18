"use strict";
// Mounted-page readiness regression. Every API request is an offline fixture.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const { chromium } = require("./acquisition/node_modules/playwright");

async function main() {
  const root = path.resolve(__dirname, "../frontend/out");
  const shots = fs.mkdtempSync(path.join(os.tmpdir(), "ra-preferences-smoke-"));
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, "http://localhost").pathname;
    const file = path.join(root, pathname === "/" ? "index.html" : pathname);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      response.writeHead(404).end(); return;
    }
    response.setHeader("Content-Type", ({ ".html": "text/html", ".js": "text/javascript", ".css": "text/css" })[path.extname(file)] || "application/octet-stream");
    fs.createReadStream(file).pipe(response);
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1280, height: 860 }, reducedMotion: "reduce" });
    const errors = [], pendingReads = [], pendingImports = [], saves = [], starts = [];
    let importRequests = 0;
    page.on("pageerror", error => errors.push(error.message));
    const stageModels = { planner: "gpt-6-luna-xhigh", scout: "gpt-6-luna-high",
      gap_analysis: "gpt-6-luna-xhigh", search_agent: "gpt-6-luna-xhigh",
      source_selection: "gpt-6-luna-xhigh", extractor: "gpt-6-luna-high", analyst: "gpt-6-luna-xhigh" };
    const saved = { modelProfile: "configurable-2026-09", stageModels, dbPath: "/example/preferences.sqlite3",
      maxTokens: 500000, maxCost: "10.00", maxCalls: 160, supportEnabled: true, challengeEnabled: false,
      sourceTarget: 10, metadataDepth: 20, seedExpansionEnabled: true, scholarlySearchMode: "lexical",
      useSerpSearch: true, useExa: true, useOpenAlex: true, useArxiv: false, usePubmed: false, useCrossref: true };
    await page.route("**/api/**", async route => {
      const request = route.request();
      const url = new URL(request.url());
      assert.equal(url.origin, `http://127.0.0.1:${server.address().port}`);
      let result;
      if (url.pathname === "/api/preferences") {
        if (request.method() === "GET") result = await new Promise(resolve => pendingReads.push(resolve));
        else { saves.push(request.postDataJSON()); result = { status: 200, json: saves.at(-1) }; }
      } else if (url.pathname === "/api/model-options") {
        result = { status: 200, json: { choices: Object.values(stageModels).filter((value, index, all) => all.indexOf(value) === index)
          .map(id => ({ id, label: id, provider: "openai", input_per_million: "1", output_per_million: "1" })), defaults: stageModels } };
      } else if (url.pathname === "/api/configuration/check") {
        result = { status: 200, json: { configured: true, message: "Offline ready", default_db_path: saved.dbPath,
          firecrawl_enabled: false, saved_credentials: ["openai"], saved_settings: [],
          service: { state: "healthy", wigolo_ready: true, message: "Offline ready" } } };
      } else if (url.pathname === "/api/research/start") {
        starts.push(request.postDataJSON());
        result = { status: 200, json: { started: false, classification: "configuration_error",
          run_id: "11111111-1111-4111-8111-111111111111", message: "Offline submission captured; no research started." } };
      } else if (url.pathname === "/api/history/import") {
        importRequests++;
        result = await new Promise(resolve => pendingImports.push(resolve));
      } else result = { status: 404, json: { detail: "Unexpected offline request" } };
      try { await route.fulfill(result); } catch (error) {
        // Closing the panel deliberately aborts its pending import request.
        if (url.pathname !== "/api/history/import") throw error;
      }
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.getByText("Loading your saved settings…", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Research", exact: true }).click();
    assert.equal(await page.getByRole("button", { name: "Settings", exact: true }).isDisabled(), true);
    assert.equal(await page.getByRole("button", { name: /Provider setup/ }).isDisabled(), true);
    assert.equal(await page.getByLabel("Model budget limit").count(), 0);
    assert.equal(await page.getByRole("button", { name: /Begin research/ }).count(), 0);
    await page.waitForTimeout(450);
    assert.equal(saves.length, 0); assert.equal(starts.length, 0);
    await page.screenshot({ path: path.join(shots, "loading.png"), fullPage: true });
    assert.equal(pendingReads.length, 1);
    pendingReads.shift()({ status: 503, json: { detail: "Generated read failure" } });
    await page.getByRole("alert").waitFor();
    assert.equal(await page.getByRole("button", { name: "Settings", exact: true }).isDisabled(), true);
    await page.screenshot({ path: path.join(shots, "retry.png"), fullPage: true });
    await page.getByRole("button", { name: "Retry settings", exact: true }).click();
    await page.getByText("Loading your saved settings…", { exact: true }).waitFor();
    const deadline = Date.now() + 5000;
    while (!pendingReads.length && Date.now() < deadline) await page.waitForTimeout(20);
    assert.equal(pendingReads.length, 1); assert.equal(saves.length, 0);
    pendingReads.shift()({ status: 200, json: saved });
    const budget = page.getByLabel("Model budget limit");
    await budget.waitFor();
    assert.equal(await budget.inputValue(), "10.00");
    await budget.selectOption("0.50");
    await page.getByRole("button", { name: "Both sides", exact: true }).click();
    await page.getByLabel("Your research question", { exact: true }).fill("A generated offline claim");
    await page.getByRole("checkbox").check();
    const saveDeadline = Date.now() + 5000;
    while (saves.at(-1)?.maxCost !== "0.50" && Date.now() < saveDeadline) await page.waitForTimeout(20);
    assert.equal(saves.at(-1)?.maxCost, "0.50");
    assert.equal(saves.at(-1)?.challengeEnabled, true);
    await page.getByRole("button", { name: /Begin research/ }).click();
    await page.getByText("Offline submission captured; no research started.", { exact: true }).waitFor();
    assert.equal(starts.length, 1);
    assert.equal(starts[0].max_cost_usd, "0.50");
    assert.equal(starts[0].support_enabled, true); assert.equal(starts[0].challenge_enabled, true);
    assert.equal(await budget.inputValue(), "0.50");
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    let dialog = page.getByRole("dialog");
    await dialog.getByText("Advanced limits & history import", { exact: true }).click();
    await dialog.getByRole("button", { name: "Import this database into app storage", exact: true }).click();
    const importing = dialog.getByRole("button", { name: "Importing saved research…", exact: true });
    await importing.waitFor();
    assert.equal(await importing.isDisabled(), true);
    assert.equal(await dialog.getByLabel("SQLite database", { exact: true }).isDisabled(), true);
    assert.equal(await dialog.getByLabel("Run ID optional", { exact: true }).isDisabled(), true);
    await importing.evaluate(button => button.click());
    await dialog.getByLabel("Model cost ceiling").selectOption("0.20");
    await dialog.getByRole("switch", { name: "Challenge research", exact: true }).click();
    const importDeadline = Date.now() + 5000;
    while (!pendingImports.length && Date.now() < importDeadline) await page.waitForTimeout(20);
    assert.equal(importRequests, 1);
    pendingImports.shift()({ status: 200, json: { db_path: "/example/imported.sqlite3", run_count: 2 } });
    await dialog.getByText(/Imported 2 saved runs/).waitFor();
    assert.equal(await dialog.getByLabel("SQLite database", { exact: true }).inputValue(), "/example/imported.sqlite3");
    assert.equal(await dialog.getByLabel("Model cost ceiling").inputValue(), "0.20");
    assert.equal(await dialog.getByRole("switch", { name: "Challenge research", exact: true }).getAttribute("aria-checked"), "false");
    await dialog.getByRole("button", { name: "Import this database into app storage", exact: true }).click();
    await dialog.getByRole("button", { name: "Importing saved research…", exact: true }).waitFor();
    const lateDeadline = Date.now() + 5000;
    while (!pendingImports.length && Date.now() < lateDeadline) await page.waitForTimeout(20);
    assert.equal(importRequests, 2);
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    await budget.selectOption("1.00");
    pendingImports.shift()({ status: 200, json: { db_path: "/example/late-import.sqlite3", run_count: 3 } });
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByText("Advanced limits & history import", { exact: true }).click();
    assert.equal(await dialog.getByLabel("SQLite database", { exact: true }).inputValue(), "/example/imported.sqlite3");
    assert.equal(await dialog.getByLabel("Model cost ceiling").inputValue(), "1.00");
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    const finalSaveDeadline = Date.now() + 5000;
    while ((saves.at(-1)?.maxCost !== "1.00" || saves.at(-1)?.dbPath !== "/example/imported.sqlite3") && Date.now() < finalSaveDeadline) await page.waitForTimeout(20);
    assert.equal(saves.at(-1)?.maxCost, "1.00");
    assert.equal(saves.at(-1)?.dbPath, "/example/imported.sqlite3");
    assert.deepEqual(errors, []);
    await page.screenshot({ path: path.join(shots, "ready.png"), fullPage: true });
    console.log(`PASS: settings loading/error/retry gates editing/start; exact post-load values are saved/submitted; import preserves edits, rejects duplicates and ignores closed-panel completion. Screenshots: ${shots}`);
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
