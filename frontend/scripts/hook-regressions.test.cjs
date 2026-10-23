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
function hookHarness(relative, api) {
  const state = [];
  const effects = [];
  const layoutEffects = [];
  let cursor = 0;
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
    useCallback(callback) { return callback; },
    useMemo(factory) { return factory(); },
    useLayoutEffect(effect) { layoutEffects.push(effect); },
    useEffect(effect) { effects.push(effect); },
  };
  function load(file) {
    const compiled = { exports: {} };
    const code = ts.transpileModule(fs.readFileSync(file, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
    }).outputText;
    vm.runInNewContext(code, {
      exports: compiled.exports, AbortController, Error, Set, Promise,
      process: { env: {} }, window: { setTimeout, clearTimeout },
      require(name) {
        if (name === "react") return react;
        if (name === "react/jsx-runtime") return { jsx: (type, props) => ({ type, props }),
          jsxs: (type, props) => ({ type, props }), Fragment: "Fragment" };
        if (name === "./dialog") return { Dialog: "Dialog" };
        if (name === "./workspace") return { StatusPill: "StatusPill" };
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
    render(name, ...args) { cursor = 0; effects.length = 0; layoutEffects.length = 0; return exports[name](...args); },
    runEffects() { return [...layoutEffects, ...effects].map((effect) => effect()); },
    runLayoutEffects() { return layoutEffects.map(effect => effect()); },
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
  assert.equal(result.trailError, "temporary trail failure");
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
