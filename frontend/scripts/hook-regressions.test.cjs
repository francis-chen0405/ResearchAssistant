/* eslint-disable @typescript-eslint/no-require-imports */
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

// Execute the actual hook actions with deterministic state and API boundaries.
// Browser acceptance separately covers React mounts, aborts and rendering.
function hookHarness(relative, api, options = {}) {
  const state = [];
  const effects = [];
  const layoutEffects = [];
  let cursor = 0;
  let effectCursor = 0;
  const mountedEffects = new Map();
  const sameDeps = (before, after) => before && after && before.length === after.length
    && before.every((value, index) => Object.is(value, after[index]));
  const effect = (list, callback, deps) => list.push({ callback, deps, index: effectCursor++ });
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in state)) state[index] = initial;
      return [state[index], (value) => {
        state[index] = typeof value === "function" ? value(state[index]) : value;
      }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in state)) state[index] = { current: initial };
      return state[index];
    },
    useCallback(callback, deps) {
      if (!options.trackEffects) return callback;
      const index = cursor++;
      if (!sameDeps(state[index]?.deps, deps)) state[index] = { callback, deps };
      return state[index].callback;
    },
    useMemo(factory) { return factory(); },
    useLayoutEffect(callback, deps) { effect(layoutEffects, callback, deps); },
    useEffect(callback, deps) { effect(effects, callback, deps); },
  };
  function load(file) {
    const compiled = { exports: {} };
    const code = ts.transpileModule(fs.readFileSync(file, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
    }).outputText;
    vm.runInNewContext(code, {
      exports: compiled.exports, AbortController, Error, Set, Promise, URL,
      process: { env: {} }, window: options.clock ?? { setTimeout, clearTimeout },
      fetch: options.fetch ?? fetch,
      Date: options.clock ? class extends Date { static now() { return options.clock.now; } } : Date,
      require(name) {
        if (name === "react") return react;
        if (name === "react/jsx-runtime") return { jsx: (type, props) => ({ type, props }),
          jsxs: (type, props) => ({ type, props }), Fragment: "Fragment" };
        if (name === "./dialog") return { Dialog: "Dialog" };
        if (name === "./workspace" || name === "@/components/workspace") return { StatusPill: "StatusPill" };
        if (name === "@/lib/api") return { ...load(path.resolve(__dirname, "../lib/api.ts")), researchApi: api };
        const resolved = path.resolve(path.dirname(file), `${name}.ts`);
        return load(fs.existsSync(resolved) ? resolved : resolved.replace(/\.ts$/, ".tsx"));
      },
    });
    return compiled.exports;
  }
  const exports = load(path.resolve(__dirname, "..", relative));
  return {
    exports,
    render(name, ...args) { cursor = 0; effectCursor = 0; effects.length = 0; layoutEffects.length = 0; return exports[name](...args); },
    runEffects() { return [...layoutEffects, ...effects].map(({ callback }) => callback()); },
    runLayoutEffects() { return layoutEffects.map(({ callback }) => callback()); },
    commitEffects() {
      for (const { callback, deps, index } of [...layoutEffects, ...effects]) {
        const previous = mountedEffects.get(index);
        if (previous && sameDeps(previous.deps, deps)) continue;
        previous?.cleanup?.();
        mountedEffects.set(index, { deps, cleanup: callback() });
      }
    },
    dispose() {
      for (const { cleanup } of mountedEffects.values()) cleanup?.();
      mountedEffects.clear();
    },
  };
}

function elementNodes(value) {
  if (!value || typeof value !== "object") return [];
  if (Array.isArray(value)) return value.flatMap(elementNodes);
  return [value, ...elementNodes(value.props?.children)];
}

test("source cards mark unassessed recommendations provisional and qualify partial evidence", () => {
  const harness = hookHarness("features/results/source-sections.tsx", {});
  const unassessedId = "unassessed-source";
  const partialId = "partial-source";
  const directId = "direct-source";
  const source = (sourceId, title) => ({
    source_id: sourceId, direction: "support", source_url: `https://example.test/${sourceId}`,
    title, source_type: "Article", publication_date: null, discovery_providers: ["exa"],
    discovery_round: 1, recommended: true, recommendation_rank: 1, queue_rank: 1,
    status: "recommended_analyzed", ledger_claim_ids: [], budget_prevented_reason: null,
  });
  const result = {
    recommended_sources: [source(unassessedId, "Unassessed"), source(partialId, "Qualified"), source(directId, "Direct")],
    all_surviving_sources: [source(unassessedId, "Unassessed"), source(partialId, "Qualified"), source(directId, "Direct")],
  };
  const evidence = {
    source_budget_outcomes: [], source_titles: [], study_lineage: [], shared_website_groups: [],
    items: [{
      source_id: partialId, relationship_to_claim: "qualifies", claim_fit: 4,
      gap_ids: [], selection_rationale: "Selected for comparison.",
    }, { source_id: directId, relationship_to_claim: "supports", claim_fit: 5, gap_ids: [] }],
  };
  const rendered = JSON.stringify(elementNodes(harness.render("SourceSections", { result, evidence })));
  assert.match(rendered, /Provisional · claim relationship has not been assessed\./);
  assert.match(rendered, /Qualifying evidence/);
  assert.match(rendered, /Direct support/);
});

test("provider outcome labels separate blocked and unknown requests from failures", () => {
  const { exports } = hookHarness("features/shared/presentation.ts", {});
  const { providerOutcomeLabel } = exports;
  const outcome = {
    query_attempts: 2, graph_actions: 0, search_results: 0,
    empty_queries: 0, timeout_queries: 0, failed_queries: 1,
    blocked_queries: 2, unknown_queries: 1, surviving_sources: 0,
  };
  assert.equal(
    providerOutcomeLabel(outcome),
    "2 queries · 0 results · 1 failed · 2 blocked before dispatch · 1 outcome unknown",
  );
  assert.equal(
    providerOutcomeLabel({ ...outcome, blocked_queries: 1, unknown_queries: 2 }),
    "2 queries · 0 results · 1 failed · 1 blocked before dispatch · 2 outcomes unknown",
  );
  assert.equal(
    providerOutcomeLabel({
      query_attempts: 0, graph_actions: 0, search_results: 0,
      empty_queries: 0, timeout_queries: 0, failed_queries: 0,
      blocked_queries: 2, unknown_queries: 0, surviving_sources: 0,
    }),
    "2 blocked before dispatch",
  );
  const historical = { ...outcome };
  delete historical.blocked_queries;
  delete historical.unknown_queries;
  assert.equal(
    providerOutcomeLabel(historical),
    "2 queries · 0 results · 1 failed",
  );
});

test("source cards link alternate URLs as locations for the same paper", () => {
  const harness = hookHarness("features/results/source-sections.tsx", {});
  const source = {
    source_id: "same-paper", direction: "support", source_url: "https://example.test/main",
    alternate_source_urls: ["https://example.test/alternate"],
    title: "Same paper", source_type: "Article", publication_date: null,
    discovery_providers: ["exa"], discovery_round: 1, recommended: true,
    recommendation_rank: 1, queue_rank: 1, status: "recommended_no_ledger_evidence",
    ledger_claim_ids: [], budget_prevented_reason: null,
  };
  const result = { recommended_sources: [source], all_surviving_sources: [source] };
  const rendered = elementNodes(harness.render("SourceSections", { result, evidence: null }));
  const alternate = rendered.find(
    node => node.type === "a" && node.props.href === source.alternate_source_urls[0],
  );
  assert.ok(alternate);
  assert.equal(alternate.props.children, "Alternate location");
  const content = JSON.stringify(rendered);
  assert.match(content, /Alternate locations for the same paper/);
  assert.match(content, /not additional independent evidence/);
  assert.match(content, /Provisional/);
});

for (const action of ["save", "remove", "check", "restore"]) {
  test(`provider ${action} protects input and rejects an overlapping action before commit`, async () => {
    let finish, calls = 0;
    const pending = new Promise(resolve => { finish = resolve; });
    const api = Object.fromEntries(["saveCredentials", "removeCredential", "checkConnection"].map(name =>
      [name, () => { calls++; return pending; }]));
    const harness = hookHarness("components/provider-setup.tsx", api);
    const props = { configuration: { saved_credentials: ["mimo", "openai"] }, selectedProviders: {},
      stageModels: { scout: "gpt-6-luna-high" }, onClose() {}, onSaved: async () => {} };
    let nodes = elementNodes(harness.render("ProviderSetup", props));
    nodes.find(node => node.type === "input").props.onChange({ target: { value: "GENERATED_SUBMITTED_KEY" } });
    nodes = elementNodes(harness.render("ProviderSetup", props));
    const invoke = action === "save" ? () => nodes.find(node => node.type === "form").props.onSubmit({ preventDefault() {} }) :
      nodes.find(node => node.type === "button" && node.props.children ===
        ({ remove: "Remove key", check: "Check connection", restore: "Restore standard route" }[action])).props.onClick;
    invoke(); invoke();
    assert.equal(calls, 1);
    nodes = elementNodes(harness.render("ProviderSetup", props));
    assert.equal(nodes.filter(node => node.type === "input").length, 7);
    for (const input of nodes.filter(node => node.type === "input")) assert.equal(input.props.disabled, true);
    finish({ saved: true, message: "Generated action completed" });
    await new Promise(setImmediate);
    nodes = elementNodes(harness.render("ProviderSetup", props));
    const input = nodes.find(node => node.type === "input");
    assert.equal(input.props.disabled, false);
    input.props.onChange({ target: { value: "GENERATED_LATER_KEY" } });
    nodes = elementNodes(harness.render("ProviderSetup", props));
    assert.equal(nodes.find(node => node.type === "input").props.value, "GENERATED_LATER_KEY");
  });
}

for (const oldOutcome of ["success", "failure"]) {
  test(`configuration refresh uses current selection and rejects a pre-cleanup stale ${oldOutcome}`, async () => {
    const requested = [], offline = [];
    let deferred = false, finishOld;
    const harness = hookHarness("features/preferences/use-configuration.ts", {
      configuration: models => {
        requested.push(models.scout);
        if (deferred && models.scout === "mimo-v2.6-pro") return new Promise((resolve, reject) => {
          finishOld = () => oldOutcome === "success" ? resolve({ configured: false }) : reject(new Error("Stale failure"));
        });
        return Promise.resolve({ configured: models.scout.startsWith("gpt-"), default_db_path: "generated-db" });
      },
    });
    const update = () => {}, setOffline = value => offline.push(value), notify = () => {};
    const settings = { stageModels: { scout: "mimo-v2.6-pro" }, useArxiv: true };
    let result = harness.render("useConfiguration", settings, update, setOffline, notify);
    harness.runLayoutEffects();
    const retainedRefresh = result.refreshConfiguration;
    const current = { ...settings, stageModels: { scout: "gpt-6-sol-high" } };
    result = harness.render("useConfiguration", current, update, setOffline, notify);
    harness.runLayoutEffects();
    await result.refreshConfiguration();
    await retainedRefresh();
    assert.deepEqual(requested, ["gpt-6-sol-high", "gpt-6-sol-high"]);
    deferred = true;
    result = harness.render("useConfiguration", settings, update, setOffline, notify);
    harness.runLayoutEffects();
    const old = result.refreshConfiguration();
    harness.render("useConfiguration", current, update, setOffline, notify);
    harness.runLayoutEffects(); // No passive request cleanup has run yet.
    finishOld(); await old;
    result = harness.render("useConfiguration", current, update, setOffline, notify);
    assert.equal(result.configuration.configured, true);
    assert.deepEqual(offline, [false, false]);
  });
}

test("preferences expose read failure/retry and never reload over post-load choices", async () => {
  let reads = 0, finishRead;
  const saves = [];
  const harness = hookHarness("features/preferences/use-preferences.ts", {
    preferences: async () => {
      if (++reads === 1) throw new Error("Generated initial read failure");
      return new Promise(resolve => { finishRead = resolve; });
    },
    modelOptions: async () => { throw new Error("Use bundled catalog"); },
    savePreferences: async settings => { saves.push(settings); return settings; },
  });
  const notify = () => {};
  let result = harness.render("usePreferences", notify);
  assert.equal(result.preferencesStatus, "loading");
  const cleanups = harness.runEffects();
  await new Promise(resolve => setTimeout(resolve, 0));
  result = harness.render("usePreferences", notify);
  assert.equal(result.preferencesStatus, "error");
  assert.equal(saves.length, 0);
  const pending = result.retryPreferences();
  result = harness.render("usePreferences", notify);
  assert.equal(result.preferencesStatus, "loading");
  finishRead({ maxCost: "10.00", challengeEnabled: false });
  await pending;
  result = harness.render("usePreferences", notify);
  assert.equal(result.preferencesStatus, "ready");
  assert.equal(result.settings.maxCost, "10.00");
  result.setSettings(current => ({ ...current, maxCost: "0.50", challengeEnabled: true }));
  result = harness.render("usePreferences", notify);
  await result.retryPreferences();
  assert.equal(reads, 2);
  assert.equal(result.settings.maxCost, "0.50");
  assert.equal(result.settings.challengeEnabled, true);
  cleanups.push(...harness.runEffects());
  await new Promise(resolve => setTimeout(resolve, 450));
  assert.equal(saves.length, 1);
  assert.equal(saves[0].maxCost, "0.50");
  assert.equal(saves[0].challengeEnabled, true);
  assert.ok(!("runId" in saves[0]));
  cleanups.forEach(dispose => dispose?.());
});

test("superseded and disposed preferences reads cannot publish late values", async () => {
  const reads = [];
  const harness = hookHarness("features/preferences/use-preferences.ts", {
    preferences: signal => new Promise(resolve => reads.push({ signal, resolve })),
    modelOptions: async () => { throw new Error("Use bundled catalog"); },
  });
  const notify = () => {};
  let result = harness.render("usePreferences", notify);
  const cleanups = harness.runEffects();
  await new Promise(resolve => setTimeout(resolve, 0));
  const pending = result.retryPreferences();
  assert.equal(reads[0].signal.aborted, true);
  reads[1].resolve({ maxCost: "0.50" });
  await pending;
  reads[0].resolve({ maxCost: "10.00" });
  await new Promise(setImmediate);
  result = harness.render("usePreferences", notify);
  assert.equal(result.settings.maxCost, "0.50");
  assert.equal(result.preferencesStatus, "ready");
  cleanups.forEach(dispose => dispose?.());
  const other = hookHarness("features/preferences/use-preferences.ts", {
    preferences: () => new Promise(resolve => reads.push({ resolve })),
    modelOptions: async () => { throw new Error("Use bundled catalog"); },
  });
  other.render("usePreferences", notify);
  const disposeOther = other.runEffects();
  await new Promise(resolve => setTimeout(resolve, 0));
  disposeOther.forEach(dispose => dispose?.());
  reads.at(-1).resolve({ maxCost: "20.00" });
  await new Promise(setImmediate);
  result = other.render("usePreferences", notify);
  assert.equal(result.preferencesStatus, "loading");
  assert.equal(result.settings.maxCost, "0.20");
});

test("history import uses the latest callback and ignores duplicate clicks", async () => {
  let finishImport, requests = 0;
  const selected = [];
  const harness = hookHarness("features/preferences/use-history-import.ts", {
    importHistory: (database, signal) => {
      requests++; assert.equal(database, "source-db"); assert.equal(signal.aborted, false);
      return new Promise(resolve => { finishImport = resolve; });
    },
  });
  let result = harness.render("useHistoryImport", "source-db", false, () => assert.fail("Stale callback"));
  const cleanups = harness.runEffects();
  const pending = result.importDatabase();
  await result.importDatabase();
  assert.equal(requests, 1);
  result = harness.render("useHistoryImport", "source-db", false, database => selected.push(database));
  assert.equal(result.importing, true);
  cleanups.push(...harness.runEffects());
  finishImport({ db_path: "imported-db", run_count: 2 });
  await pending;
  result = harness.render("useHistoryImport", "imported-db", false, () => {});
  assert.equal(result.importing, false);
  assert.deepEqual(selected, ["imported-db"]);
  assert.match(result.importMessage, /Imported 2 saved runs/);
  cleanups.forEach(dispose => dispose?.());
});

for (const scenario of ["closed", "active", "database-changed"]) {
  test(`history import preserves selection when ${scenario}`, async () => {
    let finishImport, signal;
    const harness = hookHarness("features/preferences/use-history-import.ts", {
      importHistory: (_database, requestSignal) => {
        signal = requestSignal; return new Promise(resolve => { finishImport = resolve; });
      },
    });
    const onImported = () => assert.fail("Late import changed selection");
    let result = harness.render("useHistoryImport", "source-db", false, onImported);
    const cleanups = harness.runEffects();
    const pending = result.importDatabase();
    if (scenario === "closed") {
      cleanups.forEach(dispose => dispose?.());
      assert.equal(signal.aborted, true);
    } else {
      result = harness.render("useHistoryImport", scenario === "database-changed" ? "new-db" : "source-db",
        scenario === "active", onImported);
      cleanups.push(...harness.runEffects());
    }
    finishImport({ db_path: "completed-copy", run_count: 2 });
    await pending;
    if (scenario !== "closed") {
      result = harness.render("useHistoryImport", "new-db", false, onImported);
      assert.equal(result.importing, false);
      assert.match(result.importMessage, /Import completed at completed-copy/);
      assert.match(result.importMessage, /current database selection was kept/);
      cleanups.forEach(dispose => dispose?.());
    }
  });
}

test("a successful trail retry clears the failure that previously hid its rows", async () => {
  let attempts = 0;
  const harness = hookHarness("features/results/use-result.ts", {
    sourceLeads: async () => ({ items: [], total: 0, offset: 0, has_more: false }),
    trail: async () => {
      if (++attempts === 1) throw new Error("temporary trail failure");
      return { items: [{ title: "Recovered trail" }] };
    },
  });
  const snapshot = { classification: "interrupted", run_id: "run", db_path: "db" };
  let result = harness.render("useResult", snapshot);
  const cleanup = harness.runEffects();
  await new Promise(setImmediate);
  result = harness.render("useResult", snapshot);
  await result.openTrail();
  result = harness.render("useResult", snapshot);
  assert.equal(result.trailError, "The research trail could not be opened.");
  await result.openTrail();
  result = harness.render("useResult", snapshot);
  assert.equal(result.trailError, null);
  assert.equal(result.trail[0].title, "Recovered trail");
  cleanup.forEach((dispose) => dispose?.());
});

for (const scenario of ["owned", "different-worker", "missing", "wrong-run"]) {
  test(`active-run reconnection validates snapshot ownership: ${scenario}`, async () => {
    let starts = 0;
    let snapshots = 0;
    const harness = hookHarness("features/research/use-research.ts", {
      start: async () => {
        starts++;
        return { started: false, classification: "duplicate_active", run_id: "requested", message: "Already active" };
      },
      snapshot: async () => {
        snapshots++;
        if (scenario === "missing") throw new Error("Run not found");
        return { run_id: scenario === "wrong-run" ? "other" : "requested",
          db_path: "canonical-db", worker_active: scenario !== "different-worker" };
      },
    });
    const notices = [];
    const notify = (message) => notices.push(message);
    const offline = () => {};
    let result = harness.render("useResearch", notify, offline);
    result.setClaim("Generated offline claim");
    result.setAcknowledged(true);
    result = harness.render("useResearch", notify, offline);
    await result.beginResearch({ preventDefault() {} }, { runId: "requested", dbPath: "db" },
      { service: { wigolo_ready: true } }, () => {});
    result = harness.render("useResearch", notify, offline);
    assert.equal(starts, 1);
    assert.equal(snapshots, 1);
    if (scenario === "owned") {
      assert.equal(result.activeRun.id, "requested");
      assert.equal(result.activeRun.database, "canonical-db");
      assert.equal(result.snapshot.worker_active, true);
    } else {
      assert.equal(result.activeRun, null);
      assert.equal(result.snapshot, null);
    }
    assert.equal(notices.at(-1), "Already active");
    assert.equal(result.busy, false);
  });
}

const flushProgress = () => new Promise(setImmediate);
function progressClock() {
  const timers = new Map();
  let nextId = 0;
  const clock = {
    now: 1_000,
    setTimeout(callback, delay) {
      const id = ++nextId;
      timers.set(id, { callback, at: clock.now + delay });
      return id;
    },
    clearTimeout(id) { timers.delete(id); },
    get pending() { return timers.size; },
    async advance(milliseconds) {
      const until = clock.now + milliseconds;
      while (true) {
        const next = [...timers.entries()].filter(([, timer]) => timer.at <= until)
          .sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        timers.delete(next[0]);
        clock.now = next[1].at;
        next[1].callback();
        await flushProgress();
      }
      clock.now = until;
      await flushProgress();
    },
  };
  return clock;
}
const progressSnapshot = (classification = "running", id = "run") => ({
  run_id: id, db_path: "db", classification, worker_active: classification === "running",
});
const progressResponse = (value) => ({ ok: true, json: async () => value });
const waitForProgressAbort = (signal) => new Promise((_resolve, reject) => {
  signal.addEventListener("abort", () => reject(signal.reason), { once: true });
});
function pollingHarness(fetch) {
  const clock = progressClock();
  const api = hookHarness("lib/api.ts", {}, { clock, fetch }).exports.researchApi;
  let starts = 0;
  const notices = [];
  const notify = (message) => notices.push(message);
  const offline = () => {};
  const harness = hookHarness("features/research/use-research.ts", {
    ...api,
    start() { starts++; assert.fail("Recovery attempted to start research"); },
  }, { clock, trackEffects: true });
  function render(enabled = true) {
    const value = harness.render("useResearch", notify, offline, enabled);
    harness.commitEffects();
    return value;
  }
  render().setActiveRun({ id: "run", database: "db" });
  render();
  return { clock, render, dispose: () => harness.dispose(), notices, get starts() { return starts; } };
}

test("hanging progress reads time out individually, pause after three failures and reconnect once", async () => {
  let healthy = false, inFlight = 0, maxInFlight = 0;
  const requests = [];
  const h = pollingHarness(async (url, { signal, method }) => {
    assert.equal(method, undefined, "Recovery must only read saved state");
    assert.match(url, /\/api\/research\/run\?db_path=db$/);
    requests.push(signal);
    inFlight++;
    maxInFlight = Math.max(maxInFlight, inFlight);
    try {
      if (!healthy) await waitForProgressAbort(signal);
      return progressResponse(progressSnapshot());
    } finally { inFlight--; }
  });
  await h.clock.advance(100_000);
  let state = h.render();
  assert.equal(requests.length, 3);
  assert.equal(new Set(requests).size, 3, "Every attempt needs a fresh request signal");
  assert.ok(requests.every(signal => signal.aborted));
  assert.equal(state.connection.state, "paused");
  assert.equal(state.snapshot, null);
  assert.equal(state.lastConfirmedAt, null);
  assert.equal(h.clock.pending, 0);
  assert.equal(state.activeRun.id, "run");
  assert.equal(state.activeRun.database, "db");
  healthy = true;
  state.reconnect(); state.reconnect(); state.reconnect();
  await flushProgress();
  state = h.render();
  assert.equal(requests.length, 4, "Repeated reconnect clicks cannot overlap reads");
  assert.equal(state.connection.state, "connected");
  assert.equal(state.connection.error, null);
  assert.equal(state.connection.recovered, true);
  assert.equal(state.snapshot.run_id, "run");
  assert.equal(state.lastConfirmedAt, h.clock.now);
  assert.equal(maxInFlight, 1);
  assert.equal(h.starts, 0);
  h.dispose();
  assert.equal(h.clock.pending, 0);
});

test("repeated errors before the first snapshot keep the run and expose paused recovery", async () => {
  let calls = 0;
  const h = pollingHarness(async () => { calls++; throw new Error("Service unavailable"); });
  await h.clock.advance(100_000);
  let state = h.render();
  assert.equal(calls, 3);
  assert.equal(state.connection.state, "paused");
  assert.equal(state.connection.error, "Service unavailable");
  assert.equal(state.snapshot, null);
  h.render(false);
  h.render(true);
  await h.clock.advance(100_000);
  state = h.render();
  assert.equal(calls, 3, "Navigation must not silently reset the failure budget");
  assert.equal(state.activeRun.id, "run");
  assert.equal(h.notices.length, 0, "Polling uses its scoped connection status");
  h.dispose();
});

test("connection failures retain the last confirmed snapshot and receipt time", async () => {
  let calls = 0;
  const h = pollingHarness(async () => {
    if (++calls > 1) throw new Error("Read failed");
    return progressResponse(progressSnapshot());
  });
  await h.clock.advance(0);
  const confirmed = h.render();
  await h.clock.advance(100_000);
  const stale = h.render();
  assert.equal(stale.connection.state, "paused");
  assert.equal(stale.snapshot, confirmed.snapshot);
  assert.equal(stale.lastConfirmedAt, confirmed.lastConfirmedAt);
  h.dispose();
});

for (const change of ["navigation", "replacement", "unmount"]) {
  test(`late progress responses after ${change} cannot publish or schedule follow-up`, async () => {
    let finish, signal, calls = 0;
    const h = pollingHarness((_url, init) => {
      calls++; signal = init.signal;
      // Simulate a transport completion already queued when cleanup aborts it.
      return new Promise(resolve => { finish = resolve; });
    });
    await h.clock.advance(0);
    if (change === "navigation") h.render(false);
    if (change === "replacement") {
      h.render().setActiveRun({ id: "replacement", database: "other-db" });
      h.render(false);
    }
    if (change === "unmount") h.dispose();
    assert.equal(signal.aborted, true);
    assert.equal(h.clock.pending, 0, "Cleanup clears even a pending deadline");
    finish(progressResponse(progressSnapshot()));
    await flushProgress();
    await h.clock.advance(100_000);
    assert.equal(calls, 1);
    if (change !== "unmount") {
      const state = h.render(false);
      assert.equal(state.snapshot, null);
      assert.equal(state.lastConfirmedAt, null);
    }
    h.dispose();
  });
}

test("terminal snapshots cancel future polling and reconnect cannot restart them", async () => {
  let calls = 0;
  const h = pollingHarness(async () => {
    calls++;
    return progressResponse(progressSnapshot("released"));
  });
  const staleActions = h.render();
  await h.clock.advance(0);
  staleActions.reconnect();
  await flushProgress();
  const state = h.render();
  assert.equal(state.snapshot.classification, "released");
  state.reconnect();
  await h.clock.advance(100_000);
  assert.equal(calls, 1);
  assert.equal(h.clock.pending, 0);
  assert.equal(h.starts, 0);
  h.dispose();
});

test("snapshot deadline includes a hanging response body and lifecycle abort clears its timer", async () => {
  for (const lifecycleAbort of [false, true]) {
    const clock = progressClock();
    const lifecycle = new AbortController();
    let requestSignal;
    const api = hookHarness("lib/api.ts", {}, { clock, fetch: async (_url, { signal }) => {
      requestSignal = signal;
      return { ok: true, json: () => waitForProgressAbort(signal) };
    } }).exports.researchApi;
    const pending = api.snapshot("run", "db", lifecycle.signal);
    const rejected = assert.rejects(pending);
    await flushProgress();
    if (lifecycleAbort) lifecycle.abort();
    else await clock.advance(10_000);
    await rejected;
    assert.equal(requestSignal.aborted, true);
    assert.equal(clock.pending, 0);
  }
});

test("cancellation is sent only once, confirmed only by the backend, and never retried automatically", async () => {
  for (const outcome of ["confirmed", "declined", "unknown", "old-selection"]) {
    let finish, cancelCalls = 0;
    const h = pollingHarness(async (url, { signal }) => {
      if (url.includes("/cancel")) {
        cancelCalls++;
        if (outcome === "unknown") return waitForProgressAbort(signal);
        return new Promise(resolve => { finish = resolve; });
      }
      return progressResponse(progressSnapshot());
    });
    await h.clock.advance(0);
    let state = h.render();
    const pending = state.cancel();
    await state.cancel();
    state = h.render();
    assert.equal(state.cancellation.state, "sending");
    assert.equal(cancelCalls, 1);
    if (outcome === "old-selection") {
      state.setActiveRun({ id: "other", database: "other-db" });
      h.render(false);
    }
    if (outcome === "unknown") await h.clock.advance(10_000);
    else finish(progressResponse({ cancelled: outcome !== "declined", message: "Backend reply" }));
    await pending;
    state = h.render(outcome !== "old-selection");
    assert.equal(state.cancellation.state, outcome === "confirmed" ? "requested"
      : outcome === "old-selection" ? "idle" : "unconfirmed");
    await h.clock.advance(10_000);
    assert.equal(cancelCalls, 1);
    if (outcome === "confirmed") { await state.cancel(); assert.equal(cancelCalls, 1); }
    h.dispose();
  }
});

test("recovery controls expose scoped status, last-confirmed time and confirmed cancellation only", () => {
  const h = hookHarness("features/research/connection.tsx", {});
  for (const lastConfirmedAt of [null, 10_000]) {
    const props = {
      connection: { state: "paused", error: "Read timed out", recovered: false },
      lastConfirmedAt, cancellation: { state: "unconfirmed", message: "Check History" },
      onReconnect() {}, onHistory() {}, onCancel() {},
    };
    const nodes = elementNodes(h.render("ResearchRecovery", props));
    assert.ok(nodes.some(node => node.props.role === "status" && node.props["aria-live"] === "polite"));
    assert.ok(nodes.some(node => node.type === "button" && node.props.children === "Reconnect" && !node.props.disabled));
    assert.ok(nodes.some(node => node.type === "button" && node.props.children === "Open History"));
    assert.ok(nodes.some(node => node.type === "button" && node.props.children === "Cancel run"));
    assert.match(JSON.stringify(nodes), /Research may still be running/);
    if (lastConfirmedAt === null) assert.match(JSON.stringify(nodes), /No progress snapshot confirmed/);
    else assert.ok(nodes.some(node => node.type === "time" && node.props.dateTime));
  }
});

test("a fresh explicit selection of the same run clears the previous cancellation guard", async () => {
  let cancelCalls = 0;
  const h = pollingHarness(async (url) => {
    if (url.includes("/cancel")) {
      cancelCalls++;
      return progressResponse({ cancelled: true, message: "Requested" });
    }
    return progressResponse(progressSnapshot());
  });
  await h.clock.advance(0);
  await h.render().cancel();
  assert.equal(h.render().cancellation.state, "requested");
  h.render().reset();
  h.render().setActiveRun({ id: "run", database: "db" });
  let state = h.render();
  assert.equal(state.cancellation.state, "idle");
  await state.cancel();
  state = h.render();
  assert.equal(cancelCalls, 2);
  assert.equal(state.cancellation.state, "requested");
  h.dispose();
});

test("citation labels do not infer randomization or vendor identity from unrelated sources", () => {
  const { exports } = hookHarness("features/results/source-titles.tsx", {});
  assert.notEqual(exports.evidenceSourceType({ source_type: "clinical trial", source_url: "https://example.org/study" }), "Randomized trial");
  assert.equal(exports.evidenceConflictNotice({ source_url: "https://notflocksafety.com/article" }), null);
  assert.match(exports.evidenceConflictNotice({ source_url: "https://blog.flocksafety.com/article" }), /commercial interest/);
});

test("claim status does not infer evidence balance from finding counts", () => {
  const { CoverageStatus } = hookHarness("features/results/coverage-status.tsx", {}).exports;
  const assessment = { supporting_count: 20, challenging_count: 1, qualifying_count: 0,
    unrelated_count: 0, admitted_source_ids: [], limitations: [], unresolved_gap_count: 0,
    partial_coverage_count: 0, unavailable_coverage_count: 0, coverage_incomplete: true };
  const tree = CoverageStatus({ result: { all_surviving_sources: [], claim_coverage_map: [] },
    evidence: { post_analysis_assessment: assessment } });
  const text = JSON.stringify(tree);
  assert.match(text, /Claim not established by the admitted evidence/);
  assert.match(text, /reason was not recorded/);
  assert.doesNotMatch(text, /Supporting findings observed/);
});

test("unknown search stop and exception do not expose technical text", () => {
  const { researchStopLabel, understandableRunMessage } = hookHarness("features/shared/presentation.ts", {}).exports;
  assert.doesNotMatch(researchStopLabel("unexpected_internal_exception"), /unexpected_internal_exception/);
  assert.doesNotMatch(understandableRunMessage({ classification: "failed", message: "RuntimeError: private detail" }), /RuntimeError/);
});

test("recommended sources are not repeated in survivor cards", () => {
  const { SourceSections } = hookHarness("features/results/source-sections.tsx", {}).exports;
  const source = { source_id: "one", source_url: "https://example.com", title: "A source",
    status: "recommended_analyzed", recommended: true, discovery_providers: [], discovery_round: 1 };
  const tree = SourceSections({ result: { recommended_sources: [source], all_surviving_sources: [source] }, evidence: null });
  const cards = elementNodes(tree).filter((node) => node.type === "article");
  assert.equal(cards.length, 1);
});


test("incomplete quotation does not discard a trailing qualification", () => {
  const { completeQuote } = hookHarness("features/results/admitted-evidence.tsx", {}).exports;
  assert.equal(completeQuote("The treatment reduced the outcome. However, only among"), null);
  assert.equal(completeQuote("An incomplete passage without an ending"), null);
  assert.equal(completeQuote("The treatment reduced the outcome. However, only among adults." ).text,
    "The treatment reduced the outcome. However, only among adults.");
});

test("bottom line precedes status and does not rank repeated findings", () => {
  const { V2ResultPaper } = hookHarness("features/results/paper.tsx", {}).exports;
  const item = (id, relationship) => ({ ledger_claim_id: id, source_id: id,
    source_url: "https://example.org/" + id, relationship_to_claim: relationship,
    approved_factual_statement: id + " finding." });
  const evidence = { items: [item("first", "supports"), item("copy", "supports"), item("contrast", "challenges")], source_titles: [] };
  const result = { exact_claim: "Example claim", directions: {support_enabled: true, challenge_enabled: true},
    synthesis: {sections: []}, all_surviving_sources: [], recommended_sources: [] };
  const tree = V2ResultPaper({ result, evidence });
  const children = tree.props.children;
  assert.equal(children[3].props["aria-labelledby"], "bottom-line-heading");
  const text = JSON.stringify(children[3]);
  assert.match(text, /copy finding/);
  assert.match(text, /contrast finding/);
  assert.doesNotMatch(text, /first finding/);
  assert.match(text, /not necessarily representative/);
  assert.match(text, /does not establish the balance/);
});

test("discovery grouping retains fragments together but preserves query distinctions", () => {
  const { SourceLeads, readableReason } = hookHarness("features/results/source-leads.tsx", {}).exports;
  const lead = (id, url) => ({ lead_id:id, url, title:id, capture_status:"unknown", disposition:"pending",
    search_directions:[], providers:[], rounds:[], confidence:"recorded", unknowns:[], history:[] });
  const tree = SourceLeads({ items:[lead("a", "https://example.org/a?version=1#one"),
    lead("b", "https://example.org/a?version=1#two"), lead("c", "https://example.org/a?version=2")],
    total:3, notice:null, loading:false, loadingMore:false, error:null, hasMore:false,
    onLoadMore() {}, onRetry() {} });
  assert.equal(elementNodes(tree).filter(node => node.type === "article").length, 2);
  assert.match(JSON.stringify(tree), /additional discovery/);
  assert.doesNotMatch(readableReason("RuntimeError: secret internals"), /RuntimeError/);
  assert.match(readableReason("cap_prevented"), /limit/);
});


test("quotation preserves recorded omissions and abbreviations", () => {
  const { completeQuote } = hookHarness("features/results/admitted-evidence.tsx", {}).exports;
  const passage = "Dr. Smith reported a result. ... However, the sample was small.";
  assert.equal(completeQuote(passage).text, passage);
  assert.equal(completeQuote("The effect was observed. ... However, only"), null);
});

test("new brief copies add the same bounded findings and retain the original release", () => {
  const { briefWithReadingAid } = hookHarness("features/results/reading-aid.ts", {}).exports;
  const evidence = { items: [{ledger_claim_id:"b", source_url:"https://mirror.example/work", relationship_to_claim:"supports", claim_fit:4, approved_factual_statement:"The measured outcome was associated with the program."}] };
  const result = {exact_claim:"Does the program work?", directions:{support_enabled:true, challenge_enabled:false}, all_surviving_sources:[], claim_coverage_map:[], unresolved_material_gaps:[], stopping:{reason:"budget"}};
  const copy = briefWithReadingAid("# Original release", result, evidence);
  assert.match(copy, /not established by the admitted evidence/);
  assert.match(copy, /not necessarily representative/);
  assert.match(copy, /https:\/\/mirror.example\/work/);
  assert.match(copy, /coverage was not assessed/);
  assert.match(copy, /research limit stopped further work/);
  assert.match(copy, /original released brief and its recorded hash remain unchanged/i);
  assert.doesNotMatch(copy, /# Original release$/);
  assert.match(briefWithReadingAid("# Original release", result, null), /detailed evidence is unavailable/);
});

test("study design is separate from publication type and unknown interests stay unknown", () => {
  const { evidenceSourceType, evidenceStudyDesign, evidenceConflictNotice } = hookHarness("features/results/source-titles.tsx", {}).exports;
  const trial = {source_type:"randomized_trial", source_url:"https://example.org/copy"};
  assert.equal(evidenceStudyDesign(trial), "Randomized trial");
  assert.equal(evidenceSourceType(trial), "Publication type not recorded");
  assert.equal(evidenceStudyDesign({source_type:"working_paper"}), "Study design not recorded");
  assert.equal(evidenceConflictNotice(trial), null);
});

test("verified DOI metadata takes priority over an unreliable captured title", () => {
  const { evidenceCitation, sourceTitles } = hookHarness("features/results/source-titles.tsx", {}).exports;
  const item = {source_id:"one", source_url:"https://mirror.example/file.pdf", title:"paper.pdf",
    authors:["Unverified name"], publication_venue:"Unverified host", verified_publication:{
      doi:"10.1000/abc", canonical_url:"https://doi.org/10.1000/abc", title:"Verified publication",
      authors:["A. Author"], publication_date:"2024-02-01", venue:"Journal", verification:"crossref_doi"}};
  const helper = sourceTitles({all_surviving_sources:[]}, {items:[item], source_titles:[{source_id:"one",display_title:"PDF file: file.pdf"}]});
  assert.equal(helper.sourceHeading("one", item.title, item.source_url), "Verified publication");
  assert.match(evidenceCitation(item), /A. Author · 2024 · Journal/);
  assert.doesNotMatch(evidenceCitation(item), /Unverified/);
});

test("recorded source stops distinguish calls, tokens, money and unknown limits", () => {
  const { sourceBudgetStop, sourceLocalStop } = hookHarness("features/shared/presentation.ts", {}).exports;
  assert.match(sourceBudgetStop("physical_call_ceiling"), /call limit/);
  assert.match(sourceBudgetStop("token_reserve"), /token allowance/);
  assert.match(sourceBudgetStop("cost_reserve"), /money allowance/);
  assert.match(sourceBudgetStop("unrecognized_internal"), /not recorded/);
  assert.match(sourceLocalStop("token_cap_blocked"), /token limit/);
  assert.match(sourceLocalStop("physical_call_cap_blocked"), /call limit/);
});

test("nonrandomized working papers retain both publication type and study design", () => {
  const { evidenceSourceType, evidenceStudyDesign } = hookHarness("features/results/source-titles.tsx", {}).exports;
  for (const source_type of ["nonrandomized working paper", "non-randomized working paper", "not randomized working paper"]) {
    const item = { source_type, source_url: "https://institute.example/paper" };
    assert.equal(evidenceSourceType(item), "Working paper");
    assert.equal(evidenceStudyDesign(item), "Observational study");
  }
});

test("copies and downloads use the server's canonical report interpretation verbatim", () => {
  const { briefWithReadingAid } = hookHarness("features/results/reading-aid.ts", {}).exports;
  const report = "# Reading aid\n\nVerified findings.\nUSD 0.05 reported; USD 0.02 reserved.\n";
  assert.equal(briefWithReadingAid("immutable release", {}, { reading_aid_markdown: report }), report);
});

test("complete publication opening replaces illustrative selection and links all findings", () => {
  const { V2ResultPaper } = hookHarness("features/results/paper.tsx", {}).exports;
  const evidence = { items: [], publication_opening: [
    { text: "The randomized study measured theft.", ledger_claim_ids: ["trial", "copy"] },
    { text: "The observational study measured clearance.", ledger_claim_ids: ["observation"] },
    { text: "Recorded limitations: follow-up was six months.", ledger_claim_ids: ["trial", "observation"] },
  ] };
  const result = { exact_claim: "Example claim", directions: { support_enabled: true, challenge_enabled: true },
    synthesis: { sections: [] }, all_surviving_sources: [], recommended_sources: [] };
  const tree = V2ResultPaper({ result, evidence });
  const opening = tree.props.children[3];
  assert.match(JSON.stringify(opening), /randomized study/);
  assert.match(JSON.stringify(opening), /observational study/);
  assert.match(JSON.stringify(opening), /do not establish independent studies/);
  assert.doesNotMatch(JSON.stringify(opening), /not necessarily representative/);
  assert.equal(elementNodes(opening).filter(node => node.type === "button").length, 3);
});

test("source pagination retries preserve earlier records and discard repeated record IDs", async () => {
  let calls = 0;
  const lead = id => ({ lead_id: id, url: "https://example.org/page", history: [] });
  const api = {
    sourceLeads: async (_run, _db, offset) => {
      calls++;
      if (!offset) return { items: [lead("a"), lead("a")], offset: 0, total: 3, has_more: true };
      if (calls === 2) throw Error("temporary failure");
      return { items: [lead("a"), lead("b")], offset: 2, total: 3, has_more: false };
    },
  };
  const h = hookHarness("features/results/use-result.ts", api);
  const snapshot = { run_id: "run", db_path: "db", classification: "cancelled" };
  h.render("useResult", snapshot); h.runEffects();
  await new Promise(resolve => setImmediate(resolve));
  let state = h.render("useResult", snapshot);
  assert.equal(state.sourceLeads.length, 1);
  await state.loadMoreSourceLeads();
  state = h.render("useResult", snapshot);
  assert.ok(state.sourceLeadsError);
  assert.equal(state.sourceLeads.length, 1);
  await state.loadMoreSourceLeads();
  state = h.render("useResult", snapshot);
  assert.deepEqual(Array.from(state.sourceLeads, lead => lead.lead_id), ["a", "b"]);
  assert.equal(state.sourceLeadsHasMore, false);
});

test("a rejected attempt does not obscure a saved release or remove resume guidance", () => {
  const { understandableRunMessage, understandableAttemptMessage } = hookHarness("features/shared/presentation.ts", {}).exports;
  const attempt = { classification: "invalid_input", diagnostic_component: "resume", message: "RuntimeError: private internals" };
  assert.match(understandableRunMessage({ classification: "released", attempt_diagnostic: attempt }), /saved research result is available/);
  assert.match(understandableRunMessage({ classification: "invalid_input", attempt_diagnostic: attempt }), /original settings or start a new run/);
  assert.doesNotMatch(understandableAttemptMessage(attempt), /RuntimeError/);
});
