"use strict";
const { _electron: electron } = require("./acquisition/node_modules/playwright");
const { mkdtempSync, rmSync } = require("node:fs");
const { tmpdir } = require("node:os");
const path = require("node:path");
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");

async function quitNormally(desktop) {
  const child = desktop.process();
  const exited = new Promise((resolve) => child.once("exit", resolve));
  await desktop.evaluate(({ app }) => { setTimeout(() => app.quit(), 0); });
  let timer;
  try {
    await Promise.race([exited, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error("Normal desktop shutdown timed out")), 100000);
    })]);
  } finally { clearTimeout(timer); }
}

(async () => {
  const data = mkdtempSync(path.join(tmpdir(), "ResearchAssistant UI "));
  let desktop;
  try {
    desktop = await electron.launch({
      executablePath: process.argv[2] || require("electron"),
      args: process.argv[2] ? ["--desktop-smoke"] : [__dirname, "--desktop-smoke"],
      env: { ...process.env, RESEARCHASSISTANT_DATA_DIR: data }, timeout: 60000,
    });
    await desktop.firstWindow({ timeout: 60000 });
    let page;
    for (let attempt = 0; attempt < 300; attempt++) {
      page = desktop.windows().find((candidate) => !candidate.isClosed() && candidate.url().startsWith("http://127.0.0.1:"));
      if (page) break;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    assert.ok(page, "Desktop did not expose its loaded local window");
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.getByRole("heading", { name: /Research a claim/ }).waitFor({ timeout: 30000 });
    assert.match(await page.title(), /ResearchAssistant/);
    assert.equal(await page.evaluate(() => typeof window.require), "undefined");
    const health = await page.evaluate(async () => (await fetch("/api/health")).status);
    assert.equal(health, 200);
    assert.equal(await page.evaluate(() => localStorage.length), 0);
    await page.getByRole("button", { name: /provider setup/i }).click();
    assert.equal(await page.locator('input[type="password"]').count(), 7);
    assert.equal(await page.locator('input[type="password"]').first().inputValue(), "");
    await page.screenshot({ path: path.join(__dirname, "build/desktop-provider-setup.png") });
    assert.deepEqual(errors, []);
    const duplicate = spawn(process.argv[2] || require("electron"),
      process.argv[2] ? ["--desktop-smoke"] : [__dirname, "--desktop-smoke"],
      { env: { ...process.env, RESEARCHASSISTANT_DATA_DIR: data }, stdio: "ignore" });
    const duplicateCode = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => { duplicate.kill(); reject(new Error("Duplicate launch did not exit")); }, 10000);
      duplicate.once("exit", (code) => { clearTimeout(timer); resolve(code); });
      duplicate.once("error", reject);
    });
    assert.equal(duplicateCode, 0);
    assert.equal(desktop.windows().filter((candidate) => !candidate.isClosed()).length, 1);
    await quitNormally(desktop);
    desktop = null;
    console.log("PASS: desktop window, authenticated renderer requests, seven empty password fields, no browser storage or renderer Node access, duplicate launch exclusion, normal shutdown");
  } finally {
    if (desktop) await quitNormally(desktop);
    rmSync(data, { recursive: true, force: true });
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
