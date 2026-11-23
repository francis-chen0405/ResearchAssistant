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
        const resolved = name.startsWith("@/")
          ? path.resolve(__dirname, "..", `${name.slice(2)}.ts`)
          : path.resolve(path.dirname(file), `${name}.ts`);
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

test("source rows mark unassessed recommendations provisional and qualify partial evidence", () => {
  const harness = hookHarness("features/results/sources-tab.tsx", {});
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
  const row = (source) => JSON.stringify(elementNodes(harness.render("SourceRow", {
    source, title: undefined, evidence, showReason: true,
  })));
  assert.match(row(result.recommended_sources[0]), /Not yet assessed; recommended from its search ranking\./);
  assert.match(row(result.recommended_sources[1]), /Direct · Adds context/);
  assert.match(row(result.recommended_sources[1]), /Selected for comparison\./);
  assert.match(row(result.recommended_sources[2]), /Direct · Supports/);
  assert.doesNotMatch(row(result.recommended_sources[1]), /Supports/);
});

test("every shortlisted-source status maps to one plain outcome", () => {
  const { sourceOutcome } = hookHarness("features/results/sources-tab.tsx", {}).exports;
  const label = (status, budgetOutcome) => sourceOutcome({ status, budget_prevented_reason: "token_reserve" }, budgetOutcome).label;
  assert.equal(label("surviving_not_deeply_analyzed"), "Shortlisted; not read in depth");
  assert.equal(label("recommended_analyzed"), "Read and assessed");
  assert.equal(label("surviving_analyzed"), "Read and assessed");
  assert.equal(label("recommended_analyzer_admitted"), "Used as evidence");
  assert.equal(label("surviving_analyzer_rejected"), "Read; no finding kept");
  assert.equal(label("recommended_analyzer_failed"), "Assessment failed");
  assert.equal(label("recommended_no_ledger_evidence"), "Not yet assessed");
  assert.match(label("budget_prevented_analysis"), /token allowance/);
  assert.equal(label("surviving_analyzer_failed", "token_cap_blocked"), "A per-source token limit stopped the reading");
  assert.equal(label("unknown_internal_status"), "Outcome not recognized");
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

test("source rows link alternate URLs as locations for the same paper", () => {
  const harness = hookHarness("features/results/sources-tab.tsx", {});
  const source = {
    source_id: "same-paper", direction: "support", source_url: "https://example.test/main",
    alternate_source_urls: ["https://example.test/alternate"],
    title: "Same paper", source_type: "Article", publication_date: null,
    discovery_providers: ["exa"], discovery_round: 1, recommended: true,
    recommendation_rank: 1, queue_rank: 1, status: "recommended_no_ledger_evidence",
    ledger_claim_ids: [], budget_prevented_reason: null,
  };
  const rendered = elementNodes(harness.render("SourceRow", { source, title: undefined, evidence: null, showReason: true }));
  const alternate = rendered.find(
    node => node.type === "a" && node.props.href === source.alternate_source_urls[0],
  );
  assert.ok(alternate);
  assert.equal(alternate.props.children, "Alternate location");
  assert.equal(alternate.props.rel, "noopener noreferrer");
  const content = JSON.stringify(rendered);
  assert.match(content, /Also available at/);
  assert.match(content, /Same paper, not separate evidence/);
  assert.match(content, /Not yet assessed/);
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
        ({ remove: "Remove key", check: "Check connection", restore: "Reset OpenAI endpoint" }[action])).props.onClick;
    invoke(); invoke();
    assert.equal(calls, 1);
    nodes = elementNodes(harness.render("ProviderSetup", props));
    assert.equal(nodes.filter(node => node.type === "input").length, 9);
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
    // Walk children and the Banner's title/action slots.
    const walk = (value) => !value || typeof value !== "object" ? [] : Array.isArray(value) ? value.flatMap(walk)
      : [value, ...walk(value.props?.children), ...walk(value.props?.title), ...walk(value.props?.action)];
    const isButton = (node, label) => (node.type === "button" || node.type?.name === "Button") && node.props.children === label;
    const nodes = walk(h.render("ResearchRecovery", props));
    assert.ok(nodes.some(node => node.props.role === "status" && node.props["aria-live"] === "polite"));
    assert.ok(nodes.some(node => isButton(node, "Reconnect") && !node.props.disabled));
    assert.ok(nodes.some(node => isButton(node, "Open History")));
    assert.match(JSON.stringify(nodes), /Research may still be running/);
    if (lastConfirmedAt === null) assert.match(JSON.stringify(nodes), /No progress snapshot confirmed/);
    else assert.ok(nodes.some(node => node.type === "time" && node.props.dateTime));
    // A healthy connection keeps only the polite status region; no banner or buttons.
    const healthy = walk(h.render("ResearchRecovery", { ...props, connection: { state: "connected", error: null, recovered: false } }));
    assert.ok(healthy.some(node => node.props.role === "status" && node.props["aria-live"] === "polite"));
    assert.equal(healthy.filter(node => node.type?.name === "Banner" || node.type?.name === "Button").length, 0);
  }
  // Cancel is a separate action that asks for confirmation and states saved work is kept.
  let cancelled = 0;
  const cancelProps = { cancellation: { state: "idle", message: null }, onCancel() { cancelled += 1; } };
  const walk = (value) => !value || typeof value !== "object" ? [] : Array.isArray(value) ? value.flatMap(walk)
    : [value, ...walk(value.props?.children)];
  let nodes = walk(h.render("CancelRun", cancelProps));
  const open = nodes.find(node => node.type?.name === "Button" && node.props.children === "Cancel run");
  assert.ok(open);
  open.props.onClick();
  assert.equal(cancelled, 0, "Opening the confirmation does not cancel");
  nodes = walk(h.render("CancelRun", cancelProps));
  assert.match(JSON.stringify(nodes), /Work saved so far is kept/);
  nodes.find(node => node.type?.name === "Button" && node.props.children === "Stop research").props.onClick();
  assert.equal(cancelled, 1);
  const sending = walk(h.render("CancelRun", { ...cancelProps, cancellation: { state: "sending", message: "Sending cancellation request…" } }));
  assert.ok(sending.some(node => node.type?.name === "Button" && node.props.children === "Sending cancellation…" && node.props.disabled));
  assert.equal(walk(h.render("CancelRun", { ...cancelProps, canCancel: false })).length, 0);
});

test("progress phases map every known stage and later rounds never move back", () => {
  const { phaseOf, activitySentence, phases } = hookHarness("features/research/phases.ts", {}).exports;
  assert.deepEqual([...phases], ["Plan", "Search", "Read", "Analyse", "Write up"]);
  for (const stage of ["claim_planner", "discovery", "scout", "gap_analysis", "adaptive_search", "acquisition",
    "source_selection", "deep_analysis", "evidence_admission", "review", "synthesis", "final_renderer_validator"]) {
    assert.notEqual(phaseOf(stage), null, stage);
  }
  assert.equal(phaseOf("an_unknown_future_stage"), null, "Unknown stages do not map to step one");
  assert.equal(activitySentence("adaptive_search", 2), "Follow-up search, round 2");
  assert.equal(activitySentence("claim_planner", 3), "Follow-up search, round 3");
  assert.equal(activitySentence("acquisition", 1), "Reading sources");
  assert.doesNotMatch(activitySentence("an_unknown_future_stage", 1), /unknown_future/);
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

// Label inference itself moved to the backend owner (tests/test_result_display_projection.py).
test("export copies take labels from the backend projection and infer none themselves", () => {
  const { briefWithReadingAid } = hookHarness("features/results/reading-aid.ts", {}).exports;
  const item = (id, url) => ({ ledger_claim_id: id, source_id: id, source_url: url, source_type: "clinical trial",
    relationship_to_claim: "supports", claim_fit: 4, approved_factual_statement: id + " finding." });
  const result = { exact_claim: "Claim", directions: { support_enabled: true }, all_surviving_sources: [],
    claim_coverage_map: [], unresolved_material_gaps: [], stopping: { reason: "budget" } };
  const evidence = { items: [item("vendor", "https://blog.flocksafety.com/a"), item("other", "https://notflocksafety.com/a")],
    source_titles: [{ source_id: "vendor", display_title: "t", publisher_interest: "The publisher has a commercial interest." }] };
  const copy = briefWithReadingAid("# Release", result, evidence);
  assert.equal((copy.match(/Conflict of interest/g) ?? []).length, 1);
  assert.match(copy, /commercial interest/);
  assert.doesNotMatch(copy, /Randomized trial/);
  assert.match(copy, /Study design not recorded/);
});

test("evidence picture does not infer balance from raw finding counts", () => {
  const { findingsByRelationship, evidencePicture } = hookHarness("features/results/model.ts", {}).exports;
  const item = (id, relationship, fit, family = id) => ({ ledger_claim_id: id, source_id: id, source_family: family,
    source_url: `https://example.org/${id}`, relationship_to_claim: relationship, claim_fit: fit,
    approved_factual_statement: `${id} finding.` });
  // Twenty supporting records from one publication count once, so they cannot outweigh by number.
  const onePublication = Array.from({ length: 20 }, (_, index) => item(`s${index}`, "supports", 5, "family:one"));
  const picture = evidencePicture(findingsByRelationship({ items: [...onePublication, item("c", "challenges", 5)] }),
    { support_enabled: true, challenge_enabled: true });
  assert.equal(picture.label, "Evidence is mixed");
  assert.doesNotMatch(picture.label, /true|false|proven|established|dominat/i);
  // Many indirect findings never earn a "mostly" label.
  const indirect = Array.from({ length: 6 }, (_, index) => item(`p${index}`, "supports", 3));
  assert.equal(evidencePicture(findingsByRelationship({ items: indirect }), { support_enabled: true, challenge_enabled: true }).label,
    "Evidence is limited or indirect");
  assert.equal(evidencePicture(findingsByRelationship({ items: [] }), { support_enabled: true }).label, "No usable evidence found");
});

test("evidence picture follows the recorded rules and always carries the scope note", () => {
  const { findingsByRelationship, evidencePicture } = hookHarness("features/results/model.ts", {}).exports;
  const item = (id, relationship, fit) => ({ ledger_claim_id: id, source_id: id, source_family: id,
    source_url: `https://example.org/${id}`, relationship_to_claim: relationship, claim_fit: fit,
    approved_factual_statement: `${id} finding.` });
  const both = { support_enabled: true, challenge_enabled: true };
  const label = (items, directions = both) => evidencePicture(findingsByRelationship({ items }), directions);
  assert.equal(label([item("a", "supports", 4), item("b", "supports", 5), item("c", "qualifies", 3)]).label, "Evidence mostly supports");
  // One direct publication is not enough for "mostly".
  assert.equal(label([item("a", "supports", 5), item("c", "qualifies", 3)]).label, "Evidence is limited or indirect");
  // The side must hold two thirds of all counted publications.
  assert.equal(label([item("a", "supports", 4), item("b", "supports", 4), item("c", "qualifies", 3), item("d", "qualifies", 3)]).label,
    "Evidence is limited or indirect");
  // Twice the other side's direct publications is required.
  assert.equal(label([item("a", "challenges", 4), item("b", "challenges", 4), item("c", "challenges", 5), item("d", "supports", 4), item("e", "supports", 4)]).label,
    "Evidence is mixed");
  assert.equal(label([item("a", "challenges", 4), item("b", "challenges", 4)]).label, "Evidence mostly challenges");
  assert.equal(label([item("a", "supports", 4)], { support_enabled: true, challenge_enabled: false }).scopeNote,
    "Only supporting evidence was searched for.");
  assert.equal(label([item("a", "supports", 4)]).scopeNote, null);
});

test("mirrors of one publication merge into one finding and count once", () => {
  const { findingsByRelationship, publicationCounts } = hookHarness("features/results/model.ts", {}).exports;
  const item = (id, url, title, fit = 4) => ({ ledger_claim_id: id, source_id: id, source_family: `unverified-data:${id}`,
    source_url: url, title, relationship_to_claim: "challenges", claim_fit: fit, approved_factual_statement: `${id} statement.` });
  const evidence = {
    items: [
      item("ojp", "https://www.ojp.gov/a", "License Plate Reader (LPR) Police Patrols in Crime Hot Spots"),
      item("nij", "https://nij.ojp.gov/a", "License Plate Reader (LPR) Police Patrols in Crime Hot Spots", 3),
      item("other", "https://example.org/b", "A different evaluation of plate readers in two cities"),
    ],
    source_titles: [],
    study_lineage: [],
  };
  const findings = findingsByRelationship(evidence);
  assert.equal(findings.challenges.length, 2);
  const merged = findings.challenges.find((finding) => finding.item.ledger_claim_id === "ojp");
  assert.deepEqual(Array.from(merged.alsoAt, (location) => location.url), ["https://nij.ojp.gov/a"]);
  assert.equal(merged.mergeBasis, "matching title");
  assert.equal(merged.related[0].approved_factual_statement, "nij statement.");
  assert.equal(publicationCounts(findings).publications, 2);
  const { strengthLabel } = hookHarness("features/results/model.ts", {}).exports;
  assert.deepEqual([5, 4, 3, 2, null].map(strengthLabel), ["Direct", "Direct", "Partial", "Background", null]);
});

test("summary leads with findings, says each disclosure once and never prints not recorded", () => {
  const { ResultSummary } = hookHarness("features/results/summary.tsx", {}).exports;
  const { findingsByRelationship } = hookHarness("features/results/model.ts", {}).exports;
  const result = {
    exact_claim: "Example claim", directions: { support_enabled: true },
    synthesis: { sections: [] }, all_surviving_sources: [], recommended_sources: [],
    claim_coverage_map: [{ coverage_state: "covered", evidence_summary: "" }], unresolved_material_gaps: [],
    post_analysis_assessment: { partial_coverage_count: 1 }, stopping: { reason: "budget" },
  };
  const evidence = { items: [
    { ledger_claim_id: "trial", source_id: "trial", source_url: "https://example.org/trial",
      source_type: "randomized_trial", relationship_to_claim: "supports", claim_fit: 3,
      approved_factual_statement: "The intervention improved completion." },
    { ledger_claim_id: "followup", source_id: "followup", source_url: "https://example.org/followup",
      source_type: "observational_study", relationship_to_claim: "challenges", claim_fit: 2,
      approved_factual_statement: "The follow-up found no difference." },
  ] };
  evidence.items.forEach((item) => { item.source_family = item.source_id; });
  const opened = [];
  const tree = ResultSummary({ result, evidence, findings: findingsByRelationship(evidence), onOpenEvidence: (id) => opened.push(id) });
  const found = elementNodes(tree).find(node => node.props?.["aria-labelledby"] === "summary-found");
  const foundText = JSON.stringify(found);
  assert.match(foundText, /The intervention improved completion.*The follow-up found no difference/);
  assert.match(foundText, /may not be representative/);
  for (const button of elementNodes(found).filter(node => node.type === "button")) button.props.onClick();
  assert.deepEqual(opened, ["trial", "followup"]);
  const text = JSON.stringify(tree);
  assert.doesNotMatch(text, /not recorded|Support-directed/i);
  assert.doesNotMatch(text, /How to read this/, "The Summary has no reading-notes block");
  assert.doesNotMatch(foundText, /Only supporting evidence/);
  const picture = elementNodes(tree).find(node => node.props?.["aria-labelledby"] === "evidence-picture");
  assert.doesNotMatch(JSON.stringify(picture), /true|false|proven|established/i);
});

test("unknown search stop and exception do not expose technical text", () => {
  const { researchStopLabel, understandableRunMessage } = hookHarness("features/shared/presentation.ts", {}).exports;
  assert.doesNotMatch(researchStopLabel("unexpected_internal_exception"), /unexpected_internal_exception/);
  assert.doesNotMatch(understandableRunMessage({ classification: "failed", message: "RuntimeError: private detail" }), /RuntimeError/);
});

test("planner failures explain grouping and budget limits without exposing provider text", () => {
  const { understandableRunMessage, understandableAttemptMessage } = hookHarness("features/shared/presentation.ts", {}).exports;
  const message = "LLMProviderExecutionError: private-input claim_coverage_focus:planner_duplicate_coverage_dimension";
  const snapshot = { classification: "failed", stage: "claim_planner", message };
  assert.match(understandableRunMessage(snapshot), /planner repeated a coverage category/);
  assert.doesNotMatch(understandableRunMessage(snapshot), /private-input|LLMProviderExecutionError/);
  assert.match(understandableAttemptMessage({ classification: "failed", message }), /before searching for sources/);
  assert.match(understandableRunMessage({ ...snapshot, message: "v2 cost ceiling cannot cover this call" }), /remaining research budget/);
  assert.match(understandableRunMessage({ ...snapshot, message: "provider content failed the semantic response contract" }), /invalid research plan/);
  assert.equal(understandableRunMessage({ ...snapshot, classification: "released" }), "The saved research result is available.");
});

test("recommended sources are not repeated in the other shortlisted sources", () => {
  const { SourcesTab } = hookHarness("features/results/sources-tab.tsx", {}).exports;
  const source = { source_id: "one", source_url: "https://example.com", title: "A source",
    status: "recommended_analyzed", recommended: true, discovery_providers: [], discovery_round: 1 };
  const tree = SourcesTab({ result: { recommended_sources: [source], all_surviving_sources: [source] }, evidence: null, run: { run_id: "run", db_path: "db" } });
  const rows = elementNodes(tree).filter((node) => node.type?.name === "SourceRow");
  assert.equal(rows.length, 1);
});


test("incomplete quotation does not discard a trailing qualification", () => {
  const { completeQuote } = hookHarness("features/results/quote.ts", {}).exports;
  assert.equal(completeQuote("The treatment reduced the outcome. However, only among"), null);
  assert.equal(completeQuote("An incomplete passage without an ending"), null);
  assert.equal(completeQuote("The treatment reduced the outcome. However, only among adults." ).text,
    "The treatment reduced the outcome. However, only among adults.");
});

test("summary falls back to one finding per group, chosen by a stable rule and disclosed as illustrative", () => {
  const { ResultSummary } = hookHarness("features/results/summary.tsx", {}).exports;
  const { findingsByRelationship, foundSummary } = hookHarness("features/results/model.ts", {}).exports;
  const item = (id, relationship) => ({ ledger_claim_id: id, source_id: id, source_family: id,
    source_url: "https://example.org/" + id, relationship_to_claim: relationship,
    approved_factual_statement: id + " finding." });
  const evidence = { items: [item("first", "supports"), item("copy", "supports"), item("contrast", "challenges")], source_titles: [] };
  const result = { exact_claim: "Example claim", directions: {support_enabled: true, challenge_enabled: true},
    synthesis: {sections: []}, all_surviving_sources: [], recommended_sources: [], unresolved_material_gaps: [],
    stopping: { reason: "budget" } };
  const findings = findingsByRelationship(evidence);
  const found = foundSummary(result, evidence, findings);
  assert.equal(found.selection, "top");
  assert.equal(found.paragraphs.length, 0);
  assert.deepEqual(Array.from(found.items, item => item.ledger_claim_id), ["copy", "contrast"]);
  const text = JSON.stringify(ResultSummary({ result, evidence, findings, onOpenEvidence() {} }));
  assert.match(text, /copy finding/);
  assert.match(text, /contrast finding/);
  assert.doesNotMatch(text, /first finding/);
  assert.match(text, /may not be representative/);
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
  const { completeQuote } = hookHarness("features/results/quote.ts", {}).exports;
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

// Study-design and publication-type inference is pinned on the backend owner
// (tests/test_result_display_projection.py); cards only show what it projected.
test("finding source lines show projected labels and omit unrecorded ones", () => {
  const { sourceLine } = hookHarness("features/results/evidence-list.tsx", {}).exports;
  const item = { source_url: "https://www.example.org/copy", source_type: "randomized_trial" };
  assert.equal(sourceLine({ source_name: "Journal", year: "2024", source_kind: null, study_design: "Randomized trial" }, item),
    "Journal · 2024 · Randomized trial");
  assert.equal(sourceLine(undefined, item), "example.org");
  assert.doesNotMatch(sourceLine({ source_name: null, year: null }, item), /not recorded|Randomized/);
});

test("verified publication heading and link take priority in finding cards", () => {
  const { FindingCard } = hookHarness("features/results/evidence-list.tsx", {}).exports;
  const item = {source_id:"one", ledger_claim_id:"one", source_url:"https://mirror.example/file.pdf", title:"paper.pdf",
    quote_passage: "The program reduced theft.", evidence_summary: "Directly measured.", limitations: [],
    approved_factual_statement: "The program reduced theft.", verified_publication:{
      doi:"10.1000/abc", canonical_url:"https://doi.org/10.1000/abc", title:"Verified publication",
      authors:["A. Author"], publication_date:"2024-02-01", venue:"Journal", verification:"crossref_doi"}};
  const titles = new Map([["one", { source_id: "one", display_title: "PDF file: file.pdf", heading: "Verified publication", source_name: "Journal" }]]);
  const nodes = elementNodes(FindingCard({ finding: { item, relationship: "supports", strength: "Direct", groupId: "one", related: [], alsoAt: [], mergeBasis: null }, titles }));
  const text = JSON.stringify(nodes);
  assert.match(text, /Verified publication/);
  assert.doesNotMatch(text, /paper\.pdf|PDF file/);
  assert.ok(nodes.some(node => node.type === "a" && node.props.href === "https://doi.org/10.1000/abc" && node.props.children === "10.1000/abc"));
  assert.ok(nodes.some(node => node.type === "a" && node.props.href === "https://mirror.example/file.pdf" && node.props.rel === "noopener noreferrer"));
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

test("finding cards show the stored passage verbatim, flagging a possibly cut-off one", () => {
  const { FindingCard } = hookHarness("features/results/evidence-list.tsx", {}).exports;
  // Render nested Passage elements so their text is part of the card output.
  const expand = (nodes) => nodes.flatMap((node) => node.type?.name === "Passage" ? [node, ...elementNodes(node.type(node.props))] : [node]);
  const record = (id, quote_passage) => ({ source_id: id, ledger_claim_id: id, source_url: `https://example.org/${id}`, quote_passage,
    evidence_summary: "Why.", limitations: ["Surface temperatures only."], approved_factual_statement: `${id} statement.` });
  const card = (quote_passage, related = []) => JSON.stringify(expand(elementNodes(FindingCard({
    finding: { item: record("main", quote_passage), relationship: "qualifies", strength: "Background", groupId: "s",
      related, alsoAt: [], mergeBasis: related.length ? "matching title" : null },
    titles: new Map(),
  }))));
  const partial = card("The outcome was lower. However, only among");
  assert.match(partial, /may be cut off/);
  assert.match(partial, /The outcome was lower\. However, only among/);
  const complete = card("The outcome was lower among adults.");
  assert.match(complete, /The outcome was lower among adults\./);
  assert.doesNotMatch(complete, /may be cut off/);
  assert.match(complete, /Surface temperatures only\./);
  // A merged mirror keeps every record's own exact passage.
  const merged = card("The outcome was lower among adults.", [record("mirror", "A second exact passage. However, only among")]);
  assert.match(merged, /mirror statement\./);
  assert.match(merged, /A second exact passage\. However, only among/);
  assert.match(merged, /may be cut off/);
});

test("copies and downloads use the server's canonical report interpretation verbatim", () => {
  const { briefWithReadingAid } = hookHarness("features/results/reading-aid.ts", {}).exports;
  const report = "# Reading aid\n\nVerified findings.\nUSD 0.05 reported; USD 0.02 reserved.\n";
  assert.equal(briefWithReadingAid("immutable release", {}, { reading_aid_markdown: report }), report);
});

test("complete publication opening replaces illustrative selection and links all findings", () => {
  const { ResultSummary } = hookHarness("features/results/summary.tsx", {}).exports;
  const { findingsByRelationship } = hookHarness("features/results/model.ts", {}).exports;
  const item = (id, statement) => ({ ledger_claim_id: id, source_id: id, source_family: id, source_url: `https://example.org/${id}`,
    relationship_to_claim: "supports", claim_fit: 4, approved_factual_statement: statement });
  const evidence = { items: [item("trial", "The randomized study measured theft."), item("copy", "The copy measured theft."),
    item("observation", "The observational study measured clearance.")],
  opening_notice: "Grouped by publication. Separate publications do not establish independent studies.",
  publication_opening: [
    { text: "Citation: The randomized study measured theft.", ledger_claim_ids: ["trial", "copy"] },
    { text: "Citation: The observational study measured clearance.", ledger_claim_ids: ["observation"] },
    { text: "Recorded limitations: follow-up was six months.", ledger_claim_ids: ["trial", "observation"] },
  ] };
  const result = { exact_claim: "Example claim", directions: { support_enabled: true, challenge_enabled: true },
    synthesis: { sections: [] }, all_surviving_sources: [], recommended_sources: [], unresolved_material_gaps: [],
    stopping: { reason: "budget" } };
  const tree = ResultSummary({ result, evidence, findings: findingsByRelationship(evidence), onOpenEvidence() {} });
  const opening = elementNodes(tree).find(node => node.props?.["aria-labelledby"] === "summary-found");
  assert.match(JSON.stringify(opening), /randomized study/);
  assert.match(JSON.stringify(opening), /observational study/);
  assert.match(JSON.stringify(opening), /do not establish independent studies/);
  assert.doesNotMatch(JSON.stringify(opening), /not necessarily representative|may not be representative/);
  assert.equal(elementNodes(opening).filter(node => node.type === "button").length, 3);
});

test("evidence groups by relationship, shows three per group and keeps the rest behind Show all", () => {
  const { EvidenceGroups } = hookHarness("features/results/evidence-list.tsx", {}).exports;
  const { findingsByRelationship } = hookHarness("features/results/model.ts", {}).exports;
  const item = (id, relationship, direction) => ({ ledger_claim_id: id, source_id: id, source_family: id, direction,
    source_url: `https://example.org/${id}`, relationship_to_claim: relationship, claim_fit: 4,
    approved_factual_statement: id + " finding.", quote_passage: "Text.", evidence_summary: "Why." });
  // A challenge found by the support-directed search must appear under Challenges.
  const items = ["a", "b", "c", "d", "e"].map((id) => item(id, "supports", "support"))
    .concat([item("caution", "challenges", "support"), item("context", "qualifies", "support")]);
  const evidence = { items, source_titles: [] };
  const render = (expanded) => elementNodes(EvidenceGroups({ findings: findingsByRelationship(evidence), evidence, expanded, onExpand() {} }));
  const collapsed = render(new Set());
  const cards = (nodes, relationship) => nodes.filter(node => node.type?.name === "FindingCard" && node.props.finding.relationship === relationship);
  assert.equal(cards(collapsed, "supports").length, 3);
  assert.deepEqual(cards(collapsed, "challenges").map(node => node.props.finding.item.ledger_claim_id), ["caution"]);
  assert.equal(cards(collapsed, "qualifies").length, 1);
  assert.ok(collapsed.some(node => node.type?.name === "ShowAll" && node.props.count === 5));
  assert.equal(cards(render(new Set(["supports"])), "supports").length, 5);
  assert.doesNotMatch(JSON.stringify(collapsed), /Support-directed|Challenge-directed/);
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

test("lead grouping ignores tracking and query order but preserves publication versions", () => {
  const { leadPageKey } = hookHarness("features/results/source-leads.tsx", {}).exports;
  assert.equal(leadPageKey("https://example.org/a?version=1&utm_source=mail#top"), leadPageKey("https://example.org/a?version=1"));
  assert.equal(leadPageKey("https://example.org/a?b=2&a=1"), leadPageKey("https://example.org/a?a=1&b=2"));
  assert.notEqual(leadPageKey("https://example.org/a?version=1"), leadPageKey("https://example.org/a?version=2"));
});

test("admitted challenges are named without inferring dominance from counts", () => {
  const { findingsByRelationship, evidencePicture } = hookHarness("features/results/model.ts", {}).exports;
  const item = (id, relationship, fit) => ({ ledger_claim_id: id, source_id: id, source_family: id,
    source_url: `https://example.org/${id}`, relationship_to_claim: relationship, claim_fit: fit,
    approved_factual_statement: `${id} finding.` });
  // Twenty indirect supporting publications and one direct challenge: no "mostly" label.
  const items = Array.from({ length: 20 }, (_, index) => item(`s${index}`, "supports", 3)).concat([item("c", "challenges", 5)]);
  const findings = findingsByRelationship({ items });
  assert.equal(findings.challenges.length, 1);
  const picture = evidencePicture(findings, { support_enabled: true, challenge_enabled: true });
  assert.equal(picture.label, "Evidence is limited or indirect");
  assert.doesNotMatch(picture.label, /dominat|established|true|false/i);
});

// Social-post headings are pinned on the backend owner (tests/test_result_display_projection.py).
test("finding cards use the projected heading, not a post's opening line", () => {
  const { FindingCard } = hookHarness("features/results/evidence-list.tsx", {}).exports;
  const item = { source_id: "post", ledger_claim_id: "post", source_url: "https://www.linkedin.com/posts/example",
    title: "An unreliable first line of a post", quote_passage: "Text.", evidence_summary: "Why.", approved_factual_statement: "Statement." };
  const titles = new Map([["post", { source_id: "post", display_title: item.title, heading: "Post on LinkedIn", source_name: "LinkedIn", source_kind: "Social post" }]]);
  const text = JSON.stringify(elementNodes(FindingCard({ finding: { item, relationship: "supports", strength: "Direct", groupId: "post", related: [], alsoAt: [], mergeBasis: null }, titles })));
  assert.match(text, /Post on LinkedIn/);
  assert.doesNotMatch(text, /An unreliable first line/);
});

test("depth presets write the existing settings and anything else reads Custom", () => {
  const { presetOf, depthPresets } = hookHarness("features/research/presets.ts", {}).exports;
  for (const preset of depthPresets) assert.equal(presetOf(preset), preset.id);
  assert.equal(presetOf({ sourceTarget: 10, metadataDepth: 30, maxCost: "0.20" }), "Standard");
  assert.equal(presetOf({ sourceTarget: 10, metadataDepth: 30, maxCost: "0.50" }), "Custom");
  assert.equal(presetOf({ sourceTarget: 30, metadataDepth: 50, maxCost: "1.00" }), "Custom");
});

test("history uses one plain outcome per run and explains where stopped runs ended", () => {
  const { historyOutcome, historyReason } = hookHarness("features/history/outcome.ts", {}).exports;
  assert.equal(historyOutcome("completed").label, "Complete");
  assert.equal(historyOutcome("released").label, "Complete");
  assert.equal(historyOutcome("blocked").label, "Stopped early");
  assert.equal(historyOutcome("failed").label, "Failed");
  assert.equal(historyReason({ status: "failed", stage: "claim_planner" }), "Stopped during planning");
  assert.equal(historyReason({ status: "blocked", stage: "deep_analysis" }), "Stopped during analysis");
  assert.equal(historyReason({ status: "completed", stage: "final_renderer_validator" }), null);
  assert.equal(historyReason({ status: "interrupted", stage: "unknown_stage" }), "Stopped before completing");
});

test("research start rejects concurrent submissions and ignores a response after reset", async () => {
  let finish;
  let calls = 0;
  const h = hookHarness("features/research/use-research.ts", {
    start: () => { calls++; return new Promise(resolve => { finish = resolve; }); },
  });
  const notices = [];
  const render = () => h.render("useResearch", message => notices.push(message), () => {});
  let research = render();
  research.setClaim("A claim");
  research = render();
  const settings = { runId: "", dbPath: "original" };
  const configuration = { service: { wigolo_ready: true } };
  const pending = research.beginResearch(null, settings, configuration, () => {});
  await research.beginResearch(null, settings, configuration, () => {});
  assert.equal(calls, 1);
  render().reset();
  finish({ started: true, run_id: "stale", message: "Started" });
  await pending;
  research = render();
  assert.equal(research.activeRun, null);
  assert.equal(research.busy, false);
  assert.equal(notices.includes("Started"), false);
});

test("reset during tool startup prevents a stale paid research request", async () => {
  let finish;
  let starts = 0;
  const h = hookHarness("features/research/use-research.ts", {
    startService: () => new Promise(resolve => { finish = resolve; }),
    start: async () => { starts++; },
  });
  const render = () => h.render("useResearch", () => {}, () => {});
  let research = render();
  research.setClaim("A claim");
  research = render();
  const pending = research.beginResearch(null, { runId: "", dbPath: "db" },
    { service: { wigolo_ready: false } }, () => {});
  render().reset();
  finish({ wigolo_ready: true });
  await pending;
  assert.equal(starts, 0);
  assert.equal(render().busy, false);
});

test("successful research start clears busy before showing the active run", async () => {
  const h = hookHarness("features/research/use-research.ts", {
    start: async () => ({ started: true, run_id: "started", message: "Started" }),
  });
  const render = () => h.render("useResearch", () => {}, () => {});
  let research = render();
  research.setClaim("A claim");
  research = render();
  const pending = research.beginResearch(null, { runId: "", dbPath: "db" },
    { service: { wigolo_ready: true } }, () => {});
  assert.equal(render().busy, true);
  await pending;
  research = render();
  assert.equal(research.activeRun.id, "started");
  assert.equal(research.busy, false);
});

test("reset during duplicate-run snapshot lookup ignores its late ownership result", async () => {
  let finishSnapshot;
  const h = hookHarness("features/research/use-research.ts", {
    start: async () => ({ started: false, classification: "duplicate_active", run_id: "duplicate", message: "Already active" }),
    snapshot: () => new Promise(resolve => { finishSnapshot = resolve; }),
  });
  const render = () => h.render("useResearch", () => {}, () => {});
  let research = render();
  research.setClaim("A claim");
  research = render();
  const pending = research.beginResearch(null, { runId: "", dbPath: "db" },
    { service: { wigolo_ready: true } }, () => {});
  await new Promise(setImmediate);
  assert.equal(render().busy, true);
  render().reset();
  finishSnapshot({ run_id: "duplicate", db_path: "db", worker_active: true });
  await pending;
  research = render();
  assert.equal(research.activeRun, null);
  assert.equal(research.snapshot, null);
  assert.equal(research.busy, false);
});
