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
  const root = path.resolve(__dirname, "../frontend/out");
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
    const rejectedResumeRunId = "44444444-4444-4444-8444-444444444444";
    const interruptedRunId = "55555555-5555-4555-8555-555555555555";
    let preferences = {
      modelProfile: "configurable-2026-09",
      stageModels: {
        planner: "gpt-6-luna-xhigh",
        scout: "gpt-6-luna-high",
        gap_analysis: "gpt-6-luna-xhigh",
        search_agent: "gpt-6-luna-xhigh",
        source_selection: "gpt-6-luna-xhigh",
        extractor: "gpt-6-luna-high",
        analyst: "gpt-6-luna-xhigh",
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
    let startCalls = 0;
    let recoveryMode = false;
    let recoveryHealthy = false;
    let recoveryTerminal = false;
    let cancelCalls = 0;
    let sourcePhase = 0;
    let releaseFirstRun = false;
    let firstReleased = false;
    let sourceCalls = 0;
    const source = (index, overrides = {}) => ({
      work_id: `work-${index}`,
      title: [
        "Regional education programs and course completion",
        "Matched comparison of course completion across districts",
        "Completion outcomes in a multi-site program evaluation",
        "A follow-up study of program participation and completion",
        "Course completion across regional programs: a systematic review",
        "A rural cohort study of program participation",
        "Course completion after a change to the intervention",
        "An independent replication with a different outcome measure",
      ][index - 1],
      url: `https://studies.example.org/work/${index}`,
      readable_url: null,
      first_round: index >= 7 ? 2 : 1,
      state: "lead",
      note: "Saved metadata describes a comparison of course completion rates between program participants and a comparison group.",
      note_kind: "metadata",
      angle: null,
      ...overrides,
    });
    const savedSources = () => {
      if (sourcePhase === 0) return [];
      if (sourcePhase === 1) return [source(1), source(2)];
      const screened = source(1, { state: "screened", note_kind: "scout", note: "Scout identified a direct outcome comparison." });
      if (sourcePhase === 2) return [screened, source(2)];
      const stages = [
        source(2, { state: "assessed", note_kind: "analyst", note: "The Analyst assessed the claim fit and evidence quality from the saved source." }),
        source(3, { state: "admitted", note_kind: "analyst", note: "The Analyst identified an eligible comparison from the saved source." }),
        source(4, { state: "screened", note_kind: "scout" }),
        source(5, { angle: "Systematic review" }),
        source(6, { angle: "Cohort study" }),
      ];
      return sourcePhase === 3
        ? [{ ...screened, state: "full_text", readable_url: "https://archive.example.org/verified/1" }, ...stages, source(7, { angle: "New in round 2" })]
        : [source(8, { state: "screened", note_kind: "scout" }), ...stages, source(7, { angle: "New in round 2" })];
    };
    let confirmCancellation;
    let snapshotCalls = 0;
    let activeSnapshots = 0;
    let maxActiveSnapshots = 0;
    let snapshotStartedResolve = () => {};
    let snapshotStarted = Promise.resolve();
    const armSnapshotStart = () => {
      snapshotStarted = new Promise((resolve) => { snapshotStartedResolve = resolve; });
    };
    const progress = { status: "running", model_attempts: 1, retrieval_attempts: 1, usable_snapshots: 1, candidates: 1 };
    const makeSnapshot = (classification, snapshotRunId = runId, overrides = {}) => ({
      run_id: snapshotRunId,
      db_path: database,
      raw_claim: started?.raw_claim ?? "A deterministic polling test claim",
      classification,
      exit_code: classification === "released" ? 0 : null,
      stage: classification === "released" ? "validation"
        : sourcePhase >= 3 ? "adaptive_search" : sourcePhase === 2 ? "scout" : "discovery",
      latest_checkpoint: null,
      completed_checkpoints: classification === "released" ? 1 : 0,
      total_checkpoints: 1,
      current_research_round: sourcePhase >= 3 ? 2 : 1,
      progress_percent: classification === "released" ? 100 : 10,
      message: classification === "released" ? "Research released."
        : sourcePhase >= 3 ? "Checking follow-up sources and comparing available evidence." : "Finding sources.",
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
      research_controls: { research_mode: "balanced", sources_per_stance_per_round: 10, discovery_providers: ["arxiv"], metadata_depth: 20 },
      v2_diagnostics: classification === "running" ? {
        logical_discovery_operations: 3,
        physical_search_requests: 3,
        retained_metadata_records: 12,
        sources_survived_probe: 2,
        approved_evidence_records: 1,
        diagnostic_messages: ["Offline saved coverage warning."],
      } : null,
      ...overrides,
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
            ["gpt-6-luna-high", "GPT-6 Luna · High", "openai"],
            ["gpt-6-luna-xhigh", "GPT-6 Luna · XHigh", "openai"],
            ["mimo-v2.6-pro", "MiMo v2.6 Pro", "mimo"],
            ["mimo-v2.6-flash", "MiMo v2.6 Flash", "mimo"],
            ["gpt-6-sol-high", "GPT-6 Sol · High", "openai"],
            ["gpt-5.6-terra-high", "GPT-5.6 Terra · High", "openai"],
          ].map(([id, label, provider]) => ({
            id,
            label,
            provider,
            input_per_million:
              id === "mimo-v2.6-pro" ? "0.435" :
              id === "mimo-v2.6-flash" ? "0.14" :
              id.startsWith("gpt-6-luna-") ? "0.10" : "2.00",
            output_per_million:
              id === "mimo-v2.6-pro" ? "0.87" :
              id === "mimo-v2.6-flash" ? "0.28" :
              id === "gpt-6-sol-high" ? "10.00" :
              id === "gpt-5.6-terra-high" ? "12.00" : "0.50",
          })),
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
        startCalls++;
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
          }, {
            run_id: rejectedResumeRunId,
            raw_claim: "A run with a rejected resume attempt",
            status: "running",
            stage: "discovery",
            updated_at: "2026-09-21T00:00:00Z",
          }, {
            run_id: interruptedRunId,
            raw_claim: "A run interrupted before restart",
            status: "running",
            stage: "discovery",
            updated_at: "2026-09-22T00:00:00Z",
          }],
        };
      } else if (pathname === `/api/research/${replacementRunId}`) {
        body = makeSnapshot("released", replacementRunId, {
          persisted_status: "completed",
          worker_active: false,
          attempt_diagnostic: {
            classification: "invalid_input",
            exit_code: 2,
            message: "A completed run rejected changed settings.",
            diagnostic_component: "startup",
          },
        });
      } else if (pathname === `/api/research/${rejectedResumeRunId}`) {
        snapshotCalls += 1;
        body = makeSnapshot("invalid_input", rejectedResumeRunId, {
          persisted_status: "running",
          worker_active: false,
          message: "Discovery settings changed; start a new run.",
          attempt_diagnostic: {
            classification: "invalid_input",
            exit_code: 2,
            message: "Discovery settings changed; start a new run.",
            diagnostic_component: "resume",
          },
        });
      } else if (pathname === `/api/research/${interruptedRunId}`) {
        snapshotCalls += 1;
        body = makeSnapshot("interrupted", interruptedRunId, {
          persisted_status: "running",
          worker_active: false,
          message: "No active worker in this app. Saved progress and reservations are unchanged; resume with the original settings or start a new run.",
        });
      } else if (pathname.endsWith("/live-sources")) {
        const id = pathname.split("/")[3];
        assert.equal(url.searchParams.get("db_path"), database);
        const revision = String(sourcePhase);
        const unchanged = url.searchParams.get("known") === revision;
        let items = id === runId ? savedSources() : [];
        if (id === runId && url.searchParams.has("offset") && sourcePhase === 4) {
          items = [
            ...items,
            source(1, { state: "full_text", readable_url: "https://archive.example.org/verified/1" }),
            source(9, { title: "Saved source with an unsafe link", url: "javascript:alert(1)" }),
          ];
        }
        if (id === runId) sourceCalls++;
        body = { run_id: id, revision, unchanged, items: unchanged ? [] : items, total: items.length };
      } else if (pathname === `/api/research/${runId}/cancel`) {
        cancelCalls++;
        await new Promise(resolve => { confirmCancellation = resolve; });
        body = { cancelled: true, message: "Cancellation requested." };
      } else if (pathname === `/api/research/${runId}`) {
        const call = ++snapshotCalls;
        activeSnapshots += 1;
        maxActiveSnapshots = Math.max(maxActiveSnapshots, activeSnapshots);
        snapshotStartedResolve();
        snapshotStartedResolve = () => {};
        try {
          if (recoveryMode) {
            assert.equal(request.method(), "GET");
            assert.equal(url.searchParams.get("db_path"), database);
            if (recoveryHealthy) body = makeSnapshot(recoveryTerminal ? "cancelled" : "running");
            else { status = 503; body = { detail: "Progress read unavailable" }; }
          } else if (call === 1) {
            await WAIT(25);
            status = 503;
            body = { detail: "Temporary status outage" };
          } else if (call === 2) {
            // This exceeds the old 1.5s interval, which would overlap call 3.
            await WAIT(1800);
            body = makeSnapshot("running");
          } else if (!firstReleased) {
            if (releaseFirstRun) {
              run = "released";
              firstReleased = true;
            }
            body = makeSnapshot(run);
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
    await page.getByLabel("Your research question", { exact: true }).fill("Does the regional education program increase course completion?");
    await page.getByRole("checkbox").check();
    armSnapshotStart();
    await page.getByRole("button", { name: "Begin research", exact: true }).click();
    await snapshotStarted;
    await page.mouse.move(5, 5);
    await page.getByText("Temporary status outage", { exact: true }).waitFor();
    const sources = page.getByRole("region", { name: "Sources found so far", exact: true });
    const cards = sources.locator(".live-source-card");
    await sources.getByText("Promising sources will appear here as they’re found.").waitFor();
    assert.equal(await cards.count(), 0);
    sourcePhase = 1;
    const initialCard = cards.filter({ hasText: source(1).title });
    await initialCard.getByText("Lead", { exact: true }).waitFor();
    sourcePhase = 2;
    await initialCard.getByText("Screened", { exact: true }).waitFor();
    sourcePhase = 3;
    await page.getByRole("button", { name: "Dismiss", exact: true }).click();
    await page.mouse.move(5, 5);
    await initialCard.getByText("Full text", { exact: true }).waitFor();
    assert.equal(await initialCard.getByRole("link").getAttribute("href"), "https://archive.example.org/verified/1");
    assert.equal(await cards.count(), 7);
    await cards.filter({ hasText: source(2).title }).getByText("Assessed", { exact: true }).waitFor();
    await cards.filter({ hasText: source(3).title }).getByText("Admitted", { exact: true }).waitFor();
    await sources.getByText("New in round 2", { exact: true }).waitFor();
    if (process.env.RESEARCHASSISTANT_SHORTLIST_SCREENSHOTS) {
      const screenshots = process.env.RESEARCHASSISTANT_SHORTLIST_SCREENSHOTS;
      await page.screenshot({ path: path.join(screenshots, "shortlist-desktop.png"), fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.screenshot({ path: path.join(screenshots, "shortlist-narrow.png"), fullPage: true });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390);
      await page.setViewportSize({ width: 1280, height: 860 });
    }
    await initialCard.hover();
    await initialCard.getByRole("link").focus();
    await initialCard.locator("summary").focus();
    await page.keyboard.press("Enter");
    await initialCard.getByText("Scout screening", { exact: true }).waitFor();
    const rotated = page.waitForResponse(async (response) =>
      response.url().includes(`/api/research/${runId}/live-sources`) &&
      (await response.json()).revision === "4"
    );
    sourcePhase = 4;
    await rotated;
    await page.mouse.move(5, 5);
    assert.equal(await initialCard.count(), 1, "The focused and open card stays in place");
    assert.equal(await page.locator(":focus").textContent(), "Source details");
    await page.keyboard.press("Enter");
    await initialCard.locator("details:not([open])").waitFor({ state: "attached" });
    await page.mouse.move(5, 5);
    await sources.locator(".all-live-sources > summary").focus();
    await cards.filter({ hasText: source(8).title }).waitFor();
    assert.equal(await initialCard.count(), 0);
    const browse = sources.getByText("All sources", { exact: true });
    await browse.click();
    await sources.getByRole("link", { name: source(1).title }).waitFor();
    await sources.getByText("Saved source with an unsafe link").waitFor();
    assert.equal(await sources.getByRole("link", { name: "Saved source with an unsafe link" }).count(), 0);
    await browse.click();
    releaseFirstRun = true;
    await page.getByText("Poll smoke result", { exact: true }).waitFor({ timeout: 10000 });
    await page.getByText("All sources", { exact: true }).click();
    await page.getByRole("link", { name: source(1).title }).waitFor();
    const sourceCallsAtStop = sourceCalls;
    assert.equal(maxActiveSnapshots, 1, "Delayed status responses must never overlap");
    const verifiedSameRunConcurrency = maxActiveSnapshots;
    const terminalCallCount = snapshotCalls;
    await WAIT(1800);
    assert.equal(snapshotCalls, terminalCallCount, "Terminal status must stop follow-up polling");
    assert.equal(sourceCalls, sourceCallsAtStop, "Terminal status must stop shortlist polling");

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
    assert.equal(await page.getByRole("link", { name: source(1).title }).count(), 0);
    await page.getByText("Latest execution attempt: The latest attempt could not use the requested settings. Check the research settings and try again.", { exact: true }).waitFor();

    await page.getByRole("button", { name: "Saved research", exact: true }).click();
    await page.getByText("A run with a rejected resume attempt", { exact: true }).click();
    await page.getByText("The latest resume attempt could not use the requested settings. Resume with the original settings or start a new run.", { exact: true }).first().waitFor();
    assert.equal(await page.locator(".report-meta").getByText("Metadata depth", { exact: true }).count(), 0);
    assert.equal(await page.getByRole("button", { name: "Cancel run", exact: true }).count(), 0, "A rejected resume with no worker must not show Cancel run");
    const rejectedResumePollCount = snapshotCalls;
    await WAIT(1800);
    assert.equal(snapshotCalls, rejectedResumePollCount, "A rejected resume attempt must stop polling");

    await page.getByRole("button", { name: "Saved research", exact: true }).click();
    await page.getByText("A run interrupted before restart", { exact: true }).click();
    await page.getByText("No active worker in this app. Saved progress and reservations are unchanged; resume with the original settings or start a new run.", { exact: true }).first().waitFor();
    assert.equal(await page.getByRole("button", { name: "Cancel run", exact: true }).count(), 0, "An interrupted run with no worker must not show Cancel run");
    const interruptedPollCount = snapshotCalls;
    await WAIT(1800);
    assert.equal(snapshotCalls, interruptedPollCount, "An interrupted run after restart must stop polling");

    await page.getByRole("button", { name: "Start new research", exact: true }).click();
    await page.getByLabel("Your research question", { exact: true }).fill("Does unmount cancel scheduled polling?");
    await page.getByRole("checkbox").check();
    armSnapshotStart();
    await page.getByRole("button", { name: "Begin research", exact: true }).click();
    await snapshotStarted;
    const callsBeforeUnmount = snapshotCalls;
    await page.reload();
    await page.getByRole("heading", { name: "Research a claim" }).waitFor();
    await WAIT(1800);
    assert.equal(snapshotCalls, callsBeforeUnmount, "Unmount must cancel the delayed follow-up");
    // Recover from repeated failures before the first snapshot, without a new run.
    recoveryMode = true;
    await page.getByRole("button", { name: "Research", exact: true }).click();
    await page.getByLabel("Your research question", { exact: true }).fill("Can this same run reconnect safely?");
    await page.getByRole("checkbox").check();
    const beforeRecovery = snapshotCalls;
    const recoveryStart = page.waitForResponse((response) => response.url().endsWith("/api/research/start"));
    await page.getByRole("button", { name: "Begin research", exact: true }).click();
    await recoveryStart;
    const recoveryStarts = startCalls;
    const connection = page.getByRole("region", { name: "Progress connection", exact: true });
    await connection.getByText(/Automatic retries paused/).waitFor();
    assert.equal(snapshotCalls, beforeRecovery + 3);
    await page.getByText("Preparing the trail", { exact: true }).waitFor();
    await connection.getByText("No progress snapshot confirmed yet.", { exact: true }).waitFor();
    await connection.getByRole("button", { name: "Cancel run", exact: true }).waitFor();
    await connection.getByRole("button", { name: "Open History", exact: true }).click();
    await page.getByText("A saved replacement run", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Research", exact: true }).click();
    await connection.getByText(/Automatic retries paused/).waitFor();
    await WAIT(1700);
    assert.equal(snapshotCalls, beforeRecovery + 3, "Navigation preserves the exhausted retry budget");
    recoveryHealthy = true;
    await connection.getByRole("button", { name: "Reconnect", exact: true }).click();
    await connection.getByText("Progress connection restored.", { exact: true }).waitFor();
    await cards.filter({ hasText: source(8).title }).waitFor();
    const lastConfirmed = await connection.locator("time").getAttribute("datetime");
    assert.ok(lastConfirmed);
    recoveryHealthy = false;
    await connection.getByText(/Automatic retries paused/).waitFor();
    assert.equal(await connection.locator("time").getAttribute("datetime"), lastConfirmed);
    await connection.getByText("Research may still be running.", { exact: true }).waitFor();
    assert.equal(await cards.count(), 7, "Last saved sources stay visible when progress disconnects");
    await connection.getByRole("button", { name: "Cancel run", exact: true }).click();
    await connection.getByRole("button", { name: "Sending cancellation…", exact: true }).waitFor();
    assert.equal(await connection.getByRole("button", { name: "Cancellation requested", exact: true }).count(), 0);
    confirmCancellation();
    const confirmedCancel = connection.getByRole("button", { name: "Cancellation requested", exact: true });
    await confirmedCancel.waitFor();
    assert.equal(await confirmedCancel.isDisabled(), true);
    assert.equal(cancelCalls, 1);
    assert.equal(startCalls, recoveryStarts, "Reconnection cannot start replacement research");
    recoveryHealthy = true;
    recoveryTerminal = true;
    await connection.getByRole("button", { name: "Reconnect", exact: true }).click();
    await page.getByRole("heading", { name: "No brief was released." }).waitFor();
    await page.getByText("All sources", { exact: true }).click();
    await page.getByRole("link", { name: source(1).title }).waitFor();
    assert.deepEqual(errors, []);
    console.log(`PASS: ${snapshotCalls} deterministic snapshots, live shortlist stages, rotation, stable focus, saved sources at stop, max same-run concurrency ${verifiedSameRunConcurrency}, terminal stop, committed release authority, rejected resume, interrupted restart, run replacement/unmount cleanup, bounded recovery before/after a snapshot, preserved retry budget, same-run reconnect and backend-confirmed cancellation.`);
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
