/* eslint-disable @typescript-eslint/no-require-imports */
"use strict";

// Run the shared offline renderer and API checks in a stable order.
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const repositoryRoot = path.resolve(__dirname, "../..");
const smokes = [
  "desktop/frontend-smoke.cjs",
  "desktop/frontend-poll-smoke.cjs",
  "desktop/configuration-race-smoke.cjs",
  "desktop/audit-api-smoke.cjs",
  "desktop/history-race-smoke.cjs",
];

for (const smoke of smokes) {
  const result = spawnSync(process.execPath, [path.join(repositoryRoot, smoke)], {
    cwd: repositoryRoot,
    env: process.env,
    stdio: "inherit",
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    process.exitCode = result.status ?? 1;
    break;
  }
}
